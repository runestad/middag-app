import json
import pathlib
from http.server import BaseHTTPRequestHandler
from ._common import *

MEDIA_MANIFEST_PATH = pathlib.Path(__file__).resolve().parents[1] / "recipe-media-manifest.json"


def load_media_manifest():
    try:
        with MEDIA_MANIFEST_PATH.open(encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return {}


def recipe_source_urls(recipe):
    return {str(recipe.get(key) or "").strip() for key in ("originalSourceUrl", "sourceUrl", "originalUrl", "link", "resolvedSourceUrl") if recipe.get(key)}


def add_verified_media(recipe, manifest):
    if any(recipe.get(key) for key in ("image", "thumbnail")):
        return recipe
    entry = manifest.get(str(recipe.get("id", "")))
    if not entry or entry.get("sourceUrl") not in recipe_source_urls(recipe):
        return recipe
    return {**recipe, "image": entry.get("image", ""), "imageRecoveryMethod": entry.get("method", ""), "imageSourceUrl": entry.get("sourceUrl", "")}

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            query = urllib.parse.urlencode({
                "app_id": f"eq.{APP_ID}",
                "select": "*",
                "order": "name.asc",
            })
            rows = supabase_request("GET", "recipes", query=query) or []
            manifest = load_media_manifest()
            recipes = [add_verified_media(row_to_recipe(row), manifest) for row in rows]
            send_json(self, {"ok": True, "recipes": recipes, "storage": "supabase"})
        except Exception as exc:
            send_json(self, {"ok": False, "error": f"{type(exc).__name__}: {exc}"}, 500)
