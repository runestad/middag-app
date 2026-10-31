import math
import unittest

from api.nutrition_calculation import calculate_nutrition, serving_count


class NutritionCalculationTests(unittest.TestCase):
    def test_understands_stored_serving_labels_and_midpoint_of_ranges(self):
        for label, expected in [(4, 4), ("ca. 4", 4), ("2 store porsjoner", 2),
                                ("3 personer (6-8 tacos)", 3), ("10 skiver", 10),
                                ("ca. 3–4", 3.5), ("4-6", 5), ("1,5", 1.5)]:
            self.assertEqual(serving_count(label), expected)

    def test_rejects_missing_ambiguous_or_invalid_serving_counts(self):
        for value in (None, "", 0, -1, "nan", "inf", "etter behov", "250 g", "6-4", True):
            with self.assertRaises(ValueError):
                serving_count(value)

    def test_sums_whole_ingredient_amounts_then_divides_once(self):
        rows = [{"ingredientIndex": 1, "calories": 300, "protein": 10, "fat": 5, "carbohydrates": 50, "fiber": 5},
                {"ingredientIndex": 2, "calories": 100, "protein": 0, "fat": 10, "carbohydrates": 0, "fiber": 0}]
        self.assertEqual(calculate_nutrition(rows, 2, 4),
                         {"calories": 100, "protein": 2.5, "fat": 3.8, "carbohydrates": 12.5, "fiber": 1.2})

    def test_rejects_missing_duplicate_and_invalid_ingredient_results(self):
        row = {"ingredientIndex": 1, "calories": 300, "protein": 10, "fat": 5, "carbohydrates": 50, "fiber": 5}
        for rows, count in [([], 1), ([row, row], 2), ([{**row, "ingredientIndex": 3}], 1),
                            ([{**row, "protein": math.nan}], 1), ([{**row, "fat": -1}], 1),
                            ([{**row, "fiber": True}], 1), ([{**row, "calories": 0}], 1)]:
            with self.assertRaises(ValueError):
                calculate_nutrition(rows, count, 4)


if __name__ == "__main__":
    unittest.main()
