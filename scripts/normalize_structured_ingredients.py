#!/usr/bin/env python3
"""Approval-gated production recipe quality migration.

Default mode is read-only: export, verify backup, analyze, and generate previews.
Production writes require --apply plus the exact SHA printed by the same dataset.
"""
import argparse
import collections
import csv
import datetime
import hashlib
import html
import json
import os
import pathlib
import re
import sys
import subprocess
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


def exact_deduplicate(values):
    result, removed, seen = [], 0, set()
    for value in values:
        marker = json.dumps(value, ensure_ascii=False, sort_keys=True) if isinstance(value, (dict, list)) else str(value)
        if marker in seen:
            removed += 1
        else:
            seen.add(marker)
            result.append(value)
    return result, removed


def build_safe_track(rows):
    recipes, events = [], []
    totals = collections.Counter()
    for row in rows:
        recipe = row_to_recipe(row)
        structured = recipe.get("structuredIngredients")
        text = recipe.get("ingredientsText")
        if not isinstance(structured, list) or not structured:
            continue
        after = []
        recipe_events = []
        for index, ingredient in enumerate(structured):
            if not isinstance(ingredient, dict) or not str(ingredient.get("item") or "").strip():
                after.append(ingredient)
                continue
            updated = dict(ingredient)
            old_name = str(ingredient.get("item") or "").strip()
            old_category = str(ingredient.get("shoppingCategory") or "").strip()
            old_unit = str(ingredient.get("unit") or "").strip()
            canonical = canonical_exact(old_name)
            known = canonical in CATEGORIES
            ambiguous = canonical in AMBIGUOUS_CANONICAL and old_category in VALID_SHOPPING and old_category != CATEGORIES.get(canonical)
            new_category = CATEGORIES.get(canonical, old_category) if known and not ambiguous else old_category
            new_unit = normalized_unit(old_unit)
            field_changes = []
            if known and not ambiguous and canonical != old_name:
                updated["item"] = canonical
                field_changes.append("ingrediensnavn")
            if known and not ambiguous and old_category in VALID_SHOPPING and new_category != old_category:
                updated["shoppingCategory"] = new_category
                field_changes.append("kategori")
            if old_unit and new_unit != old_unit:
                updated["unit"] = new_unit
                field_changes.append("enhet")
            if field_changes:
                for kind in field_changes:
                    totals[kind] += 1
                event = {
                    "recipeId": recipe.get("id"), "recipe": recipe.get("name"), "ingredientIndex": index,
                    "before": {"item": old_name, "shoppingCategory": old_category, "unit": old_unit},
                    "after": {"item": updated.get("item"), "shoppingCategory": updated.get("shoppingCategory"), "unit": updated.get("unit")},
                    "changeTypes": field_changes,
                    "reason": "Eksakt alias/enhetsvariant i sentral registry",
                    "confidence": "høy",
                }
                events.append(event)
                recipe_events.append(event)
            after.append(updated)
        # Identical lines may intentionally belong to different recipe components.
        # They are reported by the general analysis, but never removed automatically.
        removed_text = 0
        text_after = text
        if recipe_events:
            before_fields = {"structuredIngredients": structured}
            after_fields = {"structuredIngredients": after}
            recipes.append({
                "id": recipe.get("id"), "name": recipe.get("name"), "events": recipe_events,
                "before": before_fields, "after": after_fields,
                "rollback": {"id": recipe.get("id"), "fields": before_fields},
            })
    return {"recipes": recipes, "events": events, "totals": dict(totals)}


def safe_track_html(track):
    rows = []
    for event in track["events"]:
        before, after = event["before"], event["after"]
        rows.append(f"""<tr>
<td>{html.escape(str(event['recipe']))}<small>ID {html.escape(str(event['recipeId']))}</small></td>
<td>{html.escape(str(before.get('item','—')))}</td><td>{html.escape(str(after.get('item','—')))}</td>
<td>{html.escape(str(before.get('shoppingCategory','—')))}</td><td>{html.escape(str(after.get('shoppingCategory','—')))}</td>
<td>{html.escape(str(before.get('unit','—')))}</td><td>{html.escape(str(after.get('unit','—')))}</td>
<td>{html.escape(event['reason'])}</td><td><span class="confidence">{event['confidence']}</span></td></tr>""")
    total_fields = sum(track["totals"].values())
    return f"""<!doctype html><html lang="no"><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>Spor A – sikker normalisering</title><style>
body{{font:15px system-ui;background:#f5f3ee;color:#263126;margin:0}}main{{max-width:1500px;margin:auto;padding:28px}}
.summary{{display:flex;gap:12px;flex-wrap:wrap}}.card{{background:white;border-radius:14px;padding:14px 18px;box-shadow:0 4px 18px #0001}}
input{{width:100%;box-sizing:border-box;padding:12px;margin:18px 0;border:1px solid #bbc5b8;border-radius:10px}}
.table{{overflow:auto;background:white;border-radius:14px}}table{{border-collapse:collapse;width:100%;min-width:1250px}}th,td{{padding:10px;border-bottom:1px solid #e4e7e1;text-align:left;vertical-align:top}}
th{{position:sticky;top:0;background:#324b35;color:white}}small{{display:block;color:#6c776d}}.confidence{{background:#dff1df;padding:3px 8px;border-radius:20px}}
</style><main><h1>Spor A – sikker normalisering</h1><p>Kun eksisterende, strukturerte ingredienser. Ingen tomme felt fylles, ingen mengder endres.</p>
<div class="summary"><div class="card"><b>{len(track['recipes'])}</b><br>oppskrifter</div><div class="card"><b>{total_fields}</b><br>felt/linjer</div>
{''.join(f'<div class="card"><b>{value}</b><br>{html.escape(key)}</div>' for key,value in sorted(track['totals'].items()))}</div>
<input id="q" placeholder="Søk etter oppskrift eller ingrediens">
<div class="table"><table><thead><tr><th>Oppskrift</th><th>Eksisterende ingrediens</th><th>Foreslått ingrediens</th><th>Gammel kategori</th><th>Ny kategori</th><th>Gammel enhet</th><th>Ny enhet</th><th>Årsak</th><th>Sikkerhet</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div>
<script>q.oninput=()=>document.querySelectorAll('tbody tr').forEach(r=>r.hidden=!r.innerText.toLowerCase().includes(q.value.toLowerCase()))</script></main></html>"""


def safe_track_markdown(track):
    total_fields = sum(track["totals"].values())
    lines = [
        "# Spor A – sikker normalisering", "",
        "## Avgrensning", "",
        "- Bare eksisterende `structuredIngredients` og beviselig identiske dublettlinjer behandles.",
        "- Manglende ingredienser og fremgangsmåte fylles aldri inn.",
        "- Ikke-tomme felt erstattes aldri med tomme verdier.",
        "- `original`, mengde, noter og oppskriftens mening beholdes.",
        "- Tvetydige eller ukjente ingredienser forblir urørt.", "",
        "## Eksakte tall", "",
        f"- Oppskrifter som foreslås endret: {len(track['recipes'])}",
        f"- Felt/identiske linjer som foreslås endret: {total_fields}",
        f"- Ingrediensnavn: {track['totals'].get('ingrediensnavn', 0)}",
        f"- Handlelistekategori: {track['totals'].get('kategori', 0)}",
        f"- Enhet: {track['totals'].get('enhet', 0)}",
        f"- Helt identiske dublettlinjer: {track['totals'].get('dublettfjerning', 0)}", "",
        "## 30 representative før/etter-eksempler", "",
    ]
    for event in track["events"][:30]:
        lines += [
            f"### {event['recipe']} (ID {event['recipeId']})", "",
            f"- Typer: {', '.join(event['changeTypes'])}",
            f"- Årsak: {event['reason']}",
            f"- Sikkerhet: {event['confidence']}", "```json",
            json.dumps({"før": event["before"], "etter": event["after"]}, ensure_ascii=False, indent=2), "```", "",
        ]
    lines += ["## Komplett liste over berørte oppskrifter", ""]
    lines += [f"- ID {recipe['id']}: {recipe['name']} ({len(recipe['events'])} endringshendelser)" for recipe in track["recipes"]]
    lines += ["", "## Bekreftelse", "", "Tomme og manglende felt forblir urørt. Produksjonsdata er ikke endret.", ""]
    return "\n".join(lines)


def load_recipe_file(path):
    records = []
    try:
        if path.suffix.lower() == ".csv":
            with path.open(encoding="utf-8-sig", newline="") as handle:
                for row in csv.DictReader(handle):
                    data = row.get("data")
                    if data:
                        try:
                            parsed = json.loads(data)
                        except Exception:
                            continue
                        parsed.setdefault("id", row.get("id"))
                        records.append(parsed)
        else:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            loaded = loaded.get("recipes", loaded) if isinstance(loaded, dict) else loaded
            if isinstance(loaded, list):
                for record in loaded:
                    if isinstance(record, dict):
                        records.append(row_to_recipe(record) if "data" in record else record)
    except Exception:
        return []
    return records


def local_source_files():
    roots = [
        pathlib.Path.home() / "Desktop" / "Middagsdatabase",
        pathlib.Path.home() / "Downloads",
        pathlib.Path.home() / "Documents" / "GitHub" / "middag-app",
        ROOT,
    ]
    found = []
    for root in roots:
        if not root.exists():
            continue
        for current, directories, files in os.walk(str(root)):
            directories[:] = [name for name in directories if name not in {".git", ".data-migrations", "node_modules", "__pycache__"}]
            for filename in files:
                lower = filename.lower()
                if ("recipe" in lower or "oppskrift" in lower) and lower.endswith((".json", ".csv")):
                    path = pathlib.Path(current) / filename
                    if path not in found:
                        found.append(path)
    return found


def record_has(record, field):
    value = record.get(field)
    return bool(value.strip()) if isinstance(value, str) else bool(value)


def build_recovery_track(rows):
    sources = collect_recovery_sources()
    reports = []
    for row in rows:
        recipe = row_to_recipe(row)
        missing = []
        if not record_has(recipe, "ingredientsText") and not record_has(recipe, "structuredIngredients"):
            missing.append("ingredienser")
        if not record_has(recipe, "instructions") and not record_has(recipe, "structuredInstructions"):
            missing.append("fremgangsmåte")
        if not missing:
            continue
        traces = {}
        for key in ("caption", "rawText", "raw", "ocrText", "ocrResult", "image", "images", "screenshot", "sourceText"):
            if record_has(recipe, key):
                traces[key] = True
        matches = []
        rid, link, name = str(recipe.get("id") or ""), str(recipe.get("link") or "").strip(), str(recipe.get("name") or "").strip().casefold()
        for source_name, candidate in sources:
            candidate_id = str(candidate.get("id") or "")
            candidate_link = str(candidate.get("link") or "").strip()
            candidate_name = str(candidate.get("name") or candidate.get("title") or "").strip().casefold()
            match_type = "id" if rid and candidate_id == rid else "lenke" if link and candidate_link == link else "navn" if name and candidate_name == name else ""
            if not match_type:
                continue
            available = [field for field in ("ingredientsText", "structuredIngredients", "instructions", "structuredInstructions", "caption", "rawText", "ocrText") if record_has(candidate, field)]
            useful = ("ingredienser" in missing and any(field in available for field in ("ingredientsText", "structuredIngredients"))) or ("fremgangsmåte" in missing and any(field in available for field in ("instructions", "structuredInstructions")))
            if useful or available:
                matches.append({"source": source_name, "match": match_type, "availableFields": available, "usefulForMissingData": useful})
        useful_matches = [match for match in matches if match["usefulForMissingData"]]
        if any(match["match"] in ("id", "lenke") for match in useful_matches):
            probability = "høy"
        elif useful_matches:
            probability = "middels"
        elif traces or link:
            probability = "lav"
        else:
            probability = "ingen kjent kilde"
        existing_fields = [field for field in ("name", "category", "ingredientsText", "structuredIngredients", "instructions", "structuredInstructions", "tags", "emoji", "status") if record_has(recipe, field)]
        reports.append({
            "id": recipe.get("id"), "name": recipe.get("name"), "source": recipe.get("source"), "link": recipe.get("link"),
            "createdAt": row.get("created_at"), "updatedAt": row.get("updated_at"),
            "existingFields": existing_fields, "missingFields": missing, "traces": traces,
            "matches": matches, "recoveryProbability": probability,
        })
    return {"recipes": reports, "sourceFilesScanned": len(set(source for source, _ in sources)), "sourceRecordsScanned": len(sources)}


def collect_recovery_sources():
    sources = []
    for path in local_source_files():
        for record in load_recipe_file(path):
            sources.append((str(path), record))
    # Git snapshots are kept separate from current working files.
    try:
        commits = subprocess.check_output(["git", "log", "--all", "--format=%H", "--", "recipes.json"], cwd=str(ROOT), text=True).splitlines()
        for commit in commits:
            raw = subprocess.check_output(["git", "show", f"{commit}:recipes.json"], cwd=str(ROOT), text=True, stderr=subprocess.DEVNULL)
            loaded = json.loads(raw)
            loaded = loaded.get("recipes", loaded) if isinstance(loaded, dict) else loaded
            for record in loaded if isinstance(loaded, list) else []:
                sources.append((f"git:{commit[:12]}:recipes.json", record))
    except Exception:
        pass
    return sources


def recovery_html(track):
    order = ["høy", "middels", "lav", "ingen kjent kilde"]
    sections = []
    for probability in order:
        cards = []
        for recipe in [item for item in track["recipes"] if item["recoveryProbability"] == probability]:
            matches = "".join(f"<li><code>{html.escape(match['source'])}</code> – treff på {match['match']}; felt: {html.escape(', '.join(match['availableFields']) or 'ingen oppskriftsfelt')}</li>" for match in recipe["matches"][:12])
            cards.append(f"""<article><h3>{html.escape(str(recipe['name']))} <small>ID {html.escape(str(recipe['id']))}</small></h3>
<p><b>Mangler:</b> {html.escape(', '.join(recipe['missingFields']))}<br><b>Finnes:</b> {html.escape(', '.join(recipe['existingFields']))}<br>
<b>Kilde:</b> {html.escape(str(recipe.get('source') or '—'))} · <a href="{html.escape(str(recipe.get('link') or '#'))}">original lenke</a><br>
<b>Opprettet:</b> {html.escape(str(recipe.get('createdAt') or '—'))} · <b>Oppdatert:</b> {html.escape(str(recipe.get('updatedAt') or '—'))}<br>
<b>Råspor:</b> {html.escape(', '.join(recipe['traces']) or 'ingen')}</p><details><summary>{len(recipe['matches'])} mulige lokale treff</summary><ul>{matches or '<li>Ingen lokale treff</li>'}</ul></details></article>""")
        sections.append(f"<section><h2>{probability.title()} ({len(cards)})</h2>{''.join(cards) or '<p>Ingen.</p>'}</section>")
    return f"""<!doctype html><html lang="no"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Spor B – gjenoppretting</title>
<style>body{{font:15px system-ui;background:#f5f3ee;color:#263126;margin:0}}main{{max-width:1050px;margin:auto;padding:28px}}nav{{display:flex;gap:8px;flex-wrap:wrap}}nav button{{padding:8px 12px}}article{{background:white;border-radius:14px;padding:16px;margin:10px 0;box-shadow:0 3px 14px #0001}}small{{color:#68746a}}a{{color:#356344}}code{{word-break:break-all}}input{{width:100%;box-sizing:border-box;padding:12px;margin:18px 0}}</style>
<main><h1>Spor B – kartlegging av manglende oppskriftsdata</h1><p>{len(track['recipes'])} berørte oppskrifter. {track['sourceFilesScanned']} lokale/Git-kilder og {track['sourceRecordsScanned']} historiske poster undersøkt. Ingen eldre data er brukt som sannhetskilde.</p>
<input id="q" placeholder="Søk etter oppskrift, kilde eller felt">{''.join(sections)}
<script>q.oninput=()=>document.querySelectorAll('article').forEach(r=>r.hidden=!r.innerText.toLowerCase().includes(q.value.toLowerCase()))</script></main></html>"""


def recovery_field_value(record, field):
    if field == "ingredienser":
        return {
            "ingredientsText": record.get("ingredientsText"),
            "structuredIngredients": record.get("structuredIngredients"),
        }
    return {
        "instructions": record.get("instructions"),
        "structuredInstructions": record.get("structuredInstructions"),
    }


def build_high_recovery_preview(rows, recovery):
    production = {str(row.get("id")): row_to_recipe(row) for row in rows}
    sources = collect_recovery_sources()
    previews = []
    for item in recovery["recipes"]:
        if item["recoveryProbability"] != "høy":
            continue
        current = production[str(item["id"])]
        candidate_groups = {}
        for source_name, candidate in sources:
            match_type = ""
            if str(candidate.get("id") or "") == str(item["id"]):
                match_type = "id"
            elif item.get("link") and str(candidate.get("link") or "").strip() == str(item["link"]).strip():
                match_type = "lenke"
            if not match_type:
                continue
            recoverable = {}
            for missing_field in item["missingFields"]:
                value = recovery_field_value(candidate, missing_field)
                if any(record_has(value, key) for key in value):
                    recoverable[missing_field] = value
            if not recoverable:
                continue
            fingerprint = hash_json(recoverable)
            group = candidate_groups.setdefault(fingerprint, {
                "recoverableFields": recoverable, "sources": [], "matchTypes": set(),
            })
            group["sources"].append(source_name)
            group["matchTypes"].add(match_type)
        groups = []
        for fingerprint, group in candidate_groups.items():
            groups.append({
                "fingerprint": fingerprint,
                "recoverableFields": group["recoverableFields"],
                "sources": sorted(set(group["sources"])),
                "matchTypes": sorted(group["matchTypes"]),
            })
        groups.sort(key=lambda group: (-len(group["sources"]), group["fingerprint"]))
        previews.append({
            "id": item["id"], "name": item["name"], "link": item.get("link"),
            "production": {
                "ingredientsText": current.get("ingredientsText"),
                "structuredIngredients": current.get("structuredIngredients"),
                "instructions": current.get("instructions"),
                "structuredInstructions": current.get("structuredInstructions"),
            },
            "missingFields": item["missingFields"], "candidateVersions": groups,
            "hasConflictingVersions": len(groups) > 1,
        })
    return previews


def high_recovery_html(previews):
    cards = []
    for recipe in previews:
        versions = []
        for index, version in enumerate(recipe["candidateVersions"], 1):
            fields = []
            for field, value in version["recoverableFields"].items():
                fields.append(f"<h4>{html.escape(field)}</h4><pre>{html.escape(json.dumps(value, ensure_ascii=False, indent=2))}</pre>")
            sources = "".join(f"<li><code>{html.escape(source)}</code></li>" for source in version["sources"])
            versions.append(f"""<div class="candidate"><h3>Historisk kandidat {index}</h3>
<p><b>Kan gjenopprette:</b> {html.escape(', '.join(version['recoverableFields']))}<br>
<b>Treff:</b> {html.escape(', '.join(version['matchTypes']))}<br><b>Identiske kilder:</b> {len(version['sources'])}</p>
{''.join(fields)}<details><summary>Vis alle kilder</summary><ul>{sources}</ul></details></div>""")
        current = html.escape(json.dumps(recipe["production"], ensure_ascii=False, indent=2))
        conflict = '<span class="warn">Flere ulike historiske versjoner – må velges manuelt</span>' if recipe["hasConflictingVersions"] else '<span class="ok">Én unik historisk versjon</span>'
        cards.append(f"""<article><header><div><h2>{html.escape(str(recipe['name']))}</h2><small>ID {html.escape(str(recipe['id']))}</small></div>{conflict}</header>
<p><b>Mangler i produksjon:</b> {html.escape(', '.join(recipe['missingFields']))} · <a href="{html.escape(str(recipe.get('link') or '#'))}">Original kilde</a></p>
<div class="compare"><div><h3>Produksjon nå</h3><pre>{current}</pre></div><div><h3>Mulige gjenopprettingsdata</h3>{''.join(versions)}</div></div></article>""")
    return f"""<!doctype html><html lang="no"><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>Recipe Recovery – høy sannsynlighet</title><style>
body{{font:15px system-ui;background:#f5f3ee;color:#263126;margin:0}}main{{max-width:1400px;margin:auto;padding:28px}}article{{background:white;border-radius:16px;padding:20px;margin:18px 0;box-shadow:0 4px 18px #0001}}header{{display:flex;justify-content:space-between;gap:16px;align-items:start}}
.compare{{display:grid;grid-template-columns:1fr 1fr;gap:16px}}pre{{white-space:pre-wrap;overflow-wrap:anywhere;background:#f2f4f0;padding:12px;border-radius:10px;max-height:440px;overflow:auto}}.candidate{{border:1px solid #d8ded4;padding:12px;border-radius:12px;margin-bottom:12px}}
.warn{{background:#fff0cd;color:#744b00;padding:6px 10px;border-radius:20px}}.ok{{background:#dff1df;color:#28552c;padding:6px 10px;border-radius:20px}}code{{word-break:break-all}}small{{color:#69736a}}a{{color:#356344}}@media(max-width:800px){{.compare{{grid-template-columns:1fr}}header{{display:block}}}}
</style><main><h1>Recipe Recovery – side-by-side preview</h1><p>{len(previews)} oppskrifter med høy gjenopprettingssannsynlighet. Dette er kun sammenligning; ingen data er skrevet tilbake.</p>{''.join(cards)}</main></html>"""


def build_url_reimport_plan(recovery):
    queue = []
    for recipe in recovery["recipes"]:
        if recipe["recoveryProbability"] != "lav":
            continue
        link = str(recipe.get("link") or "").strip()
        source_type = "Instagram" if "instagram" in link else "TikTok" if "tiktok" in link else "Nettside" if link else "Mangler URL"
        queue.append({
            "id": recipe["id"], "name": recipe["name"], "source": recipe.get("source"),
            "url": link, "sourceType": source_type, "missingFields": recipe["missingFields"],
            "workflow": [
                "Åpne original URL",
                "Hent caption/tekst eller velg skjermbilder",
                "Kjør automatisk OCR og AI-parser",
                "Kontroller markerte usikre felt i forhåndsvisningen",
                "Sammenlign med eksisterende metadata",
                "Lagre bare etter eksplisitt brukergodkjenning",
            ],
            "databaseWriteAllowed": False,
        })
    return queue


def url_reimport_html(queue):
    rows = "".join(f"""<tr><td>{html.escape(str(item['name']))}<small>ID {html.escape(str(item['id']))}</small></td>
<td>{html.escape(item['sourceType'])}</td><td>{html.escape(', '.join(item['missingFields']))}</td>
<td><a href="{html.escape(item['url'] or '#')}">{html.escape(item['url'] or 'Mangler URL')}</a></td><td>Venter på reimport</td></tr>""" for item in queue)
    return f"""<!doctype html><html lang="no"><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>Recipe Recovery – URL-reimportplan</title><style>body{{font:15px system-ui;background:#f5f3ee;color:#263126;margin:0}}main{{max-width:1200px;margin:auto;padding:28px}}.notice{{background:#fff0cd;padding:14px;border-radius:12px}}table{{width:100%;border-collapse:collapse;background:white}}th,td{{padding:10px;border-bottom:1px solid #e1e5df;text-align:left;vertical-align:top}}th{{background:#324b35;color:white}}small{{display:block;color:#69736a}}a{{color:#356344;word-break:break-all}}.table{{overflow:auto;border-radius:14px}}input{{width:100%;box-sizing:border-box;padding:12px;margin:18px 0}}</style>
<main><h1>Recipe Recovery – URL-basert reimport</h1><p class="notice">Ingen lokale kopier brukes til rekonstruksjon. Hver av de {len(queue)} oppskriftene skal gå gjennom original URL, automatisk OCR/AI og redigerbar forhåndsvisning. Lagring krever alltid et eksplisitt valg.</p>
<ol><li>Åpne original URL.</li><li>Hent caption eller velg skjermbilder.</li><li>OCR og AI-parser starter automatisk.</li><li>Kontroller usikre felt.</li><li>Lagre først etter godkjenning.</li></ol>
<input id="q" placeholder="Søk i reimportkøen"><div class="table"><table><thead><tr><th>Oppskrift</th><th>Kildetype</th><th>Mangler</th><th>Original URL</th><th>Status</th></tr></thead><tbody>{rows}</tbody></table></div>
<script>q.oninput=()=>document.querySelectorAll('tbody tr').forEach(r=>r.hidden=!r.innerText.toLowerCase().includes(q.value.toLowerCase()))</script></main></html>"""


def generate_recipe_recovery_project(rows, recovery, output):
    project = output / "Recipe Recovery"
    project.mkdir()
    high = build_high_recovery_preview(rows, recovery)
    queue = build_url_reimport_plan(recovery)
    (project / "high-confidence-side-by-side.json").write_text(json.dumps(high, ensure_ascii=False, indent=2), encoding="utf-8")
    (project / "high-confidence-side-by-side.html").write_text(high_recovery_html(high), encoding="utf-8")
    (project / "url-reimport-plan.json").write_text(json.dumps(queue, ensure_ascii=False, indent=2), encoding="utf-8")
    (project / "url-reimport-plan.html").write_text(url_reimport_html(queue), encoding="utf-8")
    readme = f"""# Recipe Recovery

- Høy sannsynlighet: {len(high)} side-by-side-sammenligninger
- Lav sannsynlighet: {len(queue)} oppskrifter i URL-basert reimportkø
- Produksjonsendringer fra dette prosjektet: ingen
- Historiske kilder brukes kun som sammenligningsgrunnlag.
- Reimport krever redigerbar forhåndsvisning og eksplisitt lagring.
"""
    (project / "README.md").write_text(readme, encoding="utf-8")
    return project, high, queue


def generate_review_tracks(rows, output):
    safe = build_safe_track(rows)
    rollback = {"createdAt": datetime.datetime.now().isoformat(), "appId": APP_ID, "recipes": [recipe["rollback"] for recipe in safe["recipes"]]}
    (output / "safe-normalization-diff.json").write_text(json.dumps(safe, ensure_ascii=False, indent=2), encoding="utf-8")
    (output / "safe-normalization-rollback.json").write_text(json.dumps(rollback, ensure_ascii=False, indent=2), encoding="utf-8")
    (output / "safe-normalization-preview.html").write_text(safe_track_html(safe), encoding="utf-8")
    (output / "safe-normalization-report.md").write_text(safe_track_markdown(safe), encoding="utf-8")
    (output / "safe-normalization-affected-recipes.json").write_text(json.dumps([{"id": recipe["id"], "name": recipe["name"]} for recipe in safe["recipes"]], ensure_ascii=False, indent=2), encoding="utf-8")
    recovery = build_recovery_track(rows)
    (output / "missing-recipes-recovery.json").write_text(json.dumps(recovery, ensure_ascii=False, indent=2), encoding="utf-8")
    (output / "missing-recipes-recovery-report.html").write_text(recovery_html(recovery), encoding="utf-8")
    generate_recipe_recovery_project(rows, recovery, output)
    return safe, recovery


def patch_recipe_fields(recipe_id, current_recipe, fields):
    updated = dict(current_recipe)
    updated.update(fields)
    query = urllib.parse.urlencode({"id": f"eq.{recipe_id}", "app_id": f"eq.{APP_ID}"})
    supabase_request("PATCH", "recipes", payload=recipe_to_row(updated), query=query, prefer="return=minimal")


def rollback_safe_changes(original_by_id, safe_recipes, applied_ids):
    for recipe in reversed(safe_recipes):
        recipe_id = str(recipe["id"])
        if recipe_id not in applied_ids:
            continue
        original = original_by_id[recipe_id]
        patch_recipe_fields(recipe["id"], original, recipe["rollback"]["fields"])


def verify_safe_application(before_rows, after_rows, safe):
    before = {str(row.get("id")): row_to_recipe(row) for row in before_rows}
    after = {str(row.get("id")): row_to_recipe(row) for row in after_rows}
    failures = []
    for change in safe["recipes"]:
        recipe_id = str(change["id"])
        expected = dict(before[recipe_id])
        expected.update(change["after"])
        if after.get(recipe_id) != expected:
            failures.append({"id": change["id"], "name": change["name"]})
    return {"verified": not failures, "checkedRecipes": len(safe["recipes"]), "failures": failures}


def execute_safe_track(rows, safe, approved_sha, output):
    safe_sha = hash_json(safe)
    if approved_sha != safe_sha:
        raise SystemExit(f"Avbrutt: godkjent Spor A-SHA samsvarer ikke. Dagens SHA er {safe_sha}.")
    original_by_id = {str(row.get("id")): row_to_recipe(row) for row in rows}
    applied = set()
    try:
        for recipe in safe["recipes"]:
            recipe_id = str(recipe["id"])
            patch_recipe_fields(recipe["id"], original_by_id[recipe_id], recipe["after"])
            applied.add(recipe_id)
    except Exception:
        rollback_safe_changes(original_by_id, safe["recipes"], applied)
        raise
    after_rows = fetch_rows()
    verification = verify_safe_application(rows, after_rows, safe)
    (output / "safe-normalization-application-verification.json").write_text(
        json.dumps(verification, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    if not verification["verified"]:
        rollback_safe_changes(original_by_id, safe["recipes"], applied)
        raise SystemExit("Etterkontroll feilet. Alle anvendte Spor A-endringer ble rullet tilbake.")
    return verification


def execute_rollback(rows, rollback_path, approved_sha):
    payload = json.loads(rollback_path.read_text(encoding="utf-8"))
    rollback_sha = hash_json(payload)
    if approved_sha != rollback_sha:
        raise SystemExit(f"Avbrutt: rollback-SHA samsvarer ikke. Dagens SHA er {rollback_sha}.")
    current = {str(row.get("id")): row_to_recipe(row) for row in rows}
    for item in payload.get("recipes", []):
        recipe_id = str(item["id"])
        if recipe_id not in current:
            raise SystemExit(f"Avbrutt: oppskrift {recipe_id} finnes ikke lenger.")
        patch_recipe_fields(item["id"], current[recipe_id], item["fields"])
    return len(payload.get("recipes", []))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Deaktivert gammel bred migrering")
    parser.add_argument("--apply-safe", action="store_true")
    parser.add_argument("--approved-safe-sha", default="")
    parser.add_argument("--rollback", type=pathlib.Path)
    parser.add_argument("--approved-rollback-sha", default="")
    args = parser.parse_args()
    if args.apply:
        raise SystemExit("Den brede --apply-modusen er deaktivert. Bruk kun --apply-safe med godkjent Spor A-SHA.")
    load_env()
    rows = fetch_rows()
    if args.rollback:
        count = execute_rollback(rows, args.rollback, args.approved_rollback_sha)
        print(f"Rollback fullført for {count} oppskrifter.")
        return
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
    safe_track, recovery_track = generate_review_tracks(json.loads(backup_path.read_text(encoding="utf-8")), output)
    recovery_counts = collections.Counter(recipe["recoveryProbability"] for recipe in recovery_track["recipes"])
    safe_approval_sha = hash_json(safe_track)
    summary = {
        **result["stats"], "approvalSha": approval_sha, "backupVerified": verification["verified"],
        "safeRecipes": len(safe_track["recipes"]), "safeEvents": len(safe_track["events"]),
        "safeChangeTypes": safe_track["totals"], "safeApprovalSha": safe_approval_sha,
        "rollbackSha": hash_json(json.loads((output / "safe-normalization-rollback.json").read_text(encoding="utf-8"))),
        "recovery": dict(recovery_counts), "output": str(output),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if not args.apply_safe:
        print("DRY RUN: Ingen databaseendringer eller SQL ble generert.")
        return
    application_verification = execute_safe_track(rows, safe_track, args.approved_safe_sha, output)
    print(f"Spor A fullført og verifisert for {application_verification['checkedRecipes']} oppskrifter. Backup: {backup_path}")


if __name__ == "__main__":
    main()
