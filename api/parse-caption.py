
# ===== v23 Norwegian text normalizer =====
def normalize_saved_recipe_v23(data):
    import re
    def clean(v):
        if not isinstance(v, str):
            return v
        s=v
        reps=[
            (r"\bwhite onion\b","gul løk"),(r"\bwhite\s+løk\b","gul løk"),
            (r"\byellow onion\b","gul løk"),(r"\byellow\s+løk\b","gul løk"),
            (r"\bred onion\b","rødløk"),(r"\bred\s+løk\b","rødløk"),
            (r"\bspring onion\b","vårløk"),(r"\bgreen onion\b","vårløk"),
            (r"\bcelery stalks?\b","stangselleri"),(r"\bcelery\b","stangselleri"),
            (r"\bgarlic cloves?\b","fedd hvitløk"),(r"\bgarlic\b","hvitløk"),
            (r"\bcarrots?\b","gulrot"),(r"\bcucumber\b","agurk"),
            (r"\btomatoes\b","tomater"),(r"\btomato\b","tomat"),
            (r"\bbell peppers?\b","paprika"),(r"\bchicken\b","kylling"),
            (r"\bbeef\b","biff"),(r"\bpork\b","svin"),(r"\bshrimp\b","scampi"),
            (r"\bcornstarch\b","maizena"),(r"\bcorn starch\b","maizena"),
            (r"\bsoy sauce\b","soyasaus"),(r"\bolive oil\b","olivenolje"),
            (r"\bsesame oil\b","sesamolje"),(r"\brice vinegar\b","riseddik"),
            (r"\bcoconut milk\b","kokosmelk"),(r"\bnoodles\b","nudler")
        ]
        for pat, repl in reps:
            s=re.sub(pat,repl,s,flags=re.I)
        def num(x): return float(str(x).replace(",","."))
        s=re.sub(r"(\d+(?:[.,]\d+)?)\s*cups?\s+(?:chopped\s+|diced\s+|sliced\s+)?(?:celery|stangselleri)\b",lambda m:f"{max(1,round(num(m.group(1))*2))} stilker stangselleri",s,flags=re.I)
        s=re.sub(r"(\d+(?:[.,]\d+)?)\s*cups?\s+(?:chopped\s+|diced\s+|sliced\s+)?(?:onion|løk|gul løk)\b",lambda m:f"{max(1,round(num(m.group(1))))} gul løk",s,flags=re.I)
        s=re.sub(r"(\d+(?:[.,]\d+)?)\s*cups?\b",lambda m:f"{str(round(num(m.group(1))*2.4,1)).replace('.',',')} dl",s,flags=re.I)
        s=re.sub(r"(\d+(?:[.,]\d+)?)\s*(tbsp|tablespoons?)\b",lambda m:f"{m.group(1).replace('.',',')} ss",s,flags=re.I)
        s=re.sub(r"(\d+(?:[.,]\d+)?)\s*(tsp|teaspoons?)\b",lambda m:f"{m.group(1).replace('.',',')} ts",s,flags=re.I)
        return "\n".join(re.sub(r"\s+"," ",x).strip() for x in s.splitlines())
    def walk(x):
        if isinstance(x,str): return clean(x)
        if isinstance(x,list): return [walk(i) for i in x]
        if isinstance(x,dict): return {k:walk(v) for k,v in x.items()}
        return x
    return walk(data)

def normalize_recipe_payload_v23(data):
    return normalize_saved_recipe_v23(data)

from http.server import BaseHTTPRequestHandler
from ._common import *

class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            api_key = os.environ.get("OPENAI_API_KEY", "").strip()
            if not api_key:
                return send_json(self, {"ok": False, "error": "OPENAI_API_KEY mangler i Vercel Environment Variables"}, 400)

            payload = read_body(self)
            caption = (payload.get("caption") or "").strip()
            recipe_name = (payload.get("recipeName") or "").strip()
            source_url = (payload.get("sourceUrl") or "").strip()
            existing_category = (payload.get("category") or "").strip()

            if not caption:
                return send_json(self, {"ok": False, "error": "Caption/oppskriftstekst mangler"}, 400)

            system = """Du er en norsk oppskriftsparser for en privat middagsapp.
Hent ut strukturert oppskrift fra rotete Instagram/TikTok-caption, nettsidetekst eller OCR-tekst.
Ikke gjett ingredienser som ikke står i teksten.
Omgjør trygt til norske/metric mål: cups≈dl, tbsp=ss, tsp=ts, oz=g, lb=g/kg.
Hver ingrediens skal få handlelistekategori fra nøyaktig denne listen. Krydder, salt, pepper, oljer, eddik, soyasaus og sauser skal ikke havne under Frukt og grønt:
Frukt og grønt, Kjøtt, Kjølevarer, Meieri, Frys, Hermetikk/halvfabrikat, Tørrvarer, Krydder, Glutenfritt, Bakevarer, Annet.
Returner KUN gyldig JSON."""

            schema_instruction = """Returner dette JSON-formatet:
{
  "title": "string",
  "category": "Vegetar|Salat|Pasta|Kjøtt|Kylling|Fisk|Airfryer|Annet|Snacks",
  "subcategory": "string",
  "servings": "string",
  "timeMinutes": number|null,
  "ingredients": [
    {
      "amount": "string",
      "unit": "string",
      "item": "string",
      "note": "string",
      "shoppingCategory": "Frukt og grønt|Kjøtt|Kjølevarer|Meieri|Frys|Hermetikk/halvfabrikat|Tørrvarer|Krydder|Glutenfritt|Bakevarer|Annet",
      "original": "string"
    }
  ],
  "instructions": ["string"],
  "tags": ["string"],
  "confidence": "high|medium|low",
  "notes": "string",
  "tags": ["string"],
  "emoji": "string"
}"""

            user = {
                "known_recipe_name": recipe_name,
                "existing_category": existing_category,
                "source_url": source_url,
                "caption_or_ocr_text": caption,
            }

            body = {
                "model": os.environ.get("OPENAI_MODEL", "gpt-4.1-mini"),
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": schema_instruction + "\n\nInput:\n" + json.dumps(user, ensure_ascii=False)},
                ],
                "temperature": 0.1,
                "response_format": {"type": "json_object"},
            }

            req = urllib.request.Request(
                "https://api.openai.com/v1/chat/completions",
                data=json.dumps(body).encode("utf-8"),
                headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
                method="POST",
            )

            try:
                with urllib.request.urlopen(req, timeout=60, context=get_ssl_context()) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as e:
                detail = e.read().decode("utf-8", errors="replace")
                return send_json(self, {"ok": False, "error": f"OpenAI API-feil {e.code}: {detail}"}, 500)

            content = data["choices"][0]["message"]["content"]
            parsed = json.loads(content)
            return send_json(self, {"ok": True, "parsed": parsed})

        except Exception as exc:
            send_json(self, {"ok": False, "error": f"{type(exc).__name__}: {exc}"}, 500)
