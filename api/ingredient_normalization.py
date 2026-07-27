import json
import os
import re
import unicodedata


CATALOG_PATH = os.path.join(os.path.dirname(__file__), "..", "ingredient-catalog.json")


def _key(value):
    text = unicodedata.normalize("NFKD", str(value or "").strip().lower())
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = re.sub(r"\([^)]*\)", "", text)
    text = re.sub(r"[,;].*$", "", text)
    text = re.sub(
        r"\b(fresh|freshly|dried|chopped|finely|thinly|sliced|diced|minced|"
        r"grated|large|medium|small|heaped|smooth|natural|drained|rinsed|"
        r"optional|to serve|fersk|torket|hakket|finhakket|skivet|revet|"
        r"stor|liten|valgfritt|til servering|i terninger)\b",
        " ",
        text,
    )
    return re.sub(r"\s+", " ", text).strip(" -")


def load_catalog():
    with open(CATALOG_PATH, encoding="utf-8") as handle:
        catalog = json.load(handle)
    aliases = {}
    categories = {}
    for ingredient in catalog["ingredients"]:
        name = ingredient["name"]
        category = ingredient["category"]
        categories[name] = category
        for alias in [name] + ingredient.get("aliases", []):
            aliases[_key(alias)] = name
    return catalog, aliases, categories


CATALOG, ALIASES, CATEGORIES = load_catalog()


def normalize_ingredient_name(value):
    original = str(value or "").strip()
    lookup = _key(original)
    if lookup in ALIASES:
        return ALIASES[lookup]

    # Prefer the longest whole alias embedded in a more descriptive name.
    matches = [
        (len(alias), canonical)
        for alias, canonical in ALIASES.items()
        if len(alias) >= 4 and re.search(rf"(^|\s){re.escape(alias)}($|\s)", lookup)
    ]
    if matches:
        return max(matches)[1]
    return original.lower()


def ingredient_category(name, fallback="Annet"):
    canonical = normalize_ingredient_name(name)
    return CATEGORIES.get(canonical, fallback if fallback in CATALOG["categories"] else "Annet")


def normalize_structured_ingredient(ingredient):
    if not isinstance(ingredient, dict):
        return ingredient
    normalized = dict(ingredient)
    normalized["item"] = normalize_ingredient_name(ingredient.get("item"))
    normalized["shoppingCategory"] = ingredient_category(
        normalized["item"], ingredient.get("shoppingCategory") or "Annet"
    )
    return normalized


def normalize_structured_ingredients(ingredients):
    if not isinstance(ingredients, list):
        return []
    return [normalize_structured_ingredient(item) for item in ingredients]
