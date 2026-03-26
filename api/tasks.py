"""GET /api/tasks — Fetch all tasks.
POST /api/tasks — Create a new task.
Body: {"title": "...", "description": "...", "status": "To Do", "priority": "Medium",
       "assignee": "", "due_date": "", "parent_task_id": "", "links": "[]", "created_by": "..."}
"""
from http.server import BaseHTTPRequestHandler
from api._shared import (
    json_response, read_body, gsheet_all_tasks, process_tasks,
    gsheet_append_task, generate_task_id, TASK_HEADERS
)
import time


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            raw = gsheet_all_tasks()
            if raw is None:
                json_response(self, 500, {"ok": False, "error": "Failed to connect to Google Sheets"})
                return
            tasks = process_tasks(raw)
            json_response(self, 200, {"ok": True, "data": tasks, "count": len(tasks)})
        except Exception as e:
            json_response(self, 500, {"ok": False, "error": str(e)})

    def do_POST(self):
        try:
            body = read_body(self)
            title = (body.get("title") or "").strip()
            if not title:
                json_response(self, 400, {"ok": False, "error": "Title is required"})
                return

            now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            task_id = generate_task_id()

            task = {
                "task_id": task_id,
                "title": title,
                "description": body.get("description", ""),
                "status": body.get("status", "To Do"),
                "priority": body.get("priority", "Medium"),
                "assignee": body.get("assignee", ""),
                "due_date": body.get("due_date", ""),
                "parent_task_id": body.get("parent_task_id", ""),
                "links": body.get("links", "[]"),
                "created_by": body.get("created_by", ""),
                "created_at": now,
                "updated_at": now,
            }

            success = gsheet_append_task(task)
            if not success:
                json_response(self, 500, {"ok": False, "error": "Failed to save task"})
                return

            json_response(self, 200, {"ok": True, "task_id": task_id, "task": task})
        except Exception as e:
            json_response(self, 500, {"ok": False, "error": str(e)})

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()
