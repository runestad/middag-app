import pathlib
import re
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


class BugfixUxPassTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = (ROOT / "index.html").read_text(encoding="utf-8")
        cls.javascript = (ROOT / "app.js").read_text(encoding="utf-8")
        cls.styles = (ROOT / "styles.css").read_text(encoding="utf-8")

    def test_dialog_close_controls_never_submit_or_validate(self):
        close_buttons = re.findall(r"<button[^>]*>(?:Lukk|Avbryt)</button>", self.html)
        self.assertTrue(close_buttons)
        self.assertTrue(all('type="button"' in button for button in close_buttons))
        self.assertNotIn('value="cancel"', self.html)
        self.assertIn("button.closest(\"dialog\")?.close()", self.javascript)

    def test_decimal_servings_accept_norwegian_input(self):
        for field_id in ("importServings", "plannedServingsInput"):
            field = re.search(rf'<input id="{field_id}"[^>]*>', self.html).group(0)
            self.assertIn('type="text"', field)
            self.assertIn('inputmode="decimal"', field)
        self.assertIn('id="recipeServingsV30" type="text" inputmode="decimal"', self.javascript)

    def test_favorite_toggle_normalizes_ids_and_persists(self):
        self.assertIn("function favoriteId(id){return String(id)}", self.javascript)
        toggle = self.javascript[self.javascript.index("function toggleFavorite(id)"):]
        self.assertIn("savePlan()", toggle[:700])
        self.assertIn("renderRecipeResults()", toggle[:700])
        self.assertIn("renderPickerResults()", toggle[:700])

    def test_favorite_is_available_in_all_recipe_views(self):
        picker_card = self.javascript[self.javascript.index("function recipeCardHtmlV28"):self.javascript.index("function renderRecipeResultsV28")]
        self.assertIn("toggleFavorite", picker_card)
        self.assertNotIn('scope==="recipes"?', picker_card)
        detail = self.javascript[self.javascript.index("window.openRecipeDetails=function(id){", self.javascript.index("function nutritionHtmlV28")):]
        self.assertIn("★ Favoritt", detail[:3000])
        self.assertIn("window.openPickerPreview", self.javascript)
        self.assertIn('if(!$("recipeDialog").open)', detail[:3000])

    def test_source_action_uses_original_recipe_url(self):
        self.assertIn("function originalRecipeSourceUrlV31", self.javascript)
        self.assertIn(">Åpne kilde</a>", self.javascript)
        source_helper = self.javascript[self.javascript.index("function originalRecipeSourceUrlV31"):]
        self.assertNotIn(".trim()||", source_helper[:700])

    def test_direct_url_import_does_not_create_shell_recipe(self):
        self.assertIn('data-add-recipe-mode="url"', self.html)
        start = self.javascript.index("function beginNewRecipeImportV31")
        end = self.javascript.index("/* ===== v30", start)
        flow = self.javascript[start:end]
        self.assertIn('$("importDialog").showModal()', flow)
        self.assertNotIn("recipes.push", flow)
        self.assertIn("autoFetchRecipeUrlV27", self.javascript)

    def test_shopping_checkbox_is_a_stable_circle(self):
        rule = self.styles[self.styles.index(".shopping-check {"):self.styles.index("}", self.styles.index(".shopping-check {"))]
        for declaration in ("width: 25px", "height: 25px", "aspect-ratio: 1 / 1", "box-sizing: border-box", "flex-shrink: 0", "justify-self: center", "padding: 0", "border-radius: 50%"):
            self.assertIn(declaration, rule)

    def test_rapid_shopping_add_preserves_focus_and_viewport(self):
        self.assertNotIn("scrollIntoView", self.javascript)
        helper = self.javascript[self.javascript.index("function renderShoppingWithoutViewportJumpV31"):]
        self.assertIn("window.scrollY", helper[:600])
        self.assertIn("window.scrollTo", helper[:600])
        self.assertIn("focus({preventScroll:true})", helper[:600])
        self.assertGreaterEqual(self.javascript.count("renderShoppingWithoutViewportJumpV31()"), 3)


if __name__ == "__main__":
    unittest.main()
