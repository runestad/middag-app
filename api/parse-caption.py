import json
import os
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler

from ._common import get_ssl_context, read_body, send_json
from .ingredient_normalization import CATALOG, normalize_structured_ingredients


RECIPE_CATEGORIES = ["Vegetar", "Salat", "Pasta", "Kjøtt", "Kylling", "Fisk", "Airfryer", "Snacks", "Annet"]


def finalize_parsed_recipe(parsed):
    parsed = parsed if isinstance(parsed, dict) else {}
    parsed["ingredients"] = normalize_structured_ingredients(parsed.get("ingredients"))
    parsed["instructions"] = [str(step).strip() for step in parsed.get("instructions", []) if str(step).strip()]
    parsed["category"] = parsed.get("category") if parsed.get("category") in RECIPE_CATEGORIES else "Annet"
    parsed["uncertainties"] = [
        uncertainty
        for uncertainty in parsed.get("uncertainties", [])
        if isinstance(uncertainty, dict)
        and uncertainty.get("field")
        and uncertainty.get("reason")
    ]
    return parsed


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            api_key = os.environ.get("OPENAI_API_KEY", "").strip()
            if not api_key:
                return send_json(self, {"ok": False, "error": "OPENAI_API_KEY mangler"}, 400)

            payload = read_body(self)
            caption = (payload.get("caption") or "").strip()
            if not caption:
                return send_json(self, {"ok": False, "error": "Oppskriftstekst mangler"}, 400)

            category_list = ", ".join(CATALOG["categories"])
            system = f"""Du er en presis norsk oppskriftsparser.
Returner kun JSON. Behold alle oppgitte mengder og ingredienser; aldri gjett manglende data.
Oversett navn, noter og fremgangsmåte til naturlig norsk. Bruk norske måleenheter (ss, ts, dl, ml, g, kg, stk).
Hver ingrediens må ha én handlelistekategori fra: {category_list}.
Marker usikkerhet på det konkrete feltet, ikke på hele oppskriften. Et ellers komplett resultat skal fortsatt fylles ut."""
            schema = """Format:
{
  "title":"string",
  "category":"Vegetar|Salat|Pasta|Kjøtt|Kylling|Fisk|Airfryer|Snacks|Annet",
  "servings":"string",
  "ingredients":[
    {"amount":"string","unit":"string","item":"string","note":"string","shoppingCategory":"string","original":"string"}
  ],
  "instructions":["string"],
  "tags":["string"],
  "emoji":"string",
  "confidence":"high|medium|low",
  "uncertainties":[
    {"field":"title|category|servings|ingredients.N|instructions.N","reason":"kort norsk forklaring","sourceText":"relevant originaltekst"}
  ]
}
Bruk nullbasert indeks N. uncertainties skal være tom når alt er tydelig."""
            context = {
                "knownRecipeName": payload.get("recipeName", ""),
                "existingCategory": payload.get("category", ""),
                "sourceUrl": payload.get("sourceUrl", ""),
                "text": caption,
            }
            request_body = {
                "model": os.environ.get("OPENAI_MODEL", "gpt-4.1-mini"),
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": schema + "\n\n" + json.dumps(context, ensure_ascii=False)},
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
            try:
                with urllib.request.urlopen(request, timeout=90, context=get_ssl_context()) as response:
                    api_result = json.loads(response.read().decode("utf-8"))
            except urllib.error.HTTPError as error:
                detail = error.read().decode("utf-8", errors="replace")
                return send_json(self, {"ok": False, "error": f"OpenAI API-feil {error.code}: {detail}"}, 500)

            parsed = json.loads(api_result["choices"][0]["message"]["content"])
            return send_json(self, {"ok": True, "parsed": finalize_parsed_recipe(parsed)})
        except Exception as exc:
            send_json(self, {"ok": False, "error": f"{type(exc).__name__}: {exc}"}, 500)
