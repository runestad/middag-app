import copy
import importlib
import unittest
from unittest.mock import patch
from api.import_units import metric_ingredient
from api.recipe_import import instruction_lines, structured_recipe
import test_recipe_edit_persistence

parser = importlib.import_module('api.parse-caption')
extractor = importlib.import_module('api.fetch-recipe')


class AutomaticRecipeImportTests(unittest.TestCase):
    def test_units_convert_once_and_keep_source(self):
        item={'amount':'1/2','unit':'cup','item':'gresk yoghurt','original':'1/2 cup Greek yogurt'}
        result=metric_ingredient(item)
        self.assertEqual((result['amount'],result['unit']),('1,2','dl'))
        self.assertEqual(metric_ingredient(result),result)
        self.assertEqual(result['original'],item['original'])
        self.assertEqual(item['amount'],'1/2')

    def test_weight_volume_fraction_and_range_conversions(self):
        cases=[('1 1/2','cups','3,6','dl'),('2–3','tbsp','2–3','ss'),('2','oz','56,699','g'),('1','lb','453,592','g'),('2','fl oz','59,147','ml'),('1','teaspoon','1','ts'),('½','cup','1,2','dl')]
        for amount,unit,expected,target in cases:
            result=metric_ingredient({'amount':amount,'unit':unit,'item':'test'})
            self.assertEqual((result['amount'],result['unit']),(expected,target))

    def test_ambiguous_compound_amount_is_not_relabelled(self):
        item={'amount':'1/2 + 2 tbsp','unit':'cup','item':'mel'}
        self.assertEqual(metric_ingredient(item),item)

    def test_source_repair_precedes_conversion(self):
        parsed=parser.finalize_parsed_recipe({'servings':'4','ingredients':[
            {'amount':'0.5','unit':'dl','item':'parmesan','original':'1/2 cup parmesan'},
            {'amount':'2','unit':'stk','item':'hvitløk','original':'2 garlic cloves'}],
            'instructions':['Bland.']},'1/2 cup parmesan\n2 garlic cloves')
        self.assertEqual([(r['amount'],r['unit']) for r in parsed['ingredients']],[('1,2','dl'),('2','fedd')])

    def test_nested_steps_and_servings_reach_language_parser_without_mutation(self):
        recipe={'recipeYield':'4 servings','recipeIngredient':['1 cup rice'],
                'recipeInstructions':[{'@type':'HowToSection','name':'Rice','itemListElement':[{'@type':'HowToStep','text':'Boil rice.'},{'text':'Rest.'}]}]}
        before=copy.deepcopy(recipe)
        text=extractor.recipe_text(recipe)
        result=structured_recipe(recipe,'https://example.org/food','https://example.org/food','example.org')
        self.assertIn('4 servings',text)
        self.assertIn('Boil rice.',text)
        self.assertEqual(result['instructionSteps'],['Boil rice.','Rest.'])
        self.assertEqual(recipe,before)
        self.assertEqual(instruction_lines('One step.'),['One step.'])

    def test_recipe_specific_image_precedes_site_social_image(self):
        images=extractor.image_candidates('<meta property="og:image" content="/logo.jpg">',{'image':'/pasta.jpg'},'https://example.org/recipe')
        self.assertEqual(images[0]['url'],'https://example.org/pasta.jpg')

    def test_missing_source_fields_are_exposed(self):
        parsed=parser.finalize_parsed_recipe({'ingredients':[],'instructions':[],'uncertainties':None},'Only a title')
        self.assertEqual({x['field'] for x in parsed['uncertainties']},{'ingredients','instructions','servings'})
        self.assertFalse(parsed['ingredients'])

    def test_reviewed_category_survives_save_and_readback(self):
        helper=test_recipe_edit_persistence.RecipeEditTests()
        old={'id':'1','name':'Pasta'}
        ingredient={'amount':'200','unit':'g','item':'pasta','shoppingCategory':'Glutenfritt'}
        response,_=helper.call_save(old,{'id':'1','explicitContentEdit':True,'patch':{'structuredIngredients':[ingredient]}})
        self.assertEqual(response[1]['recipe']['structuredIngredients'][0]['shoppingCategory'],'Glutenfritt')

    def test_manual_freezer_category_keeps_its_meaning(self):
        helper=test_recipe_edit_persistence.RecipeEditTests()
        response,_=helper.call_save({'id':'1','name':'Pasta'},{'id':'1','explicitContentEdit':True,'patch':{'structuredIngredients':[{'amount':'200','unit':'g','item':'pasta','shoppingCategory':'Frysevarer'}]}})
        self.assertEqual(response[1]['recipe']['structuredIngredients'][0]['shoppingCategory'],'Frys')


class TikTokCaptionTests(unittest.TestCase):
    def test_only_requested_video_is_extracted(self):
        import json
        payload={'items':[{'id':'99','desc':'Wrong recipe'}, {'id':'123','desc':'1 cup rice\nBoil rice.','video':{'cover':'https://example.org/cover.jpg'}}]}
        html='<script id="__UNIVERSAL_DATA_FOR_REHYDRATION__" type="application/json">'+json.dumps(payload)+'</script>'
        result=extractor.tiktok_embedded_recipe(html,'https://www.tiktok.com/@cook/video/123')
        self.assertEqual(result['caption'],'1 cup rice\nBoil rice.')
        self.assertEqual(result['image'],'https://example.org/cover.jpg')
        self.assertIsNone(extractor.tiktok_embedded_recipe(html,'https://www.tiktok.com/@cook/video/456'))

    def test_oembed_strips_share_tracking(self):
        import urllib.parse
        with patch.object(extractor,'fetch_text',return_value=('{"title":"Recipe"}','application/json','https://www.tiktok.com/oembed')) as fetch:
            extractor.tiktok_oembed('https://www.tiktok.com/@cook/video/123?_r=1&_t=share')
        self.assertEqual(urllib.parse.parse_qs(urllib.parse.urlparse(fetch.call_args.args[0]).query)['url'],['https://www.tiktok.com/@cook/video/123'])
