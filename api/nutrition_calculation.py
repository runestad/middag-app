"""Calculate serving nutrition from individually estimated ingredient totals."""
import math
import re

FIELDS = ("calories", "protein", "fat", "carbohydrates", "fiber")


def serving_count(value):
    """Use the midpoint for a stated range; never guess a missing yield."""
    label = str(value or "").strip().lower().replace(",", ".")
    match = re.fullmatch(
        r"(?:ca\.?\s*)?(\d+(?:\.\d+)?)(?:\s*[-–—]\s*(\d+(?:\.\d+)?))?"
        r"\s*(?:(?:store|små|stor|liten)\s+)?"
        r"(?:porsjon(?:er)?|person(?:er)?|skiver|stk\.?)?(?:\s*\([^)]*\))?", label)
    if not match:
        raise ValueError("Oppgi antall porsjoner for å beregne næring per porsjon.")
    low = float(match[1])
    high = float(match[2]) if match[2] else low
    if not 0 < low <= high <= 1000:
        raise ValueError("Ugyldig antall porsjoner.")
    return (low + high) / 2


def calculate_nutrition(rows, ingredient_count, portions):
    """Validate one row per input, then sum and divide in code, not in the model."""
    if not isinstance(rows, list) or len(rows) != ingredient_count or not ingredient_count:
        raise ValueError("Næringsberegningen mangler ingredienser. Prøv igjen.")
    seen = set()
    totals = dict.fromkeys(FIELDS, 0.0)
    for row in rows:
        index = row.get("ingredientIndex") if isinstance(row, dict) else None
        if type(index) is not int or not 1 <= index <= ingredient_count or index in seen:
            raise ValueError("Ufullstendig næringsberegning. Prøv igjen.")
        seen.add(index)
        for key in FIELDS:
            value = row.get(key)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                raise ValueError("Ugyldige næringsverdier. Prøv igjen.")
            totals[key] += value
    if totals["calories"] <= 0:
        raise ValueError("Beregningen ga ingen kalorier. Prøv igjen.")
    return {key: round(value / portions, 1) for key, value in totals.items()}
