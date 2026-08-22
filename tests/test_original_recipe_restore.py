import importlib.util
import json
import pathlib
import unittest
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("api.ensure_original_recipes", ROOT / "api" / "ensure-original-recipes.py")
MODULE = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(MODULE)


class OriginalRecipeRestoreTests(unittest.TestCase):
    def test_fixture_contains_both_missing_original_recipes(self):
        recipes = json.loads((ROOT / "recipes.json").read_text(encoding="utf-8"))
        names = {recipe["name"] for recipe in recipes}
        self.assertIn("Spicy cucumber side dish", names)
        self.assertIn("Thai red curry udon noodle soup", names)
        self.assertEqual(len(recipes), 230)

    def test_restore_is_idempotent_and_never_updates_existing_recipe(self):
        calls = []
        def request(method, path, payload=None, query=None, prefer=None):
            calls.append((method, payload))
            return [{"id": "existing", "name": "User name"}] if method == "GET" else None
        with patch.object(MODULE, "supabase_request", side_effect=request):
            result = MODULE.ensure_missing_original_recipes()
        self.assertEqual(result["created"], [])
        self.assertFalse(any(method in ("PATCH", "POST") for method, _ in calls))

    def test_restore_inserts_exact_names_without_extraction_titles(self):
        calls = []
        def request(method, path, payload=None, query=None, prefer=None):
            calls.append((method, payload)); return [] if method == "GET" else None
        with patch.object(MODULE, "supabase_request", side_effect=request):
            result = MODULE.ensure_missing_original_recipes()
        self.assertEqual([row["name"] for row in result["created"]], ["Spicy cucumber side dish", "Thai red curry udon noodle soup"])
        inserted = [payload for method, payload in calls if method == "POST"]
        self.assertEqual([row["name"] for row in inserted], ["Spicy cucumber side dish", "Thai red curry udon noodle soup"])


if __name__ == "__main__": unittest.main()
