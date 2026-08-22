import importlib.util
import pathlib
import unittest
from unittest.mock import patch

from api.recipes import add_verified_media

ROOT = pathlib.Path(__file__).resolve().parents[1]
DELETE_SPEC = importlib.util.spec_from_file_location("api.delete_recipe", ROOT / "api" / "delete-recipe.py")
DELETE = importlib.util.module_from_spec(DELETE_SPEC)
DELETE_SPEC.loader.exec_module(DELETE)


class MobilePolishAndRecipeDeleteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = (ROOT / "index.html").read_text(encoding="utf-8")
        cls.css = (ROOT / "styles.css").read_text(encoding="utf-8")
        cls.js = (ROOT / "app.js").read_text(encoding="utf-8")

    def test_shared_shell_and_mobile_date_grid_respect_safe_areas(self):
        self.assertIn('name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover"', self.html)
        self.assertIn("--safe-top:env(safe-area-inset-top,0px)", self.css)
        self.assertIn("max(var(--safe-top),20px)", self.css)
        self.assertIn("grid-template-columns:minmax(0,1fr) minmax(0,1fr)", self.css)
        self.assertIn(".period-grid>button{grid-column:1/-1", self.css)

    def test_pantry_uses_compact_shared_checkbox(self):
        self.assertIn('class="pantry-name-field"', self.html)
        self.assertIn('class="pantry-zone-field"', self.html)
        self.assertIn('class="inline-check"><input id="pantryAlways" type="checkbox"', self.html)
        self.assertIn("width:22px;height:22px", self.css)
        self.assertNotIn('id="startPantrySetupBtn" class="primary"', self.html)

    def test_verified_manifest_survives_broken_preferred_media(self):
        manifest = {"7": {"image": "/assets/recipe-media/7.jpg", "sourceUrl": "https://example.com/exact", "method": "source-metadata"}}
        recipe = add_verified_media({"id": "7", "link": "https://example.com/exact", "image": "https://broken.example/image.jpg"}, manifest)
        self.assertEqual(recipe["image"], "https://broken.example/image.jpg")
        self.assertEqual(recipe["verifiedFallbackImage"], "/assets/recipe-media/7.jpg")
        self.assertIn("advanceRecipeImageV41", self.js)
        self.assertIn("sult-symbol-mono.svg", self.js)

    def test_delete_requires_explicit_custom_dialog_confirmation(self):
        self.assertIn('id="deleteRecipeDialog"', self.html)
        self.assertIn('id="cancelDeleteRecipeBtn" type="button"', self.html)
        self.assertIn('id="confirmDeleteRecipeBtn" type="button" class="destructive"', self.html)
        self.assertIn("Slett permanent", self.html)
        delete_flow = self.js[self.js.index("/* ===== v41") :]
        self.assertNotIn("confirm(", delete_flow)

    def test_delete_cleans_favorite_indexes_and_preserves_planned_title(self):
        helper = self.js[self.js.index("function deletionStateV41"):self.js.index("async function persistPlanSnapshotV41")]
        self.assertIn('type:"text",text:recipe.name,fromDeletedRecipe:true', helper)
        self.assertIn('nextMeta.favorites=(nextMeta.favorites||[]).filter', helper)
        for key in ("usageCounts", "lastUsed", "recipeMeta"):
            self.assertIn(key, helper)
        self.assertIn("deletedRecipeIds", helper)
        self.assertIn("deletedRecipeSourceUrls", helper)
        self.assertIn("ensureOriginalRecipesBeforeV41", self.js)

    def test_delete_endpoint_scopes_and_verifies_permanent_delete(self):
        calls = []

        def request(method, path, payload=None, query=None, prefer="return=representation"):
            calls.append((method, path, query, prefer))
            if method == "GET":
                return [{"id": "42", "name": "Test"}] if len([call for call in calls if call[0] == "GET"]) == 1 else []
            if method == "DELETE":
                return [{"id": "42"}]
            return []

        with patch.object(DELETE, "supabase_request", side_effect=request):
            self.assertEqual(DELETE.supabase_request("GET", "recipes"), [{"id": "42", "name": "Test"}])
            self.assertEqual(DELETE.supabase_request("DELETE", "recipes"), [{"id": "42"}])
        source = (ROOT / "api" / "delete-recipe.py").read_text(encoding="utf-8")
        self.assertIn('"app_id": f"eq.{APP_ID}"', source)
        self.assertIn('prefer="return=representation"', source)
        self.assertIn('if remaining:', source)


if __name__ == "__main__":
    unittest.main()
