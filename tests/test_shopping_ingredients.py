import json,pathlib,subprocess,unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
def run(body):
 return json.loads(subprocess.check_output(['node','-e',"const m=require('./shopping-ingredients.js');"+body],cwd=ROOT,text=True))
class ShoppingIngredientsTests(unittest.TestCase):
 def test_fraction_conversion_and_idempotence(self):
  result=run("console.log(JSON.stringify(['1/2 cup shredded carrots','1 1/2 cups black beans','½ cup tomatoes','1½ cup rice','1/4 tsp salt','500g carrots','1,5 dl milk','1/0 cup rice','1–2 cups milk'].map(x=>[m.convert(x),m.convert(m.convert(x))])));")
  self.assertEqual([x[0] for x in result],['1,2 dl shredded carrots','3,6 dl black beans','1,2 dl tomatoes','3,6 dl rice','0,25 ts salt','500 g carrots','1,5 dl milk','1/0 cup rice','1–2 cups milk'])
  self.assertTrue(all(a==b for a,b in result))
 def test_unknown_amounts_ranges_and_missing_values_are_not_invented(self):
  result=run("console.log(JSON.stringify(['null brokkoli','undefined ris','litt salt','1–2 ss olje','1/0 cup rice','1/4,8 dl gulrot'].map(x=>m.parse(x))));")
  self.assertEqual(result[0]['original'],'brokkoli')
  self.assertTrue(all(x['amount'] is None for x in result))
 def test_units_and_names_keep_their_meaning(self):
  result=run("console.log(JSON.stringify(['2 bunt gressløk','3 potter basilikum','2 dl gulrot','1 l melk','2 egg','løk'].map(x=>m.parse(x))));")
  self.assertEqual([x['unit'] for x in result],['bunt','potte','dl','l','',''])
  self.assertEqual(result[-1]['name'],'løk')
 def test_product_categories_before_component_names(self):
  cases={'1 ts malt koriander':'Krydder','½ ts korianderpulver':'Krydder','1 ts løk pulver':'Krydder','chiliolje':'Tørrvarer','avokadooljespray (til steking)':'Tørrvarer','1 l kyllingkraft':'Hermetikk/halvfabrikat','kokosmelk':'Hermetikk/halvfabrikat','proteinpulver':'Tørrvarer','bakepulver':'Bakevarer','fersk basilikum':'Frukt og grønt','1 potte basilikum':'Frukt og grønt','5–6 kvister frisk timian':'Frukt og grønt','brokkoli (bakt med olje og salt)':'Frukt og grønt','chili (eller chiliflak)':'Frukt og grønt','tørkede urter':'Krydder','1 ts tørket dill':'Krydder','røkt paprikapulver':'Krydder','soltørkede tomater':'Hermetikk/halvfabrikat','ferske tomater':'Frukt og grønt','kyllingkrydder':'Krydder','kyllingfilet':'Kjøtt','2 garlic cloves, minced':None,'malt koriander (eller fersk koriander)':'Krydder'}
  actual=run('console.log(JSON.stringify('+json.dumps(list(cases),ensure_ascii=False)+'.map(x=>m.category(x))));')
  self.assertEqual(actual,list(cases.values()))
 def test_string_recipe_ingredients_scale(self):
  self.assertEqual(run("console.log(JSON.stringify([m.scale('1/2 cup carrots',2),m.scale('1/2 cup carrots',1),m.scale('salt etter smak',2)]));"),['1 cup carrots','1/2 cup carrots','salt etter smak'])

 def test_legacy_repair_requires_exact_unambiguous_source_matches(self):
  result=run("const text='1/4,8 dl carrots + 1/4,8 dl beans';const candidates=[{legacy:'1/4,8 dl carrots',current:'1,2 dl carrots'},{legacy:'1/4,8 dl beans',current:'1,2 dl beans'}];console.log(JSON.stringify([m.recoverLegacyGroup(text,candidates),m.recoverLegacyGroup(text,candidates.slice(0,1)),m.recoverLegacyGroup(text,[...candidates,{legacy:candidates[0].legacy,current:'99 carrots'}]),m.recoverLegacyGroup('milk + butter',candidates)]));")
  self.assertEqual(result,[['1,2 dl carrots','1,2 dl beans'],None,None,None])
