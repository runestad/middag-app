from http.server import BaseHTTPRequestHandler
from ._common import *

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            query = urllib.parse.urlencode({
                "app_id": f"eq.{APP_ID}",
                "select": "*",
                "order": "name.asc",
            })
            rows = supabase_request("GET", "recipes", query=query) or []
            send_json(self, {"ok": True, "recipes": [row_to_recipe(r) for r in rows], "storage": "supabase"})
        except Exception as exc:
            send_json(self, {"ok": False, "error": f"{type(exc).__name__}: {exc}"}, 500)
