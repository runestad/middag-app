import copy
import importlib.util
import pathlib
import unittest
from unittest.mock import patch

from api import recovery


ROOT = pathlib.Path(__file__).resolve().parents[1]
FETCH_PATH = ROOT / "api" / "fetch-recipe.py"
FETCH_SPEC = importlib.util.spec_from_file_location("api.fetch_recipe_endpoint", FETCH_PATH)
FETCH_MODULE = importlib.util.module_from_spec(FETCH_SPEC)
FETCH_SPEC.loader.exec_module(FETCH_MODULE)


class RecoverySystemTests(unittest.TestCase):
    def setUp(self):
        self.row = {
            "id": "42",
            "name": "Test",
            "data": {"id": "42", "name": "Test", "ingredientsText": "", "instructions": "Behold dette."},
            "updated_at": "2026-07-27T10:00:00+00:00",
        }
        self.candidate = {
            "id": "42",
            "candidateFingerprint": "abc",
            "sources": ["historisk/recipes.json"],
            "candidate": {"ingredienser": {"ingredientsText": "1 stk gul løk"}},
        }

    def test_preview_only_includes_requested_missing_field(self):
        with patch.object(recovery, "get_recipe_row", return_value=copy.deepcopy(self.row)), \
             patch.object(recovery, "candidate_for", return_value=copy.deepcopy(self.candidate)):
            preview = recovery.build_preview("42", ["ingredientsText"])
        self.assertEqual([item["field"] for item in preview["fields"]], ["ingredientsText"])
        self.assertTrue(preview["fields"][0]["wasMissing"])
        self.assertTrue(preview["previewToken"])

    def test_non_empty_field_is_never_overwritten_implicitly(self):
        candidate = copy.deepcopy(self.candidate)
        candidate["candidate"]["instructions"] = "Historisk tekst"
        with patch.object(recovery, "get_recipe_row", return_value=copy.deepcopy(self.row)), \
             patch.object(recovery, "candidate_for", return_value=candidate):
            with self.assertRaisesRegex(ValueError, "allerede innhold"):
                recovery.build_preview("42", ["instructions"])

    def test_manifest_has_reviewed_queue_counts(self):
        manifest = recovery.load_manifest()
        self.assertEqual(manifest["counts"], {
            "total": 187, "high": 21, "medium": 1, "url": 159, "manual": 6,
        })

    def test_ui_requires_explicit_confirm(self):
        html = (ROOT / "index.html").read_text(encoding="utf-8")
        javascript = (ROOT / "app.js").read_text(encoding="utf-8")
        self.assertIn('id="recoveryConfirmBtn"', html)
        self.assertIn("Confirm Restore", html)
        self.assertIn('action:"preview"', javascript)
        self.assertIn('action:"confirm"', javascript)

    def test_url_queue_reuses_existing_import_dialog(self):
        javascript = (ROOT / "app.js").read_text(encoding="utf-8")
        start = javascript.index("window.startRecoveryImportV27")
        end = javascript.index("\n};", start) + 3
        snippet = javascript[start:end]
        self.assertIn("openImport(item.id)", snippet)
        self.assertIn("autoFetchRecipeUrlV27", snippet)

    def test_private_urls_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "Private"):
            FETCH_MODULE.validate_public_url("http://127.0.0.1/private")

    def test_json_ld_recipe_becomes_parser_input(self):
        html = """
        <script type="application/ld+json">
        {"@type":"Recipe","name":"Suppe","recipeIngredient":["1 gul løk"],
         "recipeInstructions":[{"@type":"HowToStep","text":"Kok opp."}]}
        </script>
        """
        recipes = FETCH_MODULE.json_ld_recipes(html)
        self.assertEqual(recipes[0]["name"], "Suppe")
        parser_input = FETCH_MODULE.recipe_text(recipes[0])
        self.assertIn("1 gul løk", parser_input)
        self.assertIn("Kok opp.", parser_input)

    def test_tiktok_shortlink_thumbnail_keeps_original_source(self):
        original = "https://vm.tiktok.com/ABC123/"
        canonical = "https://www.tiktok.com/@cook/video/123456"
        with patch.object(FETCH_MODULE, "tiktok_oembed", return_value={"image": "https://cdn.example/exact.jpg", "resolvedUrl": canonical}) as oembed, \
             patch.object(FETCH_MODULE, "fetch_text", return_value=("<html></html>", "text/html", canonical)):
            result = FETCH_MODULE.extract(original)
        oembed.assert_called_once_with(canonical)
        self.assertEqual(result["image"], "https://cdn.example/exact.jpg")
        self.assertEqual(result["resolvedUrl"], canonical)
        self.assertEqual(result["method"], "oembed-resolved-shortlink")

    def test_recovered_high_items_are_removed_from_queue(self):
        javascript = (ROOT / "app.js").read_text(encoding="utf-8")
        self.assertIn("function highQueueV27()", javascript)
        self.assertIn('status !== "recovered"', javascript)

    def test_cancelled_import_clears_recovery_context(self):
        javascript = (ROOT / "app.js").read_text(encoding="utf-8")
        self.assertIn('$("importDialog")?.addEventListener("close"', javascript)
        self.assertIn("if (recoverySaveInProgressV27) return", javascript)

    def test_pending_audit_backup_can_be_validated_for_rollback(self):
        history = {
            "entries": [{
                "id": "history-1",
                "recipeId": "42",
                "recipeName": "Test",
                "status": "pending",
                "rollbackAvailable": False,
                "rolledBackAt": None,
                "fields": [{
                    "field": "ingredientsText",
                    "before": "",
                    "after": "1 stk gul løk",
                }],
            }],
        }
        restored_row = copy.deepcopy(self.row)
        restored_row["data"]["ingredientsText"] = "1 stk gul løk"
        with patch.object(recovery, "get_state", return_value=history), \
             patch.object(recovery, "get_recipe_row", return_value=restored_row):
            preview = recovery.build_rollback_preview("history-1")
        self.assertEqual(preview["fields"][0]["after"], "")

    def test_pending_audit_backup_rejects_unapplied_restore(self):
        history = {
            "entries": [{
                "id": "history-1",
                "recipeId": "42",
                "recipeName": "Test",
                "status": "pending",
                "rollbackAvailable": False,
                "rolledBackAt": None,
                "fields": [{
                    "field": "ingredientsText",
                    "before": "",
                    "after": "1 stk gul løk",
                }],
            }],
        }
        with patch.object(recovery, "get_state", return_value=history), \
             patch.object(recovery, "get_recipe_row", return_value=copy.deepcopy(self.row)):
            with self.assertRaisesRegex(ValueError, "endret etter gjenopprettingen"):
                recovery.build_rollback_preview("history-1")


if __name__ == "__main__":
    unittest.main()
