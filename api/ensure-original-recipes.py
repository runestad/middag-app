"""Idempotently restore the two recipes absent from the original import."""

import urllib.parse
from http.server import BaseHTTPRequestHandler

from ._common import APP_ID, recipe_to_row, send_json, supabase_request


MISSING_ORIGINAL_RECIPES = (
    {
        "id": "original-spicy-cucumber-side-dish",
        "name": "Spicy cucumber side dish",
        "category": "Vegetar",
        "link": "https://www.instagram.com/reel/DY5aSADv-CJ/?igsh=NXEzeWg3cG43OHJ6",
        "source": "Instagram",
        "servings": "",
        "ingredientsText": "",
        "instructions": "",
        "status": "Må sjekkes manuelt",
        "manualCheck": "Ja – original Instagram Reel krever gjenoppretting.",
        "comment": "Gjenopprettet fra original oppskriftsliste 2026-08-22.",
        "ingredientLines": [],
    },
    {
        "id": "original-thai-red-curry-udon-noodle-soup",
        "name": "Thai red curry udon noodle soup",
        "category": "Vegetar",
        "link": "https://www.instagram.com/reel/DZS9sxXP1Ru/?igsh=dWFjcjQwbmZudnhm",
        "source": "Instagram",
        "servings": "",
        "ingredientsText": "",
        "instructions": "",
        "status": "Må sjekkes manuelt",
        "manualCheck": "Ja – original Instagram Reel krever gjenoppretting.",
        "comment": "Gjenopprettet fra original oppskriftsliste 2026-08-22.",
        "ingredientLines": [],
    },
)


def ensure_missing_original_recipes():
    created, existing = [], []
    for recipe in MISSING_ORIGINAL_RECIPES:
        query = urllib.parse.urlencode({"app_id": "eq." + APP_ID, "link": "eq." + recipe["link"], "select": "id,name", "limit": "1"})
        rows = supabase_request("GET", "recipes", query=query) or []
        if rows:
            existing.append({"id": rows[0].get("id"), "name": rows[0].get("name")})
            continue
        supabase_request("POST", "recipes", payload=recipe_to_row(recipe), prefer="return=minimal")
        created.append({"id": recipe["id"], "name": recipe["name"]})
    return {"created": created, "existing": existing}


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            result = ensure_missing_original_recipes()
            send_json(self, {"ok": True, **result, "storage": "supabase"})
        except Exception as exc:
            send_json(self, {"ok": False, "error": "{}: {}".format(type(exc).__name__, exc)}, 500)
