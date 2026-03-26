"""Shared helpers for all serverless functions.
NOT a Vercel function (prefixed with _).
"""

import gspread
import json
import os
import tempfile
import time
import secrets

# ── Config ──────────────────────────────────────────────────────────
SPREADSHEET_ID = os.environ.get("SPREADSHEET_ID", "1YPd37qh3b08wtSDMUaALmCcWHHib3KgnzaLlBR61HBk")
TASKS_GID = 0          # First tab: "Tasks"
PRESENCE_TAB_NAME = "Presence"

TASK_HEADERS = [
    "task_id", "title", "description", "status", "priority",
    "assignee", "due_date", "parent_task_id", "links",
    "created_by", "created_at", "updated_at",
    "category", "stage", "deal_value"
]

# ── Google Sheets Connection ────────────────────────────────────────
_gspread_client = None
_tasks_sheet = None

def _get_client(force_reconnect=False):
    """Return authorised gspread client (cached within invocation)."""
    global _gspread_client
    if _gspread_client is not None and not force_reconnect:
        return _gspread_client
    tmp_path = None
    try:
        creds_json = os.environ.get("GOOGLE_CREDENTIALS_JSON", "")
        if not creds_json:
            return None
        creds_dict = json.loads(creds_json)
        tmp = tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False)
        json.dump(creds_dict, tmp)
        tmp.close()
        tmp_path = tmp.name
        _gspread_client = gspread.service_account(filename=tmp_path)
        return _gspread_client
    except Exception as e:
        print(f"[GSheets] Connection failed: {e}")
        return None
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


def _get_tasks_sheet(force_reconnect=False):
    """Return the Tasks worksheet (cached within invocation)."""
    global _tasks_sheet
    if _tasks_sheet is not None and not force_reconnect:
        return _tasks_sheet
    client = _get_client(force_reconnect=force_reconnect)
    if client is None:
        return None
    try:
        wb = client.open_by_key(SPREADSHEET_ID)
        _tasks_sheet = wb.get_worksheet_by_id(TASKS_GID)
        return _tasks_sheet
    except Exception as e:
        print(f"[GSheets] Failed to open tasks sheet: {e}")
        return None


def _get_presence_tab():
    """Return the Presence tab, creating it if needed."""
    client = _get_client()
    if client is None:
        return None
    try:
        wb = client.open_by_key(SPREADSHEET_ID)
        try:
            return wb.worksheet(PRESENCE_TAB_NAME)
        except Exception:
            tab = wb.add_worksheet(title=PRESENCE_TAB_NAME, rows=2, cols=2)
            tab.update_cell(1, 1, "Key")
            tab.update_cell(1, 2, "Value")
            tab.update_cell(2, 1, "heartbeats")
            tab.update_cell(2, 2, "{}")
            return tab
    except Exception as e:
        print(f"[GSheets] Failed to open presence tab: {e}")
        return None


# ── Task ID Generation ──────────────────────────────────────────────
def generate_task_id():
    """Generate a unique task ID: t_<unix_ms>_<4hex>."""
    return f"t_{int(time.time() * 1000)}_{secrets.token_hex(2)}"


# ── CRUD: Read ──────────────────────────────────────────────────────
def gsheet_all_tasks():
    """Fetch all tasks as list of dicts."""
    sh = _get_tasks_sheet()
    if sh is None:
        return None
    try:
        all_values = sh.get_all_values()
    except Exception:
        sh = _get_tasks_sheet(force_reconnect=True)
        if sh is None:
            return None
        all_values = sh.get_all_values()

    if not all_values:
        return []

    headers = all_values[0]
    records = []
    for row in all_values[1:]:
        padded = row + [""] * (len(headers) - len(row))
        record = dict(zip(headers, padded))
        # Skip blank rows
        if not record.get("task_id", "").strip():
            continue
        records.append(record)
    return records


def process_tasks(raw_rows):
    """Transform raw sheet rows into clean JSON-ready dicts."""
    tasks = []
    for row in raw_rows:
        task = {}
        for h in TASK_HEADERS:
            task[h] = (row.get(h) or "").strip()
        tasks.append(task)
    return tasks


# ── CRUD: Create ────────────────────────────────────────────────────
def gsheet_append_task(task_dict):
    """Append a new task row. Returns True on success."""
    sh = _get_tasks_sheet()
    if sh is None:
        return False
    values = [task_dict.get(h, "") for h in TASK_HEADERS]
    sh.append_row(values, value_input_option="USER_ENTERED")
    return True


# ── CRUD: Update ────────────────────────────────────────────────────
def gsheet_update_task_field(task_id, col_header, value):
    """Find row by task_id, update one cell + updated_at. Returns rows updated."""
    sh = _get_tasks_sheet()
    if sh is None:
        return 0

    headers = sh.row_values(1)
    if col_header not in headers:
        return 0

    col_idx = headers.index(col_header) + 1

    # Find task_id column
    if "task_id" not in headers:
        return 0
    id_col = headers.index("task_id") + 1
    id_vals = sh.col_values(id_col)

    for row_idx, cell in enumerate(id_vals[1:], start=2):
        if cell.strip() == task_id:
            sh.update_cell(row_idx, col_idx, value if value is not None else "")
            # Also update updated_at
            if "updated_at" in headers:
                ua_col = headers.index("updated_at") + 1
                sh.update_cell(row_idx, ua_col, time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
            return 1
    return 0


# ── CRUD: Delete ────────────────────────────────────────────────────
def gsheet_delete_tasks(task_ids):
    """Delete multiple tasks by task_id. Returns count deleted."""
    if not task_ids:
        return 0
    sh = _get_tasks_sheet()
    if sh is None:
        return 0

    all_values = sh.get_all_values()
    if not all_values:
        return 0

    headers = all_values[0]
    if "task_id" not in headers:
        return 0
    id_col_idx = headers.index("task_id")

    ids_set = set(task_ids)
    rows_to_delete = []
    for i, row in enumerate(all_values[1:], start=2):
        cell = (row[id_col_idx] if id_col_idx < len(row) else "").strip()
        if cell in ids_set:
            rows_to_delete.append(i)

    # Delete in reverse order to preserve row indices
    for row_num in sorted(rows_to_delete, reverse=True):
        sh.delete_rows(row_num)

    return len(rows_to_delete)


def find_all_descendants(all_tasks, root_task_id):
    """Given flat task list, find all descendant task_ids recursively."""
    children_map = {}
    for t in all_tasks:
        parent = t.get("parent_task_id", "").strip()
        if parent:
            children_map.setdefault(parent, []).append(t["task_id"].strip())

    descendants = []
    queue = [root_task_id]
    while queue:
        current = queue.pop(0)
        kids = children_map.get(current, [])
        descendants.extend(kids)
        queue.extend(kids)
    return descendants


# ── Presence ────────────────────────────────────────────────────────
def read_presence():
    """Read all heartbeats from the Presence tab."""
    tab = _get_presence_tab()
    if tab is None:
        return {}
    try:
        raw = tab.cell(2, 2).value or "{}"
        return json.loads(raw)
    except Exception:
        return {}


def write_presence(user_email):
    """Update heartbeat for a user. Returns all heartbeats."""
    tab = _get_presence_tab()
    if tab is None:
        return {}
    try:
        raw = tab.cell(2, 2).value or "{}"
        heartbeats = json.loads(raw)
    except Exception:
        heartbeats = {}

    heartbeats[user_email] = int(time.time())
    tab.update_cell(2, 2, json.dumps(heartbeats))
    return heartbeats


# ── HTTP Helpers ────────────────────────────────────────────────────
def json_response(handler, status, data):
    """Send a JSON response with CORS headers."""
    body = json.dumps(data, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
    handler.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def read_body(handler):
    """Read and parse JSON body from request."""
    length = int(handler.headers.get("Content-Length", 0))
    if length == 0:
        return {}
    raw = handler.rfile.read(length)
    return json.loads(raw)
