import importlib.util
import pathlib
import unittest

from api.recipes import add_verified_media

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("recover_recipe_media", ROOT / "scripts" / "recover_recipe_media.py")
MEDIA = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MEDIA)


class FocusedMobileFixTests(unittest.TestCase):
    def setUp(self):
        self.html = (ROOT / "index.html").read_text(encoding="utf-8")
        self.js = (ROOT / "app.js").read_text(encoding="utf-8")
        self.css = (ROOT / "styles.css").read_text(encoding="utf-8")

    def test_date_inputs_have_no_duplicate_visible_helpers(self):
        self.assertIn('id="startDate"', self.html)
        self.assertIn('id="endDate"', self.html)
        self.assertNotIn('id="startDateLabel"', self.html)
        self.assertNotIn('id="endDateLabel"', self.html)
        self.assertIn("createDaysBtn:createDayRows", self.js)

    def test_manual_meal_input_stays_visible_on_mobile(self):
        final_mobile = self.css[self.css.rindex("@media(max-width:560px)"):]
        self.assertIn(".day-manual-row{display:grid}", final_mobile)
        self.assertNotIn(".day-manual-row{display:none}", final_mobile)

    def test_freezer_controls_keep_existing_mutations(self):
        self.assertIn('class="freezer-stepper"', self.js)
        self.assertIn("changeFreezerQty", self.js)
        self.assertIn("removeFreezerItem", self.js)
        self.assertIn("savePlan();renderFreezer()", self.js)

    def test_stored_media_resolution_and_no_overwrite(self):
        recipe = {"id": "1", "name": "Test", "sourceMetadata": {"thumbnailUrl": "https://images.example/exact.jpg"}, "link": "https://example.com/recipe"}
        row = MEDIA.recover_one(recipe, lambda _: (_ for _ in ()).throw(AssertionError("must not fetch")))
        self.assertEqual(row["status"], "already-usable")
        self.assertEqual(row["image"], "https://images.example/exact.jpg")

    def test_recovery_is_idempotent_and_preserves_identity(self):
        recipe = {"id": "abc", "name": "Exact", "link": "https://example.com/exact"}
        fetcher = lambda _: {"image": "https://images.example/exact.jpg", "imageMethod": "opengraph-image", "resolvedUrl": "https://example.com/exact"}
        first = MEDIA.recover_one(recipe, fetcher)
        persisted = dict(recipe, image=first["image"])
        second = MEDIA.recover_one(persisted, fetcher)
        self.assertEqual(first["id"], "abc")
        self.assertEqual(first["sourceUrl"], recipe["link"])
        self.assertEqual(second["status"], "already-usable")

    def test_manifest_requires_id_and_exact_source_and_preserves_good_image(self):
        manifest = {"1": {"image": "/assets/recipe-media/1.jpg", "sourceUrl": "https://example.com/exact", "method": "source-metadata"}}
        self.assertNotIn("image", add_verified_media({"id": "1", "link": "https://example.com/wrong"}, manifest))
        current = add_verified_media({"id": "1", "link": "https://example.com/exact", "image": "https://good.example/current.jpg"}, manifest)
        self.assertEqual(current["image"], "https://good.example/current.jpg")
        recovered = add_verified_media({"id": "1", "link": "https://example.com/exact"}, manifest)
        self.assertEqual(recovered["image"], "/assets/recipe-media/1.jpg")

    def test_freezer_grouping_and_persistence_contracts_remain(self):
        self.assertIn('(groups[item.category||"Annet"] ||= []).push(item)', self.js)
        self.assertIn("item.qty=Math.max(0,Number(item.qty||0)+delta);savePlan();renderFreezer()", self.js)
        self.assertIn("freezerItems=freezerItems.filter(x=>x.id!==id);savePlan();renderFreezer()", self.js)
        self.assertIn("freezerItems.push({id:`freezer-${Date.now()}`", self.js)
        self.assertIn("smoothieblanding mango ananas banan", self.js)


if __name__ == "__main__":
    unittest.main()
