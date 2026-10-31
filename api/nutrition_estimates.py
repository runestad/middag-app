"""Ingredient-bound nutrition estimates; never modify stored recipe content."""
import hashlib
import json
import math

FIELDS = ("calories", "protein", "fat", "carbohydrates", "fiber")


def valid_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0


def valid_nutrition(value):
    return isinstance(value, dict) and all(valid_number(value.get(key)) for key in FIELDS) and value["calories"] > 0


def nutrition_fingerprint(recipe):
    payload = {"ingredients": recipe.get("structuredIngredients") or recipe.get("ingredientsText") or "",
               "servings": str(recipe.get("servings") or "").strip()}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def with_nutrition_estimate(recipe, estimates=None):
    if valid_nutrition(recipe.get("nutrition")):
        return recipe
    if estimates is None:
        from .nutrition_estimates_data import ESTIMATES
        estimates = ESTIMATES
    entry = estimates.get(str(recipe.get("id")))
    if not entry or entry.get("fingerprint") != nutrition_fingerprint(recipe) or not valid_nutrition(entry.get("nutrition")):
        return recipe
    values = dict(entry["nutrition"])
    current = recipe.get("nutrition")
    # All-zero records are import placeholders, not measured zero values.
    if isinstance(current, dict) and any(valid_number(v) and v > 0 for v in current.values()):
        for key in FIELDS:
            value = current.get(key)
            if valid_number(value) and (key != "calories" or value > 0):
                values[key] = value
    return {**recipe, "nutrition": values, "nutritionEstimated": True}
