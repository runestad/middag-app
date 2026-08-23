import json
import pathlib
import re
import uuid
from http.server import BaseHTTPRequestHandler
from ._common import *

MEDIA_MANIFEST_PATH = pathlib.Path(__file__).resolve().parents[1] / "recipe-media-manifest.json"
IMAGE_BUCKET = "recipe-images"
MAX_IMAGE_BYTES = 8 * 1024 * 1024
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}


def safe_storage_segment(value):
    return re.sub(r"[^A-Za-z0-9_-]", "-", str(value or "").strip())[:160]


def valid_owned_image_path(path, recipe_id=None):
    prefix = f"{safe_storage_segment(APP_ID)}/{safe_storage_segment(recipe_id)}/" if recipe_id else f"{safe_storage_segment(APP_ID)}/"
    return bool(path and path.startswith(prefix) and ".." not in path and path.count("/") == 2)


def recipe_exists(recipe_id):
    query = urllib.parse.urlencode({"id": f"eq.{recipe_id}", "app_id": f"eq.{APP_ID}", "select": "id", "limit": "1"})
    return bool(supabase_request("GET", "recipes", query=query) or [])


def ensure_image_bucket():
    try:
        supabase_storage_request("GET", f"bucket/{IMAGE_BUCKET}")
    except RuntimeError as error:
        if "404" not in str(error):
            raise
        payload = json.dumps({"id": IMAGE_BUCKET, "name": IMAGE_BUCKET, "public": False, "file_size_limit": MAX_IMAGE_BYTES,
                              "allowed_mime_types": sorted(ALLOWED_IMAGE_TYPES)}).encode("utf-8")
        try:
            supabase_storage_request("POST", "bucket", payload, "application/json")
        except RuntimeError as create_error:
            if "409" not in str(create_error):
                raise


def load_media_manifest():
    try:
        with MEDIA_MANIFEST_PATH.open(encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return {}


def recipe_source_urls(recipe):
    return {str(recipe.get(key) or "").strip() for key in ("originalSourceUrl", "sourceUrl", "originalUrl", "link", "resolvedSourceUrl") if recipe.get(key)}


def add_verified_media(recipe, manifest):
    entry = manifest.get(str(recipe.get("id", "")))
    if not entry or entry.get("sourceUrl") not in recipe_source_urls(recipe):
        return recipe
    verified = entry.get("image", "")
    if not any(recipe.get(key) for key in ("image", "thumbnail")):
        return {**recipe, "image": verified, "imageRecoveryMethod": entry.get("method", ""), "imageSourceUrl": entry.get("sourceUrl", "")}
    # Preserve an existing preferred image, but always expose the verified local
    # source-aware asset so the renderer can recover from a failed remote URL.
    return {**recipe, "verifiedFallbackImage": verified}

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            image_path = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query).get("imagePath", [""])[0]
            if image_path:
                if not valid_owned_image_path(image_path):
                    return send_json(self, {"ok": False, "error": "Ugyldig bildesti."}, 400)
                body, content_type = supabase_storage_request("GET", f"object/{IMAGE_BUCKET}/{urllib.parse.quote(image_path, safe='/')}")
                self.send_response(200)
                self.send_header("Content-Type", content_type)
                self.send_header("Cache-Control", "private, max-age=3600")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                return self.wfile.write(body)
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

    def do_POST(self):
        try:
            recipe_id = self.headers.get("X-Recipe-Id", "")
            content_type = self.headers.get("Content-Type", "").split(";", 1)[0].lower()
            length = int(self.headers.get("Content-Length", "0") or 0)
            if not safe_storage_segment(recipe_id) or not recipe_exists(recipe_id):
                return send_json(self, {"ok": False, "error": "Oppskriften finnes ikke."}, 404)
            if content_type not in ALLOWED_IMAGE_TYPES:
                return send_json(self, {"ok": False, "error": "Bildet må være JPEG, PNG eller WebP."}, 415)
            if length <= 0 or length > MAX_IMAGE_BYTES:
                return send_json(self, {"ok": False, "error": "Bildet er tomt eller for stort."}, 413)
            body = self.rfile.read(length)
            if len(body) != length:
                raise ValueError("Hele bildefilen ble ikke mottatt.")
            ensure_image_bucket()
            extension = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}[content_type]
            path = f"{safe_storage_segment(APP_ID)}/{safe_storage_segment(recipe_id)}/{uuid.uuid4()}.{extension}"
            supabase_storage_request("POST", f"object/{IMAGE_BUCKET}/{urllib.parse.quote(path, safe='/')}", body, content_type)
            send_json(self, {"ok": True, "path": path})
        except Exception as exc:
            send_json(self, {"ok": False, "error": f"{type(exc).__name__}: {exc}"}, 500)

    def do_DELETE(self):
        try:
            payload = read_body(self)
            path, recipe_id = str(payload.get("path") or ""), str(payload.get("recipeId") or "")
            if not valid_owned_image_path(path, recipe_id):
                return send_json(self, {"ok": False, "error": "Ugyldig bildesti."}, 400)
            supabase_storage_request("DELETE", f"object/{IMAGE_BUCKET}/{urllib.parse.quote(path, safe='/')}")
            send_json(self, {"ok": True})
        except Exception as exc:
            send_json(self, {"ok": False, "error": f"{type(exc).__name__}: {exc}"}, 500)
