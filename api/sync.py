"""GET/POST /api/sync?type=presence — Team presence heartbeat system.
GET: Returns all heartbeats.
POST Body: {"user": "alice@company.com"} — Updates heartbeat, returns all.
"""
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from api._shared import json_response, read_body, read_presence, write_presence


class handler(BaseHTTPRequestHandler):
    def _get_type(self):
        qs = parse_qs(urlparse(self.path).query)
        return (qs.get("type", [""])[0] or "").lower()

    def do_GET(self):
        try:
            sync_type = self._get_type()
            if sync_type == "presence":
                heartbeats = read_presence()
                json_response(self, 200, {"ok": True, "presence": heartbeats})
            else:
                json_response(self, 400, {"ok": False, "error": "Unknown sync type"})
        except Exception as e:
            json_response(self, 500, {"ok": False, "error": str(e)})

    def do_POST(self):
        try:
            sync_type = self._get_type()
            body = read_body(self)

            if sync_type == "presence":
                user = (body.get("user") or "").strip()
                if not user:
                    json_response(self, 400, {"ok": False, "error": "user is required"})
                    return
                heartbeats = write_presence(user)
                json_response(self, 200, {"ok": True, "presence": heartbeats})
            else:
                json_response(self, 400, {"ok": False, "error": "Unknown sync type"})
        except Exception as e:
            json_response(self, 500, {"ok": False, "error": str(e)})

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()
