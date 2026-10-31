import json
import pathlib
import subprocess
import unittest

from api.recipe_import import merge_reviewed_recipe
import test_recipe_edit_persistence

ROOT = pathlib.Path(__file__).resolve().parents[1]


def node(script):
    return json.loads(subprocess.check_output(["node", "-e", script], cwd=ROOT, text=True))


class ImageCompressionTests(unittest.TestCase):
    def prepare(self, encoder, bitmap=True):
        return node("""
const calls=[],dimensions=[],released=[];
const bitmap={width:4032,height:3024,close(){released.push('bitmap')}};
global.createImageBitmap=async()=>bitmap;
global.URL={createObjectURL:()=> 'blob:test',revokeObjectURL:url=>released.push(url)};
global.Image=class {constructor(){this.naturalWidth=4032;this.naturalHeight=3024} set src(value){this.onload()}};
global.document={createElement:()=>({width:0,height:0,getContext(){return {fillRect(){},drawImage(){}}},toBlob(callback,type,quality){
 calls.push([type,quality]);dimensions.push([this.width,this.height]);
 """ + encoder + """
}})};
""" + ("delete global.createImageBitmap;" if not bitmap else "") + """
const R=require('./recipe-image.js');
R.prepare({type:'image/jpeg',size:30*1024*1024}).then(blob=>console.log(JSON.stringify({blob,calls,dimensions,released}))).catch(e=>{console.error(e);process.exit(1)});
""")

    def test_safari_png_fallback_uses_small_jpeg(self):
        result = self.prepare("callback({type:type==='image/webp'?'image/png':'image/jpeg',size:type==='image/webp'?1800000:350000});")
        self.assertEqual(result["blob"]["type"], "image/jpeg")
        self.assertLessEqual(result["blob"]["size"], 750000)
        self.assertEqual([c[0] for c in result["calls"]], ["image/webp", "image/jpeg"])
        self.assertEqual(result["dimensions"][0], [1600, 1200])
        self.assertIn("bitmap", result["released"])

    def test_large_output_retries_with_smaller_dimensions(self):
        result = self.prepare("callback({type,size:this.width>1024?1800000:450000});")
        self.assertEqual(result["blob"]["size"], 450000)
        self.assertIn([1024, 768], result["dimensions"])

    def test_browser_image_decoder_works_without_image_bitmap(self):
        result = self.prepare("callback({type,size:350000});", bitmap=False)
        self.assertEqual(result["blob"]["size"], 350000)
        self.assertIn("blob:test", result["released"])

    def test_quality_is_reduced_before_resolution(self):
        result = self.prepare("callback({type,size:quality>.72?900000:500000});")
        self.assertEqual(result["blob"]["size"], 500000)
        self.assertEqual(result["dimensions"][-1], [1600, 1200])
        self.assertEqual(result["calls"][-1][1], .72)


class ImportSaveTests(unittest.TestCase):
    def save(self, servings="", fail=False, timeout=False, missing=None):
        js=(ROOT/"app.js").read_text()
        snippet=js[js.index("const saveParsedRecipeBeforeV28="):js.index("const addRecipeToDayBeforeV28=")]
        return node("""
const elements={parsedIngredients:{value:'400 g mager cottage cheese\\n4 egg\\n300 g havregryn'},importServings:{value:SERVINGS},importDialog:{open:true},saveParsedBtn:{textContent:'Lagre'},aiStatus:{},importSaveStatus:{}};
const $=id=>elements[id];let importBusyV50=false,importSavingV50=false,activeImportId='draft',importRunV26=1;
const window={lastAiParsedRecipe:{uncertainties:[{field:'ingredients.0',reason:'Kontroller kilden'}]}};
let saved=0,requests=0;
const recipeById=()=>({}),ingredientsToText=()=>'',previewIngredientsV26=()=>[{item:'mager cottage cheese',amount:'400',unit:'g'}];
const importMissingV50=()=>MISSING;
const completeNutritionV56=n=>!!(n&&n.calories>0);
const setImportBusyV50=busy=>{importBusyV50=busy;elements.saveParsedBtn.disabled=busy||importSavingV50};
let saveParsedRecipe=async()=>{saved++};
const consoleWarn=console.warn;console.warn=()=>{};
const fetch=async(url,{signal})=>{requests++;if(TIMEOUT)return new Promise((resolve,reject)=>signal.addEventListener('abort',()=>reject(new Error('timeout'))));if(FAIL)throw new Error('temporary failure');return{ok:true,json:async()=>({ok:true,nutrition:{calories:400,protein:20,fat:10,carbohydrates:50,fiber:5}})}};
""".replace("SERVINGS", json.dumps(servings)).replace("MISSING",json.dumps(missing if missing is not None else ["antall porsjoner","bilde"]))
        .replace("TIMEOUT",json.dumps(timeout)).replace("FAIL",json.dumps(fail))
        + ("const setTimeout=fn=>{queueMicrotask(fn);return 1},clearTimeout=()=>{};" if timeout else "")
        + snippet + """
saveParsedRecipe().then(()=>console.log(JSON.stringify({saved,requests,pending:window.lastAiParsedRecipe.nutritionPending,nutrition:window.lastAiParsedRecipe.nutrition,warnings:window.lastAiParsedRecipe.uncertainties,locked:importSavingV50,disabled:elements.saveParsedBtn.disabled,message:elements.importSaveStatus.textContent})));
""")

    def test_correct_ingredients_save_despite_yellow_warnings_missing_yield_and_image(self):
        result=self.save()
        self.assertEqual((result["saved"],result["requests"]),(1,0))
        self.assertTrue(result["pending"])
        self.assertFalse(result["locked"])
        self.assertFalse(result["disabled"])
        self.assertEqual(len(result["warnings"]),1)

    def test_nutrition_failure_does_not_block_recipe_save(self):
        result=self.save("4", fail=True)
        self.assertEqual((result["saved"],result["requests"]),(1,1))
        self.assertTrue(result["pending"])
        self.assertFalse(result["disabled"])

    def test_nutrition_timeout_releases_save_and_preserves_recipe(self):
        result=self.save("4", timeout=True)
        self.assertEqual(result["saved"],1)
        self.assertTrue(result["pending"])
        self.assertFalse(result["locked"])

    def test_serving_labels_can_reach_calculator_and_save_complete_nutrition(self):
        result=self.save("4 porsjoner")
        self.assertEqual(result["saved"],1)
        self.assertFalse(result["pending"])
        self.assertEqual(result["nutrition"]["calories"],400)

    def test_missing_required_content_is_visible_next_to_save_button(self):
        result=self.save(missing=["navn","ingredienser"])
        self.assertEqual(result["saved"],0)
        self.assertIn("navn, ingredienser",result["message"])

    def test_accepting_warning_keeps_ingredient_and_other_warnings(self):
        js=(ROOT/"app.js").read_text()
        snippet=js[js.index("function confirmIngredientV57"):js.index("function setPreviewIngredientsV50")]
        result=node("""
const window={lastAiParsedRecipe:{ingredients:[{amount:'400',unit:'g',item:'mager cottage cheese'}],uncertainties:[{field:'ingredients.0',reason:'check'},{field:'servings',reason:'missing'}]}};
const syncStructuredPreviewV28=()=>{},showImportUncertaintiesV26=()=>{},structuredPreviewV28=()=>{};
"""+snippet+"confirmIngredientV57(0);console.log(JSON.stringify(window.lastAiParsedRecipe));")
        self.assertEqual(result["ingredients"][0]["amount"],"400")
        self.assertEqual(result["uncertainties"],[{"field":"servings","reason":"missing"}])

    def test_saved_edit_does_not_resurrect_stale_nutrition(self):
        old={"id":"1","name":"Pizza","ingredientsText":"2 egg","nutrition":{"calories":200},"nutritionEstimate":{"calories":200}}
        response,_=test_recipe_edit_persistence.RecipeEditTests().call_save(old,{"id":"1","explicitContentEdit":True,"patch":{"ingredientsText":"4 egg","nutritionPending":True}})
        self.assertEqual(response[0],200)
        self.assertEqual(response[1]["recipe"]["ingredientsText"],"4 egg")
        self.assertNotIn("nutrition",response[1]["recipe"])
        self.assertNotIn("nutritionEstimate",response[1]["recipe"])
        self.assertEqual(old["nutrition"]["calories"],200)
        self.assertEqual(merge_reviewed_recipe(old,{"category":"Pasta"})["nutrition"],old["nutrition"])


if __name__ == "__main__":
    unittest.main()
