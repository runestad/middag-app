from http.server import BaseHTTPRequestHandler
from ._common import *

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            q = urllib.parse.urlencode({"key": f"eq.plan:{APP_ID}", "select": "*"})
            rows = supabase_request("GET", "app_state", query=q) or []
            data = rows[0].get("data") if rows else {}
            send_json(self, {"ok": True, "plan": data or {}, "storage": "supabase"})
        except Exception as exc:
            send_json(self, {"ok": False, "error": f"{type(exc).__name__}: {exc}"}, 500)

    def do_POST(self):
        try:
            payload = read_body(self)
            data = payload.get("plan") if isinstance(payload.get("plan"), dict) else payload
            key = f"plan:{APP_ID}"

            q = urllib.parse.urlencode({"key": f"eq.{key}", "select": "*"})
            rows = supabase_request("GET", "app_state", query=q) or []
            row = {"key": key, "app_id": APP_ID, "data": data}

            if rows:
                update_q = urllib.parse.urlencode({"key": f"eq.{key}"})
                supabase_request("PATCH", "app_state", payload=row, query=update_q, prefer="return=representation")
            else:
                supabase_request("POST", "app_state", payload=row, prefer="return=representation")

            send_json(self, {"ok": True, "storage": "supabase"})
        except Exception as exc:
            send_json(self, {"ok": False, "error": f"{type(exc).__name__}: {exc}"}, 500)
