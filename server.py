#!/usr/bin/env python3
"""Student Status Board - minimal in-memory classroom status app.

No database, no persistence, no external dependencies. Run with:
    python3 server.py
Listens on 0.0.0.0:2225.
"""

import json
import re
import secrets
import threading
import uuid
from http import cookies
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HOST = "0.0.0.0"
PORT = 2225
ADMIN_PASSWORD = "alta3"
VALID_STATUSES = {"working", "good", "away"}
MAX_NAME_LENGTH = 50

STATIC_DIR = Path(__file__).parent / "static"
INDEX_HTML = (STATIC_DIR / "index.html").read_text()
ADMIN_HTML = (STATIC_DIR / "admin.html").read_text()

# --- In-memory state -------------------------------------------------------

lock = threading.Lock()
students = {}          # student_id -> {id, name, status}
admin_sessions = set()  # set of valid admin session tokens

DELETE_STUDENT_RE = re.compile(r"^/api/admin/students/([^/]+)$")


def make_student_public(student):
    return {"id": student["id"], "name": student["name"], "status": student["status"]}


class Handler(BaseHTTPRequestHandler):
    server_version = "StudentStatusBoard/1.0"
    protocol_version = "HTTP/1.1"  # keep-alive: avoids a fresh TCP connection per request

    def log_message(self, format, *args):
        pass  # keep the console quiet; this is a classroom utility

    # -- helpers --------------------------------------------------------

    def get_cookie(self, name):
        raw = self.headers.get("Cookie")
        if not raw:
            return None
        jar = cookies.SimpleCookie()
        try:
            jar.load(raw)
        except cookies.CookieError:
            return None
        morsel = jar.get(name)
        return morsel.value if morsel else None

    def read_json_body(self):
        length = int(self.headers.get("Content-Length", 0) or 0)
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        try:
            data = json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return None
        if not isinstance(data, dict):
            return None
        return data

    def send_json(self, code, obj, cookie_header=None):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        if cookie_header:
            self.send_header("Set-Cookie", cookie_header)
        self.end_headers()
        self.wfile.write(body)

    def send_html(self, html):
        body = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def require_admin(self):
        token = self.get_cookie("admin_session")
        with lock:
            return token is not None and token in admin_sessions

    # -- routing ----------------------------------------------------------

    def do_GET(self):
        if self.path == "/":
            self.send_html(INDEX_HTML)
        elif self.path == "/admin":
            self.send_html(ADMIN_HTML)
        elif self.path == "/api/me":
            self.handle_get_me()
        elif self.path == "/api/admin/students":
            self.handle_admin_students()
        else:
            self.send_json(404, {"error": "not found"})

    def do_POST(self):
        if self.path == "/api/register":
            self.handle_register()
        elif self.path == "/api/status":
            self.handle_status()
        elif self.path == "/api/admin/login":
            self.handle_admin_login()
        elif self.path == "/api/admin/reset":
            self.handle_admin_reset()
        else:
            self.send_json(404, {"error": "not found"})

    def do_DELETE(self):
        match = DELETE_STUDENT_RE.match(self.path)
        if match:
            self.handle_admin_delete(match.group(1))
        else:
            self.send_json(404, {"error": "not found"})

    # -- student endpoints --------------------------------------------------

    def handle_get_me(self):
        student_id = self.get_cookie("student_id")
        with lock:
            student = students.get(student_id) if student_id else None
        if not student:
            self.send_json(404, {"error": "no such student"})
            return
        self.send_json(200, make_student_public(student))

    def handle_register(self):
        data = self.read_json_body()
        if data is None:
            self.send_json(400, {"error": "invalid request body"})
            return
        name = str(data.get("name", "")).strip()
        if not name:
            self.send_json(400, {"error": "name is required"})
            return
        if len(name) > MAX_NAME_LENGTH:
            self.send_json(400, {"error": f"name must be {MAX_NAME_LENGTH} characters or fewer"})
            return

        student_id = uuid.uuid4().hex
        student = {"id": student_id, "name": name, "status": "working"}
        with lock:
            students[student_id] = student

        cookie_header = f"student_id={student_id}; Path=/; Max-Age=2592000; SameSite=Lax"
        self.send_json(200, make_student_public(student), cookie_header=cookie_header)

    def handle_status(self):
        student_id = self.get_cookie("student_id")
        data = self.read_json_body()
        if data is None:
            self.send_json(400, {"error": "invalid request body"})
            return
        status = data.get("status")
        if status not in VALID_STATUSES:
            self.send_json(400, {"error": "invalid status"})
            return
        with lock:
            student = students.get(student_id) if student_id else None
            if not student:
                self.send_json(404, {"error": "no such student"})
                return
            student["status"] = status
            result = make_student_public(student)
        self.send_json(200, result)

    # -- admin endpoints ------------------------------------------------

    def handle_admin_login(self):
        data = self.read_json_body()
        if data is None:
            self.send_json(400, {"error": "invalid request body"})
            return
        password = data.get("password", "")
        if password != ADMIN_PASSWORD:
            self.send_json(401, {"error": "incorrect password"})
            return
        token = secrets.token_hex(16)
        with lock:
            admin_sessions.add(token)
        cookie_header = f"admin_session={token}; Path=/; SameSite=Lax; HttpOnly"
        self.send_json(200, {"ok": True}, cookie_header=cookie_header)

    def handle_admin_students(self):
        if not self.require_admin():
            self.send_json(401, {"error": "not authenticated"})
            return
        with lock:
            roster = [make_student_public(s) for s in students.values()]
        self.send_json(200, {"students": roster})

    def handle_admin_reset(self):
        if not self.require_admin():
            self.send_json(401, {"error": "not authenticated"})
            return
        with lock:
            for student in students.values():
                if student["status"] != "away":
                    student["status"] = "working"
            roster = [make_student_public(s) for s in students.values()]
        self.send_json(200, {"students": roster})

    def handle_admin_delete(self, student_id):
        if not self.require_admin():
            self.send_json(401, {"error": "not authenticated"})
            return
        with lock:
            students.pop(student_id, None)
        self.send_json(200, {"ok": True})


class Server(ThreadingHTTPServer):
    # Default backlog is only 5 -- too small for a full classroom (20-30
    # students) all clicking a status button within the same second (e.g.
    # right after an instructor says "everyone set yourself to away").
    # Connections beyond the backlog get refused/reset by the OS before our
    # code ever runs. Raise it generously.
    request_queue_size = 128
    daemon_threads = True


def main():
    server = Server((HOST, PORT), Handler)
    print(f"Student Status Board listening on http://{HOST}:{PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
