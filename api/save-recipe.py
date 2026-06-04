
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
            payload = read_body(self)
            recipe_id = payload.get("id")
            if recipe_id is None:
                return send_json(self, {"ok": False, "error": "Missing recipe id"}, 400)

            patch = payload.get("patch") if isinstance(payload.get("patch"), dict) else {
                k: v for k, v in payload.items() if k != "id"
            }

            q = urllib.parse.urlencode({
                "id": f"eq.{recipe_id}",
                "app_id": f"eq.{APP_ID}",
                "select": "*",
            })
            rows = supabase_request("GET", "recipes", query=q) or []
            current = row_to_recipe(rows[0]) if rows else {"id": recipe_id}
            current.update(patch)
            row = recipe_to_row(current)

            if rows:
                update_q = urllib.parse.urlencode({"id": f"eq.{recipe_id}", "app_id": f"eq.{APP_ID}"})
                supabase_request("PATCH", "recipes", payload=row, query=update_q, prefer="return=representation")
                return send_json(self, {"ok": True, "updated": True, "id": recipe_id, "storage": "supabase"})

            supabase_request("POST", "recipes", payload=row, prefer="return=representation")
            return send_json(self, {"ok": True, "updated": False, "id": recipe_id, "storage": "supabase"})

        except Exception as exc:
            send_json(self, {"ok": False, "error": f"{type(exc).__name__}: {exc}"}, 500)
