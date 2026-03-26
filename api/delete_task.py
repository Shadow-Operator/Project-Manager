"""POST /api/delete_task — Delete a task and optionally its subtasks.
Body: {"task_id": "t_...", "cascade": true}
"""
from http.server import BaseHTTPRequestHandler
from api._shared import (
    json_response, read_body, gsheet_all_tasks,
    gsheet_delete_tasks, find_all_descendants
)


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            body = read_body(self)
            task_id = (body.get("task_id") or "").strip()
            cascade = body.get("cascade", False)

            if not task_id:
                json_response(self, 400, {"ok": False, "error": "task_id is required"})
                return

            ids_to_delete = [task_id]

            if cascade:
                raw = gsheet_all_tasks()
                if raw is None:
                    json_response(self, 500, {"ok": False, "error": "Failed to read tasks"})
                    return
                descendants = find_all_descendants(raw, task_id)
                ids_to_delete.extend(descendants)

            deleted = gsheet_delete_tasks(ids_to_delete)
            json_response(self, 200, {"ok": True, "deleted": deleted})
        except Exception as e:
            json_response(self, 500, {"ok": False, "error": str(e)})

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()
