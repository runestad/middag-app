import urllib.parse
from http.server import BaseHTTPRequestHandler

from ._common import APP_ID, read_body, send_json, supabase_request


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            recipe_id = read_body(self).get("id")
            if recipe_id is None or not str(recipe_id).strip():
                return send_json(self, {"ok": False, "error": "Oppskrifts-ID mangler."}, 400)

            filters = {"id": f"eq.{recipe_id}", "app_id": f"eq.{APP_ID}"}
            lookup_query = urllib.parse.urlencode({**filters, "select": "id,name"})
            rows = supabase_request("GET", "recipes", query=lookup_query) or []
            if len(rows) != 1:
                return send_json(self, {"ok": False, "error": "Oppskriften ble ikke funnet."}, 404)

            deleted = supabase_request(
                "DELETE", "recipes", query=urllib.parse.urlencode(filters),
                prefer="return=representation"
            ) or []
            if len(deleted) != 1 or str(deleted[0].get("id")) != str(recipe_id):
                raise RuntimeError("Slettingen kunne ikke bekreftes")

            remaining = supabase_request("GET", "recipes", query=lookup_query) or []
            if remaining:
                raise RuntimeError("Oppskriften finnes fortsatt etter sletting")
            send_json(self, {"ok": True, "id": recipe_id, "deleted": True, "storage": "supabase"})
        except Exception as exc:
            send_json(self, {"ok": False, "error": f"{type(exc).__name__}: {exc}"}, 500)
