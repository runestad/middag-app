#!/usr/bin/env python3
"""Safe, approval-gated normalization of recipes.structuredIngredients."""
import argparse
import datetime
import hashlib
import json
import os
import pathlib
import sys
import urllib.parse

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from api._common import APP_ID, row_to_recipe, recipe_to_row, supabase_request  # noqa: E402
from api.ingredient_normalization import normalize_structured_ingredients  # noqa: E402


def load_env():
    path = ROOT / ".env"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


def fetch_rows():
    query = urllib.parse.urlencode({"app_id": f"eq.{APP_ID}", "select": "*", "order": "id"})
    return supabase_request("GET", "recipes", query=query) or []


def build_changes(rows):
    changes, inventory = [], {}
    for row in rows:
        recipe = row_to_recipe(row)
        before = recipe.get("structuredIngredients")
        if not isinstance(before, list) or not before:
            continue
        after = normalize_structured_ingredients(before)
        for old, new in zip(before, after):
            name = str(old.get("item") or "").strip()
            key = (new.get("item"), new.get("shoppingCategory"))
            entry = inventory.setdefault(key, {"canonical": key[0], "category": key[1], "count": 0, "variants": set()})
            entry["count"] += 1
            entry["variants"].add(name)
        if before != after:
            # Preserve every recipe field and every ingredient field except item/category.
            changed = dict(recipe)
            changed["structuredIngredients"] = after
            changes.append({"id": recipe["id"], "name": recipe.get("name", ""), "before": before, "after": after, "row": recipe_to_row(changed)})
    report = [{**value, "variants": sorted(value["variants"])} for value in inventory.values()]
    return changes, sorted(report, key=lambda item: (-item["count"], item["canonical"]))


def digest_changes(changes):
    safe = [{"id": item["id"], "before": item["before"], "after": item["after"]} for item in changes]
    return hashlib.sha256(json.dumps(safe, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--approved-sha", default="")
    args = parser.parse_args()
    load_env()
    rows = fetch_rows()
    changes, inventory = build_changes(rows)
    timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    output = ROOT / ".data-migrations" / timestamp
    output.mkdir(parents=True)
    (output / "backup.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    (output / "ingredient-inventory.json").write_text(json.dumps(inventory, ensure_ascii=False, indent=2), encoding="utf-8")
    (output / "diff.json").write_text(json.dumps([{key: value for key, value in item.items() if key != "row"} for item in changes], ensure_ascii=False, indent=2), encoding="utf-8")
    sha = digest_changes(changes)
    sample = changes[:10]
    print(json.dumps({"recipes": len(rows), "changed": len(changes), "approvalSha": sha, "sample": [{key: value for key, value in item.items() if key != "row"} for item in sample], "output": str(output)}, ensure_ascii=False, indent=2))
    if not args.apply:
        print("\nDRY RUN: Ingen databaseendringer ble gjort.")
        return
    if not args.approved_sha or args.approved_sha != sha:
        raise SystemExit("Avbrutt: --approved-sha må være identisk med approvalSha fra denne kjøringen.")
    for change in changes:
        query = urllib.parse.urlencode({"id": f"eq.{change['id']}", "app_id": f"eq.{APP_ID}"})
        supabase_request("PATCH", "recipes", payload=change["row"], query=query, prefer="return=minimal")
    print(f"Oppdatert {len(changes)} oppskrifter. Backup: {output / 'backup.json'}")


if __name__ == "__main__":
    main()
