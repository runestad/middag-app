#!/usr/bin/env python3
"""Read-only metadata backfill analysis for MatplanApp.

This tool only performs Supabase GET requests. It creates a verified local
backup and review artifacts, but contains no write, PATCH, POST, SQL or apply
mode.
"""

import argparse
import hashlib
import html
import json
import os
import re
import ssl
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


FIELDS = [
    "nutrition.protein", "nutrition.calories", "nutrition.fat",
    "nutrition.carbohydrates", "nutrition.fiber", "glutenFree",
    "vegetarian", "vegan", "highProtein", "under500Kcal", "mealType",
    "mainProtein", "prepTime", "cookTime", "totalTime", "freezerFriendly",
    "childFriendly", "baseServings",
]
GLUTEN_RISK = (
    "hvete", "bygg", "rug", "pasta", "nudler", "tortilla", "brød", "mel",
    "soyasaus", "buljong", "havre", "worcestershire", "miso", "seitan",
)
ANIMAL = (
    "kylling", "kjøtt", "biff", "svin", "kalkun", "fisk", "laks", "ørret",
    "reker", "scampi", "ansjos", "fiskesaus", "østerssaus", "gelatin",
)
NON_VEGAN = ANIMAL + (
    "egg", "melk", "fløte", "smør", "ost", "parmesan", "feta", "halloumi",
    "honning", "yoghurt", "rømme",
)
PROTEINS = [
    ("kylling", "Kylling"), ("biff", "Storfe"), ("kjøttdeig", "Kjøttdeig"),
    ("svin", "Svin"), ("laks", "Laks"), ("ørret", "Ørret"), ("reker", "Reker"),
    ("scampi", "Reker"), ("tofu", "Tofu"), ("kikerter", "Kikerter"),
    ("linser", "Linser"), ("bønner", "Bønner"), ("egg", "Egg"),
]


def load_env(path):
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


def ssl_context():
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


def fetch_recipes():
    base = os.environ["SUPABASE_URL"].rstrip("/")
    if base.endswith("/rest/v1"):
        base = base[:-8]
    key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    rows, offset, page_size = [], 0, 1000
    while True:
        query = urllib.parse.urlencode({
            "select": "*", "order": "name.asc", "limit": page_size,
            "offset": offset,
        })
        request = urllib.request.Request(
            f"{base}/rest/v1/recipes?{query}",
            headers={"apikey": key, "Authorization": f"Bearer {key}"},
            method="GET",
        )
        with urllib.request.urlopen(request, context=ssl_context(), timeout=60) as response:
            page = json.loads(response.read().decode("utf-8"))
        rows.extend(page)
        if len(page) < page_size:
            return rows
        offset += page_size


def data_for(row):
    data = row.get("data")
    merged = dict(data) if isinstance(data, dict) else {}
    for key in ("id", "name", "category", "source", "link", "status", "created_at", "updated_at"):
        if row.get(key) not in (None, ""):
            merged.setdefault(key, row[key])
    return merged


def present(value):
    return value not in (None, "", [], {})


def nutrition(recipe):
    value = recipe.get("nutrition") or recipe.get("nutritionEstimate") or {}
    return value if isinstance(value, dict) else {}


def field_value(recipe, field):
    if field.startswith("nutrition."):
        return nutrition(recipe).get(field.split(".", 1)[1])
    return recipe.get(field)


def positive(value):
    try:
        return float(str(value).replace(",", ".")) > 0
    except (TypeError, ValueError):
        return False


def ingredients(recipe):
    value = recipe.get("structuredIngredients")
    return value if isinstance(value, list) else []


def ingredient_text(recipe):
    parts = [str(recipe.get("ingredientsText") or "")]
    for item in ingredients(recipe):
        if isinstance(item, dict):
            parts.append(" ".join(str(item.get(key) or "") for key in ("amount", "unit", "item", "note")))
    return " ".join(parts).lower()


def amount_quality(recipe):
    structured = [item for item in ingredients(recipe) if isinstance(item, dict)]
    if not structured:
        return 0, 0, []
    numeric, ambiguous = 0, []
    for item in structured:
        amount = str(item.get("amount") or "").strip()
        if re.match(r"^\d+(?:[.,]\d+)?(?:\s*[–-]\s*\d+(?:[.,]\d+)?)?$", amount):
            numeric += 1
        elif amount:
            ambiguous.append(amount)
    return numeric, len(structured), ambiguous


def conservative_proposal(recipe):
    proposal, reasons, conflicts = {}, {}, []
    text = ingredient_text(recipe)
    tags = " ".join(str(tag).lower() for tag in (recipe.get("tags") or []))
    category = str(recipe.get("category") or "").lower()
    base = recipe.get("baseServings") if positive(recipe.get("baseServings")) else recipe.get("servings")
    if not present(recipe.get("baseServings")) and positive(base):
        proposal["baseServings"] = float(str(base).replace(",", "."))
        reasons["baseServings"] = "Eksisterende gyldig servings brukes som grunnporsjoner."

    values = nutrition(recipe)
    protein, calories = values.get("protein"), values.get("calories")
    if not present(recipe.get("highProtein")) and positive(protein) and positive(calories):
        protein_share = float(protein) * 4 / float(calories)
        proposal["highProtein"] = float(protein) >= 25 and protein_share >= 0.20
        reasons["highProtein"] = "Minst 25 g protein per porsjon og minst 20 % av energien fra protein."
    if not present(recipe.get("under500Kcal")) and positive(calories):
        proposal["under500Kcal"] = float(calories) < 500
        reasons["under500Kcal"] = "Avledet fra eksisterende kaloriestimat per porsjon."

    if not present(recipe.get("vegetarian")) and text:
        proposal["vegetarian"] = not any(term in text for term in ANIMAL)
        reasons["vegetarian"] = "Konservativ ingredienskontroll mot kjøtt, fisk og animalske sauser."
    if not present(recipe.get("vegan")) and text:
        proposal["vegan"] = not any(term in text for term in NON_VEGAN)
        reasons["vegan"] = "Konservativ ingredienskontroll mot animalske ingredienser."
    if not present(recipe.get("glutenFree")) and text:
        risky = [term for term in GLUTEN_RISK if term in text]
        proposal["glutenFree"] = "uncertain" if risky else "uncertain"
        reasons["glutenFree"] = (
            "Usikker: mulig glutenrisiko i " + ", ".join(risky[:6])
            if risky else "Usikker: fravær av åpenbar hvete er ikke tilstrekkelig ved cøliaki."
        )

    if not present(recipe.get("mainProtein")):
        matches = [label for term, label in PROTEINS if term in text]
        if len(set(matches)) == 1:
            proposal["mainProtein"] = matches[0]
            reasons["mainProtein"] = "Én tydelig proteinkilde i ingrediensene."
    if not present(recipe.get("mealType")):
        joined = f"{category} {tags} {str(recipe.get('name') or '').lower()}"
        meal = next((value for term, value in (
            ("frokost", "Frokost"), ("dessert", "Dessert"),
            ("snack", "Mellommåltid"), ("lunsj", "Lunsj"),
        ) if term in joined), "Middag")
        proposal["mealType"] = meal
        reasons["mealType"] = "Avledet fra eksisterende kategori, navn og tags."

    prep = recipe.get("prepMinutes")
    if not present(recipe.get("prepTime")) and positive(prep):
        proposal["prepTime"] = float(prep)
        reasons["prepTime"] = "Kopiert fra eksisterende prepMinutes."
    for field, tag in (("freezerFriendly", "frysevennlig"), ("childFriendly", "barnevennlig")):
        if not present(recipe.get(field)) and tag in tags:
            proposal[field] = True
            reasons[field] = f"Eksisterende tag «{tag}»."

    for key in list(proposal):
        if present(recipe.get(key)):
            conflicts.append(key)
            proposal.pop(key)
            reasons.pop(key, None)
    return proposal, reasons, conflicts


def analyze(rows):
    missing = Counter()
    groups = Counter()
    changes, rollback, manual = [], [], []
    enough, missing_ingredients, ambiguous_recipes, existing_metadata, partial_metadata = 0, 0, 0, 0, 0
    for row in rows:
        recipe = data_for(row)
        for field in FIELDS:
            if not present(field_value(recipe, field)):
                missing[field] += 1
        existing_count = sum(present(field_value(recipe, field)) for field in FIELDS)
        existing_metadata += int(existing_count > 0)
        partial_metadata += int(0 < existing_count < len(FIELDS))
        structured = ingredients(recipe)
        numeric, total, ambiguous = amount_quality(recipe)
        has_ingredients = bool(structured or str(recipe.get("ingredientsText") or "").strip())
        if not has_ingredients:
            missing_ingredients += 1
        if ambiguous:
            ambiguous_recipes += 1
        base = recipe.get("baseServings") or recipe.get("servings")
        sufficient = total >= 3 and numeric / max(total, 1) >= 0.60 and positive(base)
        enough += int(sufficient)
        proposal, reasons, conflicts = conservative_proposal(recipe) if has_ingredients else ({}, {}, [])
        if not has_ingredients or not positive(base):
            group = "C"
        elif sufficient and proposal and all(value != "uncertain" for value in proposal.values()):
            group = "A"
        elif proposal:
            group = "B"
        else:
            group = "C"
        groups[group] += 1
        entry = {
            "id": row.get("id"), "name": recipe.get("name"), "group": group,
            "baseServings": base or None, "ingredientCount": total,
            "numericIngredientCount": numeric, "ambiguousAmounts": ambiguous,
            "existing": {field: field_value(recipe, field) for field in FIELDS if present(field_value(recipe, field))},
            "proposed": proposal, "reasons": reasons, "conflicts": conflicts,
            "warnings": (
                ([] if has_ingredients else ["Mangler ingrediensdata"]) +
                ([] if positive(base) else ["Mangler grunnporsjoner"]) +
                (["Tvetydige mengder"] if ambiguous else []) +
                (["Ny næringsberegning krever konfigurert beregningskilde"] if not all(positive(nutrition(recipe).get(key)) for key in ("protein", "calories", "fat", "carbohydrates", "fiber")) else [])
            ),
        }
        if proposal:
            changes.append(entry)
            rollback.append({"id": row.get("id"), "fields": {key: recipe.get(key, None) for key in proposal}})
        if group != "A":
            manual.append(entry)
    return {
        "stats": {
            "totalRecipes": len(rows), "missingByField": dict(missing),
            "sufficientIngredientData": enough, "missingIngredients": missing_ingredients,
            "ambiguousAmounts": ambiguous_recipes, "recipesWithExistingMetadata": existing_metadata,
            "partialMetadata": partial_metadata, "cannotProcessSafely": groups["C"],
            "groups": dict(groups), "proposedRecipeChanges": len(changes),
            "proposedFieldChanges": sum(len(item["proposed"]) for item in changes),
        },
        "changes": changes, "rollback": rollback, "manual": manual,
    }


def render_report(result, output):
    stats = result["stats"]
    lines = [
        "# Metadata-backfill – skrivebeskyttet analyse", "",
        "Ingen produksjonsdata er endret. Ingen SQL er generert.", "",
        "## Sammendrag", "",
        f"- Oppskrifter analysert: **{stats['totalRecipes']}**",
        f"- Tilstrekkelig strukturert ingrediensgrunnlag: **{stats['sufficientIngredientData']}**",
        f"- Mangler ingrediensdata: **{stats['missingIngredients']}**",
        f"- Har tvetydige mengder: **{stats['ambiguousAmounts']}**",
        f"- Har eksisterende metadata som bevares: **{stats['recipesWithExistingMetadata']}**",
        f"- Delvis metadata: **{stats['partialMetadata']}**",
        f"- Gruppe A / B / C: **{stats['groups'].get('A',0)} / {stats['groups'].get('B',0)} / {stats['groups'].get('C',0)}**",
        f"- Kan ikke behandles trygt: **{stats['cannotProcessSafely']}**", "",
        "## Mangler per felt", "",
    ]
    lines += [f"- `{field}`: {count}" for field, count in stats["missingByField"].items()]
    lines += [
        "", "## Regler", "",
        "- Eksisterende ikke-tomme metadata bevares.",
        "- `baseServings` foreslås bare fra eksisterende gyldig `servings`.",
        "- Proteinrik betyr minst 25 g protein per porsjon og minst 20 % energi fra protein.",
        "- Glutenfri settes aldri sikkert fra fravær av hvete; tvilsomme produkter gir `uncertain`.",
        "- Næringsverdier presenteres som omtrentlige, ikke medisinsk presise.",
        "- Denne kjøringen manglet lokal OpenAI-nøkkel og utførte derfor ingen ny næringsberegning.",
    ]
    (output / "metadata-backfill-report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def render_preview(result, output):
    cards = []
    for item in result["changes"] + [x for x in result["manual"] if not x["proposed"]]:
        rows = []
        keys = sorted(set(item["existing"]) | set(item["proposed"]))
        for key in keys:
            rows.append(
                "<tr><th>{}</th><td>{}</td><td>{}</td></tr>".format(
                    html.escape(key),
                    html.escape(json.dumps(item["existing"].get(key), ensure_ascii=False)),
                    html.escape(json.dumps(item["proposed"].get(key), ensure_ascii=False)),
                )
            )
        warnings = "".join(f"<li>{html.escape(w)}</li>" for w in item["warnings"])
        cards.append(
            f'<article data-group="{item["group"]}" data-flags="{html.escape(" ".join(item["warnings"]).lower())}">'
            f'<header><span class="group group-{item["group"]}">Gruppe {item["group"]}</span>'
            f'<h2>{html.escape(str(item["name"] or "Uten navn"))}</h2></header>'
            f'<p>{item["ingredientCount"]} strukturerte ingredienser · baseServings: {html.escape(str(item["baseServings"] or "mangler"))}</p>'
            f'<ul>{warnings}</ul><table><thead><tr><th>Felt</th><th>Eksisterende</th><th>Forslag</th></tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table></article>'
        )
    document = """<!doctype html><html lang="no"><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>Metadata-backfill preview</title><style>
body{font:15px system-ui;background:#f3f5ef;color:#243126;margin:0}.wrap{max-width:1180px;margin:auto;padding:24px}
.filters{position:sticky;top:0;background:#f3f5ef;padding:12px 0;display:flex;gap:8px;flex-wrap:wrap}
button{padding:9px 13px;border:1px solid #ccd5c8;border-radius:999px;background:white}article{background:white;margin:14px 0;padding:18px;border-radius:18px;box-shadow:0 4px 18px #2332}
header{display:flex;align-items:center;gap:12px}.group{padding:5px 9px;border-radius:999px;font-weight:700}.group-A{background:#dff2df}.group-B{background:#fff1c9}.group-C{background:#f6d9d5}
table{border-collapse:collapse;width:100%;display:block;overflow:auto}th,td{text-align:left;padding:8px;border-bottom:1px solid #e7ebe3;vertical-align:top}
</style><div class="wrap"><h1>Metadata-backfill preview</h1><p>Kun forhåndsvisning. Ingen produksjonsdata er endret.</p>
<div class="filters"><button onclick="filterCards('')">Alle</button><button onclick="filterCards('A')">Høy</button><button onclick="filterCards('B')">Middels</button><button onclick="filterCards('C')">Lav / ikke skriv</button><button onclick="filterFlag('gluten')">Glutenfri usikker</button><button onclick="filterFlag('grunnporsjoner')">Mangler porsjoner</button><button onclick="filterFlag('ingrediensdata')">Mangler ingredienser</button><button onclick="filterFlag('konflikt')">Metadata-konflikt</button></div>
""" + "".join(cards) + """</div><script>
function filterCards(group){document.querySelectorAll('article').forEach(card=>card.hidden=group&&card.dataset.group!==group)}
function filterFlag(flag){document.querySelectorAll('article').forEach(card=>card.hidden=!card.dataset.flags.includes(flag))}
</script></html>"""
    (output / "metadata-backfill-preview.html").write_text(document, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    parser.add_argument("--env", type=Path, default=Path(".env"))
    args = parser.parse_args()
    load_env(args.env)
    if not os.environ.get("SUPABASE_URL") or not os.environ.get("SUPABASE_SERVICE_ROLE_KEY"):
        raise SystemExit("SUPABASE_URL og SUPABASE_SERVICE_ROLE_KEY må finnes i lokal .env")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = args.output or Path(".data-migrations") / f"metadata-backfill-{stamp}"
    output.mkdir(parents=True, exist_ok=False)
    rows = fetch_recipes()
    backup = output / "recipes-backup.json"
    backup.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    restored = json.loads(backup.read_text(encoding="utf-8"))
    digest = hashlib.sha256(backup.read_bytes()).hexdigest()
    verification = {
        "verified": restored == rows, "recipeCount": len(restored),
        "sha256": digest, "restorableFormat": isinstance(restored, list),
        "verifiedAt": datetime.now(timezone.utc).isoformat(),
    }
    (output / "backup-verification.json").write_text(json.dumps(verification, indent=2), encoding="utf-8")
    if not verification["verified"]:
        raise SystemExit("Backup-verifisering feilet; analysen stoppet.")
    result = analyze(restored)
    (output / "metadata-backfill-diff.json").write_text(json.dumps(result["changes"], ensure_ascii=False, indent=2), encoding="utf-8")
    (output / "metadata-backfill-rollback.json").write_text(json.dumps(result["rollback"], ensure_ascii=False, indent=2), encoding="utf-8")
    (output / "metadata-backfill-manual-review.json").write_text(json.dumps(result["manual"], ensure_ascii=False, indent=2), encoding="utf-8")
    render_report(result, output)
    render_preview(result, output)
    summary = {"output": str(output.resolve()), **result["stats"], "backup": verification}
    (output / "analysis-summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
