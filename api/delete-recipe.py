import re
import urllib.parse
from http.server import BaseHTTPRequestHandler

from ._common import APP_ID, read_body, row_to_recipe, send_json, supabase_request, supabase_storage_request


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            recipe_id = read_body(self).get("id")
            if recipe_id is None or not str(recipe_id).strip():
                return send_json(self, {"ok": False, "error": "Oppskrifts-ID mangler."}, 400)

            filters = {"id": f"eq.{recipe_id}", "app_id": f"eq.{APP_ID}"}
            lookup_query = urllib.parse.urlencode({**filters, "select": "id,name,data"})
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
            cleanup_warning = ""
            image_path = str(row_to_recipe(rows[0]).get("userImagePath") or "").strip()
            storage_app_id = re.sub("[^A-Za-z0-9_-]", "-", APP_ID)[:160]
            storage_recipe_id = re.sub("[^A-Za-z0-9_-]", "-", str(recipe_id))[:160]
            owned_prefix = f"{storage_app_id}/{storage_recipe_id}/"
            if image_path and image_path.startswith(owned_prefix) and ".." not in image_path:
                try:
                    supabase_storage_request("DELETE", f"object/recipe-images/{urllib.parse.quote(image_path, safe='/')}")
                except Exception as cleanup_error:
                    cleanup_warning = f"Bildet kunne ikke ryddes automatisk: {cleanup_error}"
            send_json(self, {"ok": True, "id": recipe_id, "deleted": True, "storage": "supabase", "cleanupWarning": cleanup_warning})
        except Exception as exc:
            send_json(self, {"ok": False, "error": f"{type(exc).__name__}: {exc}"}, 500)
