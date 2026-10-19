"""Validate new AI imports against their verbatim source, never saved user edits."""
import copy
import re
from fractions import Fraction


FRACTIONS = {"½": "1/2", "¼": "1/4", "¾": "3/4", "⅓": "1/3", "⅔": "2/3", "⅛": "1/8"}
NUMBER = r"(?:\d+\s+\d+/\d+|\d+/\d+|\d+(?:[.,]\d+)?)"
VOLUME = {"cup": 240, "cups": 240, "dl": 100, "ml": 1, "l": 1000,
          "ss": 15, "tbsp": 15, "tablespoon": 15, "tablespoons": 15,
          "ts": 5, "tsp": 5, "teaspoon": 5, "teaspoons": 5}


def comparable(text):
    text = str(text or "").lower()
    for symbol, fraction in FRACTIONS.items():
        text = text.replace(symbol, " " + fraction)
    return re.sub(r"\s+", " ", text).strip()


def quantity(text):
    text = comparable(text).replace(",", ".")
    if not re.fullmatch(NUMBER, text):
        return None
    try:
        return sum(Fraction(part) for part in text.split())
    except (ValueError, ZeroDivisionError):
        return None


def validate_import(ingredients, caption):
    result, warnings = copy.deepcopy(ingredients), []
    source = comparable(caption)
    for index, item in enumerate(result):
        if not isinstance(item, dict):
            continue
        for field in ("amount", "unit", "note"):
            if str(item.get(field) or "").lower().strip() in ("null", "undefined", "nan"):
                item[field] = ""
        original = comparable(item.get("original"))
        # A model-generated or previously translated 'original' is not evidence.
        verified = bool(original and original in source)
        reasons = []
        if not verified:
            reasons.append("Kildelinjen kunne ikke bekreftes ordrett. Kontroller mengde og enhet.")
        elif re.search(r"\d+/\d+,\d+", original):
            reasons.append("Kildelinjen inneholder en skadet brøk.")
        else:
            cup = re.match(r"^(" + NUMBER + r")\s+(?:packed\s+)?cups?\b", original)
            amount = quantity(item.get("amount"))
            compound = bool(re.search(r"\+\s*\d|\b(?:or|eller)\s+\d", original))
            if compound:
                reasons.append("Kilden har flere mengder eller alternativer. Kontroller at alle er med.")
            if cup and not compound and item.get("unit") == "dl" and amount == quantity(cup[1]):
                # Retain the source unit; display handles the conversion once.
                item["unit"] = "cup"
            measure = re.match(r"^(" + NUMBER + r")\s+(?:packed\s+)?(" + "|".join(sorted(VOLUME, key=len, reverse=True)) + r")\b", original)
            if measure and amount is not None and item.get("unit") in VOLUME and not compound:
                expected = float(quantity(measure[1])) * VOLUME[measure[2]]
                actual = float(amount) * VOLUME[item["unit"]]
                if abs(expected - actual) > max(.01, expected * .06):
                    reasons.append("Mengden stemmer ikke med kilden etter omregning.")
            primary = re.split(r"[,;(]", original)[0]
            clove = re.match(r"^(" + NUMBER + r")\s+.*(?:cloves?\b|fedd\b)", primary)
            garlic = re.search(r"\b(?:garlic|hvitløk|hvitløksfedd)\b", primary)
            if clove and garlic and item.get("item", "").lower() == "hvitløk" and item.get("unit") == "stk" and amount == quantity(clove[1]):
                item["unit"] = "fedd"
            if "black pepper" in original and re.fullmatch(r"(?:sort|svart|black) paprika", item.get("item", ""), re.I):
                item["item"] = "sort pepper"
                item["shoppingCategory"] = "Krydder"
            # Keep optional/to-taste quantities absent, but expose missing amounts.
            if not str(item.get("amount") or "").strip() and not re.search(r"to taste|etter smak|valgfritt|optional|garnish|pynt|servering", original):
                reasons.append("Mengde mangler i denne ingrediensen.")
        for reason in reasons:
            warnings.append({"field": f"ingredients.{index}", "reason": reason, "sourceText": item.get("original") or ""})
    return result, warnings
