from http.server import BaseHTTPRequestHandler
from ._common import *

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        send_json(self, {
            "ok": True,
            "storage": "supabase",
            "ai": bool(os.environ.get("OPENAI_API_KEY", "").strip()),
            "app_id": APP_ID,
        })
