from http.server import BaseHTTPRequestHandler
from ._common import *

class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            payload = read_body(self)
            recipe_id = payload.get("id")
            if recipe_id is None:
                return send_json(self, {"ok": False, "error": "Missing recipe id"}, 400)

            patch = payload.get("patch") if isinstance(payload.get("patch"), dict) else {
                k: v for k, v in payload.items() if k != "id"
            }

            q = urllib.parse.urlencode({
                "id": f"eq.{recipe_id}",
                "app_id": f"eq.{APP_ID}",
                "select": "*",
            })
            rows = supabase_request("GET", "recipes", query=q) or []
            current = row_to_recipe(rows[0]) if rows else {"id": recipe_id}
            current.update(patch)
            row = recipe_to_row(current)

            if rows:
                update_q = urllib.parse.urlencode({"id": f"eq.{recipe_id}", "app_id": f"eq.{APP_ID}"})
                supabase_request("PATCH", "recipes", payload=row, query=update_q, prefer="return=representation")
                return send_json(self, {"ok": True, "updated": True, "id": recipe_id, "storage": "supabase"})

            supabase_request("POST", "recipes", payload=row, prefer="return=representation")
            return send_json(self, {"ok": True, "updated": False, "id": recipe_id, "storage": "supabase"})

        except Exception as exc:
            send_json(self, {"ok": False, "error": f"{type(exc).__name__}: {exc}"}, 500)
