import importlib.util
import pathlib
import unittest

from api.recipe_import import (assess_import_quality, choose_resolved_url,
                               normalize_source_url, safe_recipe_merge,
                               structured_recipe)


ROOT = pathlib.Path(__file__).resolve().parents[1]
FETCH_SPEC = importlib.util.spec_from_file_location("api.fetch_recipe_test", ROOT / "api" / "fetch-recipe.py")
FETCH = importlib.util.module_from_spec(FETCH_SPEC)
FETCH_SPEC.loader.exec_module(FETCH)


class ProductionHardeningTests(unittest.TestCase):
    def test_url_normalization_removes_tracking_but_keeps_identity(self):
        value = normalize_source_url("https://www.instagram.com/reel/ABC/?igsh=x&utm_source=y&foo=1")
        self.assertIn("/reel/ABC/", value)
        self.assertIn("foo=1", value)
        self.assertNotIn("igsh", value)
        self.assertNotIn("utm_source", value)

    def test_social_landing_redirect_is_rejected(self):
        original = "https://www.tiktok.com/@cook/video/123456"
        self.assertEqual(choose_resolved_url(original, "https://www.tiktok.com/?_r=1"), original)

    def test_structured_recipe_keeps_source_title_as_metadata(self):
        result = structured_recipe({"name": "Website title", "recipeIngredient": ["1 løk", "2 egg", "salt"], "recipeInstructions": ["Kutt.", "Stek."]}, "https://example.com/r", "https://example.com/r", "example.com")
        self.assertEqual(result["sourceTitle"], "Website title")
        self.assertNotIn("name", result)
        self.assertEqual(result["importQuality"]["status"], "COMPLETE")

    def test_existing_name_and_better_content_are_preserved(self):
        existing = {"name": "Pasta fredag", "ingredientLines": [str(i) for i in range(14)], "instructions": "Behold dette"}
        incoming = {"name": "Carbonara", "ingredientLines": ["a", "b", "c"], "instructions": ""}
        merged = safe_recipe_merge(existing, incoming)
        self.assertEqual(merged["name"], "Pasta fredag")
        self.assertEqual(len(merged["ingredientLines"]), 14)
        self.assertEqual(merged["instructions"], "Behold dette")

    def test_quality_rejects_page_dump(self):
        quality = assess_import_quality({"ingredientLines": ["1 løk"], "instructionSteps": ["x" * 1700]})
        self.assertEqual(quality["status"], "INCOMPLETE")
        self.assertIn("malformed_instructions", quality["issues"])

    def test_nextjs_escaped_recipe_json_ld_is_recognized(self):
        source = '<script>{\\"@context\\":\\"https://schema.org\\",\\"@type\\":\\"Recipe\\",\\"name\\":\\"Soup\\",\\"recipeIngredient\\":[\\"1 onion\\"]}</script>'
        recipes = FETCH.json_ld_recipes(source)
        self.assertEqual(recipes[0]["name"], "Soup")

    def test_redirect_handler_supports_308(self):
        self.assertTrue(callable(FETCH.PublicRedirectHandler.http_error_308))

    def test_tiktok_shortlink_is_resolved_before_oembed(self):
        original_fetch, original_oembed = FETCH.fetch_text, FETCH.tiktok_oembed
        calls = []
        try:
            FETCH.fetch_text = lambda url: ("", "text/html", "https://www.tiktok.com/@cook/video/123")
            FETCH.tiktok_oembed = lambda url: calls.append(url) or {"caption": "Full recipe"}
            result = FETCH.extract("https://vm.tiktok.com/ABC/")
        finally:
            FETCH.fetch_text, FETCH.tiktok_oembed = original_fetch, original_oembed
        self.assertEqual(calls, ["https://www.tiktok.com/@cook/video/123"])
        self.assertEqual(result["method"], "oembed-resolved-shortlink")

    def test_ui_has_focused_import_and_resumable_pantry(self):
        html = (ROOT / "index.html").read_text(encoding="utf-8")
        javascript = (ROOT / "app.js").read_text(encoding="utf-8")
        self.assertIn('id="newRecipeName"', html)
        self.assertIn('id="newRecipeUrl"', html)
        self.assertIn('id="pantrySetupDialog"', html)
        self.assertIn("appMeta.pantrySetupIndex", javascript)
        self.assertIn("$(\"importName\").value=name", javascript)


if __name__ == "__main__":
    unittest.main()
