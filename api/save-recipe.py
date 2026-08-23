import re
import urllib.parse
from http.server import BaseHTTPRequestHandler

from ._common import APP_ID, read_body, recipe_to_row, row_to_recipe, send_json, supabase_request
from .data_merge import merge_preserving_existing_data
from .ingredient_normalization import normalize_structured_ingredients
from .recipe_import import safe_recipe_merge


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            payload = read_body(self)
            recipe_id = payload.get("id")
            if recipe_id is None:
                return send_json(self, {"ok": False, "error": "Missing recipe id"}, 400)
            patch = payload.get("patch") if isinstance(payload.get("patch"), dict) else {
                key: value for key, value in payload.items() if key != "id"
            }
            patch = dict(patch)
            unset_fields = payload.get("unsetFields") if isinstance(payload.get("unsetFields"), list) else []
            allowed_unsets = {"reviewOverride", "userImagePath"}
            ownership_patch = {}
            if "reviewOverride" in patch:
                if patch["reviewOverride"] not in ("approved", "needs-help"):
                    return send_json(self, {"ok": False, "error": "Ugyldig reviewOverride."}, 400)
                ownership_patch["reviewOverride"] = patch.pop("reviewOverride")
            if "userImagePath" in patch:
                image_path = str(patch.pop("userImagePath") or "").strip()
                storage_app_id = re.sub(r"[^A-Za-z0-9_-]", "-", str(APP_ID).strip())[:160]
                storage_recipe_id = re.sub(r"[^A-Za-z0-9_-]", "-", str(recipe_id).strip())[:160]
                expected_prefix = f"{storage_app_id}/{storage_recipe_id}/"
                if not image_path.startswith(expected_prefix) or ".." in image_path:
                    return send_json(self, {"ok": False, "error": "Ugyldig bildesti."}, 400)
                ownership_patch["userImagePath"] = image_path
            if "structuredIngredients" in patch:
                patch["structuredIngredients"] = normalize_structured_ingredients(patch["structuredIngredients"])

            query = urllib.parse.urlencode({"id": f"eq.{recipe_id}", "app_id": f"eq.{APP_ID}", "select": "*"})
            rows = supabase_request("GET", "recipes", query=query) or []
            current = row_to_recipe(rows[0]) if rows else {"id": recipe_id}
            # Existing user names are immutable through import/recovery patches.
            # A name may only be set on a new recipe or by an explicit name edit.
            explicit_name_edit = bool(payload.get("explicitNameEdit"))
            if rows and not explicit_name_edit:
                patch.pop("name", None)
                patch.pop("title", None)
            patch = safe_recipe_merge(current, patch)
            current = merge_preserving_existing_data(current, patch)
            current.update(ownership_patch)
            for field in unset_fields:
                if field in allowed_unsets:
                    current.pop(field, None)
            row = recipe_to_row(current)
            if rows:
                update_query = urllib.parse.urlencode({"id": f"eq.{recipe_id}", "app_id": f"eq.{APP_ID}"})
                supabase_request("PATCH", "recipes", payload=row, query=update_query, prefer="return=representation")
                return send_json(self, {"ok": True, "updated": True, "id": recipe_id, "storage": "supabase"})
            supabase_request("POST", "recipes", payload=row, prefer="return=representation")
            return send_json(self, {"ok": True, "updated": False, "id": recipe_id, "storage": "supabase"})
        except Exception as exc:
            send_json(self, {"ok": False, "error": f"{type(exc).__name__}: {exc}"}, 500)
