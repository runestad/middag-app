#!/usr/bin/env python3
"""Approval-gated production recipe quality migration.

Default mode is read-only: export, verify backup, analyze, and generate previews.
Production writes require --apply plus the exact SHA printed by the same dataset.
"""
import argparse
import collections
import datetime
import hashlib
import html
import json
import os
import pathlib
import re
import sys
import urllib.parse

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from api._common import APP_ID, row_to_recipe, recipe_to_row, supabase_request  # noqa: E402
from api.ingredient_normalization import ALIASES, CATALOG, CATEGORIES, _key  # noqa: E402

VALID_SHOPPING = set(CATALOG["categories"])
VALID_RECIPE_CATEGORIES = {"Vegetar", "Salat", "Pasta", "Kjøtt", "Kylling", "Fisk", "Airfryer", "Snacks", "Annet"}
RECIPE_CATEGORY_ALIASES = {
    "pasta": "Pasta", "pastaretter": "Pasta", "chicken": "Kylling", "kyllingretter": "Kylling",
    "kylling": "Kylling", "vegetarian": "Vegetar", "vegetar": "Vegetar", "meat": "Kjøtt",
    "kjøttretter": "Kjøtt", "kjøtt": "Kjøtt", "fish": "Fisk", "fiskeretter": "Fisk",
    "fisk": "Fisk", "salater": "Salat", "salat": "Salat", "air fryer": "Airfryer",
    "airfryer": "Airfryer", "snack": "Snacks", "snacks": "Snacks", "annet": "Annet",
}
UNIT_ALIASES = {
    "tablespoon": "ss", "tablespoons": "ss", "tbsp": "ss", "tbs": "ss", "spiseskje": "ss",
    "teaspoon": "ts", "teaspoons": "ts", "tsp": "ts", "teskje": "ts",
    "gram": "g", "grams": "g", "gr": "g", "g": "g",
    "kilogram": "kg", "kilograms": "kg", "kilo": "kg", "kg": "kg",
    "millilitre": "ml", "millilitres": "ml", "milliliter": "ml", "ml": "ml",
    "decilitre": "dl", "decilitres": "dl", "desiliter": "dl", "dl": "dl",
    "litre": "l", "litres": "l", "liter": "l", "l": "l",
    "piece": "stk", "pieces": "stk", "stykk": "stk", "stykk.": "stk", "stk": "stk",
    "clove": "fedd", "cloves": "fedd", "fedd": "fedd",
    "can": "boks", "cans": "boks", "boks": "boks",
    "pack": "pakke", "packs": "pakke", "package": "pakke", "pakke": "pakke",
    "stalk": "stilk", "stalks": "stilk", "stilk": "stilk",
    "bunch": "bunt", "bunches": "bunt", "bunt": "bunt",
}
ENGLISH_WORDS = re.compile(
    r"\b(onion|scallion|cornstarch|cilantro|pepper|tomato|garlic|carrot|celery|"
    r"chicken|beef|pork|shrimp|butter|cream|cheese|flour|broth|stock|beans|"
    r"chopped|diced|sliced|minced|fresh|dried|optional|serving)\b", re.I
)
HTML_RE = re.compile(r"<[^>]+>|&(?:nbsp|amp|lt|gt|quot);", re.I)
OCR_RE = re.compile(r"(?:\b[Il|]{3,}\b|\b\d+to\s*°|[^\w\s.,:;!?%°+&/()'’\"-])", re.UNICODE)
AMBIGUOUS_CANONICAL = {"paprika"}


def load_env():
    path = ROOT / ".env"
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


def fetch_rows():
    query = urllib.parse.urlencode({"app_id": f"eq.{APP_ID}", "select": "*", "order": "id"})
    return supabase_request("GET", "recipes", query=query) or []


def canonical_exact(value):
    original = str(value or "").strip()
    canonical = ALIASES.get(_key(original))
    return canonical or original


def normalized_unit(value):
    original = str(value or "").strip()
    return UNIT_ALIASES.get(original.lower(), original)


def normalized_recipe_category(value):
    original = str(value or "").strip()
    if original in VALID_RECIPE_CATEGORIES:
        return original
    return RECIPE_CATEGORY_ALIASES.get(original.lower(), original)


def normalized_tags(tags):
    if not isinstance(tags, list):
        return []
    result, seen = [], set()
    translations = {"chicken": "kylling", "meat": "kjøtt", "fish": "fisk", "vegetarian": "vegetar", "soup": "suppe", "salad": "salat"}
    for tag in tags:
        clean = translations.get(str(tag).strip().lower(), str(tag).strip().lower())
        if clean and clean not in seen:
            seen.add(clean)
            result.append(clean)
    return result


def proposed_emoji(recipe):
    if str(recipe.get("emoji") or "").strip():
        return recipe.get("emoji")
    return {"Vegetar": "🥦", "Salat": "🥗", "Pasta": "🍝", "Kjøtt": "🥩", "Kylling": "🍗", "Fisk": "🐟", "Airfryer": "🔥", "Snacks": "🥒"}.get(recipe.get("category"), "🍽️")


def analyze_and_propose(rows):
    changes, ingredient_inventory, reviews, issues = [], {}, [], collections.Counter()
    units, shopping_categories = collections.Counter(), collections.Counter()
    recipe_names, recipe_links = collections.defaultdict(list), collections.defaultdict(list)
    total_ingredients = normalization_count = category_changes = unit_changes = 0
    for key in (
        "ødelagt JSON", "tomme felt", "manglende ingredienskategorier",
        "ugyldige handlelistekategorier", "ugyldige tegn", "HTML-rester",
        "mulige OCR-feil", "engelske ingredienser", "ugyldige enheter",
        "oppskrifter uten ingredienser", "oppskrifter uten fremgangsmåte",
        "tomme oppskriftsnavn", "ugyldige oppskriftskategorier",
        "dublette ingredienser i samme oppskrift",
    ):
        issues[key] = 0

    for row in rows:
        recipe = row_to_recipe(row)
        recipe_id, name = recipe.get("id"), str(recipe.get("name") or "").strip()
        recipe_names[name.casefold()].append(recipe_id)
        if recipe.get("link"):
            recipe_links[str(recipe["link"]).strip()].append(recipe_id)
        proposed = dict(recipe)
        structured = recipe.get("structuredIngredients")
        ingredients_text = str(recipe.get("ingredientsText") or "")
        instructions = recipe.get("instructions")
        structured_instructions = recipe.get("structuredInstructions")
        if not ingredients_text.strip() and not structured:
            issues["oppskrifter uten ingredienser"] += 1
        if not str(instructions or "").strip() and not structured_instructions:
            issues["oppskrifter uten fremgangsmåte"] += 1
        if not name:
            issues["tomme oppskriftsnavn"] += 1
        for field in ("name", "category", "ingredientsText", "instructions", "tags", "emoji", "status"):
            value = recipe.get(field)
            if value is None or value == "" or value == []:
                issues["tomme felt"] += 1
        if HTML_RE.search(json.dumps(recipe, ensure_ascii=False)):
            issues["HTML-rester"] += 1
        if OCR_RE.search(ingredients_text):
            issues["mulige OCR-feil"] += 1
        if "\ufffd" in json.dumps(recipe, ensure_ascii=False):
            issues["ugyldige tegn"] += 1

        category = normalized_recipe_category(recipe.get("category"))
        if category not in VALID_RECIPE_CATEGORIES:
            issues["ugyldige oppskriftskategorier"] += 1
            reviews.append({"recipeId": recipe_id, "recipe": name, "field": "category", "value": recipe.get("category"), "reason": "Ukjent oppskriftskategori"})
        elif category != recipe.get("category"):
            proposed["category"] = category
        proposed["tags"] = normalized_tags(recipe.get("tags"))
        proposed["emoji"] = proposed_emoji({**recipe, "category": category})

        new_structured, names_in_recipe = [], collections.Counter()
        for index, ingredient in enumerate(structured if isinstance(structured, list) else []):
            if not isinstance(ingredient, dict):
                reviews.append({"recipeId": recipe_id, "recipe": name, "field": f"structuredIngredients.{index}", "value": ingredient, "reason": "Ingrediensen er ikke et JSON-objekt"})
                new_structured.append(ingredient)
                continue
            total_ingredients += 1
            old_item = str(ingredient.get("item") or "").strip()
            old_category = str(ingredient.get("shoppingCategory") or "").strip()
            old_unit = str(ingredient.get("unit") or "").strip()
            units[old_unit or "(tom)"] += 1
            shopping_categories[old_category or "(tom)"] += 1
            canonical = canonical_exact(old_item)
            known = canonical in CATEGORIES
            category_after = CATEGORIES[canonical] if known else old_category
            ambiguous = canonical in AMBIGUOUS_CANONICAL and old_category in VALID_SHOPPING and old_category != category_after
            if ambiguous:
                category_after = old_category
            unit_after = normalized_unit(old_unit)
            names_in_recipe[(canonical or old_item).casefold()] += 1
            inventory_key = canonical.casefold() or "(tom)"
            inv = ingredient_inventory.setdefault(inventory_key, {
                "name": canonical, "status": "KNOWN" if known else "NEW", "category": category_after,
                "count": 0, "variants": set(), "units": set(), "needsReview": False,
            })
            inv["count"] += 1
            inv["variants"].add(old_item)
            inv["units"].add(old_unit)

            reasons = []
            if not old_item:
                reasons.append("Tomt ingrediensnavn")
            if not known:
                reasons.append("Ikke i Ingredient Registry")
            if old_category not in VALID_SHOPPING:
                reasons.append("Manglende eller ugyldig handlelistekategori")
                if not old_category:
                    issues["manglende ingredienskategorier"] += 1
                else:
                    issues["ugyldige handlelistekategorier"] += 1
            if old_unit and unit_after == old_unit and old_unit.lower() not in UNIT_ALIASES and old_unit not in {"ss", "ts", "g", "kg", "ml", "dl", "l", "stk", "fedd", "boks", "pakke", "stilk", "bunt"}:
                reasons.append("Ukjent enhet")
                issues["ugyldige enheter"] += 1
            if ENGLISH_WORDS.search(old_item):
                reasons.append("Mulig engelsk ingrediensnavn")
                issues["engelske ingredienser"] += 1
            if re.search(r"\b(og|eller|&|/)\b", old_item, re.I) and not known:
                reasons.append("Sammensatt eller alternativ ingrediens må vurderes")
            if ambiguous:
                reasons.append("Navnet er tvetydig; eksisterende kategori er beholdt")
            if reasons:
                inv["needsReview"] = True
                reviews.append({"recipeId": recipe_id, "recipe": name, "field": f"structuredIngredients.{index}", "value": old_item, "reason": "; ".join(sorted(set(reasons)))})

            updated = dict(ingredient)
            if known and canonical != old_item:
                updated["item"] = canonical
                normalization_count += 1
            if known and category_after != old_category:
                updated["shoppingCategory"] = category_after
                category_changes += 1
            if unit_after != old_unit:
                updated["unit"] = unit_after
                unit_changes += 1
            new_structured.append(updated)
        issues["dublette ingredienser i samme oppskrift"] += sum(count - 1 for count in names_in_recipe.values() if count > 1)
        proposed["structuredIngredients"] = new_structured
        changed_fields = [field for field in ("name", "category", "ingredientsText", "structuredIngredients", "instructions", "structuredInstructions", "tags", "emoji", "status") if proposed.get(field) != recipe.get(field)]
        if changed_fields:
            changes.append({"id": recipe_id, "name": name, "fields": changed_fields, "before": {field: recipe.get(field) for field in changed_fields}, "after": {field: proposed.get(field) for field in changed_fields}, "row": recipe_to_row(proposed)})

    duplicate_names = {name: ids for name, ids in recipe_names.items() if name and len(ids) > 1}
    duplicate_links = {link: ids for link, ids in recipe_links.items() if len(ids) > 1}
    issues["dublettgrupper navn"] = len(duplicate_names)
    issues["dublettgrupper lenke"] = len(duplicate_links)
    registry = []
    for item in ingredient_inventory.values():
        registry.append({**item, "variants": sorted(item["variants"]), "units": sorted(item["units"])})
    registry.sort(key=lambda item: (item["status"] != "NEW", item["name"].casefold()))
    return {
        "changes": changes, "registry": registry, "reviews": reviews, "issues": dict(issues),
        "units": dict(units), "shoppingCategories": dict(shopping_categories),
        "duplicateNames": duplicate_names, "duplicateLinks": duplicate_links,
        "stats": {"recipes": len(rows), "ingredients": total_ingredients, "uniqueIngredients": len(registry),
                  "normalizations": normalization_count, "categoryChanges": category_changes,
                  "unitChanges": unit_changes, "duplicateGroups": len(duplicate_names) + len(duplicate_links),
                  "recipesNeedingReview": len(set(item["recipeId"] for item in reviews))},
    }


def hash_json(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def verify_backup(path, rows):
    loaded = json.loads(path.read_text(encoding="utf-8"))
    checks = {
        "validJson": isinstance(loaded, list),
        "rowCountMatches": len(loaded) == len(rows),
        "idsMatch": sorted(str(row.get("id")) for row in loaded) == sorted(str(row.get("id")) for row in rows),
        "contentHashMatches": hash_json(loaded) == hash_json(rows),
        "restorableShape": all(isinstance(row, dict) and "id" in row and "data" in row for row in loaded),
    }
    checks["verified"] = all(checks.values())
    return checks


def report_markdown(result, verification, output):
    stats, issues = result["stats"], result["issues"]
    lines = ["# Produksjonsanalyse – MatplanApp", "", "## Sikkerhet", "",
             f"- Backup: `{output / 'backup.json'}`", f"- Gjenopprettingstest: **{'BESTÅTT' if verification['verified'] else 'FEILET'}**",
             "- Produksjonsdata endret: **Nei**", "- SQL generert: **Nei**", "", "## Sammendrag", "",
             f"- Oppskrifter: {stats['recipes']}", f"- Strukturerte ingredienser: {stats['ingredients']}",
             f"- Unike ingredienser: {stats['uniqueIngredients']}", f"- Sikre navnenormaliseringer: {stats['normalizations']}",
             f"- Sikre kategoriendringer: {stats['categoryChanges']}", f"- Enhetsendringer: {stats['unitChanges']}",
             f"- Dublettgrupper: {stats['duplicateGroups']}", f"- Oppskrifter som trenger manuell kontroll: {stats['recipesNeedingReview']}",
             "", "## Datakvalitetsfunn", ""]
    lines += [f"- {key}: {value}" for key, value in sorted(issues.items())]
    lines += ["", "## 20 konkrete før/etter-eksempler", ""]
    for change in result["changes"][:20]:
        lines += [f"### {change['name']} (ID {change['id']})", "", f"Endrede felt: {', '.join(change['fields'])}", "```json",
                  json.dumps({"før": change["before"], "etter": change["after"]}, ensure_ascii=False, indent=2), "```", ""]
    lines += ["## Ingredienser som trenger vurdering", ""]
    for item in result["reviews"]:
        lines.append(f"- **{item['recipe']}** (ID {item['recipeId']}), `{item['field']}`: `{item['value']}` — {item['reason']}")
    lines += ["", "## Enheter i produksjonsdata", "", "```json", json.dumps(result["units"], ensure_ascii=False, indent=2), "```",
              "", "## Handlelistekategorier i produksjonsdata", "", "```json", json.dumps(result["shoppingCategories"], ensure_ascii=False, indent=2), "```"]
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--approved-sha", default="")
    args = parser.parse_args()
    load_env()
    rows = fetch_rows()
    timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    output = ROOT / ".data-migrations" / timestamp
    output.mkdir(parents=True)
    backup_path = output / "backup.json"
    backup_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    verification = verify_backup(backup_path, rows)
    if not verification["verified"]:
        raise SystemExit("Backupverifisering feilet. Analyse og skriving er avbrutt.")

    result = analyze_and_propose(json.loads(backup_path.read_text(encoding="utf-8")))
    changes = result.pop("changes")
    safe_diff = [{key: value for key, value in item.items() if key != "row"} for item in changes]
    approval_sha = hash_json(safe_diff)
    (output / "backup-verification.json").write_text(json.dumps(verification, indent=2), encoding="utf-8")
    (output / "diff.json").write_text(json.dumps(safe_diff, ensure_ascii=False, indent=2), encoding="utf-8")
    (output / "preview.json").write_text(json.dumps(safe_diff[:20], ensure_ascii=False, indent=2), encoding="utf-8")
    (output / "ingredient-registry.preview.json").write_text(json.dumps(result["registry"], ensure_ascii=False, indent=2), encoding="utf-8")
    (output / "manual-review.json").write_text(json.dumps(result["reviews"], ensure_ascii=False, indent=2), encoding="utf-8")
    (output / "report.md").write_text(report_markdown({**result, "changes": changes}, verification, output), encoding="utf-8")
    summary = {**result["stats"], "approvalSha": approval_sha, "backupVerified": verification["verified"], "output": str(output)}
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if not args.apply:
        print("DRY RUN: Ingen databaseendringer eller SQL ble generert.")
        return
    if args.approved_sha != approval_sha:
        raise SystemExit("Avbrutt: eksplisitt godkjent SHA samsvarer ikke med dagens diff.")
    for change in changes:
        query = urllib.parse.urlencode({"id": f"eq.{change['id']}", "app_id": f"eq.{APP_ID}"})
        supabase_request("PATCH", "recipes", payload=change["row"], query=query, prefer="return=minimal")
    print(f"Oppdatert {len(changes)} oppskrifter. Backup: {backup_path}")


if __name__ == "__main__":
    main()
