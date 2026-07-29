import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "analyze_metadata_backfill.py"
SPEC = importlib.util.spec_from_file_location("metadata_analysis", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class MetadataBackfillAnalysisTests(unittest.TestCase):
    def test_tool_contains_no_supabase_write_method(self):
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn('method="GET"', source)
        self.assertNotIn('method="PATCH"', source)
        self.assertNotIn('method="POST"', source)
        self.assertNotIn("update recipes", source.lower())
        self.assertNotIn("--apply", source)

    def test_existing_metadata_is_preserved(self):
        recipe = {
            "name": "Kyllinggryte",
            "baseServings": 4,
            "vegetarian": False,
            "structuredIngredients": [
                {"amount": "400", "unit": "g", "item": "kylling"},
                {"amount": "1", "unit": "stk", "item": "gul løk"},
                {"amount": "2", "unit": "dl", "item": "fløte"},
            ],
        }
        proposed, _, _ = MODULE.conservative_proposal(recipe)
        self.assertNotIn("vegetarian", proposed)
        self.assertEqual(recipe["vegetarian"], False)

    def test_missing_servings_is_group_c_and_not_guessed(self):
        rows = [{
            "id": "r1",
            "name": "Gryte",
            "data": {
                "name": "Gryte",
                "structuredIngredients": [
                    {"amount": "1", "unit": "stk", "item": "gul løk"},
                    {"amount": "2", "unit": "stk", "item": "gulrot"},
                    {"amount": "3", "unit": "dl", "item": "vann"},
                ],
            },
        }]
        result = MODULE.analyze(rows)
        self.assertEqual(result["stats"]["groups"]["C"], 1)
        self.assertNotIn("baseServings", result["changes"][0]["proposed"])

    def test_legacy_servings_is_safe_base_proposal(self):
        recipe = {
            "servings": "4",
            "structuredIngredients": [{"amount": "2", "unit": "stk", "item": "egg"}],
        }
        proposed, reasons, _ = MODULE.conservative_proposal(recipe)
        self.assertEqual(proposed["baseServings"], 4.0)
        self.assertIn("servings", reasons["baseServings"])

    def test_gluten_free_is_never_asserted_from_absence(self):
        recipe = {
            "baseServings": 2,
            "structuredIngredients": [{"amount": "2", "unit": "stk", "item": "egg"}],
        }
        proposed, _, _ = MODULE.conservative_proposal(recipe)
        self.assertEqual(proposed["glutenFree"], "uncertain")


if __name__ == "__main__":
    unittest.main()
