"""Capabilities for household browsers and read-only recipe links."""
import hashlib
import hmac
import json
import os
import re
import time
from http.cookies import CookieError, SimpleCookie
from http.server import BaseHTTPRequestHandler

from ._common import APP_ID, send_json

COOKIE = "__Host-sult_owner"
LIFETIME = 400 * 24 * 3600


def signature(purpose, value):
    secret = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    if not secret:
        raise ValueError("Missing signing key")
    message = json.dumps(["sult-v1", APP_ID, purpose, value], separators=(",", ":")).encode()
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


def valid_signature(purpose, value, supplied):
    return bool(re.fullmatch(r"[a-f0-9]{64}", supplied or "") and
                hmac.compare_digest(signature(purpose, value), supplied))


def owner_verifier():
    return os.environ.get("SULT_OWNER_LINK_SHA256", "").strip()


def valid_owner_key(key):
    return bool(isinstance(key, str) and re.fullmatch(r"[a-f0-9]{64}", key) and
                hmac.compare_digest(hashlib.sha256(key.encode()).hexdigest(), owner_verifier()))


def owner_cookie():
    expires = str(int(time.time()) + LIFETIME)
    proof = signature("owner-session", [owner_verifier(), expires])
    return f"{COOKIE}={expires}.{proof}; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age={LIFETIME}"


def has_owner_session(headers):
    if not owner_verifier():
        return False
    cookies = SimpleCookie()
    try:
        cookies.load(headers.get("Cookie", ""))
        expires, proof = cookies[COOKIE].value.split(".")
        return (bool(re.fullmatch(r"\d{10}", expires)) and int(time.time()) < int(expires)
                and valid_signature("owner-session", [owner_verifier(), expires], proof))
    except (KeyError, ValueError, CookieError):
        return False


class OwnerRequestHandler(BaseHTTPRequestHandler):
    """Check access at HTTP dispatch, before any GET or mutation handler runs."""

    def handle_public_request(self):
        return False

    def parse_request(self):
        if not super().parse_request():
            return False
        if self.command not in ("GET", "HEAD") and self.headers.get("Sec-Fetch-Site") == "cross-site":
            send_json(self, {"ok": False, "error": "Forespørselen ble avvist."}, 403)
            return False
        if self.handle_public_request():
            return False
        if not has_owner_session(self.headers):
            send_json(self, {"ok": False, "error": "Åpne den private eierlenken for å få tilgang."}, 401)
            return False
        return True
