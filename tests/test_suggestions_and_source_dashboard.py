import copy
import json
import pathlib
import subprocess
import unittest
from unittest.mock import patch

from api import recovery
from api.ingredient_normalization import ingredient_category

ROOT = pathlib.Path(__file__).resolve().parents[1]


def node(script):
    return json.loads(subprocess.check_output(['node', '-e', script], cwd=ROOT, text=True))


class SuggestionTests(unittest.TestCase):
    def test_single_category_fills_requested_count(self):
        result = node("""
          const m=require('./recipe-suggestions.js');
          const candidates=Array.from({length:12},(_,id)=>({recipe:{id,category:'Pasta'},pantryScore:id/12}));
          const seen=new Set();const first=m.choose(candidates,5,{seen,random:()=>.5});
          const second=m.choose(candidates,5,{seen,last:first.map(r=>r.id),random:()=>.5});
          console.log(JSON.stringify([first.map(r=>r.id),second.map(r=>r.id)]));
        """)
        self.assertEqual([len(batch) for batch in result], [5, 5])
        self.assertFalse(set(result[0]) & set(result[1]))

    def test_surprise_rotates_even_when_one_recipe_matches_all_pantry_items(self):
        result = node("""
          const m=require('./recipe-suggestions.js'),seen=new Set();
          const candidates=Array.from({length:8},(_,id)=>({recipe:{id,category:'Vegetar'},pantryScore:id===0?1:0}));
          let last=[];const ids=Array.from({length:16},()=>{
            const selected=m.choose(candidates,1,{seen,last,random:()=>.5});last=selected.map(r=>r.id);return last[0];
          });console.log(JSON.stringify(ids));
        """)
        self.assertEqual(len(set(result[:8])), 8)
        self.assertEqual(len(set(result[8:])), 8)
        self.assertTrue(all(a != b for a, b in zip(result, result[1:])))

    def test_small_pool_no_duplicate_ids_or_missing_slots(self):
        result = node("""
          const m=require('./recipe-suggestions.js');
          const a={recipe:{id:1,category:'Pasta'}},b={recipe:{id:2,category:'Pasta'}};
          console.log(JSON.stringify([m.choose([],5),m.choose([a,a,b],5).map(r=>r.id)]));
        """)
        self.assertEqual(result[0], [])
        self.assertEqual(set(result[1]), {1, 2})
        self.assertEqual(len(result[1]), 2)

    def test_varies_categories_but_keeps_pantry_and_recent_preferences(self):
        result = node("""
          const m=require('./recipe-suggestions.js');
          const candidates=[{recipe:{id:1,category:'Pasta'},pantryScore:1,recent:true},
            {recipe:{id:2,category:'Pasta'},pantryScore:1},
            {recipe:{id:3,category:'Fisk'},pantryScore:.4},
            {recipe:{id:4,category:'Salat'},pantryScore:.2}];
          console.log(JSON.stringify(m.choose(candidates,3,{random:()=>.5}).map(r=>r.id)));
        """)
        self.assertEqual(result, [2, 3, 4])


class CategoryTests(unittest.TestCase):
    def test_seafood_and_known_other_items_match_in_browser_and_import(self):
        cases = {'scampi': 'Kjøtt og fisk', 'ørretfilet': 'Kjøtt og fisk', 'kyllingfilet': 'Kjøtt og fisk',
                 'worcestersaus': 'Tørrvarer', 'oliven': 'Hermetikk/halvfabrikat', 'rødvin': 'Drikke',
                 'hermetisk tunfisk': 'Hermetikk/halvfabrikat', 'olivenolje': 'Tørrvarer',
                 'fiskesaus': 'Tørrvarer', 'kyllingkrydder': 'Krydder', 'laksekrydder': 'Krydder', 'øl': 'Drikke'}
        actual = node("const m=require('./shopping-ingredients.js');console.log(JSON.stringify(" + json.dumps(list(cases)) + '.map(m.category)));')
        self.assertEqual(actual, list(cases.values()))
        for name, expected in cases.items():
            self.assertEqual(ingredient_category(name), expected, name)

    def test_frozen_products_and_legacy_categories_keep_their_meaning(self):
        self.assertEqual(node("const m=require('./shopping-ingredients.js');console.log(JSON.stringify([m.category('frosne scampi'),m.categoryName('Kjøtt'),m.categoryName('Frys'),m.categoryName('Kjølevarer')]));"),
                         ['Frysevarer', 'Kjøtt og fisk', 'Frysevarer', 'Kjølevarer'])
        self.assertEqual(ingredient_category('frosne scampi'), 'Frys')
        self.assertEqual(ingredient_category('ukjent vare', 'Kjøtt'), 'Kjøtt og fisk')


class CurrentRecoveryDashboardTests(unittest.TestCase):
    def test_old_missing_flags_and_deleted_recipes_do_not_count(self):
        manifest = {'high': [{'id': '1'}, {'id': 'deleted'}], 'url': [{'id': '1'}]}
        original = copy.deepcopy(manifest)
        recipe = {'id': 1, 'name': 'Restored', 'manualCheck': 'Ja', 'ingredientsText': '1 løk', 'instructions': 'Stek løken.'}
        queues, summary = recovery.current_dashboard(manifest, [recipe])
        self.assertEqual(summary['missingContent'], 0)
        self.assertEqual(summary['withContent'], 1)
        self.assertTrue(all(not queues[k] for k in ('high', 'medium', 'url', 'manual')))
        self.assertEqual(manifest, original)

    def test_current_missing_recipes_are_deduplicated_and_new_items_are_included(self):
        manifest = {'high': [{'id': '1', 'name': 'Old name'}], 'url': [{'id': '1'}]}
        recipes = [{'id': 1, 'name': 'Current name'}, {'id': 2, 'name': 'New', 'link': 'https://example.com/recipe'}, {'id': 3, 'name': 'Manual'}]
        queues, summary = recovery.current_dashboard(manifest, recipes)
        self.assertEqual(summary['missingContent'], 3)
        self.assertEqual(queues['high'][0]['name'], 'Current name')
        self.assertEqual([r['id'] for r in queues['url']], ['2'])
        self.assertEqual([r['id'] for r in queues['manual']], ['3'])

    def test_dashboard_endpoint_reads_current_rows_without_mutating_state(self):
        calls, responses = [], []
        def database(method, table, **kwargs):
            calls.append((method, table))
            return [{'id': '1', 'name': 'Ready', 'data': {'ingredientsText': '1 løk', 'instructions': 'Stek.'}}]
        handler = object.__new__(recovery.handler)
        handler.path = '/api/recovery'
        with patch.object(recovery, 'load_manifest', return_value={'url': [{'id': '1'}]}), \
             patch.object(recovery, 'get_state', return_value={'items': {'1': {'status': 'manual'}}}), \
             patch.object(recovery, 'supabase_request', side_effect=database), \
             patch.object(recovery, 'send_json', side_effect=lambda h, data, status=200: responses.append((status, data))):
            handler.do_GET()
        self.assertEqual(calls, [('GET', 'recipes')])
        self.assertEqual(responses[0][0], 200)
        self.assertEqual(responses[0][1]['contentHealth']['missingContent'], 0)
        self.assertEqual(responses[0][1]['manifest']['url'], [])


if __name__ == '__main__':
    unittest.main()
