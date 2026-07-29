import json
import os
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler

from ._common import get_ssl_context, read_body, send_json


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            api_key = os.environ.get("OPENAI_API_KEY", "").strip()
            if not api_key:
                return send_json(self, {"ok": False, "error": "OPENAI_API_KEY mangler"}, 400)
            payload = read_body(self)
            ingredients = payload.get("ingredients") or []
            if not ingredients:
                return send_json(self, {"ok": False, "error": "Ingredienser mangler"}, 400)
            request_body = {
                "model": os.environ.get("OPENAI_MODEL", "gpt-4.1-mini"),
                "messages": [
                    {"role": "system", "content": (
                        "Estimer næringsinnhold per porsjon for en oppskrift. Returner kun JSON med "
                        "protein, calories, fat, carbohydrates og fiber som ikke-negative tall. "
                        "Vær konservativ. Dette er et omtrentlig estimat, ikke medisinsk informasjon."
                    )},
                    {"role": "user", "content": json.dumps({
                        "ingredients": ingredients,
                        "servings": payload.get("servings") or "",
                    }, ensure_ascii=False)},
                ],
                "temperature": 0,
                "response_format": {"type": "json_object"},
            }
            request = urllib.request.Request(
                "https://api.openai.com/v1/chat/completions",
                data=json.dumps(request_body).encode("utf-8"),
                headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=60, context=get_ssl_context()) as response:
                result = json.loads(response.read().decode("utf-8"))
            values = json.loads(result["choices"][0]["message"]["content"])
            nutrition = {
                key: round(max(0, float(values.get(key) or 0)), 1)
                for key in ("protein", "calories", "fat", "carbohydrates", "fiber")
            }
            return send_json(self, {"ok": True, "nutrition": nutrition})
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            return send_json(self, {"ok": False, "error": f"OpenAI API-feil {error.code}: {detail}"}, 500)
        except Exception as exc:
            return send_json(self, {"ok": False, "error": f"{type(exc).__name__}: {exc}"}, 500)
