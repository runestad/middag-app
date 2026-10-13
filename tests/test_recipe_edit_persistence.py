"""Regression tests for observed production data-loss and editor bugs."""
import copy
import importlib.util
import json
import pathlib
import subprocess
import unittest
from unittest.mock import patch

from api._common import recipe_to_row
from api.ingredient_normalization import normalize_ingredient_name, ingredient_category
from api.recipe_import import safe_recipe_merge, merge_reviewed_recipe

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('api.save_recipe_edit_test', ROOT / 'api/save-recipe.py')
SAVE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SAVE)


class RecipeEditTests(unittest.TestCase):
    def call_save(self, existing, payload, empty_write=False):
        rows = [recipe_to_row(existing)] if existing else []
        writes, responses = [], []
        def database(method, path, **kwargs):
            if method == 'GET':
                return copy.deepcopy(rows)
            writes.append(kwargs['payload'])
            return [] if empty_write else [kwargs['payload']]
        with patch.object(SAVE, 'read_body', return_value=payload), patch.object(SAVE, 'supabase_request', side_effect=database), patch.object(SAVE, 'send_json', side_effect=lambda h, data, status=200: responses.append((status,data))):
            SAVE.handler.do_POST(object.__new__(SAVE.handler))
        return responses[-1], writes

    def test_new_recipe_keeps_its_entered_name(self):
        response, writes = self.call_save(None, {'id':'new','patch':{'name':'Min fredagspasta','ingredientsText':'2 egg'}})
        self.assertEqual(response[0], 200)
        self.assertEqual(writes[0]['name'], 'Min fredagspasta')

    def test_reviewed_corrections_survive_database_roundtrip(self):
        old={'id':'1','name':'Min pasta','servings':'4','ingredientsText':'400 g pasta','structuredIngredients':[{'item':'pasta','amount':'400'}],'instructions':'Stek feil ting.'}
        payload={'id':'1','explicitContentEdit':True,'patch':{'name':'AI tittel','servings':'2','ingredientsText':'200 g glutenfri pasta','structuredIngredients':[{'amount':'200','unit':'g','item':'glutenfri pasta'}],'instructions':'Kok pastaen.'}}
        response,writes=self.call_save(old,payload)
        actual=response[1]['recipe']
        self.assertEqual(actual['name'],'Min pasta')
        self.assertEqual(actual['ingredientsText'],'200 g glutenfri pasta')
        self.assertEqual(actual['structuredIngredients'][0]['item'],'glutenfri pasta')
        self.assertEqual(actual['servings'],'2')
        self.assertEqual(actual['instructions'],'Kok pastaen.')
        self.assertEqual(actual['ingredientLines'],['200 g glutenfri pasta'])

    def test_explicit_rename_is_not_discarded(self):
        response,_=self.call_save({'id':'1','name':'Gammelt'}, {'id':'1','explicitNameEdit':True,'patch':{'name':'Nytt'}})
        self.assertEqual(response[1]['recipe']['name'],'Nytt')

    def test_automatic_recovery_stays_fill_only(self):
        old={'name':'Min pasta','ingredientsText':'400 g pasta'}
        self.assertEqual(safe_recipe_merge(old,{'name':'AI','ingredientsText':'2 egg'})['ingredientsText'],'400 g pasta')

    def test_no_false_success_when_database_did_not_update(self):
        response,_=self.call_save({'id':'1','name':'Pasta'}, {'id':'1','patch':{'category':'Pasta'}},empty_write=True)
        self.assertEqual(response[0],500)
        self.assertFalse(response[1]['ok'])

    def test_blank_edits_do_not_delete_stored_recipe(self):
        old={'name':'Pasta','ingredientsText':'2 egg','instructions':'Stek eggene.'}
        self.assertEqual(merge_reviewed_recipe(old,{'ingredientsText':'','instructions':''}),old)

    def test_text_edit_invalidates_stale_structured_aliases(self):
        result=merge_reviewed_recipe({'name':'Pasta','structuredIngredients':[{'item':'feil'}],'baseServings':4},{'ingredientsText':'1 egg','servings':'2-3'})
        self.assertNotIn('structuredIngredients',result)
        self.assertNotIn('baseServings',result)

    def test_name_is_required_before_creating_a_row(self):
        response,writes=self.call_save(None,{'id':'1','patch':{'ingredientsText':'1 egg'}})
        self.assertEqual(response[0],400)
        self.assertEqual(writes,[])

    def test_specific_ingredient_types_and_alternatives_are_preserved(self):
        for name in ['glutenfri pasta','lett kokosmelk','malt ingefær','røkt paprikapulver','olivenolje eller smør','gresk yoghurt']:
            self.assertEqual(normalize_ingredient_name(name),name)
        self.assertEqual(normalize_ingredient_name('fresh basil'),'fersk basilikum')
        self.assertEqual(normalize_ingredient_name('tomatoes'),'tomat')
        self.assertEqual(normalize_ingredient_name('diced tomatoes'),'hakkede tomater')

    def test_powders_are_not_all_spices(self):
        for name,category in [('vaniljeproteinpulver','Tørrvarer'),('bakepulver','Bakevarer'),('paprikapulver','Krydder'),('malt ingefær','Krydder'),('fersk basilikum','Frukt og grønt'),('glutenfri pasta','Glutenfritt')]:
            self.assertEqual(ingredient_category(name),category)

    def test_editor_does_not_split_ingredient_names_as_unit_prefixes(self):
        js=(ROOT/'app.js').read_text()
        start=js.index('function previewIngredientsV26()')
        end=js.index('parseCaptionAI = async function(options={})',start)
        script='const window={};const $=()=>({value:"løk\\ngulrot\\nmelk\\n1 1/2 ss olje\\n1/2 ts salt"});\n'+js[start:end]+'\nconsole.log(JSON.stringify(previewIngredientsV26()));'
        result=json.loads(subprocess.check_output(['node','-e',script],text=True))
        self.assertEqual([r['item'] for r in result],['løk','gulrot','melk','olje','salt'])
        self.assertEqual(result[3]['amount'],'1 1/2')
        self.assertEqual(result[4]['amount'],'1/2')

    def test_stale_preview_never_overwrites_manual_text(self):
        js=(ROOT/'app.js').read_text()
        start=js.index('function syncStructuredPreviewV28()')
        end=js.index('const parseCaptionAIBeforeV28',start)
        script='const elements={structuredIngredientPreview:{dataset:{sourceText:"old"}},parsedIngredients:{value:"corrected"}};const $=id=>elements[id];let refreshed=false;function structuredPreviewV28(){refreshed=true};\n'+js[start:end]+'\nsyncStructuredPreviewV28();console.log(JSON.stringify({refreshed,text:elements.parsedIngredients.value}));'
        result=json.loads(subprocess.check_output(['node','-e',script],text=True))
        self.assertEqual(result,{'refreshed':True,'text':'corrected'})
