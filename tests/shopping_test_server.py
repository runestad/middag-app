"""Local browser fixture: real plan HTTP handlers, isolated in-memory storage.

Run from the repository root. No credentials or production requests are used.
"""
import copy
import json
import pathlib
import sys
import threading
import urllib.parse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from api import plan

ROOT = pathlib.Path(__file__).resolve().parents[1]
lock = threading.Lock()
row = {}
version = 0


def reset():
    global row, version
    version += 1
    row = {"key": f"plan:{plan.APP_ID}", "updated_at": str(version), "data": {
        "items": {}, "freezerItems": [], "meta": {"favorites": []},
        "updatedAt": "2026-01-01T00:00:00.000Z",
        "shoppingItems": [{"id": "milk", "text": "Melk", "category": "Meieri",
                           "updatedAt": "2026-01-01T00:00:00.000Z"}]}}


def storage(method, table, payload=None, query=None, **kwargs):
    global row, version
    assert table == "app_state"
    params = urllib.parse.parse_qs(query or "")
    with lock:
        if method == "GET":
            fields = params.get("select", ["*"])[0]
            return [copy.deepcopy(row if fields == "*" else {k: row.get(k) for k in fields.split(",")})]
        if method == "PATCH":
            expected = params.get("data->>updatedAt", [""])[0]
            if expected != "eq." + row["data"]["updatedAt"]:
                return []
            version += 1
            row = {**copy.deepcopy(payload), "updated_at": str(version)}
            return [{"key": row["key"]}]
        raise AssertionError(method)


plan.supabase_request = storage
reset()


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def log_message(self, *args):
        pass

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path == "/api/plan":
            return plan.handler.do_GET(self)
        if path == "/api/recipes":
            return plan.send_json(self, {"ok": True, "recipes": []})
        if path == "/__test__/state":
            return plan.send_json(self, copy.deepcopy(row["data"]))
        if path.startswith("/api/"):
            return plan.send_json(self, {"ok": True})
        return super().do_GET()

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        if path == "/api/plan":
            return plan.handler.do_POST(self)
        if path == "/__test__/reset":
            reset()
        elif path == "/__test__/remote":
            data = plan.read_body(self)
            plan._persist_plan_with_retry(row["key"], {**copy.deepcopy(row["data"]), **data})
        return plan.send_json(self, {"ok": True})


if __name__ == "__main__":
    server = ThreadingHTTPServer(("127.0.0.1", int(sys.argv[1]) if len(sys.argv) > 1 else 8765), Handler)
    print(f"Shopping test server: http://127.0.0.1:{server.server_port}", flush=True)
    server.serve_forever()
