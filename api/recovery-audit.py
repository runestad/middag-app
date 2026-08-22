"""Authenticated-deployment recovery audit surface.

The endpoint deliberately performs no writes. Vercel Deployment Protection is
the access boundary used by the existing application, just like /api/recipes.
"""

import collections
import hashlib
import html
import json
import urllib.parse
from http.server import BaseHTTPRequestHandler

from ._common import APP_ID, row_to_recipe, send_json, supabase_request
from .recipe_health import classify_source, stored_completeness


def recipe_url(recipe):
    for key in ("originalSourceUrl", "sourceUrl", "originalUrl", "link", "resolvedSourceUrl"):
        value = str(recipe.get(key) or "").strip()
        if value:
            return value
    return ""


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(value):
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def work_items(rows):
    items = []
    for row in rows:
        recipe = row_to_recipe(row)
        health = stored_completeness(recipe)
        if health["status"] == "INCOMPLETE":
            items.append({"id": str(recipe.get("id") or row.get("id") or ""), "title": recipe.get("name") or recipe.get("title") or "",
                          "url": recipe_url(recipe), "recipe": recipe, "expectedDigest": digest(recipe), "missing": health["issues"]})
    return items


def audit_item(recipe):
    health = stored_completeness(recipe)
    url = recipe_url(recipe)
    source_type = classify_source(url)
    has_ingredients = "missing_ingredients" not in health["issues"]
    has_instructions = "missing_instructions" not in health["issues"]
    social = source_type.startswith(("TIKTOK", "INSTAGRAM", "FACEBOOK"))
    if health["status"] != "INCOMPLETE":
        group = "COMPLETE"
    elif not url or source_type in ("NO_SOURCE", "MALFORMED_URL"):
        group = "D"
    elif social:
        group = "B"
    else:
        # Reachability/extraction inspection refines A into C after the stored
        # snapshot. Until then, a valid ordinary source is an A candidate.
        group = "A"
    return {
        "id": str(recipe.get("id") or ""),
        "title": recipe.get("name") or recipe.get("title") or "",
        "sourceUrl": url,
        "resolvedSourceUrl": str(recipe.get("resolvedSourceUrl") or ""),
        "sourceType": source_type,
        "hasIngredients": has_ingredients,
        "hasInstructions": has_instructions,
        "hasServings": bool(str(recipe.get("servings") or "").strip()),
        "hasImage": bool(recipe.get("image") or recipe.get("thumbnail") or recipe.get("verifiedFallbackImage")),
        "previousRecoveryAttempt": bool(recipe.get("sourceLastChecked") or recipe.get("extractionMethod") or recipe.get("importQuality") or recipe.get("recovery")),
        "incompleteReasons": health["issues"],
        "initialGroup": group,
        "ingredientCount": health["ingredientCount"],
        "instructionCount": health["instructionCount"],
    }


def build_audit(recipes):
    items = [audit_item(recipe) for recipe in recipes]
    incomplete = [item for item in items if item["initialGroup"] != "COMPLETE"]
    counts = collections.Counter(item["initialGroup"] for item in incomplete)
    return {
        "totalRecipes": len(items),
        "completeRecipes": len(items) - len(incomplete),
        "incompleteRecipes": len(incomplete),
        "missingIngredients": sum(not item["hasIngredients"] for item in incomplete),
        "missingInstructions": sum(not item["hasInstructions"] for item in incomplete),
        "missingBoth": sum(not item["hasIngredients"] and not item["hasInstructions"] for item in incomplete),
        "initialGroups": {key: counts.get(key, 0) for key in "ABCDE"},
        "items": items,
    }


def production_rows():
    query = urllib.parse.urlencode({"app_id": "eq." + APP_ID, "select": "*", "order": "name.asc", "limit": "5000"})
    return supabase_request("GET", "recipes", query=query) or []


def audit_html(audit, backup_rows=None):
    payload = json.dumps(audit, ensure_ascii=False).replace("</", "<\\/")
    backup = json.dumps(backup_rows or [], ensure_ascii=False).replace("</", "<\\/")
    summary = {key: value for key, value in audit.items() if key != "items"}
    return """<!doctype html><html lang=\"no\"><meta charset=\"utf-8\"><title>Recipe recovery audit</title>
<body><h1>Recipe recovery audit</h1><pre id=\"summary\">{summary}</pre>
<script id=\"recipe-audit-data\" type=\"application/json\">{payload}</script>
<script id=\"recipe-backup-data\" type=\"application/json\">{backup}</script></body></html>""".format(
        summary=html.escape(json.dumps(summary, ensure_ascii=False, indent=2)), payload=payload, backup=backup
    )


def workbench_html(items):
    payload = json.dumps(items, ensure_ascii=False).replace("</", "<\\/")
    template = """<!doctype html><html lang=\"no\"><meta charset=\"utf-8\"><title>Recipe recovery workbench</title>
<style>body{font:15px system-ui;max-width:900px;margin:30px auto;padding:0 20px}button{padding:10px 16px}textarea{width:100%;height:260px}pre{white-space:pre-wrap}</style>
<h1>Recipe recovery workbench</h1><p>This page is read-only. It builds patches but never saves recipes.</p>
<textarea id=\"manualCaption\" placeholder=\"Optional externally fetched public caption\"></textarea>
<button id=\"start\">Build dry-run plan</button> <strong id=\"progress\">Ready</strong><pre id=\"summary\"></pre>
<textarea id=\"plan\" readonly></textarea><script id=\"work-items\" type=\"application/json\">__PAYLOAD__</script>
<script>
const items=JSON.parse(document.querySelector('#work-items').textContent), plan=[];
const lines=v=>Array.isArray(v)?v.map(x=>typeof x==='object'?(x.text||x.item||x.original||x.name||''):String(x)).filter(x=>x.trim()):String(v||'').split(/\\n/).map(x=>x.trim()).filter(Boolean);
const valid=(ings,steps)=>ings.length>0&&steps.length>0&&!/^ingredients?$/i.test(ings.join(' '))&&!/^(see|se) (video|kilde)$/i.test(steps.join(' '))&&!ings.concat(steps).some(x=>/\\[object Object\\]|accept cookies|log in to continue/i.test(x));
const social=url=>/instagram|tiktok|facebook/i.test(url);
function patchFromParsed(item,parsed,source){if(parsed.confidence==='low')return null;const old=item.recipe,patch={};const ingredients=(parsed.ingredients||[]).filter(x=>x&&String(x.item||x.original||x).trim());const steps=(parsed.instructions||[]).map(String).map(x=>x.trim()).filter(Boolean);const ingredientText=ingredients.map(x=>typeof x==='object'?[x.amount,x.unit,x.item,x.note].filter(Boolean).join(' '):String(x)).join('\\n');if(!lines(old.structuredIngredients).length&&!lines(old.ingredientLines).length&&!lines(old.ingredientsText).length&&ingredientText){patch.ingredientsText=ingredientText;patch.structuredIngredients=ingredients}if(!lines(old.structuredInstructions).length&&!lines(old.instructionSteps).length&&!lines(old.instructions).length&&steps.length){patch.instructions=steps.map((x,i)=>`${i+1}. ${x}`).join('\\n');patch.structuredInstructions=steps}if(!old.servings&&parsed.servings)patch.servings=parsed.servings;if(!old.image&&source.image)patch.image=source.image;patch.recoveryProvenance={method:social(item.url)?'social-caption-parser':'source-extractor',sourceUrl:item.url,confidence:parsed.confidence||source.importQuality?.status||'unknown',uncertainties:parsed.uncertainties||[]};const merged={...old,...patch};return valid(lines(merged.structuredIngredients).length?lines(merged.structuredIngredients):lines(merged.ingredientsText),lines(merged.structuredInstructions).length?lines(merged.structuredInstructions):lines(merged.instructions))?patch:null}
async function processItem(item){if(!item.url)return{...item,recipe:undefined,group:'D',reason:'Ingen kilde lagret',patch:null};try{const supplied=document.querySelector('#manualCaption').value.trim(),fetched=supplied&&items.length===1?{ok:true,result:{caption:supplied}}:await fetch('/api/fetch-recipe',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({url:item.url})}).then(r=>r.json());if(!fetched.ok)throw new Error(fetched.error||'Kilden kunne ikke hentes');const source=fetched.result||{},direct={ingredients:(source.structuredIngredients||source.ingredientLines||lines(source.ingredientsText)),instructions:(source.structuredInstructions||source.instructionSteps||lines(source.instructions)),servings:source.servings,confidence:source.importQuality?.status};let parsed=direct,method='source-extractor',parseError='';if(!valid(lines(direct.ingredients),lines(direct.instructions))&&source.caption&&source.caption.trim().length>=60){for(let attempt=0;attempt<3;attempt++){const response=await fetch('/api/parse-caption',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({caption:source.caption,recipeName:item.title,sourceUrl:item.url,category:item.recipe.category||''})});const result=await response.json();if(response.ok&&result.ok){parsed=result.parsed||{};method=supplied?'external-caption-parser':'social-caption-parser';parseError='';break}parseError=result.error||`Parser HTTP ${response.status}`;if(attempt<2)await new Promise(resolve=>setTimeout(resolve,(attempt+1)*1500))}}const patch=patchFromParsed(item,parsed,source);if(patch)return{...item,recipe:undefined,group:social(item.url)?'B':'A',method,patch};return{...item,recipe:undefined,group:social(item.url)?'B':'C',reason:parseError||(social(item.url)?'Kilden inneholder ikke nok oppskriftsinformasjon':'Kilden finnes, men uttrekket ga ikke komplett innhold'),diagnostics:{captionLength:(source.caption||'').length,parsedIngredients:lines(parsed.ingredients).length,parsedInstructions:lines(parsed.instructions).length,confidence:parsed.confidence||'',uncertainties:(parsed.uncertainties||[]).length},patch:null}}catch(error){return{...item,recipe:undefined,group:social(item.url)?'B':'C',reason:String(error.message||error),patch:null}}}
async function worker(queue){while(queue.length){const result=await processItem(queue.shift());plan.push(result);document.querySelector('#progress').textContent=`${plan.length} / ${items.length}`}}
document.querySelector('#start').onclick=async()=>{document.querySelector('#start').disabled=true;const queue=[...items];await Promise.all(Array.from({length:4},()=>worker(queue)));plan.sort((a,b)=>a.title.localeCompare(b.title));const counts=plan.reduce((a,x)=>(a[x.group]=(a[x.group]||0)+1,a),{}),recoverable=plan.filter(x=>x.patch).length;document.querySelector('#summary').textContent=JSON.stringify({total:plan.length,recoverable,remaining:plan.length-recoverable,groups:counts},null,2);document.querySelector('#plan').value=JSON.stringify(plan,null,2);document.querySelector('#progress').textContent='Complete'};
</script></html>"""
    return template.replace("__PAYLOAD__", payload)


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            rows = production_rows()
            if "workbench=1" in self.path:
                items = work_items(rows)
                requested = set(urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query).get("ids", [""])[0].split(",")) - {""}
                if requested:
                    items = [item for item in items if item["id"] in requested]
                body = workbench_html(items).encode("utf-8")
                self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Cache-Control", "no-store"); self.send_header("Content-Length", str(len(body)))
                self.end_headers(); self.wfile.write(body); return
            audit = build_audit([row_to_recipe(row) for row in rows])
            if "format=json" in self.path:
                return send_json(self, {"ok": True, "audit": audit})
            body = audit_html(audit, rows if "backup=1" in self.path else None).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except Exception as exc:
            send_json(self, {"ok": False, "error": f"{type(exc).__name__}: {exc}"}, 500)
