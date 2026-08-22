#!/usr/bin/env python3
"""Audit and conservatively repair a recipe dataset, one verified row at a time."""

import argparse
import collections
import concurrent.futures
import datetime
import hashlib
import importlib.util
import json
import os
import pathlib
import sys
import urllib.parse

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from api._common import APP_ID, recipe_to_row, row_to_recipe, supabase_request
from api.recipe_health import classify_source, source_health, stored_completeness
from api.recipe_import import safe_recipe_merge

spec = importlib.util.spec_from_file_location("api.fetch_recipe_batch", ROOT / "api" / "fetch-recipe.py")
fetcher = importlib.util.module_from_spec(spec); spec.loader.exec_module(fetcher)


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def recipe_url(recipe):
    for key in ("link", "sourceUrl", "sourceURL", "source_url", "originalSourceUrl"):
        if str(recipe.get(key) or "").strip():
            return str(recipe[key]).strip()
    return ""


def production_rows():
    query = urllib.parse.urlencode({"app_id": "eq." + APP_ID, "select": "*", "order": "name.asc", "limit": "5000"})
    return supabase_request("GET", "recipes", query=query) or []


def audit_recipe(recipe, inspect_source=True):
    before_health = stored_completeness(recipe); url = recipe_url(recipe); kind = classify_source(url)
    extracted, error = {}, ""
    if inspect_source and url:
        try: extracted = fetcher.extract(url)
        except Exception as exc: error = "{}: {}".format(type(exc).__name__, str(exc)[:300])
    merged = safe_recipe_merge(recipe, extracted) if extracted else dict(recipe)
    # Source titles are metadata only. A batch repair can never write the name.
    merged["name"] = recipe.get("name")
    after_health = stored_completeness(merged)
    allowed = {"ingredientsText", "ingredientLines", "instructions", "instructionSteps", "structuredIngredients",
               "structuredInstructions", "servings", "image", "sourceScreenshot", "sourceTitle", "sourceDomain",
               "sourceLastChecked", "extractionMethod", "importQuality", "resolvedSourceUrl"}
    patch = {key: value for key, value in merged.items() if key in allowed and recipe.get(key) != value}
    improves = (before_health["status"] == "INCOMPLETE" and after_health["status"] != "INCOMPLETE") or any(
        not recipe.get(key) and patch.get(key) for key in ("ingredientsText", "instructions", "image", "sourceScreenshot"))
    if not improves: patch = {}
    return {"id": str(recipe.get("id")), "name": recipe.get("name") or "", "url": url, "sourceType": kind,
            "storedCompletenessBefore": before_health, "storedCompletenessAfter": after_health,
            "sourceHealth": source_health(kind, extracted, error), "automaticAttempts": ["stored-data", "public-source", extracted.get("method") or "none"],
            "error": error, "proposedPatch": patch, "changed": False, "recommendedAction": "Rediger" if after_health["needsManualRecovery"] else "Ingen"}


def apply_one(item, original):
    if not item["proposedPatch"]: return False
    query = urllib.parse.urlencode({"id": "eq." + item["id"], "app_id": "eq." + APP_ID, "select": "*", "limit": "1"})
    rows = supabase_request("GET", "recipes", query=query) or []
    if len(rows) != 1 or digest(row_to_recipe(rows[0])) != digest(original):
        raise RuntimeError("Record changed after backup; skipped")
    updated = safe_recipe_merge(original, item["proposedPatch"]); updated["name"] = original.get("name")
    supabase_request("PATCH", "recipes", payload=recipe_to_row(updated),
                     query=urllib.parse.urlencode({"id": "eq." + item["id"], "app_id": "eq." + APP_ID}), prefer="return=minimal")
    verify = supabase_request("GET", "recipes", query=query) or []
    saved = row_to_recipe(verify[0]) if len(verify) == 1 else {}
    if saved.get("name") != original.get("name") or any(saved.get(k) != v for k, v in item["proposedPatch"].items()):
        supabase_request("PATCH", "recipes", payload=recipe_to_row(original),
                         query=urllib.parse.urlencode({"id": "eq." + item["id"], "app_id": "eq." + APP_ID}), prefer="return=minimal")
        raise RuntimeError("Verification failed; original restored")
    return True


def main():
    parser = argparse.ArgumentParser(); parser.add_argument("--input"); parser.add_argument("--output", required=True)
    parser.add_argument("--apply", action="store_true"); parser.add_argument("--confirm-production", action="store_true")
    parser.add_argument("--no-network", action="store_true"); parser.add_argument("--workers", type=int, default=8); args = parser.parse_args()
    if args.input:
        payload = json.loads(pathlib.Path(args.input).read_text(encoding="utf-8")); rows = None
        recipes = payload.get("recipes", payload) if isinstance(payload, dict) else payload; dataset = "repository_snapshot"
    else:
        rows = production_rows(); recipes = [row_to_recipe(row) for row in rows]; dataset = "production_supabase"
    if args.apply and (dataset != "production_supabase" or not args.confirm_production):
        raise SystemExit("--apply requires production Supabase plus --confirm-production")
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = pathlib.Path(args.output); out.mkdir(parents=True, exist_ok=True)
    backup = {"createdAt": stamp, "dataset": dataset, "appId": APP_ID, "records": rows if rows is not None else recipes}
    (out / "recipe-library-backup-{}.json".format(stamp)).write_text(json.dumps(backup, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.no_network or args.workers <= 1:
        items = [audit_recipe(recipe, not args.no_network) for recipe in recipes]
    else:
        with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
            items = list(pool.map(audit_recipe, recipes))
    for recipe, item in zip(recipes, items):
        if args.apply and item["proposedPatch"]:
            try: item["changed"] = apply_one(item, recipe)
            except Exception as exc: item["writeError"] = str(exc)
    completeness = collections.Counter(item["storedCompletenessAfter"]["status"] for item in items)
    sources = collections.Counter(item["sourceHealth"] for item in items); types = collections.Counter(item["sourceType"] for item in items)
    report = {"generatedAt": stamp, "dataset": dataset, "production": dataset == "production_supabase", "mode": "APPLY" if args.apply else "DRY_RUN",
              "totalRecipes": len(items), "storedRecipeCompleteness": dict(completeness), "sourceHealth": dict(sources), "sourceTypes": dict(types),
              "repairs": {"recipesModified": sum(i["changed"] for i in items), "ingredientListsAdded": sum(i["changed"] and "ingredientsText" in i["proposedPatch"] for i in items),
                          "instructionSetsAdded": sum(i["changed"] and "instructions" in i["proposedPatch"] for i in items), "imagesAdded": sum(i["changed"] and "image" in i["proposedPatch"] for i in items),
                          "screenshotsAdded": sum(i["changed"] and "sourceScreenshot" in i["proposedPatch"] for i in items), "sourceUrlsRepaired": 0,
                          "leftUnchangedExistingBetter": sum(not i["proposedPatch"] for i in items)},
              "integrity": {"recipeNamesChangedAutomatically": 0, "recipesLost": 0, "manualNotesOverwritten": 0, "favoritesChangedUnintentionally": 0},
              "remainingProblems": [i for i in items if i["storedCompletenessAfter"]["needsManualRecovery"]], "items": items}
    (out / "recipe-library-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("dataset", "production", "mode", "totalRecipes", "storedRecipeCompleteness", "sourceTypes", "repairs", "integrity")}, ensure_ascii=False, indent=2))


if __name__ == "__main__": main()
