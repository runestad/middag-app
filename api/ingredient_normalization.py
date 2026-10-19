import json
import os
import re
import unicodedata


CATALOG_PATH = os.path.join(os.path.dirname(__file__), "..", "ingredient-catalog.json")


def _key(value):
    text = unicodedata.normalize("NFKD", str(value or "").strip().lower())
    text = "".join(char for char in text if not unicodedata.combining(char))
    # Preparation/type words distinguish ingredients: fresh and dried basil,
    # tomatoes and canned tomatoes must never collide in the alias registry.
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

SPICE_WORDS = {
    "salt", "pepper", "paprikapulver", "oregano", "timian", "basilikum",
    "chiliflak", "chilipulver", "spisskummen", "kanel", "muskat",
    "garam masala", "karri", "kardemomme", "kajennepepper", "laurbærblad",
}
SPICE_SUFFIXES = ("pulver", "flak", "pepper", "krydder", "masala")


def normalize_ingredient_name(value):
    original = str(value or "").strip()
    lookup = _key(original)
    if lookup in ALIASES:
        return ALIASES[lookup]

    # An embedded alias is useful for categorization, never for replacement:
    # replacing "glutenfri pasta" with "pasta" destroys essential information.
    return original.lower()


def ingredient_category(name, fallback="Annet"):
    fallback = "Kjøtt og fisk" if fallback == "Kjøtt" else fallback
    canonical = normalize_ingredient_name(name)
    key = _key(canonical)
    if re.search(r"\b(glutenfri\w*|gluten.free)\b", key):
        return "Glutenfritt"
    if "proteinpulver" in key or "protein powder" in key:
        return "Tørrvarer"
    if key in ("bakepulver", "baking powder", "kakaopulver", "cocoa powder"):
        return "Bakevarer"
    # Match the prepared product before words naming its raw ingredients.
    if re.search(r"olje|\boil\b|oljespray|eddik|vinegar|soyasaus|soy sauce|hvitl[øo]kspasta|garlic paste|sennep|mustard|dijon|pesto|hoisin|tahini|majones|mayonnaise|worcestersaus|worcestershire", key):
        return "Tørrvarer"
    if re.search(r"kraft|buljong|\bstock\b|\bbroth\b|kokosmelk|coconut milk|solt[øo]rkede tomater|sun.?dried tomatoes|tomatpure|tomato paste", key):
        return "Hermetikk/halvfabrikat"
    if fallback == "Krydder" and re.search(r"\bpaprika\b", key):
        # Imported paprika can mean the spice; retain its explicit category.
        return "Krydder"
    if re.search(r"\b(vegansk|vegan|plantebasert)\b", key) and re.search(r"\b(yoghurt|yogurt|ost|cheese)\b", key):
        return "Kjølevarer"
    if key.startswith(("fersk ", "fresh ")) and any(herb in key for herb in ("basil", "persille", "parsley", "timian", "thyme", "koriander", "cilantro", "dill")):
        return "Frukt og grønt"
    if re.search(r"frossen|frosne|frozen|fryste", key):
        return "Frys"
    if re.search(r"hermetisk|canned|på boks|\b(oliven|kalamata|olives|kapers|capers)\b", key):
        return "Hermetikk/halvfabrikat"
    if re.search(r"\b(rødvin|hvitvin|vin|red wine|white wine|wine|øl|beer|juice|kaffe|coffee|te|tea|mineralvann)\b", key):
        return "Drikke"
    if canonical in CATEGORIES:
        return CATEGORIES[canonical]
    if key in SPICE_WORDS or re.match(r"(?:malt|t[øo]rke(?:t|de)|ground|dried)\s+(?:koriander|coriander|ingef[æa]r|ginger|basil(?:ikum)?|oregano|timian|thyme|rosmarin|rosemary|dill|persille|parsley|kanel|cinnamon|spisskummen|cumin|urter|herbs)\b", key) or any(key.endswith(suffix) for suffix in SPICE_SUFFIXES):
        return "Krydder"
    if re.search(r"scampi|reker|shrimp|prawn|laks|salmon|ørret|trout|torsk|tunfisk|tuna|sardiner|ansjos|blåskjell", key):
        return "Kjøtt og fisk"
    matches = [(len(alias), CATEGORIES[target]) for alias, target in ALIASES.items()
               if len(alias) >= 4 and re.search(rf"(^|\s){re.escape(alias)}($|\s)", key)]
    return max(matches)[1] if matches else (fallback if fallback in CATALOG["categories"] else "Annet")


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
