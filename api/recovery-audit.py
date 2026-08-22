"""Authenticated-deployment recovery audit surface.

The endpoint deliberately performs no writes. Vercel Deployment Protection is
the access boundary used by the existing application, just like /api/recipes.
"""

import collections
import html
import json
import urllib.parse
from http.server import BaseHTTPRequestHandler

from ._common import APP_ID, row_to_recipe, send_json, supabase_request
from .recipe_health import classify_source, stored_completeness


def recipe_url(recipe):
    for key in ("originalSourceUrl", "sourceUrl", "originalUrl", "link", "resolvedSourceUrl"):
        value = str(recipe.get(key) or "").strip()
        if value:
            return value
    return ""


def audit_item(recipe):
    health = stored_completeness(recipe)
    url = recipe_url(recipe)
    source_type = classify_source(url)
    has_ingredients = "missing_ingredients" not in health["issues"]
    has_instructions = "missing_instructions" not in health["issues"]
    social = source_type.startswith(("TIKTOK", "INSTAGRAM", "FACEBOOK"))
    if health["status"] != "INCOMPLETE":
        group = "COMPLETE"
    elif not url or source_type in ("NO_SOURCE", "MALFORMED_URL"):
        group = "D"
    elif social:
        group = "B"
    else:
        # Reachability/extraction inspection refines A into C after the stored
        # snapshot. Until then, a valid ordinary source is an A candidate.
        group = "A"
    return {
        "id": str(recipe.get("id") or ""),
        "title": recipe.get("name") or recipe.get("title") or "",
        "sourceUrl": url,
        "resolvedSourceUrl": str(recipe.get("resolvedSourceUrl") or ""),
        "sourceType": source_type,
        "hasIngredients": has_ingredients,
        "hasInstructions": has_instructions,
        "hasServings": bool(str(recipe.get("servings") or "").strip()),
        "hasImage": bool(recipe.get("image") or recipe.get("thumbnail") or recipe.get("verifiedFallbackImage")),
        "previousRecoveryAttempt": bool(recipe.get("sourceLastChecked") or recipe.get("extractionMethod") or recipe.get("importQuality") or recipe.get("recovery")),
        "incompleteReasons": health["issues"],
        "initialGroup": group,
        "ingredientCount": health["ingredientCount"],
        "instructionCount": health["instructionCount"],
    }


def build_audit(recipes):
    items = [audit_item(recipe) for recipe in recipes]
    incomplete = [item for item in items if item["initialGroup"] != "COMPLETE"]
    counts = collections.Counter(item["initialGroup"] for item in incomplete)
    return {
        "totalRecipes": len(items),
        "completeRecipes": len(items) - len(incomplete),
        "incompleteRecipes": len(incomplete),
        "missingIngredients": sum(not item["hasIngredients"] for item in incomplete),
        "missingInstructions": sum(not item["hasInstructions"] for item in incomplete),
        "missingBoth": sum(not item["hasIngredients"] and not item["hasInstructions"] for item in incomplete),
        "initialGroups": {key: counts.get(key, 0) for key in "ABCDE"},
        "items": items,
    }


def production_recipes():
    query = urllib.parse.urlencode({"app_id": "eq." + APP_ID, "select": "*", "order": "name.asc", "limit": "5000"})
    return [row_to_recipe(row) for row in (supabase_request("GET", "recipes", query=query) or [])]


def audit_html(audit):
    payload = json.dumps(audit, ensure_ascii=False).replace("</", "<\\/")
    summary = {key: value for key, value in audit.items() if key != "items"}
    return """<!doctype html><html lang=\"no\"><meta charset=\"utf-8\"><title>Recipe recovery audit</title>
<body><h1>Recipe recovery audit</h1><pre id=\"summary\">{summary}</pre>
<script id=\"recipe-audit-data\" type=\"application/json\">{payload}</script></body></html>""".format(
        summary=html.escape(json.dumps(summary, ensure_ascii=False, indent=2)), payload=payload
    )


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            audit = build_audit(production_recipes())
            if "format=json" in self.path:
                return send_json(self, {"ok": True, "audit": audit})
            body = audit_html(audit).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except Exception as exc:
            send_json(self, {"ok": False, "error": f"{type(exc).__name__}: {exc}"}, 500)
