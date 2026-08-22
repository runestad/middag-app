import importlib.util
import json
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("api.recovery_audit", ROOT / "api" / "recovery-audit.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class RecoveryAuditEndpointTests(unittest.TestCase):
    def test_exact_missing_breakdown_and_initial_groups(self):
        audit = MODULE.build_audit([
            {"id": "1", "name": "Complete", "ingredientsText": "a\nb\nc", "instructions": "Do this.\nThen that."},
            {"id": "2", "name": "Website", "link": "https://example.com/r", "ingredientsText": "", "instructions": "Cook."},
            {"id": "3", "name": "Social", "link": "https://www.instagram.com/reel/ABC/", "ingredientsText": "salt", "instructions": ""},
            {"id": "4", "name": "No source", "ingredientsText": "", "instructions": ""},
        ])
        self.assertEqual(audit["totalRecipes"], 4)
        self.assertEqual(audit["incompleteRecipes"], 3)
        self.assertEqual(audit["missingIngredients"], 2)
        self.assertEqual(audit["missingInstructions"], 2)
        self.assertEqual(audit["missingBoth"], 1)
        self.assertEqual(audit["initialGroups"], {"A": 1, "B": 1, "C": 0, "D": 1, "E": 0})

    def test_html_embeds_machine_readable_audit(self):
        audit = MODULE.build_audit([{"id": "x", "name": "Try </script>", "ingredientsText": "", "instructions": ""}])
        rendered = MODULE.audit_html(audit)
        self.assertIn('id="recipe-audit-data"', rendered)
        self.assertNotIn("</script>\"", rendered)
        embedded = rendered.split('type="application/json">', 1)[1].split("</script>", 1)[0]
        self.assertEqual(json.loads(embedded)["items"][0]["title"], "Try </script>")


if __name__ == "__main__":
    unittest.main()
