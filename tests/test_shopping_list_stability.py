import importlib
import json
import subprocess
import unittest
from unittest.mock import patch
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run_model(script):
    program = f"const m=require('./shopping-list-model.js');\n{script}"
    result = subprocess.run(
        ["node", "-e", program], cwd=ROOT, text=True, capture_output=True, check=True
    )
    return json.loads(result.stdout)


class ShoppingListModelTests(unittest.TestCase):
    def test_rapid_add_keeps_every_stable_id(self):
        result = run_model("""
          const items=['Melk','Brød','Ost','Bananer','Kaffe'].map((text,index)=>({id:`i${index}`,text,category:'Annet',updatedAt:`2026-01-01T00:00:0${index}.000Z`}));
          console.log(JSON.stringify(m.mergeStates(items, [])));
        """)
        self.assertEqual([item["text"] for item in result], ["Melk", "Brød", "Ost", "Bananer", "Kaffe"])
        self.assertEqual(len({item["id"] for item in result}), 5)

    def test_delete_tombstone_beats_stale_remote_snapshot(self):
        result = run_model("""
          const local=[{id:'milk',text:'Melk',deleted:true,updatedAt:'2026-01-01T00:00:03.000Z'},{id:'bread',text:'Brød',updatedAt:'2026-01-01T00:00:02.000Z'}];
          const stale=[{id:'milk',text:'Melk',deleted:false,updatedAt:'2026-01-01T00:00:01.000Z'}];
          console.log(JSON.stringify(m.mergeStates(local,stale)));
        """)
        self.assertTrue(next(item for item in result if item["id"] == "milk")["deleted"])
        self.assertIn("Brød", [item["text"] for item in result])

    def test_week_merge_is_non_destructive_and_idempotent(self):
        result = run_model("""
          const existing=['Dopapir','Zalo','Pepsi Max'].map((text,index)=>({id:`m${index}`,text,category:'Annet'}));
          const generated=['Kylling','Ris','Brokkoli'].map((text,index)=>({id:`w${index}`,text,category:'Mat'}));
          const once=m.mergeWeekMenuItems(existing,generated);
          const twice=m.mergeWeekMenuItems(once,generated);
          console.log(JSON.stringify(twice));
        """)
        self.assertEqual([item["text"] for item in result], ["Dopapir", "Zalo", "Pepsi Max", "Kylling", "Ris", "Brokkoli"])

    def test_explicit_reimport_can_restore_deleted_import(self):
        result = run_model("""
          const existing=[{id:'old',text:'Brokkoli',category:'Mat',deleted:true,updatedAt:'2026-01-02T00:00:00Z'}];
          const generated=[{id:'new',text:'Brokkoli',category:'Mat',deleted:false,updatedAt:'2026-01-03T00:00:00Z'}];
          console.log(JSON.stringify(m.mergeWeekMenuItems(existing,generated)));
        """)
        self.assertEqual(len(result), 2)
        self.assertEqual(len([item for item in result if not item["deleted"]]), 1)

    def test_conservative_dedupe_keeps_distinct_names(self):
        result = run_model("""
          const generated=['Tomat','Cherrytomat','Hermetiske tomater','Melk','Kokosmelk'].map((text,index)=>({id:`x${index}`,text,category:'Mat'}));
          console.log(JSON.stringify(m.mergeWeekMenuItems([],generated)));
        """)
        self.assertEqual(len(result), 5)


class ShoppingPersistenceTests(unittest.TestCase):
    def test_server_merges_concurrent_item_level_changes(self):
        plan_api = importlib.import_module("api.plan")
        stored = [{"id": "milk", "text": "Melk", "updatedAt": "2026-01-01T00:00:01Z"}]
        incoming = [{"id": "bread", "text": "Brød", "updatedAt": "2026-01-01T00:00:02Z"}]
        merged = plan_api._merge_shopping_items(stored, incoming)
        self.assertEqual({item["id"] for item in merged}, {"milk", "bread"})

    def test_server_tombstone_wins_over_older_item(self):
        plan_api = importlib.import_module("api.plan")
        stored = [{"id": "milk", "deleted": True, "updatedAt": "2026-01-01T00:00:03Z"}]
        incoming = [{"id": "milk", "deleted": False, "updatedAt": "2026-01-01T00:00:01Z"}]
        self.assertTrue(plan_api._merge_shopping_items(stored, incoming)[0]["deleted"])

    def test_server_retries_compare_and_swap_and_remerges(self):
        plan_api = importlib.import_module("api.plan")
        first = [{"data": {"updatedAt": "r1", "shoppingItems": [{"id": "milk", "updatedAt": "1"}]}}]
        concurrent = [{"data": {"updatedAt": "r2", "shoppingItems": [{"id": "bread", "updatedAt": "2"}]}}]
        calls = [first, [], concurrent, [{"ok": True}]]
        incoming = {"updatedAt": "r3", "shoppingItems": [{"id": "cheese", "updatedAt": "3"}]}
        with patch.object(plan_api, "supabase_request", side_effect=calls) as request:
            result = plan_api._persist_plan_with_retry("plan:test", incoming)
        self.assertEqual({item["id"] for item in result["shoppingItems"]}, {"milk", "bread", "cheese"})
        self.assertIn("data-%3E%3EupdatedAt=eq.r2", request.call_args_list[-1][1]["query"])


class ShoppingUxContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = (ROOT / "index.html").read_text()
        cls.css = (ROOT / "styles.css").read_text()
        cls.js = (ROOT / "app.js").read_text()

    def test_smart_selector_is_after_shopping_list(self):
        shopping = self.html[self.html.index('id="viewShopping"'):self.html.index('id="viewRecipes"')]
        self.assertGreater(shopping.index("Smart velger"), shopping.index('id="shoppingList"'))

    def test_inline_category_add_contract(self):
        self.assertIn("openCategoryAddV40", self.js)
        self.assertIn('event.key === "Escape"', self.js)
        self.assertIn('focus({preventScroll:true})', self.js)

    def test_date_grid_stacks_and_inputs_can_shrink(self):
        self.assertIn("@media (max-width: 430px)", self.css)
        self.assertIn(".period-grid{grid-template-columns:1fr}", self.css)
        self.assertIn('input[type="date"]{display:block;width:100%;max-width:100%;min-width:0', self.css)
        self.assertIn("column-gap:18px;row-gap:14px", self.css)

    def test_completed_items_can_be_cleared_with_tombstones(self):
        active = self.js[self.js.index("/* ===== v25 professional UI"):]
        self.assertIn("clearCompletedShoppingV25", active)
        self.assertIn('completedIds.has(item.id) ? {...item, deleted: true', active)

    def test_shopping_categories_are_complete_and_canonical(self):
        expected = '["Frukt og grønt","Kjøtt","Frysevarer","Meieri","Hermetikk/halvfabrikat","Tørrvarer","Krydder","Glutenfritt","Bakevarer","Annet"]'
        self.assertIn(f"const CATEGORIES={expected}", self.js)
        final_render = self.js[self.js.rindex("renderShoppingList=function(items)"):]
        self.assertIn("new Map(CATEGORIES.map(category=>[category,[]]))", final_render)
        self.assertIn("CATEGORIES.map(category=>renderShoppingCategoryV25", final_render)


if __name__ == "__main__":
    unittest.main()
