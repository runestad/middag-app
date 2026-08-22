#!/usr/bin/env python3
"""Read-only recipe health audit. It never writes recipe data."""

import argparse
import concurrent.futures
import json
import pathlib
import sys
import urllib.request
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from api import recipe_import

import importlib.util
spec = importlib.util.spec_from_file_location("api.fetch_recipe_audit", ROOT / "api" / "fetch-recipe.py")
fetch_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fetch_module)


def recipe_url(recipe):
    data = recipe.get("data") if isinstance(recipe.get("data"), dict) else {}
    for key in ("link", "sourceUrl", "sourceURL", "source_url", "originalSourceUrl"):
        value = recipe.get(key) or data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def load_recipes(path, url):
    if url:
        with urllib.request.urlopen(url, timeout=60) as response:
            payload = json.loads(response.read().decode("utf-8"))
    else:
        payload = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    return payload.get("recipes", []) if isinstance(payload, dict) else payload


def audit_one(recipe):
    name, url = str(recipe.get("name") or "Uten navn"), recipe_url(recipe)
    row = {"id": recipe.get("id"), "name": name, "url": url, "modified": False, "proposedPatch": {}}
    if not url:
        row.update(status="NO_SOURCE", explanation="Ingen kilde er lagret.", action="Legg inn en kilde ved behov.")
        return row
    try:
        extracted = fetch_module.extract(url)
        quality = extracted.get("importQuality") or recipe_import.assess_import_quality(extracted)
        merged = recipe_import.safe_recipe_merge(recipe, extracted)
        patch = {key: value for key, value in merged.items() if recipe.get(key) != value and key != "name"}
        status = quality.get("status", "INCOMPLETE")
        row.update(status=status, quality=quality, proposedPatch=patch,
                   explanation="Kilden inneholder en brukbar oppskrift." if status in ("COMPLETE", "PROBABLY_COMPLETE") else "Kilden ga bare deler av en brukbar oppskrift.",
                   action="Kontroller foreslåtte felt før eventuell lagring." if patch else "Ingen endring foreslått.")
    except Exception as exc:
        text = str(exc)
        status = "BROKEN_URL" if any(token in text for token in ("404", "410", "Name or service", "nodename")) else "INACCESSIBLE"
        row.update(status=status, explanation="Kilden kunne ikke nås: {}".format(text[:180]), action="Kontroller lenken eller finn en ny kilde.")
    return row


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default=str(ROOT / "recipes.json"))
    parser.add_argument("--input-url")
    parser.add_argument("--output", required=True)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    recipes = load_recipes(args.input, args.input_url)
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        rows = list(pool.map(audit_one, recipes))
    counts = {}
    for row in rows:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    report = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "mode": "READ_ONLY",
        "totalRecipes": len(recipes),
        "recipesWithUrls": sum(bool(recipe_url(r)) for r in recipes),
        "counts": counts,
        "nameChanges": 0,
        "items": rows,
    }
    pathlib.Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("mode", "totalRecipes", "recipesWithUrls", "counts", "nameChanges")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
