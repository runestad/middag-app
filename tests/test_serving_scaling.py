import json
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run_node(expression):
    script = f"""
const S = require({json.dumps(str(ROOT / "serving-scaling.js"))});
const result = (() => {{ {expression} }})();
process.stdout.write(JSON.stringify(result));
"""
    completed = subprocess.run(
        ["node", "-e", script], check=True, capture_output=True, text=True
    )
    return json.loads(completed.stdout)


class ServingScalingTests(unittest.TestCase):
    def test_scales_four_to_eight_without_mutating_recipe(self):
        result = run_node("""
const recipe = {id: 1, baseServings: 4, structuredIngredients: [
  {amount: "400", unit: "g", item: "kylling", shoppingCategory: "Kjøtt"}
]};
const before = JSON.stringify(recipe);
const scaled = S.scaledStructuredIngredients(recipe, 8);
return {amount: scaled[0].amount, unchanged: JSON.stringify(recipe) === before};
""")
        self.assertEqual(result, {"amount": "800", "unchanged": True})

    def test_scales_four_to_two(self):
        self.assertEqual(
            run_node('return S.scaleAmountText("400", 0.5);'),
            "200",
        )

    def test_human_friendly_decimals_and_fractions(self):
        self.assertEqual(run_node('return S.formatScaledAmount(2.5);'), "2,5")
        self.assertEqual(run_node('return S.formatScaledAmount(0.5);'), "½")
        self.assertEqual(run_node('return S.formatScaledAmount(1/3);'), "⅓")

    def test_ranges_scale_both_ends(self):
        self.assertEqual(run_node('return S.scaleAmountText("2–3", 2);'), "4–6")

    def test_unstructured_amounts_are_unchanged(self):
        for text in ("etter smak", "en neve", "litt", "til servering", "valgfritt"):
            self.assertEqual(
                run_node(f"return S.scaleAmountText({json.dumps(text)}, 2);"),
                text,
            )

    def test_missing_base_servings_is_not_guessed(self):
        result = run_node("""
const recipe = {id: 7, structuredIngredients: [{amount: "2", item: "egg"}]};
return {
  base: S.recipeBaseServings(recipe),
  factor: S.scaleFactorFor(recipe, 8),
  planned: S.makePlannedRecipeItem(recipe, 8)
};
""")
        self.assertIsNone(result["base"])
        self.assertIsNone(result["factor"])
        self.assertEqual(result["planned"], {"type": "recipe", "recipeId": 7})

    def test_legacy_servings_becomes_base_for_planned_occurrence(self):
        result = run_node("""
return S.makePlannedRecipeItem({id: "r1", servings: "4"}, 6);
""")
        self.assertEqual(
            result,
            {
                "type": "recipe",
                "recipeId": "r1",
                "plannedServings": 6,
                "baseServings": 4,
                "scaleFactor": 1.5,
            },
        )

    def test_multiple_occurrences_can_have_independent_servings(self):
        result = run_node("""
const recipe={id:"r1",baseServings:4,structuredIngredients:[{amount:"400",unit:"g",item:"kylling"}]};
const monday=S.scaledStructuredIngredients(recipe,6)[0].amount;
const tuesday=S.scaledStructuredIngredients(recipe,2)[0].amount;
return {monday,tuesday,total:Number(monday)+Number(tuesday)};
""")
        self.assertEqual(result, {"monday": "600", "tuesday": "200", "total": 800})


class ServingScalingUiContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.index = (ROOT / "index.html").read_text(encoding="utf-8")
        cls.app = (ROOT / "app.js").read_text(encoding="utf-8")
        cls.styles = (ROOT / "styles.css").read_text(encoding="utf-8")

    def test_scaling_module_is_loaded_before_app(self):
        self.assertLess(
            self.index.index("serving-scaling.js"),
            self.index.index('src="app.js'),
        )

    def test_add_to_day_has_serving_controls(self):
        self.assertIn('id="plannedServingsInput"', self.index)
        self.assertIn('data-planned-scale="0.5"', self.index)
        self.assertIn('data-planned-scale="2"', self.index)

    def test_plan_and_shopping_use_planned_servings(self):
        self.assertIn("plannedServings", self.app)
        self.assertIn("scaledIngredientLinesV30", self.app)
        self.assertIn("Endre porsjoner", self.app)

    def test_mobile_serving_layout_exists(self):
        self.assertIn("@media (max-width: 520px)", self.styles)
        self.assertIn(".serving-quick-actions", self.styles)


if __name__ == "__main__":
    unittest.main()
