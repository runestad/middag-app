import json
import re
import urllib.parse
import uuid
from http.server import BaseHTTPRequestHandler

from ._common import APP_ID, read_body, send_json, supabase_request, supabase_storage_request

BUCKET = "recipe-images"
MAX_UPLOAD_BYTES = 8 * 1024 * 1024
ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp"}


def safe_segment(value):
    return re.sub(r"[^A-Za-z0-9_-]", "-", str(value or "").strip())[:160]


def valid_owned_path(path, recipe_id=None):
    prefix = f"{safe_segment(APP_ID)}/{safe_segment(recipe_id)}/" if recipe_id else f"{safe_segment(APP_ID)}/"
    return bool(path and path.startswith(prefix) and ".." not in path and path.count("/") == 2)


def recipe_exists(recipe_id):
    query = urllib.parse.urlencode({"id": f"eq.{recipe_id}", "app_id": f"eq.{APP_ID}", "select": "id", "limit": "1"})
    return bool(supabase_request("GET", "recipes", query=query) or [])


def ensure_bucket():
    try:
        supabase_storage_request("GET", f"bucket/{BUCKET}")
    except RuntimeError as error:
        if "404" not in str(error):
            raise
        payload = json.dumps({"id": BUCKET, "name": BUCKET, "public": False, "file_size_limit": MAX_UPLOAD_BYTES,
                              "allowed_mime_types": sorted(ALLOWED_TYPES)}).encode("utf-8")
        try:
            supabase_storage_request("POST", "bucket", payload, "application/json")
        except RuntimeError as create_error:
            if "409" not in str(create_error):
                raise


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            path = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query).get("path", [""])[0]
            if not valid_owned_path(path):
                return send_json(self, {"ok": False, "error": "Ugyldig bildesti."}, 400)
            body, content_type = supabase_storage_request("GET", f"object/{BUCKET}/{urllib.parse.quote(path, safe='/')}")
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "private, max-age=3600")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except Exception as exc:
            send_json(self, {"ok": False, "error": f"{type(exc).__name__}: {exc}"}, 500)

    def do_POST(self):
        try:
            recipe_id = self.headers.get("X-Recipe-Id", "")
            content_type = self.headers.get("Content-Type", "").split(";", 1)[0].lower()
            length = int(self.headers.get("Content-Length", "0") or 0)
            if not safe_segment(recipe_id) or not recipe_exists(recipe_id):
                return send_json(self, {"ok": False, "error": "Oppskriften finnes ikke."}, 404)
            if content_type not in ALLOWED_TYPES:
                return send_json(self, {"ok": False, "error": "Bildet må være JPEG, PNG eller WebP."}, 415)
            if length <= 0 or length > MAX_UPLOAD_BYTES:
                return send_json(self, {"ok": False, "error": "Bildet er tomt eller for stort."}, 413)
            body = self.rfile.read(length)
            if len(body) != length:
                raise ValueError("Hele bildefilen ble ikke mottatt.")
            ensure_bucket()
            extension = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}[content_type]
            path = f"{safe_segment(APP_ID)}/{safe_segment(recipe_id)}/{uuid.uuid4()}.{extension}"
            supabase_storage_request("POST", f"object/{BUCKET}/{urllib.parse.quote(path, safe='/')}", body, content_type)
            send_json(self, {"ok": True, "path": path})
        except Exception as exc:
            send_json(self, {"ok": False, "error": f"{type(exc).__name__}: {exc}"}, 500)

    def do_DELETE(self):
        try:
            payload = read_body(self)
            path, recipe_id = str(payload.get("path") or ""), str(payload.get("recipeId") or "")
            if not valid_owned_path(path, recipe_id):
                return send_json(self, {"ok": False, "error": "Ugyldig bildesti."}, 400)
            supabase_storage_request("DELETE", f"object/{BUCKET}/{urllib.parse.quote(path, safe='/')}")
            send_json(self, {"ok": True})
        except Exception as exc:
            send_json(self, {"ok": False, "error": f"{type(exc).__name__}: {exc}"}, 500)
