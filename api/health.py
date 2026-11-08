import json
import os

from ._access import OwnerRequestHandler, owner_cookie, valid_owner_key
from ._common import APP_ID, send_json


class handler(OwnerRequestHandler):
    def handle_public_request(self):
        if self.command != "POST":
            return False
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 512 or self.headers.get_content_type() != "application/json":
                raise ValueError()
            body = json.loads(self.rfile.read(length))
            key = body.get("ownerKey") if isinstance(body, dict) else None
        except (ValueError, UnicodeError):
            key = None
        if valid_owner_key(key):
            send_json(self, {"ok": True}, headers={"Set-Cookie": owner_cookie()})
        else:
            send_json(self, {"ok": False, "error": "Eierlenken er ugyldig."}, 401)
        return True

    def do_GET(self):
        send_json(self, {
            "ok": True,
            "storage": "supabase",
            "ai": bool(os.environ.get("OPENAI_API_KEY", "").strip()),
            "app_id": APP_ID,
        }, headers={"Set-Cookie": owner_cookie()})
