import re
import urllib.parse
from http.server import BaseHTTPRequestHandler

from ._common import APP_ID, read_body, recipe_to_row, row_to_recipe, send_json, supabase_request
from .ingredient_normalization import CATALOG, normalize_structured_ingredients
from .recipe_import import safe_recipe_merge, merge_reviewed_recipe


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
            query = urllib.parse.urlencode({"id": f"eq.{recipe_id}", "app_id": f"eq.{APP_ID}", "select": "*"})
            rows = supabase_request("GET", "recipes", query=query) or []
            current = row_to_recipe(rows[0]) if rows else {"id": recipe_id}
            if "structuredIngredients" in patch:
                existing = current.get("structuredIngredients") if isinstance(current.get("structuredIngredients"), list) else []
                incoming = patch["structuredIngredients"] if isinstance(patch["structuredIngredients"], list) else []
                def reviewed_ingredient(item):
                    normalized = normalize_structured_ingredients([item])[0]
                    category = item.get("shoppingCategory") if isinstance(item, dict) else None
                    category = "Frys" if category == "Frysevarer" else category
                    if payload.get("explicitContentEdit") is True and category in CATALOG["categories"]:
                        normalized["shoppingCategory"] = category
                    return normalized
                # Editing one row must not silently rewrite every other row.
                patch["structuredIngredients"] = [
                    item if item in existing else reviewed_ingredient(item)
                    for item in incoming
                ]
            # Existing user names are immutable through import/recovery patches.
            # A name may only be set on a new recipe or by an explicit name edit.
            explicit_name_edit = bool(payload.get("explicitNameEdit"))
            if rows and current.get("name") and not explicit_name_edit:
                patch.pop("name", None)
                patch.pop("title", None)
            if payload.get("explicitContentEdit") is True:
                current = merge_reviewed_recipe(current, patch, explicit_name_edit)
            else:
                reviewed_name = patch.get("name") if explicit_name_edit else None
                current = safe_recipe_merge(current, patch)
                if reviewed_name:
                    current["name"] = reviewed_name
            if not str(current.get("name") or "").strip():
                return send_json(self, {"ok": False, "error": "Oppskriften må ha et navn."}, 400)
            current["id"] = recipe_id
            current.update(ownership_patch)
            for field in unset_fields:
                if field in allowed_unsets:
                    current.pop(field, None)
            row = recipe_to_row(current)
            if rows:
                update_query = urllib.parse.urlencode({"id": f"eq.{recipe_id}", "app_id": f"eq.{APP_ID}"})
                saved = supabase_request("PATCH", "recipes", payload=row, query=update_query, prefer="return=representation")
            else:
                saved = supabase_request("POST", "recipes", payload=row, prefer="return=representation")
            if not saved or len(saved) != 1:
                raise RuntimeError("Lagringen ble ikke bekreftet av databasen.")
            return send_json(self, {"ok": True, "updated": bool(rows), "id": recipe_id,
                                    "recipe": row_to_recipe(saved[0]), "storage": "supabase"})
        except Exception as exc:
            send_json(self, {"ok": False, "error": f"{type(exc).__name__}: {exc}"}, 500)
