import copy
import importlib.util
import pathlib
import unittest

from api.ingredient_normalization import (
    ingredient_category,
    normalize_ingredient_name,
    normalize_structured_ingredient,
    normalize_structured_ingredients,
)
PARSER_PATH = pathlib.Path(__file__).resolve().parents[1] / "api" / "parse-caption.py"
PARSER_SPEC = importlib.util.spec_from_file_location("api.parse_caption_endpoint", PARSER_PATH)
PARSER_MODULE = importlib.util.module_from_spec(PARSER_SPEC)
PARSER_SPEC.loader.exec_module(PARSER_MODULE)
finalize_parsed_recipe = PARSER_MODULE.finalize_parsed_recipe


class IngredientNormalizationTests(unittest.TestCase):
    def test_aliases_share_one_name_and_category(self):
        for alias in ["white onion", "hvit løk", "yellow onion", "løk"]:
            self.assertEqual(normalize_ingredient_name(alias), "gul løk")
            self.assertEqual(ingredient_category(alias), "Frukt og grønt")

    def test_known_category_overrides_bad_existing_category(self):
        ingredient = {"amount": "1", "unit": "stilk", "item": "celery", "shoppingCategory": "Krydder"}
        result = normalize_structured_ingredient(ingredient)
        self.assertEqual(result["item"], "stangselleri")
        self.assertEqual(result["shoppingCategory"], "Frukt og grønt")

    def test_only_name_and_category_change(self):
        ingredient = {"amount": "4,2", "unit": "dl", "item": "celery", "note": "hakket", "original": "4.2 cups celery", "shoppingCategory": "Krydder", "custom": 7}
        original = copy.deepcopy(ingredient)
        result = normalize_structured_ingredient(ingredient)
        for field in ["amount", "unit", "note", "original", "custom"]:
            self.assertEqual(result[field], original[field])

    def test_long_recipe_and_uncertainties_survive(self):
        parsed = {
            "category": "Vegetar",
            "ingredients": [{"amount": str(i), "unit": "g", "item": "carrots", "shoppingCategory": "Annet"} for i in range(30)],
            "instructions": [f"Steg {i}" for i in range(12)],
            "uncertainties": [{"field": "ingredients.4", "reason": "Utydelig tall", "sourceText": "5?"}],
        }
        result = finalize_parsed_recipe(parsed)
        self.assertEqual(len(result["ingredients"]), 30)
        self.assertEqual(len(result["instructions"]), 12)
        self.assertEqual(result["ingredients"][0]["item"], "gulrot")
        self.assertEqual(result["uncertainties"][0]["field"], "ingredients.4")

    def test_non_list_is_safe(self):
        self.assertEqual(normalize_structured_ingredients(None), [])


if __name__ == "__main__":
    unittest.main()
