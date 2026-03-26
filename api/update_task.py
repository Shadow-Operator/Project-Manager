"""POST /api/update_task — Update a single field on a task.
Body: {"task_id": "t_...", "field": "status", "value": "Done"}
"""
from http.server import BaseHTTPRequestHandler
from api._shared import json_response, read_body, gsheet_update_task_field

# Whitelist of fields that can be updated
FIELD_MAP = {
    "title": "title",
    "description": "description",
    "status": "status",
    "priority": "priority",
    "assignee": "assignee",
    "due_date": "due_date",
    "links": "links",
    "parent_task_id": "parent_task_id",
}


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            body = read_body(self)
            task_id = (body.get("task_id") or "").strip()
            field = (body.get("field") or "").strip()
            value = body.get("value", "")

            if not task_id:
                json_response(self, 400, {"ok": False, "error": "task_id is required"})
                return

            col_header = FIELD_MAP.get(field)
            if not col_header:
                json_response(self, 400, {"ok": False, "error": f"Field '{field}' is not updatable"})
                return

            updated = gsheet_update_task_field(task_id, col_header, value)
            json_response(self, 200, {"ok": True, "updated": updated})
        except Exception as e:
            json_response(self, 500, {"ok": False, "error": str(e)})

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()
