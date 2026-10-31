import copy
import math
import unittest

from api.nutrition_estimates import nutrition_fingerprint, valid_nutrition, with_nutrition_estimate


class NutritionEstimateTests(unittest.TestCase):
    def setUp(self):
        self.recipe = {"id": "test", "name": "Example", "servings": "2",
                       "structuredIngredients": [{"item": "havregryn", "amount": "100", "unit": "g"}],
                       "instructions": "Kok grøten.", "image": "/image.jpg"}
        self.values = {"calories": 200, "protein": 6, "fat": 4, "carbohydrates": 32, "fiber": 5}
        self.estimates = {"test": {"fingerprint": nutrition_fingerprint(self.recipe), "nutrition": self.values}}

    def test_fills_missing_without_mutating_recipe_or_unrelated_fields(self):
        before = copy.deepcopy(self.recipe)
        result = with_nutrition_estimate(self.recipe, self.estimates)
        self.assertEqual(result["nutrition"], self.values)
        self.assertEqual({k: result[k] for k in before}, before)
        self.assertEqual(self.recipe, before)

    def test_zero_placeholders_are_replaced_including_macros(self):
        self.recipe["nutrition"] = {k: 0 for k in self.values}
        result = with_nutrition_estimate(self.recipe, self.estimates)
        self.assertEqual(result["nutrition"], self.values)

    def test_preserves_existing_complete_nutrition(self):
        self.recipe["nutrition"] = {**self.values, "calories": 250}
        self.assertIs(with_nutrition_estimate(self.recipe, self.estimates), self.recipe)

    def test_preserves_real_values_when_filling_partial_nutrition(self):
        self.recipe["nutrition"] = {"calories": 220, "fiber": 0}
        result = with_nutrition_estimate(self.recipe, self.estimates)
        self.assertEqual(result["nutrition"]["calories"], 220)
        self.assertEqual(result["nutrition"]["fiber"], 0)
        self.assertEqual(result["nutrition"]["protein"], 6)

    def test_changed_ingredients_or_servings_reject_stale_estimate(self):
        for field, value in (("servings", "4"), ("structuredIngredients", [{"item": "ris", "amount": "200", "unit": "g"}])):
            changed = {**self.recipe, field: value}
            self.assertNotIn("nutrition", with_nutrition_estimate(changed, self.estimates))

    def test_renames_do_not_invalidate_estimate(self):
        self.assertEqual(with_nutrition_estimate({**self.recipe, "name": "New name"}, self.estimates)["nutrition"], self.values)

    def test_key_order_does_not_invalidate_estimate(self):
        changed = {**self.recipe, "structuredIngredients": [{"unit": "g", "amount": "100", "item": "havregryn"}]}
        self.assertEqual(nutrition_fingerprint(changed), nutrition_fingerprint(self.recipe))

    def test_missing_and_invalid_values_are_not_complete(self):
        for value in ({}, None, {k: 0 for k in self.values}, {**self.values, "calories": math.nan},
                      {**self.values, "protein": math.inf}, {**self.values, "fiber": -1},
                      {**self.values, "protein": True}):
            self.assertFalse(valid_nutrition(value))
        self.assertTrue(valid_nutrition({**self.values, "fiber": 0}))

    def test_text_ingredients_are_fingerprinted_when_structure_is_missing(self):
        one = {"ingredientsText": "100 g ris", "servings": 2}
        self.assertNotEqual(nutrition_fingerprint(one), nutrition_fingerprint({**one, "ingredientsText": "200 g ris"}))


if __name__ == "__main__":
    unittest.main()
