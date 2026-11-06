import unittest
from unittest.mock import patch
from api import plan


class ShoppingSaveRecoveryTests(unittest.TestCase):
    def test_shopping_save_preserves_other_domains(self):
        stored = {"updatedAt": "before", "items": {"day": ["partner's dinner"]},
                  "meta": {"pantry": ["rice"], "favorites": ["recipe"]},
                  "freezerItems": [{"id": "fish"}], "futureField": {"preserve": True},
                  "shoppingItems": [{"id": "a", "text": "Milk", "updatedAt": "1"}]}
        incoming = {"updatedAt": "after", "shoppingItems": [{"id": "b", "updatedAt": "2"}],
                    "items": {}, "meta": {}, "freezerItems": []}
        with patch.object(plan, "supabase_request", side_effect=[[{"data": stored}], [{"key": "test"}]]):
            result = plan._persist_plan_with_retry("test", incoming, shopping_only=True)
        for field in ("items", "meta", "freezerItems", "futureField"):
            self.assertEqual(result[field], stored[field])
        self.assertEqual({item["id"] for item in result["shoppingItems"]}, {"a", "b"})
        self.assertEqual(result["updatedAt"], "after")

    def test_conflict_retry_rebases_on_latest_nonshopping_data(self):
        first = {"updatedAt": "v1", "items": {"day": ["old dinner"]},
                 "shoppingItems": [{"id": "a", "updatedAt": "1"}]}
        newer = {"updatedAt": "v2", "items": {"day": ["new dinner"]},
                 "meta": {"pantry": ["new rice"]},
                 "shoppingItems": [{"id": "b", "updatedAt": "2"}]}
        incoming = {"updatedAt": "v3", "shoppingItems": [{"id": "c", "updatedAt": "3"}]}
        with patch.object(plan, "supabase_request", side_effect=[
                [{"data": first}], [], [{"data": newer}], [{"key": "test"}]]):
            result = plan._persist_plan_with_retry("test", incoming, shopping_only=True)
        self.assertEqual(result["items"], newer["items"])
        self.assertEqual(result["meta"], newer["meta"])
        self.assertEqual({item["id"] for item in result["shoppingItems"]}, {"a", "b", "c"})

    def test_retry_after_lost_acknowledgement_does_not_duplicate_or_resurrect(self):
        stored = {"updatedAt": "v2", "shoppingItems": [
            {"id": "a", "text": "Milk", "updatedAt": "2"},
            {"id": "b", "deleted": True, "updatedAt": "3"}]}
        incoming = {"updatedAt": "v1", "shoppingItems": [
            {"id": "a", "text": "Milk", "updatedAt": "2"},
            {"id": "b", "deleted": False, "updatedAt": "1"}]}
        with patch.object(plan, "supabase_request", side_effect=[[{"data": stored}], [{"key": "test"}]]):
            result = plan._persist_plan_with_retry("test", incoming, shopping_only=True)
        self.assertEqual(result["shoppingItems"], stored["shoppingItems"])


if __name__ == "__main__":
    unittest.main()
