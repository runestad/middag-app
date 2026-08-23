import json
import pathlib
import subprocess
import unittest
from unittest.mock import patch

from api.data_merge import merge_preserving_existing_data
from api.recipe_import import safe_recipe_merge
from api import recipes as IMAGE_API

ROOT = pathlib.Path(__file__).resolve().parents[1]
class RecipeOwnershipAndImagesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.js = (ROOT / "app.js").read_text(encoding="utf-8")
        cls.html = (ROOT / "index.html").read_text(encoding="utf-8")

    def run_js_helpers(self, expression):
        start = self.js.index("function normalizeRecipeOwnershipV43")
        stop = self.js.index("async function persistRecipeFieldsV43")
        snippet = self.js[start:stop].replace("recipes.forEach(normalizeRecipeOwnershipV43);", "")
        snippet = snippet.replace("const mergeCustomDataBeforeV43=mergeCustomData;\nmergeCustomData=function(){mergeCustomDataBeforeV43();recipes.forEach(normalizeRecipeOwnershipV43)};\n", "")
        script = "function recipeCompletenessV35(r){return {complete:!!r.complete}};const recipes=[];" + snippet + f"\nconsole.log(JSON.stringify({expression}));"
        result = subprocess.run(["node", "-e", script], check=True, capture_output=True, text=True)
        return json.loads(result.stdout)

    def test_review_override_is_single_needs_help_source_of_truth(self):
        result = self.run_js_helpers("[recipeNeedsHelp({complete:false}),recipeNeedsHelp({complete:false,reviewOverride:'approved'}),recipeNeedsHelp({complete:true}),recipeNeedsHelp({complete:true,reviewOverride:'needs-help'})]")
        self.assertEqual(result, [True, False, False, True])

    def test_review_override_survives_serialization_and_recovery_merge(self):
        recipe = {"id": "7", "reviewOverride": "approved", "userImagePath": "app/7/a.webp", "ingredientsText": ""}
        self.assertEqual(json.loads(json.dumps(recipe))["reviewOverride"], "approved")
        recovered = safe_recipe_merge(recipe, {"ingredientsText": "1 løk", "image": "https://source/image.jpg"})
        self.assertEqual(recovered["reviewOverride"], "approved")
        self.assertEqual(recovered["userImagePath"], "app/7/a.webp")

    def test_user_owned_fields_survive_defensive_merge(self):
        current = {"reviewOverride": "approved", "userImagePath": "app/7/old.webp"}
        merged = merge_preserving_existing_data(current, {"image": "https://source/new.jpg"})
        self.assertEqual(merged["reviewOverride"], "approved")
        self.assertEqual(merged["userImagePath"], "app/7/old.webp")

    def test_image_priority_and_broken_image_fallback_contract(self):
        self.assertIn("function getRecipeDisplayImages(recipe)", self.js)
        priority = self.js[self.js.index("function getRecipeDisplayImages"):self.js.index("recipeImageV39=getRecipeDisplayImage")]
        self.assertLess(priority.index("userRecipeImageUrlV43"), priority.index("sourceRecipeImageV43"))
        self.assertLess(priority.index("sourceRecipeImageV43"), priority.index("recipeImageFallbackV41"))
        self.assertIn("advanceRecipeImageV43", self.js)

    def test_upload_replace_remove_and_rollback_contracts(self):
        upload = self.js[self.js.index("async function uploadRecipeImageV43"):self.js.index("async function removeRecipeImageV43")]
        self.assertLess(upload.index("persistRecipeFieldsV43"), upload.index("cleanupRecipeImageV43(recipe,oldPath)"))
        self.assertIn("if(newPath)await cleanupRecipeImageV43", upload)
        remove = self.js[self.js.index("async function removeRecipeImageV43"):]
        self.assertLess(remove.index("persistRecipeFieldsV43"), remove.index("cleanupRecipeImageV43(recipe,path)"))

    def test_legacy_and_accessible_editor_contract(self):
        normalized = self.run_js_helpers("normalizeRecipeOwnershipV43({id:'1'})")
        self.assertIsNone(normalized["reviewOverride"])
        self.assertIsNone(normalized["userImagePath"])
        self.assertIn('accept="image/*"', self.html)
        self.assertIn('role="status" aria-live="polite"', self.html)

    def test_storage_paths_do_not_depend_on_recipe_title(self):
        with patch.object(IMAGE_API, "APP_ID", "test-app"):
            self.assertTrue(IMAGE_API.valid_owned_image_path("test-app/recipe-7/random.webp", "recipe-7"))
            self.assertFalse(IMAGE_API.valid_owned_image_path("test-app/other/random.webp", "recipe-7"))
            self.assertNotIn("name", IMAGE_API.safe_storage_segment("Oppskrift med navn"))

    def test_delete_is_recipe_first_and_image_cleanup_best_effort(self):
        source = (ROOT / "api" / "delete-recipe.py").read_text(encoding="utf-8")
        self.assertLess(source.index('supabase_request(\n                "DELETE", "recipes"'), source.index('supabase_storage_request("DELETE"'))
        self.assertIn("cleanup_warning", source)


if __name__ == "__main__":
    unittest.main()
