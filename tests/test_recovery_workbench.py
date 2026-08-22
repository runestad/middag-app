import importlib.util
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("api.recovery_workbench", ROOT / "api" / "recovery-audit.py")
MODULE = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(MODULE)


class RecoveryWorkbenchTests(unittest.TestCase):
    def test_only_incomplete_rows_are_work_items(self):
        rows = [
            {"id": "1", "name": "Done", "data": {"id": "1", "name": "Done", "ingredientsText": "a", "instructions": "cook"}},
            {"id": "2", "name": "Todo", "data": {"id": "2", "name": "Todo", "link": "https://example.com/r"}},
        ]
        items = MODULE.work_items(rows)
        self.assertEqual([item["id"] for item in items], ["2"])
        self.assertEqual(len(items[0]["expectedDigest"]), 64)

    def test_workbench_is_explicitly_read_only(self):
        rendered = MODULE.workbench_html([])
        self.assertIn("read-only", rendered)
        self.assertNotIn("/api/save-recipe", rendered)

    def test_recovery_patch_only_fills_empty_fields(self):
        current = {"name": "Keep", "link": "https://example.com/r", "ingredientsText": "", "instructions": ""}
        patch = {"ingredientsText": "1 løk\n2 gulrøtter", "instructions": "1. Kutt.\n2. Kok.", "recoveryProvenance": {"method": "source"}}
        merged = MODULE.validate_recovery_patch(current, patch)
        self.assertEqual(merged["name"], "Keep")
        with self.assertRaisesRegex(ValueError, "already contains"):
            MODULE.validate_recovery_patch({**current, "ingredientsText": "brukerdata"}, patch)


if __name__ == "__main__": unittest.main()
