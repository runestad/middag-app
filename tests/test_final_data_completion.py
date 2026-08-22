import pathlib
import unittest

from api.recipe_health import classify_source, stored_completeness
from api.recipe_import import safe_recipe_merge

ROOT = pathlib.Path(__file__).resolve().parents[1]


class FinalDataCompletionTests(unittest.TestCase):
    def test_completeness_is_independent_from_source(self):
        recipe = {"ingredientsText": "kylling\nsriracha\nmajones", "instructions": "Bland sausen.\nStek kyllingen.", "link": "https://www.tiktok.com/@x/video/123"}
        self.assertEqual(stored_completeness(recipe)["status"], "COMPLETE")
        self.assertEqual(classify_source(recipe["link"]), "TIKTOK_VIDEO")

    def test_source_types_are_specific(self):
        self.assertEqual(classify_source("https://www.instagram.com/reel/ABC/"), "INSTAGRAM_REEL")
        self.assertEqual(classify_source("https://www.instagram.com/p/ABC/"), "INSTAGRAM_POST")
        self.assertEqual(classify_source("notaurl"), "MALFORMED_URL")

    def test_safe_merge_never_renames_or_replaces_good_content(self):
        before = {"name": "Mitt navn", "ingredientsText": "a\nb\nc", "instructions": "Gjør dette.\nSå dette."}
        after = safe_recipe_merge(before, {"name": "Kildens navn", "ingredientsText": "a", "instructions": ""})
        self.assertEqual(after, before)

    def test_review_queue_uses_stored_content_and_plain_language(self):
        html = (ROOT / "index.html").read_text(encoding="utf-8")
        js = (ROOT / "app.js").read_text(encoding="utf-8")
        self.assertIn("Oppskrifter som trenger hjelp", html)
        self.assertIn("recipeCompletenessV35", js)
        self.assertIn("Prøv igjen", js)
        self.assertIn("Åpne kilde", js)


if __name__ == "__main__": unittest.main()
