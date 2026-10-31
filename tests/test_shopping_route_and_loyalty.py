import importlib
import json
import pathlib
import re
import subprocess
import unittest
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[1]

def node(script):
    return json.loads(subprocess.check_output(['node', '-e', script], cwd=ROOT, text=True))

class ShoppingRouteTests(unittest.TestCase):
    def test_produce_route_and_names_ignore_amounts(self):
        result = node("""
const route=require('./shopping-order');
const input=['200 g spinat','2 stk tomater','1 stk banan','4 stk epler','1 stk brokkoli'].map((text,id)=>({text,id}));
const before=JSON.stringify(input);
console.log(JSON.stringify({groups:route.group(input,'Frukt og grønt'),unchanged:before===JSON.stringify(input)}));
""")
        self.assertTrue(result['unchanged'])
        self.assertEqual([g['label'] for g in result['groups']], ['Frukt', 'Grønnsaker · uten kjøling', 'Grønnsaker · kjøl'])
        self.assertEqual([i['text'] for g in result['groups'] for i in g['items']], ['1 stk banan','4 stk epler','2 stk tomater','1 stk brokkoli','200 g spinat'])

    def test_manual_category_is_respected_and_unknowns_retained(self):
        result = node("const r=require('./shopping-order');console.log(JSON.stringify(r.group([{text:'Ukjent vare',id:1},{text:'Frosne erter',id:2}],'Frysevarer')))")
        self.assertEqual(sum(len(g['items']) for g in result),2)
        self.assertEqual(result[0]['label'],'Grønnsaker og bær')

    def test_barcode_is_standard_code128_with_quiet_zones(self):
        # Independent Code 128 fixtures verified against ReportLab.
        fixtures = {'1234567890123': '2112321122321311233311212411122141211122321141312211321212412331112', '12345678': '2112321122321311233311212411121331212331112'}
        for value in ('1234567890123','12345678'):
            svg=node("const b=require('./loyalty-card');console.log(JSON.stringify(b.barcodeSvg('"+value+"')))")
            rects=[(int(x),int(w)) for x,w in re.findall(r'<rect x="(\d+)" y="10" width="(\d+)"',svg)]
            expected=[];x=12
            for i,c in enumerate(fixtures[value]):
                width=int(c)
                if i%2==0:expected.append((x,width))
                x+=width
            self.assertEqual(rects,expected)
            self.assertEqual(rects[0][0],12)
            self.assertIn(f'viewBox="0 0 {x+12} 80"',svg)
        self.assertEqual(node("console.log(JSON.stringify(require('./loyalty-card').barcodeSvg('<bad>')))"),'')

    def test_scroll_restoration_is_clamped_after_list_shrinks(self):
        result=node("""
const fs=require('fs'),vm=require('vm');
const source=fs.readFileSync('app.js','utf8').split('function renderShoppingWithoutViewportJumpV31(){')[1].split('function addShoppingItemV25')[0];
let scrolled=null;
const ctx={window:{scrollY:1800,scrollX:0,innerHeight:800,scrollTo:v=>scrolled=v},document:{activeElement:null,documentElement:{scrollHeight:1200}},$:id=>id==='viewShopping'?{classList:{contains:()=>true}}:null,renderShoppingList:()=>{},shoppingItems:[],requestAnimationFrame:f=>f(),Math};
vm.runInNewContext('function restore(){'+source+';restore()',ctx);
console.log(JSON.stringify(scrolled));
""")
        self.assertEqual(result['top'],400)

    def test_missing_nutrition_is_not_displayed_as_zero(self):
        result=node("""
const fs=require('fs'),vm=require('vm'),s=fs.readFileSync('app.js','utf8');
const ctx={};vm.runInNewContext(s.slice(s.indexOf('function recipeNutritionV28'),s.indexOf('function recipeMinutesV28')),ctx);
console.log(JSON.stringify([ctx.recipeNutritionV28({nutrition:{calories:100,fiber:0}}),ctx.completeNutritionV56({}),ctx.completeNutritionV56({calories:100,protein:0,fat:0,carbohydrates:25,fiber:0})]));
""")
        self.assertIsNone(result[0]['protein'])
        self.assertEqual(result[0]['fiber'],0)
        self.assertFalse(result[1]);self.assertTrue(result[2])

class LoyaltyPersistenceTests(unittest.TestCase):
    def test_old_clients_cannot_erase_card(self):
        api=importlib.import_module('api.plan')
        stored={'updatedAt':'old','meta':{'remaCustomerCode':'12345678'},'shoppingItems':[]}
        writes=[]
        def db(method,table,**kwargs):
            if method=='GET':return [{'data':stored}]
            writes.append(kwargs['payload']);return [kwargs['payload']]
        with patch.object(api,'supabase_request',side_effect=db):
            saved=api._persist_plan_with_retry('plan:test',{'updatedAt':'new','meta':{},'shoppingItems':[]})
        self.assertEqual(saved['meta']['remaCustomerCode'],'12345678')

    def test_set_card_changes_only_card_and_revision(self):
        api=importlib.import_module('api.plan')
        data={'updatedAt':'old','meta':{'favorites':['1']},'items':{'monday':[1]},'shoppingItems':[{'id':'a'}]}
        with patch.object(api,'read_body',return_value={'action':'setRemaCustomerCode','code':'12345678'}), patch.object(api,'supabase_request',return_value=[{'data':data}]), patch.object(api,'_persist_plan_with_retry') as persist, patch.object(api,'send_json'):
            api.handler.do_POST(object())
        sent=persist.call_args.args[1]
        self.assertEqual(sent['items'],data['items']);self.assertEqual(sent['shoppingItems'],data['shoppingItems'])
        self.assertEqual(sent['meta'],{'favorites':['1'],'remaCustomerCode':'12345678'})
        self.assertEqual(persist.call_args.kwargs['expected_revision'],'old')

    def test_invalid_card_does_not_touch_database(self):
        api=importlib.import_module('api.plan')
        with patch.object(api,'read_body',return_value={'action':'setRemaCustomerCode','code':'<svg>'}),patch.object(api,'send_json'),patch.object(api,'supabase_request') as db:
            api.handler.do_POST(object())
        db.assert_not_called()
