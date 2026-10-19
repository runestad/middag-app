import unittest

from api.import_validation import validate_import
from api.ingredient_normalization import ingredient_category, normalize_structured_ingredient


class ImportValidationTests(unittest.TestCase):
    def ingredient(self, original, amount, unit, item):
        return {"original": original, "amount": amount, "unit": unit, "item": item}

    def test_actual_import_failures_with_verbatim_source(self):
        items = [self.ingredient("2 garlic cloves (minced)", "2", "stk", "hvitløk"),
                 self.ingredient("½ cup grated parmesan", "0.5", "dl", "parmesan"),
                 self.ingredient("1 tsp black pepper", "1", "ts", "sort paprika")]
        result, warnings = validate_import(items, "Ingredients: 2 garlic cloves (minced); ½ cup grated parmesan; 1 tsp black pepper")
        self.assertEqual([i["unit"] for i in result], ["fedd", "cup", "ts"])
        self.assertEqual(result[2]["item"], "sort pepper")
        self.assertEqual(warnings, [])
        self.assertEqual(items[0]["unit"], "stk")

    def test_old_translated_original_is_never_used_as_source(self):
        items = [self.ingredient("4,8 dl shaved parm", "2", "dl", "parmesan")]
        result, warnings = validate_import(items, "½ cup shaved parm")
        self.assertEqual(result, items)
        self.assertEqual(warnings[0]["field"], "ingredients.0")

    def test_garlic_heads_and_alternative_cloves_are_not_converted(self):
        for original in ("3 garlic & ginger blocks (or 10 garlic cloves)", "1 garlic head"):
            item = self.ingredient(original, "3" if original.startswith("3") else "1", "stk", "hvitløk")
            self.assertEqual(validate_import([item], original)[0], [item])

    def test_saved_manual_edits_do_not_use_the_import_repair(self):
        item = self.ingredient("2 garlic cloves", "3", "stk", "hvitløk")
        self.assertEqual(normalize_structured_ingredient(item)["unit"], "stk")

    def test_existing_correct_conversions_are_preserved(self):
        item = self.ingredient("1/2 cup water", "1.2", "dl", "vann")
        self.assertEqual(validate_import([item], item["original"])[0], [item])

    def test_compound_quantity_is_not_silently_reduced(self):
        item = self.ingredient("1/2 cup + 2 tbsp breadcrumbs", "0.5", "dl", "brødsmuler")
        result, warnings = validate_import([item], item["original"])
        self.assertEqual(result, [item])
        self.assertTrue(warnings)

    def test_conflicting_volume_is_flagged_without_guessing(self):
        item = self.ingredient("1/2 cup parmesan", "2", "dl", "parmesan")
        result, warnings = validate_import([item], item["original"])
        self.assertEqual(result, [item])
        self.assertTrue(warnings)

    def test_missing_quantities_are_flagged_not_invented(self):
        item = self.ingredient("broccoli", "null", None, "brokkoli")
        result, warnings = validate_import([item], "broccoli")
        self.assertEqual(result[0]["amount"], "")
        self.assertTrue(warnings)

    def test_prepared_products_and_spices_keep_their_categories(self):
        for name, expected in [("chiliolje", "Tørrvarer"), ("avokadooljespray", "Tørrvarer"),
                               ("malt koriander", "Krydder"), ("tørket ingefær", "Krydder"), ("soltørkede tomater", "Hermetikk/halvfabrikat"),
                               ("tørkede røde linser", "Tørrvarer"), ("fersk koriander", "Frukt og grønt")]:
            self.assertEqual(ingredient_category(name), expected, name)


if __name__ == "__main__":
    unittest.main()
