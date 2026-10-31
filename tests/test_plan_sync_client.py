import json
import pathlib
import subprocess
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


class PlanSyncClientTests(unittest.TestCase):
    def test_sync_uses_json_revision_when_headers_are_unavailable(self):
        app = (ROOT / "app.js").read_text()
        source = app[app.index("let syncInFlightV55"):app.index("startRealtimeSync = function(){", app.index("let syncInFlightV55"))]
        program = """
          const assert = require('node:assert/strict');
          let syncFromServer, isSavingPlan=false, saveRevisionV25=0, savedRevisionV25=0, lastLocalSaveAt=0;
          const document={hidden:false}, navigator={onLine:true};
          const appMeta={updatedAt:'same'};
          let lastRemoteUpdatedAt='same';
          const setLiveStatus=()=>{}, setShoppingStatusV25=()=>{};
          const calls=[];
          const revision='W/"plan-v2-example"';
          const fetch=async (url, options)=>{
            calls.push({url, options});
            return {status:200, ok:true, headers:{get:()=>null}, json:async()=> calls.length===1
              ? {ok:true, plan:{updatedAt:'same'}, revision}
              : {ok:true, unchanged:true, revision}};
          };
        """ + source + """
          (async()=>{
            await syncFromServer();
            assert.equal(syncEtagV55, revision);
            syncLastAttemptV55=0;
            await syncFromServer();
            assert.equal(new URL(calls[1].url, 'https://example.com').searchParams.get('since'), revision);
            assert.equal(syncInFlightV55, false);
            document.hidden=true;
            syncLastAttemptV55=0;
            await syncFromServer();
            assert.equal(calls.length,2);
            process.stdout.write(JSON.stringify({ok:true}));
          })().catch(error=>{console.error(error);process.exit(1)});
        """
        result = subprocess.run(["node", "-e", program], cwd=ROOT, text=True, capture_output=True, check=True)
        self.assertEqual(json.loads(result.stdout), {"ok": True})


if __name__ == "__main__":
    unittest.main()
