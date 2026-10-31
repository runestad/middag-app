"""Regression coverage for recipes split across ingredient and method screenshots."""
import base64
import importlib
import io
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from api import media_analysis as media

ROOT = Path(__file__).resolve().parents[1]
PARSER = importlib.import_module('api.parse-caption')
JPEG = 'data:image/jpeg;base64,/9j/AA=='
METHOD = 'Stek bunnen alene først, ca 15 min på 220 g (til den blir gyllen). Lag hjemmelaget tomatsaus å ha på valgfritt digg tilbehør. Mozzarella på toppen.'
INGREDIENTS = 'Protein pizza. Bunn: 400 gram mager cottage cheese, 4 egg, 300 gram havregryn, 2 ts bakepulver, salt.'


class ScreenshotEndpointTests(unittest.TestCase):
    def call(self, payload, text=METHOD):
        raw = json.dumps(payload).encode()
        handler = object.__new__(PARSER.handler)
        handler.path = '/api/parse-caption?media=1'
        handler.headers = {'Content-Length': str(len(raw))}
        handler.rfile = io.BytesIO(raw)
        response = {'choices': [{'message': {'content': json.dumps({'text': text})}}]}
        replies = []
        with patch.dict(media.os.environ, {'OPENAI_API_KEY': 'test-only-placeholder'}), \
             patch.object(media.urllib.request, 'urlopen', return_value=io.BytesIO(json.dumps(response).encode())) as upstream, \
             patch.object(media, 'send_json', side_effect=lambda h, data, status=200: replies.append((status, data))):
            PARSER.handler.do_POST(handler)
        return replies[0], upstream

    def test_method_only_image_reaches_vision_and_returns_verbatim_evidence(self):
        reply, upstream = self.call({'kind': 'screenshot', 'image': JPEG})
        self.assertEqual(reply, (200, {'ok': True, 'text': METHOD}))
        body = json.loads(upstream.call_args.args[0].data)
        self.assertEqual(body['messages'][1]['content'][0]['image_url'], {'url': JPEG, 'detail': 'high'})

    def test_safari_jpeg_and_webp_compression_outputs_are_supported(self):
        webp = 'data:image/webp;base64,' + base64.b64encode(b'RIFF0000WEBPtest').decode()
        for image in (JPEG, webp):
            with self.subTest(image=image):
                self.assertEqual(self.call({'kind': 'screenshot', 'image': image})[0][0], 200)

    def test_bad_remote_or_oversize_images_do_not_reach_ai(self):
        oversized = 'data:image/jpeg;base64,' + base64.b64encode(b'\xff\xd8\xff' + b'0' * 750_000).decode()
        for image in ('https://example.org/image.jpg', JPEG.replace('/9j/AA==', 'YmFk'), oversized):
            reply, upstream = self.call({'kind': 'screenshot', 'image': image})
            self.assertEqual(reply[0], 400)
            upstream.assert_not_called()

    def test_missing_ai_text_is_an_error_not_successfully_empty(self):
        reply, _ = self.call({'kind': 'screenshot', 'image': JPEG}, text=None)
        self.assertFalse(reply[1]['ok'])


class ScreenshotPipelineTests(unittest.TestCase):
    def run_pipeline(self, texts=(METHOD, INGREDIENTS), failure=-1, cancel=-1, previous=''):
        js = (ROOT / 'app.js').read_text()
        code = js[js.index('async function processScreenshotsV26()'):js.index('\nsaveParsedRecipe = async function()', js.index('async function processScreenshotsV26()'))]
        setup = '''
const texts=TEXTS, requests=[], parsed=[], busy=[], statuses=[];
const elements={screenshotInput:{files:texts.map((_,index)=>({index}))},captionInput:{value:PREVIOUS},ocrStatus:{textContent:''},parsedInstructions:{value:'Tidligere fremgangsmåte'}};
const $=id=>elements[id];let importRunV26=0,activeImportId='draft',importBusyV50=false,importSavingV50=false,mediaEvidenceV52=null;
const currentImportV50=id=>id===activeImportId;
const setImportBusyV50=value=>{importBusyV50=value;busy.push(value)};
const setImportProgressV26=()=>{};
const RecipeImage={prepare:async file=>file};const mediaDataURLV52=async file=>'compressed-image-'+file.index;
async function importRequestV50(endpoint,payload){
 if(!importBusyV50)throw new Error('Draft unlocked during image reading');
 const i=requests.length;requests.push({endpoint,payload});
 if(i===CANCEL){activeImportId='another-draft';importRunV26++;setImportBusyV50(false)}
 if(i===FAILURE)throw new Error('Midlertidig feil');
 return {ok:true,text:texts[i]};
}
async function parseCaptionAI(){parsed.push(elements.captionInput.value);importRunV26++;setImportBusyV50(false)}
'''.replace('TEXTS', json.dumps(texts)).replace('PREVIOUS', json.dumps(previous)).replace('CANCEL', str(cancel)).replace('FAILURE', str(failure))
        ending = '''
processScreenshotsV26().then(()=>console.log(JSON.stringify({requests,parsed,busy,caption:elements.captionInput.value,status:elements.ocrStatus.textContent,instructions:elements.parsedInstructions.value,evidence:mediaEvidenceV52})));
'''
        return json.loads(subprocess.check_output(['node', '-e', setup + code + ending], text=True, cwd=ROOT))

    def test_both_image_orders_send_all_evidence_to_one_parser_call(self):
        for texts in ((METHOD, INGREDIENTS), (INGREDIENTS, METHOD)):
            result = self.run_pipeline(texts)
            self.assertEqual(len(result['requests']), 2)
            self.assertEqual(len(result['parsed']), 1)
            self.assertIn(METHOD, result['parsed'][0])
            self.assertIn(INGREDIENTS, result['parsed'][0])
            self.assertEqual([r['payload']['image'] for r in result['requests']], ['compressed-image-0', 'compressed-image-1'])
            self.assertEqual(result['busy'], [True, False])

    def test_later_image_can_supplement_existing_source(self):
        result = self.run_pipeline((METHOD,), previous=INGREDIENTS)
        self.assertIn(INGREDIENTS, result['parsed'][0])
        self.assertIn(METHOD, result['parsed'][0])

    def test_failed_second_image_preserves_draft_without_partial_parse(self):
        result = self.run_pipeline(failure=1, previous='Eksisterende kildetekst')
        self.assertEqual(result['parsed'], [])
        self.assertEqual(result['caption'], 'Eksisterende kildetekst')
        self.assertEqual(result['instructions'], 'Tidligere fremgangsmåte')
        self.assertFalse(result['busy'][-1])
        self.assertIn('Midlertidig feil', result['status'])

    def test_unreadable_image_is_identified_and_good_image_still_used(self):
        result = self.run_pipeline((INGREDIENTS, ''))
        self.assertIn('Bilde 2 ga ingen lesbar', result['status'])
        self.assertEqual(len(result['parsed']), 1)
        self.assertTrue(result['evidence']['warnings'])

    def test_all_empty_images_preserve_existing_source(self):
        result = self.run_pipeline(('', ''), previous=INGREDIENTS)
        self.assertEqual(result['caption'], INGREDIENTS)
        self.assertEqual(result['parsed'], [])
        self.assertIn('ingen lesbar', result['status'])
        self.assertFalse(result['busy'][-1])

    def test_closed_or_replaced_draft_ignores_late_response(self):
        result = self.run_pipeline(cancel=0, previous='Behold')
        self.assertEqual(len(result['requests']), 1)
        self.assertEqual(result['parsed'], [])
        self.assertEqual(result['caption'], 'Behold')


if __name__ == '__main__':
    unittest.main()
