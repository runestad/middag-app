#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Engangsrydd for Middag-appens oppskriftsdatabase.

Kjør fra prosjektmappen:
  python3 scripts/cleanup_recipes_with_ai.py --dry-run
  python3 scripts/cleanup_recipes_with_ai.py --apply

Scriptet:
- henter alle oppskrifter fra Supabase
- rydder ingrediensspråk til norsk
- fikser rare hybridord, f.eks. "white løk" -> "gul løk"
- fikser måleenheter, f.eks. cups/tbsp/tsp/oz
- unngår tullemål som "4,2 dl stangselleri"
- oppdaterer tags, emoji og ingredienskategorier
- lagrer tilbake til Supabase når --apply brukes
"""

import argparse
import json
import os
import re
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from copy import deepcopy


CATEGORIES = [
    "Frukt og grønt",
    "Kjøtt",
    "Kjølevarer",
    "Meieri",
    "Frys",
    "Hermetikk/halvfabrikat",
    "Tørrvarer",
    "Krydder",
    "Glutenfritt",
    "Bakevarer",
    "Annet",
]


def load_env(path=".env"):
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))


def ssl_context():
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


def env_required(*names):
    for name in names:
        if os.environ.get(name):
            return os.environ[name]
    raise RuntimeError(f"Mangler env: ett av {', '.join(names)}")


def supabase_url():
    return env_required("SUPABASE_URL").rstrip("/")


def supabase_key():
    return env_required("SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_SECRET_KEY", "SUPABASE_ANON_KEY")


def supabase_request(method, path, payload=None, params=None):
    base = supabase_url()
    key = supabase_key()
    url = f"{base}/rest/v1/{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params, doseq=True)
    data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        },
    )
    with urllib.request.urlopen(req, context=ssl_context(), timeout=60) as resp:
        raw = resp.read().decode("utf-8")
        return json.loads(raw) if raw else None


def fetch_all_recipes():
    rows = []
    start = 0
    step = 1000
    while True:
        part = supabase_request(
            "GET",
            "recipes",
            params={
                "select": "*",
                "order": "name.asc",
                "limit": step,
                "offset": start,
            },
        )
        if not part:
            break
        rows.extend(part)
        if len(part) < step:
            break
        start += step
    return rows


def update_recipe(recipe_id, patch):
    encoded_id = str(recipe_id).replace('"', '\\"')
    return supabase_request("PATCH", "recipes", payload=patch, params={"id": f"eq.{encoded_id}"})


def normalize_number(s):
    return str(s).replace(",", ".")


def fmt_num(n):
    try:
        x = round(float(n), 1)
        if x.is_integer():
            return str(int(x))
        return str(x).replace(".", ",")
    except Exception:
        return str(n).replace(".", ",")


REPLACEMENTS = [
    (r"\bwhite onion\b", "gul løk"),
    (r"\byellow onion\b", "gul løk"),
    (r"\bred onion\b", "rødløk"),
    (r"\bspring onion\b", "vårløk"),
    (r"\bgreen onion\b", "vårløk"),
    (r"\bscallions?\b", "vårløk"),
    (r"\bonions?\b", "løk"),
    (r"\bgarlic cloves?\b", "fedd hvitløk"),
    (r"\bgarlic\b", "hvitløk"),
    (r"\bcelery stalks?\b", "stangselleri"),
    (r"\bcelery\b", "stangselleri"),
    (r"\bcarrots?\b", "gulrot"),
    (r"\bcucumber\b", "agurk"),
    (r"\btomatoes\b", "tomater"),
    (r"\btomato\b", "tomat"),
    (r"\bbell peppers?\b", "paprika"),
    (r"\bpeppers?\b", "paprika"),
    (r"\bmushrooms?\b", "sopp"),
    (r"\bspinach\b", "spinat"),
    (r"\blettuce\b", "salat"),
    (r"\bcabbage\b", "kål"),
    (r"\bcauliflower\b", "blomkål"),
    (r"\bbroccoli\b", "brokkoli"),
    (r"\bchickpeas\b", "kikerter"),
    (r"\bbeans\b", "bønner"),
    (r"\bchicken\b", "kylling"),
    (r"\bbeef\b", "biff"),
    (r"\bpork\b", "svin"),
    (r"\bshrimp\b", "scampi"),
    (r"\bsalmon\b", "laks"),
    (r"\bcornstarch\b", "maizena"),
    (r"\bcorn starch\b", "maizena"),
    (r"\bsoy sauce\b", "soyasaus"),
    (r"\bolive oil\b", "olivenolje"),
    (r"\bsesame oil\b", "sesamolje"),
    (r"\brice vinegar\b", "riseddik"),
    (r"\bcoconut milk\b", "kokosmelk"),
    (r"\bvegetable stock\b", "grønnsakskraft"),
    (r"\bchicken stock\b", "kyllingkraft"),
    (r"\bstock\b", "kraft"),
    (r"\bbroth\b", "kraft"),
    (r"\bnoodles\b", "nudler"),
    (r"\brice\b", "ris"),
    (r"\bflour\b", "mel"),
    (r"\bsugar\b", "sukker"),
    (r"\bsalt\b", "salt"),
    (r"\bblack pepper\b", "sort pepper"),
]


def translate_words(line):
    s = line
    for pattern, repl in REPLACEMENTS:
        s = re.sub(pattern, repl, s, flags=re.I)
    # fix hybrid leftovers
    s = re.sub(r"\bwhite\s+løk\b", "gul løk", s, flags=re.I)
    s = re.sub(r"\bred\s+løk\b", "rødløk", s, flags=re.I)
    s = re.sub(r"\byellow\s+løk\b", "gul løk", s, flags=re.I)
    return s


def normalize_units(line):
    s = line.strip()

    # Specific vegetable cup conversions should be count-ish, not dl.
    veg_rules = [
        (r"(\d+(?:[.,]\d+)?)\s*cups?\s+(?:chopped\s+|diced\s+|sliced\s+)?(?:celery|stangselleri)\b", lambda n: f"{max(1, round(float(normalize_number(n)) * 2))} stilker stangselleri"),
        (r"(\d+(?:[.,]\d+)?)\s*cups?\s+(?:chopped\s+|diced\s+|sliced\s+)?(?:onion|løk|gul løk)\b", lambda n: f"{max(1, round(float(normalize_number(n))))} gul løk"),
        (r"(\d+(?:[.,]\d+)?)\s*cups?\s+(?:chopped\s+|diced\s+|sliced\s+)?(?:red onion|rødløk)\b", lambda n: f"{max(1, round(float(normalize_number(n))))} rødløk"),
        (r"(\d+(?:[.,]\d+)?)\s*cups?\s+(?:chopped\s+|diced\s+|sliced\s+)?(?:carrots?|gulrot)\b", lambda n: f"{max(1, round(float(normalize_number(n)) * 2))} gulrot"),
        (r"(\d+(?:[.,]\d+)?)\s*cups?\s+(?:chopped\s+|diced\s+|sliced\s+)?(?:bell pepper|paprika)\b", lambda n: f"{max(1, round(float(normalize_number(n))))} paprika"),
        (r"(\d+(?:[.,]\d+)?)\s*cups?\s+(?:chopped\s+|diced\s+|sliced\s+)?(?:broccoli|brokkoli)\b", lambda n: f"{max(1, round(float(normalize_number(n))))} brokkoli"),
    ]
    for pattern, repl in veg_rules:
        s = re.sub(pattern, lambda m: repl(m.group(1)), s, flags=re.I)

    s = re.sub(r"(\d+(?:[.,]\d+)?)\s*cups?\b", lambda m: f"{fmt_num(float(normalize_number(m.group(1))) * 2.4)} dl", s, flags=re.I)
    s = re.sub(r"(\d+(?:[.,]\d+)?)\s*(tbsp|tablespoons?)\b", lambda m: f"{m.group(1).replace('.', ',')} ss", s, flags=re.I)
    s = re.sub(r"(\d+(?:[.,]\d+)?)\s*(tsp|teaspoons?)\b", lambda m: f"{m.group(1).replace('.', ',')} ts", s, flags=re.I)
    s = re.sub(r"(\d+(?:[.,]\d+)?)\s*(oz|ounces?)\b", lambda m: f"{round(float(normalize_number(m.group(1))) * 28.35)} g", s, flags=re.I)
    s = re.sub(r"(\d+(?:[.,]\d+)?)\s*lbs?\b", lambda m: f"{round(float(normalize_number(m.group(1))) * 453.592)} g", s, flags=re.I)

    s = re.sub(r"\bcloves?\b", "fedd", s, flags=re.I)
    s = re.sub(r"\bstalks?\b", "stilker", s, flags=re.I)
    return s


def normalize_line(line):
    s = str(line or "").strip()
    if not s:
        return ""
    # Remove bullet/numbering only when clearly ingredient list noise.
    s = re.sub(r"^[•*\-]\s*", "", s)
    s = translate_words(s)
    s = normalize_units(s)
    s = translate_words(s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def normalize_ingredients_text(text):
    if not text:
        return ""
    lines = re.split(r"\r?\n", str(text))
    normalized = [normalize_line(line) for line in lines]
    normalized = [x for x in normalized if x]
    return "\n".join(normalized)


def normalize_structured_ingredients(value):
    if not isinstance(value, list):
        return value
    out = []
    for ing in value:
        if isinstance(ing, str):
            out.append(normalize_line(ing))
        elif isinstance(ing, dict):
            new = deepcopy(ing)
            if "item" in new:
                new["item"] = normalize_line(new["item"])
            if "unit" in new:
                new["unit"] = normalize_line(new["unit"]).replace("spiseskje", "ss").replace("teskje", "ts")
            if "shoppingCategory" in new:
                new["shoppingCategory"] = categorize(" ".join(str(new.get(k, "")) for k in ("item", "unit", "note")))
            out.append(new)
        else:
            out.append(ing)
    return out


def norm(s):
    import unicodedata
    x = unicodedata.normalize("NFD", str(s or "").lower())
    return "".join(c for c in x if unicodedata.category(c) != "Mn")


def categorize(text):
    s = norm(text)

    spice = ["salt", "pepper", "oregano", "basilikum", "basil", "paprikapulver", "spisskummen", "cumin", "kanel", "chiliflak", "chili flakes", "karri", "garam masala", "laurbær", "sesamfrø", "timian", "rosmarin", "kajenne"]
    if any(w in s for w in spice):
        return "Krydder"

    dry = ["maizena", "maisstivelse", "soyasaus", "soya", "tamari", "sesamolje", "olivenolje", "olje", "riseddik", "eddik", "sriracha", "hoisin", "fiskesaus", "kraft", "buljong", "peanøttsmør", "tomatpure", "panko", "brødsmuler", "mel", "worcestershire", "ris", "pasta", "nudler", "quinoa", "bulgur", "couscous"]
    if any(w in s for w in dry):
        return "Tørrvarer"

    rules = [
        ("Kjøtt", ["flankestek", "biff", "okse", "kjøttdeig", "karbonadedeig", "svin", "kotelett", "pølse", "kalkun", "bacon", "lamm", "skinke", "kylling"]),
        ("Meieri", ["halloumi", "melk", "fløte", "rømme", "ost", "parmesan", "feta", "cottage cheese", "yoghurt", "smør", "mozzarella", "cheddar"]),
        ("Kjølevarer", ["tofu"]),
        ("Frys", ["frossen", "frosne", "edamame"]),
        ("Hermetikk/halvfabrikat", ["boks", "kokosmelk", "kidney", "kikerter", "hakkede tomater", "bønner", "mais"]),
        ("Glutenfritt", ["glutenfri"]),
        ("Bakevarer", ["brød", "pita", "tortilla", "burgerbrød", "wrap", "naan"]),
        ("Frukt og grønt", ["stangselleri", "selleri", "agurk", "gulrot", "løk", "rødløk", "gul løk", "vårløk", "hvitløk", "ingefær", "potet", "søtpotet", "squash", "tomat", "paprika", "sopp", "brokkoli", "blomkål", "kål", "spinat", "salat", "lime", "sitron", "koriander", "persille", "avokado", "aubergine", "chili", "ruccola", "asparges"]),
    ]
    for cat, words in rules:
        if any(norm(w) in s for w in words):
            return cat
    return "Annet"


def tags_for_recipe(recipe):
    text = norm(" ".join(str(recipe.get(k, "")) for k in ("name", "category", "ingredientsText", "instructions")))
    tags = set()
    if recipe.get("category"):
        tags.add(str(recipe["category"]).lower())
    rules = {
        "suppe": ["suppe", "soup"],
        "vegetar": ["vegetar", "tofu", "halloumi", "linser", "kikerter", "veggis"],
        "kylling": ["kylling"],
        "pasta": ["pasta", "spaghetti", "orzo"],
        "salat": ["salat"],
        "taco": ["taco", "fajita", "wrap"],
        "fisk": ["fisk", "laks", "ørret", "scampi", "reker"],
        "asiatisk": ["soyasaus", "sesam", "gochujang", "ramen", "nudler", "gyoza"],
        "indisk": ["curry", "masala", "indisk"],
        "glutenfritt": ["glutenfri"],
    }
    for tag, words in rules.items():
        if any(norm(w) in text for w in words):
            tags.add(tag)
    return sorted(tags)


def emoji_for_recipe(recipe):
    text = norm(" ".join([str(recipe.get("name", "")), str(recipe.get("category", "")), " ".join(tags_for_recipe(recipe))]))
    if "suppe" in text: return "🍲"
    if "salat" in text: return "🥗"
    if "pasta" in text or "spaghetti" in text: return "🍝"
    if "taco" in text: return "🌮"
    if "pizza" in text: return "🍕"
    if "kylling" in text: return "🍗"
    if "fisk" in text or "scampi" in text or "laks" in text or "ørret" in text: return "🍤"
    if "biff" in text or "kjøtt" in text: return "🥩"
    if "ramen" in text or "nudler" in text: return "🍜"
    if "curry" in text or "indisk" in text: return "🍛"
    if "vegetar" in text: return "🥦"
    return "🍽️"


def ai_cleanup(recipe):
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        return None

    prompt = {
        "task": "Rydd norsk oppskrift uten å endre retten.",
        "rules": [
            "Svar kun JSON.",
            "Oversett ingredienser til norsk.",
            "Bruk norske måleenheter: stk, fedd, stilker, g, kg, dl, l, ss, ts, pk, pose, boks.",
            "Ikke bruk dl for hele grønnsaker som løk, stangselleri, gulrot, paprika.",
            "Behold rimelige mengder. Gjett forsiktig hvis originalen er rar.",
            "shoppingCategory må være en av: " + ", ".join(CATEGORIES),
        ],
        "recipe": {
            "id": recipe.get("id"),
            "name": recipe.get("name"),
            "category": recipe.get("category"),
            "ingredientsText": recipe.get("ingredientsText"),
            "structuredIngredients": recipe.get("structuredIngredients"),
            "instructions": recipe.get("instructions"),
        },
        "return_schema": {
            "ingredientsText": "string with one ingredient per line",
            "structuredIngredients": [{"amount": "string", "unit": "string", "item": "string", "shoppingCategory": "string", "note": "string"}],
            "tags": ["string"],
            "emoji": "string",
            "notes": "string"
        },
    }

    body = {
        "model": os.environ.get("OPENAI_MODEL", "gpt-4.1-mini"),
        "temperature": 0.1,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": "Du er en norsk oppskriftsredaktør. Du retter språk, måleenheter og handlelistekategorier."},
            {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
        ],
    }

    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        method="POST",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, context=ssl_context(), timeout=90) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return json.loads(data["choices"][0]["message"]["content"])
    except Exception as e:
        print(f"  AI-feil, bruker regelbasert rydd: {e}")
        return None


def make_patch(recipe, use_ai=False):
    original_ing = recipe.get("ingredientsText") or ""
    patch = {}

    if use_ai and original_ing:
        ai = ai_cleanup(recipe)
    else:
        ai = None

    if ai and isinstance(ai, dict):
        ing_text = ai.get("ingredientsText") or original_ing
        patch["ingredientsText"] = normalize_ingredients_text(ing_text)
        if isinstance(ai.get("structuredIngredients"), list):
            patch["structuredIngredients"] = normalize_structured_ingredients(ai["structuredIngredients"])
        patch["tags"] = ai.get("tags") or tags_for_recipe({**recipe, "ingredientsText": patch["ingredientsText"]})
        patch["emoji"] = ai.get("emoji") or emoji_for_recipe({**recipe, "ingredientsText": patch["ingredientsText"]})
    else:
        patch["ingredientsText"] = normalize_ingredients_text(original_ing)
        if recipe.get("structuredIngredients"):
            patch["structuredIngredients"] = normalize_structured_ingredients(recipe.get("structuredIngredients"))
        patch["tags"] = tags_for_recipe({**recipe, "ingredientsText": patch["ingredientsText"]})
        patch["emoji"] = emoji_for_recipe({**recipe, "ingredientsText": patch["ingredientsText"]})

    patch["updatedAt"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    # Only include changed fields.
    final = {}
    for k, v in patch.items():
        if recipe.get(k) != v:
            final[k] = v
    return final


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Lagre endringer til Supabase")
    parser.add_argument("--dry-run", action="store_true", help="Vis endringer uten å lagre")
    parser.add_argument("--ai", action="store_true", help="Bruk OpenAI for ekstra grundig rydd")
    parser.add_argument("--limit", type=int, default=0, help="Begrens antall oppskrifter")
    args = parser.parse_args()

    if not args.apply and not args.dry_run:
        print("Bruk enten --dry-run eller --apply")
        sys.exit(1)

    load_env()
    recipes = fetch_all_recipes()
    if args.limit:
        recipes = recipes[: args.limit]

    print(f"Fant {len(recipes)} oppskrifter.")
    print("AI:", "på" if args.ai else "av")
    print("Modus:", "APPLY" if args.apply else "DRY RUN")

    changed = 0
    for i, recipe in enumerate(recipes, 1):
        name = recipe.get("name") or recipe.get("title") or recipe.get("id")
        patch = make_patch(recipe, use_ai=args.ai)
        if not patch:
            continue
        changed += 1
        print(f"\n[{i}/{len(recipes)}] {name}")
        if "ingredientsText" in patch:
            before = (recipe.get("ingredientsText") or "").splitlines()[:4]
            after = patch["ingredientsText"].splitlines()[:4]
            print("  Før:", " | ".join(before))
            print("  Nå:", " | ".join(after))
        print("  Felt:", ", ".join(patch.keys()))

        if args.apply:
            update_recipe(recipe["id"], patch)
            time.sleep(0.15)

    print(f"\nFerdig. {changed} oppskrifter hadde endringer.")


if __name__ == "__main__":
    main()
