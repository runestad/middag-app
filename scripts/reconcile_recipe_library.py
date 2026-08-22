#!/usr/bin/env python3
"""Reconcile the historical recipe list, current dataset, and source audit."""

import argparse
import collections
import datetime
import json
import pathlib
import re
import subprocess
import unicodedata
import urllib.parse

ROOT = pathlib.Path(__file__).resolve().parents[1]
BASELINE_COMMIT = "7661fdc"
SUPPLEMENT = ROOT / "historical" / "original_recipe_supplement.json"


def normalize_name(value):
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def canonical_url(value):
    try:
        parsed = urllib.parse.urlparse(str(value or "").strip())
    except ValueError:
        return ""
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return ""
    keep = [(k, v) for k, v in urllib.parse.parse_qsl(parsed.query) if not k.lower().startswith("utm_") and k.lower() not in {"igsh", "igshid", "fbclid", "si"}]
    return urllib.parse.urlunparse((parsed.scheme.lower(), parsed.hostname.lower(), parsed.path.rstrip("/"), "", urllib.parse.urlencode(keep), ""))


def meaningful_lines(recipe, keys):
    candidates = []
    for key in keys:
        value = recipe.get(key)
        if isinstance(value, list):
            lines = [str(item.get("text") or item.get("item") or item.get("original") or "") if isinstance(item, dict) else str(item) for item in value]
        else:
            lines = str(value or "").splitlines()
        candidates.append([line.strip() for line in lines if line.strip()])
    return max(candidates, key=len) if candidates else []


def load_original():
    raw = subprocess.check_output(["git", "show", BASELINE_COMMIT + ":recipes.json"], cwd=str(ROOT))
    recipes = json.loads(raw.decode("utf-8"))
    original = [{"name": row.get("name") or "", "url": row.get("link") or "", "historicalRecipe": row,
                 "historicalSource": "git:" + BASELINE_COMMIT + ":recipes.json"} for row in recipes]
    supplement = json.loads(SUPPLEMENT.read_text(encoding="utf-8"))
    original.extend({"name": row["name"], "url": row["url"], "historicalRecipe": row,
                     "historicalSource": supplement["source"]} for row in supplement["entries"])
    return original


def match_original(item, current, used):
    url = canonical_url(item["url"])
    exact_url = [row for row in current if str(row.get("id")) not in used and canonical_url(row.get("link")) == url and url]
    if len(exact_url) == 1:
        return exact_url[0], "source_url"
    name = normalize_name(item["name"])
    exact_name = [row for row in current if str(row.get("id")) not in used and normalize_name(row.get("name")) == name]
    if len(exact_name) == 1:
        return exact_name[0], "name"
    return None, "none"


def reconcile(original, current, source_items):
    source_by_id = {str(row.get("id")): row for row in source_items}
    used, rows = set(), []
    for old in original:
        now, method = match_original(old, current, used)
        if not now:
            rows.append({"category": "Missing from MatplanApp", "originalName": old["name"], "originalSourceUrl": old["url"],
                         "currentName": None, "currentSourceUrl": None, "differences": ["Historical recipe has no current match"],
                         "historicalSource": old["historicalSource"], "needsManualReview": True})
            continue
        used.add(str(now.get("id")))
        historical = old["historicalRecipe"]
        old_ing = meaningful_lines(historical, ("structuredIngredients", "ingredientLines", "ingredientsText"))
        new_ing = meaningful_lines(now, ("structuredIngredients", "ingredientLines", "ingredientsText"))
        old_steps = meaningful_lines(historical, ("structuredInstructions", "instructionSteps", "instructions"))
        new_steps = meaningful_lines(now, ("structuredInstructions", "instructionSteps", "instructions"))
        audit = source_by_id.get(str(now.get("id")), {})
        differences, categories = [], []
        if old["name"] != now.get("name"):
            differences.append("Name differs: historical={!r}, current={!r}".format(old["name"], now.get("name")))
            categories.append("Needs manual review")
        if canonical_url(old["url"]) != canonical_url(now.get("link")):
            differences.append("Source URL differs")
            categories.append("Source URL changed")
        if len(new_ing) < len(old_ing):
            differences.append("Possible ingredient loss: historical {}, current {}".format(len(old_ing), len(new_ing)))
            categories.append("Current recipe missing data")
        if len(new_steps) < len(old_steps):
            differences.append("Possible instruction loss: historical {}, current {}".format(len(old_steps), len(new_steps)))
            categories.append("Current recipe missing data")
        if len(new_ing) > len(old_ing) or len(new_steps) > len(old_steps):
            categories.append("Current recipe improved")
        if audit.get("sourceHealth") in ("SOURCE_INACCESSIBLE", "SOURCE_REMOVED_OR_PRIVATE", "REDIRECT_ISSUE"):
            differences.append("Current source health: " + audit["sourceHealth"])
            categories.append("Source URL broken")
        completeness = audit.get("storedCompletenessAfter") or audit.get("storedCompletenessBefore") or {}
        if completeness.get("status") == "INCOMPLETE":
            missing = ", ".join(completeness.get("issues") or ["recipe content"])
            differences.append("Current stored recipe is incomplete: " + missing)
            categories.append("Current recipe missing data")
        if not categories:
            categories.append("Exact match")
        rows.append({"category": categories[0], "categories": sorted(set(categories)), "matchMethod": method,
                     "originalName": old["name"], "originalSourceUrl": old["url"], "currentName": now.get("name"),
                     "currentSourceUrl": now.get("link"), "currentStoredIngredients": new_ing,
                     "currentStoredInstructions": new_steps, "historicalIngredientCount": len(old_ing),
                     "historicalInstructionCount": len(old_steps), "currentSourceAvailability": audit.get("sourceHealth", "NOT_CHECKED"),
                     "newlyExtractedSourceContent": audit.get("proposedPatch") or {}, "differences": differences,
                     "historicalSource": old["historicalSource"], "needsManualReview": "Needs manual review" in categories or "Current recipe missing data" in categories})
    for now in current:
        if str(now.get("id")) not in used:
            rows.append({"category": "Present in MatplanApp but not in original list", "originalName": None, "originalSourceUrl": None,
                         "currentName": now.get("name"), "currentSourceUrl": now.get("link"), "differences": ["No historical match"], "needsManualReview": True})
    url_groups = collections.defaultdict(list)
    for row in current:
        if canonical_url(row.get("link")):
            url_groups[canonical_url(row.get("link"))].append(row.get("name"))
    duplicates = [{"category": "Possible duplicate", "sourceUrl": url, "recipeNames": names,
                   "differences": ["Multiple current recipes share one content URL"], "needsManualReview": True}
                  for url, names in url_groups.items() if len(names) > 1]
    name_groups = collections.defaultdict(list)
    for row in current:
        if normalize_name(row.get("name")):
            name_groups[normalize_name(row.get("name"))].append({"name": row.get("name"), "sourceUrl": row.get("link")})
    duplicates.extend({"category": "Possible duplicate", "normalizedName": name, "recipes": recipes,
                       "differences": ["Multiple current recipes have the same exact normalized name"], "needsManualReview": True}
                      for name, recipes in name_groups.items() if len(recipes) > 1)
    return rows + duplicates


def main():
    parser = argparse.ArgumentParser(); parser.add_argument("--current", default=str(ROOT / "recipes.json")); parser.add_argument("--source-audit"); parser.add_argument("--output", required=True); args = parser.parse_args()
    current_payload = json.loads(pathlib.Path(args.current).read_text(encoding="utf-8")); current = current_payload.get("recipes", current_payload) if isinstance(current_payload, dict) else current_payload
    source_items = json.loads(pathlib.Path(args.source_audit).read_text(encoding="utf-8")).get("items", []) if args.source_audit else []
    rows = reconcile(load_original(), current, source_items); counts = collections.Counter()
    for row in rows:
        for category in row.get("categories") or [row["category"]]: counts[category] += 1
    report = {"generatedAt": datetime.datetime.now(datetime.timezone.utc).isoformat(), "dataset": "repository_snapshot",
              "production": False, "historicalBaseline": "git:" + BASELINE_COMMIT + ":recipes.json plus user supplement",
              "originalCount": 230, "currentCount": len(current), "counts": dict(counts), "nameChangesApplied": 0,
              "sourceUrlChangesApplied": 0, "rows": rows}
    output = pathlib.Path(args.output); output.parent.mkdir(parents=True, exist_ok=True); output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("dataset", "production", "originalCount", "currentCount", "counts", "nameChangesApplied", "sourceUrlChangesApplied")}, ensure_ascii=False, indent=2))


if __name__ == "__main__": main()
