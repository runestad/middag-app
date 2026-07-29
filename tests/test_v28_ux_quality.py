import pathlib
import importlib.util
import unittest

from api.ingredient_normalization import ingredient_category


ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("api.parse_caption", ROOT / "api" / "parse-caption.py")
PARSE_CAPTION = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PARSE_CAPTION)
finalize_parsed_recipe = PARSE_CAPTION.finalize_parsed_recipe


class V28UxQualityTests(unittest.TestCase):
    def test_spice_heuristic_beats_bad_fallback(self):
        self.assertEqual(ingredient_category("paprikapulver", "Frukt og grønt"), "Krydder")
        self.assertEqual(ingredient_category("ukjent chilipulver", "Frukt og grønt"), "Krydder")

    def test_parser_keeps_field_uncertainty_and_nutrition(self):
        result = finalize_parsed_recipe({
            "ingredients": [],
            "instructions": ["Gjør dette"],
            "category": "Pasta",
            "nutrition": {"protein": "28.4", "calories": "oops", "fiber": -2},
            "prepMinutes": "25",
            "uncertainties": [{"field": "ingredients.0", "reason": "Utydelig OCR"}],
        })
        self.assertEqual(result["nutrition"]["protein"], 28.4)
        self.assertEqual(result["nutrition"]["calories"], 0)
        self.assertEqual(result["nutrition"]["fiber"], 0)
        self.assertEqual(result["prepMinutes"], 25)
        self.assertEqual(len(result["uncertainties"]), 1)

    def test_ui_has_shared_picker_pantry_and_editable_categories(self):
        html = (ROOT / "index.html").read_text(encoding="utf-8")
        js = (ROOT / "app.js").read_text(encoding="utf-8")
        self.assertIn('id="viewPantry"', html)
        self.assertIn('id="structuredIngredientPreview"', html)
        self.assertIn('id="shoppingCategoryDialog"', html)
        self.assertIn('renderRecipeResultsV28("picker")', js)
        self.assertIn("recoverRecipeFromUrlV28", js)
        self.assertIn("ingredientRegistryOverrides", js)

    def test_no_automatic_recovery_or_pantry_from_checkbox(self):
        js = (ROOT / "app.js").read_text(encoding="utf-8")
        v28 = js.split("/* ===== v28", 1)[1]
        self.assertNotIn('action:"restore"', v28)
        self.assertNotIn("toggleShoppingDoneV25=function", v28)

    def test_fetch_recipe_has_image_priority_sources(self):
        source = (ROOT / "api" / "fetch-recipe.py").read_text(encoding="utf-8")
        for marker in ("opengraph-image", "metadata-thumbnail", "video-thumbnail", "first-image"):
            self.assertIn(marker, source)


if __name__ == "__main__":
    unittest.main()
