import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


class ImportUiContractTests(unittest.TestCase):
    def test_single_and_multiple_images_supported(self):
        html = (ROOT / "index.html").read_text(encoding="utf-8")
        self.assertIn('id="screenshotInput"', html)
        self.assertIn("multiple", html)
        self.assertIn('id="importProgress"', html)

    def test_image_selection_starts_pipeline(self):
        javascript = (ROOT / "app.js").read_text(encoding="utf-8")
        self.assertIn('"change", processScreenshotsV26', javascript)
        self.assertIn("await parseCaptionAI({automatic: true})", javascript)

    def test_save_stays_explicit(self):
        html = (ROOT / "index.html").read_text(encoding="utf-8")
        javascript = (ROOT / "app.js").read_text(encoding="utf-8")
        self.assertIn('id="saveParsedBtn"', html)
        self.assertNotIn("await saveParsedRecipe()", javascript[javascript.index("async function processScreenshotsV26"):])


if __name__ == "__main__":
    unittest.main()
