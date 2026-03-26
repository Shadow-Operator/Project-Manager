"""POST /api/calendar — Create or remove a Google Calendar event for a task.
Body: {"action": "add", "task_id": "t_...", "title": "...", "due_date": "2026-04-01", "description": "...", "assignee": "..."}
Body: {"action": "remove", "event_id": "..."}
GET /api/calendar — List events for a date range.
Query: ?start=2026-03-01&end=2026-04-01
"""
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from api._shared import json_response, read_body, gsheet_update_task_field
import json
import os
import tempfile

from google.oauth2 import service_account
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/calendar"]
DEFAULT_CALENDAR_ID = "partner@shadowoperator.ai"

# Map team member emails to their Google Calendar IDs
CALENDAR_MAP = {
    "partner@shadowoperator.ai": "partner@shadowoperator.ai",
    "harry@maudegroup.co.uk": "harry@maudegroup.co.uk",
}

def _get_calendar_id(assignee_email):
    """Return the calendar ID for a given assignee, or default."""
    if assignee_email and assignee_email.lower() in CALENDAR_MAP:
        return CALENDAR_MAP[assignee_email.lower()]
    return DEFAULT_CALENDAR_ID


def _get_calendar_service():
    """Build a Google Calendar API service using the same service account."""
    creds_json = os.environ.get("GOOGLE_CREDENTIALS_JSON", "")
    if not creds_json:
        return None
    tmp_path = None
    try:
        creds_dict = json.loads(creds_json)
        tmp = tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False)
        json.dump(creds_dict, tmp)
        tmp.close()
        tmp_path = tmp.name
        credentials = service_account.Credentials.from_service_account_file(
            tmp_path, scopes=SCOPES
        )
        service = build("calendar", "v3", credentials=credentials)
        return service
    except Exception as e:
        print(f"[Calendar] Service build failed: {e}")
        return None
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        """List calendar events in a date range."""
        try:
            qs = parse_qs(urlparse(self.path).query)
            start = qs.get("start", [""])[0]
            end = qs.get("end", [""])[0]

            if not start or not end:
                json_response(self, 400, {"ok": False, "error": "start and end query params required (YYYY-MM-DD)"})
                return

            service = _get_calendar_service()
            if not service:
                json_response(self, 500, {"ok": False, "error": "Failed to connect to Google Calendar"})
                return

            time_min = start + "T00:00:00Z"
            time_max = end + "T23:59:59Z"

            # Fetch events from all team calendars
            simplified = []
            seen_ids = set()
            for cal_id in set(CALENDAR_MAP.values()):
                try:
                    events_result = service.events().list(
                        calendarId=cal_id,
                        timeMin=time_min,
                        timeMax=time_max,
                        maxResults=100,
                        singleEvents=True,
                        orderBy="startTime"
                    ).execute()

                    for ev in events_result.get("items", []):
                        eid = ev.get("id", "")
                        if eid in seen_ids:
                            continue
                        seen_ids.add(eid)
                        start_date = ev.get("start", {}).get("date") or ev.get("start", {}).get("dateTime", "")[:10]
                        simplified.append({
                            "event_id": eid,
                            "title": ev.get("summary", ""),
                            "date": start_date,
                            "description": ev.get("description", ""),
                            "task_id": ev.get("extendedProperties", {}).get("private", {}).get("task_id", ""),
                        })
                except Exception as e:
                    print(f"[Calendar] Failed to fetch from {cal_id}: {e}")

            json_response(self, 200, {"ok": True, "events": simplified})
        except Exception as e:
            json_response(self, 500, {"ok": False, "error": str(e)})

    def do_POST(self):
        """Add or remove a calendar event."""
        try:
            body = read_body(self)
            action = (body.get("action") or "").strip()

            service = _get_calendar_service()
            if not service:
                json_response(self, 500, {"ok": False, "error": "Failed to connect to Google Calendar"})
                return

            if action == "add":
                task_id = body.get("task_id", "")
                title = body.get("title", "Untitled Task")
                due_date = body.get("due_date", "")
                description = body.get("description", "")
                assignee = body.get("assignee", "")

                if not due_date:
                    json_response(self, 400, {"ok": False, "error": "due_date is required to add to calendar"})
                    return

                event_body = {
                    "summary": title,
                    "description": f"{description}\n\nAssigned to: {assignee}".strip() if assignee else description,
                    "start": {"date": due_date},
                    "end": {"date": due_date},
                    "extendedProperties": {
                        "private": {"task_id": task_id}
                    }
                }

                target_calendar = _get_calendar_id(assignee)
                try:
                    event = service.events().insert(calendarId=target_calendar, body=event_body).execute()
                except Exception as cal_err:
                    # Fallback to default calendar if assignee's calendar isn't accessible
                    print(f"[Calendar] Failed to push to {target_calendar}, falling back to default: {cal_err}")
                    event = service.events().insert(calendarId=DEFAULT_CALENDAR_ID, body=event_body).execute()
                event_id = event.get("id", "")

                json_response(self, 200, {"ok": True, "event_id": event_id})

            elif action == "remove":
                event_id = (body.get("event_id") or "").strip()
                if not event_id:
                    json_response(self, 400, {"ok": False, "error": "event_id is required"})
                    return

                # Try deleting from all calendars
                deleted = False
                for cal_id in set(CALENDAR_MAP.values()):
                    try:
                        service.events().delete(calendarId=cal_id, eventId=event_id).execute()
                        deleted = True
                        break
                    except Exception:
                        continue
                if not deleted:
                    service.events().delete(calendarId=DEFAULT_CALENDAR_ID, eventId=event_id).execute()
                json_response(self, 200, {"ok": True, "deleted": True})

            else:
                json_response(self, 400, {"ok": False, "error": "action must be 'add' or 'remove'"})

        except Exception as e:
            json_response(self, 500, {"ok": False, "error": str(e)})

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()
