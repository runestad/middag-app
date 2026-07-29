import json
import importlib.util
import pathlib
import subprocess
import unittest
from unittest.mock import patch

from api.data_merge import has_meaningful_data_value, merge_preserving_existing_data
from api._common import row_to_recipe


ROOT = pathlib.Path(__file__).resolve().parents[1]
FETCH_PATH = ROOT / "api" / "fetch-recipe.py"
FETCH_SPEC = importlib.util.spec_from_file_location("api.fetch_recipe_safety", FETCH_PATH)
FETCH_MODULE = importlib.util.module_from_spec(FETCH_SPEC)
FETCH_SPEC.loader.exec_module(FETCH_MODULE)


class ServerMergeSafetyTests(unittest.TestCase):
    def test_blank_json_source_uses_preserved_top_level_database_source(self):
        recipe = row_to_recipe({
            "id": "42",
            "link": "https://example.com/original",
            "source": "Nettside",
            "data": {"id": "42", "link": " ", "source": ""},
        })
        self.assertEqual(recipe["link"], "https://example.com/original")
        self.assertEqual(recipe["source"], "Nettside")

    def test_blank_scalars_never_replace_existing_values(self):
        existing = {
            "link": "https://www.instagram.com/reel/example/",
            "source": "Instagram",
            "image": "https://images.example/recipe.jpg",
            "caption": "Behold caption",
        }
        for blank in (None, "", " ", "\n\t"):
            merged = merge_preserving_existing_data(existing, {
                "link": blank,
                "source": blank,
                "image": blank,
                "caption": blank,
            })
            self.assertEqual(merged, existing)

    def test_empty_collections_preserve_metadata_ocr_and_registry(self):
        existing = {
            "metadata": {"author": "Test", "thumbnail": "image.jpg"},
            "ocr": {"text": "1 gul løk", "confidence": 0.91},
            "ingredientRegistry": {"gul løk": {"category": "Frukt og grønt"}},
            "structuredIngredients": [{"item": "gul løk"}],
        }
        merged = merge_preserving_existing_data(existing, {
            "metadata": {},
            "ocr": {"text": "   ", "confidence": None},
            "ingredientRegistry": {},
            "structuredIngredients": [],
        })
        self.assertEqual(merged, existing)

    def test_nested_real_values_merge_without_losing_siblings(self):
        existing = {"metadata": {"author": "Test", "thumbnail": "old.jpg"}}
        merged = merge_preserving_existing_data(existing, {
            "metadata": {"thumbnail": "new.jpg", "author": " "}
        })
        self.assertEqual(merged["metadata"], {"author": "Test", "thumbnail": "new.jpg"})

    def test_zero_and_false_are_meaningful(self):
        self.assertTrue(has_meaningful_data_value(0))
        self.assertTrue(has_meaningful_data_value(False))
        self.assertEqual(
            merge_preserving_existing_data({"favorite": True, "uses": 4}, {"favorite": False, "uses": 0}),
            {"favorite": False, "uses": 0},
        )


class BrowserMergeSafetyTests(unittest.TestCase):
    def run_javascript(self, expression):
        script = (
            "const safety=require('./data-safety.js');"
            f"const result=({expression});"
            "process.stdout.write(JSON.stringify(result));"
        )
        output = subprocess.check_output(["node", "-e", script], cwd=ROOT, text=True)
        return json.loads(output)

    def test_browser_merge_preserves_all_relevant_recipe_fields(self):
        result = self.run_javascript(
            """safety.mergePreservingExistingData(
              {
                sourceUrl:'https://www.tiktok.com/@cook/video/1',
                image:'image.jpg',
                metadata:{author:'Cook',thumbnail:'thumb.jpg'},
                ocr:{text:'1 egg'},
                ingredientRegistry:{egg:{category:'Kjølevarer'}},
                aiPreview:{ingredients:[{item:'egg'}]}
              },
              {
                sourceUrl:' ', image:'', metadata:{author:null},
                ocr:{}, ingredientRegistry:{}, aiPreview:{ingredients:[]}
              }
            )"""
        )
        self.assertEqual(result["sourceUrl"], "https://www.tiktok.com/@cook/video/1")
        self.assertEqual(result["image"], "image.jpg")
        self.assertEqual(result["metadata"]["author"], "Cook")
        self.assertEqual(result["ocr"]["text"], "1 egg")
        self.assertEqual(result["ingredientRegistry"]["egg"]["category"], "Kjølevarer")
        self.assertEqual(result["aiPreview"]["ingredients"][0]["item"], "egg")

    def test_source_resolver_supports_instagram_tiktok_and_web_aliases(self):
        cases = self.run_javascript(
            """[
              safety.resolveRecipeSourceUrl({sourceUrl:' https://instagram.com/reel/one/ '}),
              safety.resolveRecipeSourceUrl({source_link:'https://vm.tiktok.com/abc/'}),
              safety.resolveRecipeSourceUrl({data:{source_url:'https://example.com/recipe'}}),
              safety.sourceTypeFromUrl('https://instagram.com/reel/one/'),
              safety.sourceTypeFromUrl('https://vm.tiktok.com/abc/'),
              safety.sourceTypeFromUrl('https://example.com/recipe'),
              safety.sourceTypeFromUrl('')
            ]"""
        )
        self.assertEqual(cases, [
            "https://instagram.com/reel/one/",
            "https://vm.tiktok.com/abc/",
            "https://example.com/recipe",
            "Instagram",
            "TikTok",
            "Nettside",
            "",
        ])

    def test_meaningful_patch_discards_blank_state(self):
        result = self.run_javascript(
            """safety.meaningfulPatch({
              link:' ', image:null, tags:[], metadata:{caption:'',author:'Chef'},
              favorite:false, servings:0
            })"""
        )
        self.assertEqual(result, {
            "metadata": {"author": "Chef"},
            "favorite": False,
            "servings": 0,
        })

    def test_generic_tiktok_redirect_never_replaces_original_source(self):
        result = self.run_javascript(
            """[
              safety.selectImportResolvedUrl(
                'https://vm.tiktok.com/ZM-original/',
                'https://www.tiktok.com/?_r=1'
              ),
              safety.selectImportResolvedUrl(
                'https://vm.tiktok.com/ZM-original/',
                'https://www.tiktok.com/@cook/video/751234567890'
              ),
              safety.selectImportResolvedUrl(
                'https://www.instagram.com/reel/ABC/',
                'https://www.instagram.com/?next=/reel/ABC/'
              ),
              safety.selectImportResolvedUrl(
                'https://example.com/old',
                'https://example.com/canonical'
              )
            ]"""
        )
        self.assertEqual(result, [
            "https://vm.tiktok.com/ZM-original/",
            "https://www.tiktok.com/@cook/video/751234567890",
            "https://www.instagram.com/reel/ABC/",
            "https://example.com/canonical",
        ])

    def test_cancelled_recovery_leaves_recipe_byte_for_byte_identical(self):
        result = self.run_javascript(
            """(() => {
              const recipe={
                id:'42',
                name:'TikTok recipe',
                link:'https://vm.tiktok.com/ZM-original/',
                source:'TikTok',
                metadata:{author:'Cook',nested:{value:1}},
                structuredIngredients:[{item:'egg',amount:'2'}]
              };
              const before=JSON.stringify(recipe);
              const recovery=safety.prepareRecoverySource(recipe);
              recovery.recipe.link=safety.selectImportResolvedUrl(
                recovery.sourceUrl,
                'https://www.tiktok.com/?_r=1'
              );
              return {
                unchanged:before===JSON.stringify(recipe),
                sameReference:recovery.recipe===recipe,
                sourceUrl:recovery.recipe.link
              };
            })()"""
        )
        self.assertEqual(result, {
            "unchanged": True,
            "sameReference": False,
            "sourceUrl": "https://vm.tiktok.com/ZM-original/",
        })


class FetchRecipeSourceSafetyTests(unittest.TestCase):
    def test_tiktok_oembed_redirect_is_not_exposed_as_recipe_source(self):
        original = "https://vm.tiktok.com/ZM-original/"
        payload = json.dumps({
            "title": "Test recipe",
            "thumbnail_url": "https://images.example/test.jpg",
        })
        with patch.object(
            FETCH_MODULE,
            "fetch_text",
            return_value=(payload, "application/json", "https://www.tiktok.com/?_r=1"),
        ):
            result = FETCH_MODULE.tiktok_oembed(original)
        self.assertEqual(result["resolvedUrl"], original)

    def test_social_redirect_requires_content_path(self):
        self.assertEqual(
            FETCH_MODULE.safe_resolved_source_url(
                "https://vm.tiktok.com/ZM-original/",
                "https://www.tiktok.com/?_r=1",
            ),
            "https://vm.tiktok.com/ZM-original/",
        )
        self.assertEqual(
            FETCH_MODULE.safe_resolved_source_url(
                "https://www.instagram.com/reel/ABC/",
                "https://www.instagram.com/",
            ),
            "https://www.instagram.com/reel/ABC/",
        )


class RecoveryRegressionContractTests(unittest.TestCase):
    def test_recovery_open_uses_immutable_resolved_source_without_writing(self):
        javascript = (ROOT / "app.js").read_text(encoding="utf-8")
        start = javascript.index("window.recoverRecipeFromUrlV28")
        end = javascript.index("\n};", start) + 3
        snippet = javascript[start:end]
        self.assertIn("prepareRecoverySource(recipeById(id))", snippet)
        self.assertIn("autoFetchRecipeUrlV27(sourceUrl,true)", snippet)
        self.assertNotIn("/api/save-recipe", snippet)
        self.assertNotIn("/api/recovery", snippet)

    def test_missing_source_has_informative_message_and_no_tiktok_default(self):
        javascript = (ROOT / "app.js").read_text(encoding="utf-8")
        self.assertIn(
            "Denne oppskriften har ingen lagret kilde-URL og kan derfor ikke gjenopprettes automatisk.",
            javascript,
        )
        safety = (ROOT / "data-safety.js").read_text(encoding="utf-8")
        self.assertIn('if (!value) return "";', safety)

    def test_recipe_save_endpoint_uses_defensive_merge(self):
        source = (ROOT / "api" / "save-recipe.py").read_text(encoding="utf-8")
        self.assertIn("merge_preserving_existing_data(current, patch)", source)
        self.assertNotIn("current.update(patch)", source)

    def test_data_safety_is_loaded_before_application(self):
        html = (ROOT / "index.html").read_text(encoding="utf-8")
        self.assertLess(html.index("data-safety.js"), html.index("app.js"))


if __name__ == "__main__":
    unittest.main()
