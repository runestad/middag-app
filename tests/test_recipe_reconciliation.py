import unittest

from scripts.reconcile_recipe_library import canonical_url, reconcile


class RecipeReconciliationTests(unittest.TestCase):
    def test_tracking_parameters_do_not_hide_same_content_url(self):
        self.assertEqual(canonical_url("https://instagram.com/reel/ABC/?igsh=x"), canonical_url("https://instagram.com/reel/ABC/"))

    def test_missing_historical_recipe_is_reported_without_creation(self):
        old = [{"name": "Historisk", "url": "https://example.com/r", "historicalRecipe": {}, "historicalSource": "user"}]
        rows = reconcile(old, [], [])
        self.assertEqual(rows[0]["category"], "Missing from MatplanApp")

    def test_better_historical_content_is_flagged_as_possible_loss(self):
        old = [{"name": "Min rett", "url": "https://example.com/r", "historicalRecipe": {"ingredientsText": "a\nb\nc", "instructions": "x\ny"}, "historicalSource": "user"}]
        current = [{"id": "1", "name": "Min rett", "link": "https://example.com/r", "ingredientsText": "a", "instructions": "x"}]
        row = reconcile(old, current, [])[0]
        self.assertIn("Current recipe missing data", row["categories"])
        self.assertEqual(row["currentName"], "Min rett")


if __name__ == "__main__": unittest.main()
