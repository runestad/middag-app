from http.server import BaseHTTPRequestHandler
from ._common import *
import os, json, urllib.request, urllib.error

class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            api_key = os.environ.get("OPENAI_API_KEY", "").strip()
            if not api_key:
                return send_json(self, {"ok": False, "error": "OPENAI_API_KEY mangler"}, 400)
            payload = read_body(self)
            prompt = (payload.get("prompt") or "").strip()
            days = payload.get("days") or []
            recipes = payload.get("recipes") or []
            compact = [{
                "id": r.get("id"), "name": r.get("name"), "category": r.get("category"),
                "tags": r.get("tags") or [], "favorite": bool(r.get("favorite")), "usage": r.get("usage") or 0
            } for r in recipes[:260]]
            system = """Du lager praktiske norske ukesmenyer. Velg kun recipeId-er fra listen. Returner KUN JSON."""
            user = {"prompt": prompt, "days": days, "recipes": compact, "format": {"items": [{"day":"mandag","recipeIds":["id1"],"note":""}]}}
            body = {"model": os.environ.get("OPENAI_MODEL","gpt-4.1-mini"), "messages":[{"role":"system","content":system},{"role":"user","content":json.dumps(user, ensure_ascii=False)}], "temperature":0.5, "response_format":{"type":"json_object"}}
            req = urllib.request.Request("https://api.openai.com/v1/chat/completions", data=json.dumps(body).encode("utf-8"), headers={"Content-Type":"application/json","Authorization":f"Bearer {api_key}"}, method="POST")
            try:
                with urllib.request.urlopen(req, timeout=60, context=get_ssl_context()) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as e:
                detail = e.read().decode("utf-8", errors="replace")
                return send_json(self, {"ok":False, "error":f"OpenAI API-feil {e.code}: {detail}"}, 500)
            parsed = json.loads(data["choices"][0]["message"]["content"])
            return send_json(self, {"ok": True, "plan": parsed})
        except Exception as exc:
            return send_json(self, {"ok": False, "error": f"{type(exc).__name__}: {exc}"}, 500)
