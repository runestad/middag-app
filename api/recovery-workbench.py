"""Read-only browser workbench for building a conservative recovery plan."""

import hashlib
import html
import json
import urllib.parse
from http.server import BaseHTTPRequestHandler

from ._common import APP_ID, row_to_recipe, send_json, supabase_request
from .recipe_health import stored_completeness


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(value):
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def source_url(recipe):
    for key in ("originalSourceUrl", "sourceUrl", "originalUrl", "link", "resolvedSourceUrl"):
        value = str(recipe.get(key) or "").strip()
        if value:
            return value
    return ""


def work_items(rows):
    items = []
    for row in rows:
        recipe = row_to_recipe(row)
        health = stored_completeness(recipe)
        if health["status"] != "INCOMPLETE":
            continue
        items.append({
            "id": str(recipe.get("id") or row.get("id") or ""),
            "title": recipe.get("name") or recipe.get("title") or "",
            "url": source_url(recipe),
            "recipe": recipe,
            "expectedDigest": digest(recipe),
            "missing": health["issues"],
        })
    return items


def workbench_html(items):
    payload = json.dumps(items, ensure_ascii=False).replace("</", "<\\/")
    return """<!doctype html><html lang=\"no\"><meta charset=\"utf-8\"><title>Recipe recovery workbench</title>
<style>body{font:15px system-ui;max-width:900px;margin:30px auto;padding:0 20px}button{padding:10px 16px}textarea{width:100%;height:260px}pre{white-space:pre-wrap}</style>
<h1>Recipe recovery workbench</h1><p>This page is read-only. It builds patches but never saves recipes.</p>
<button id=\"start\">Build dry-run plan</button> <strong id=\"progress\">Ready</strong><pre id=\"summary\"></pre>
<textarea id=\"plan\" readonly></textarea><script id=\"work-items\" type=\"application/json\">__PAYLOAD__</script>
<script>
const items=JSON.parse(document.querySelector('#work-items').textContent), plan=[];
const lines=v=>Array.isArray(v)?v.map(x=>typeof x==='object'?(x.text||x.item||x.original||x.name||''):String(x)).filter(x=>x.trim()):String(v||'').split(/\\n/).map(x=>x.trim()).filter(Boolean);
const valid=(ings,steps)=>ings.length>0&&steps.length>0&&!/^ingredients?$/i.test(ings.join(' '))&&!/^(see|se) (video|kilde)$/i.test(steps.join(' '))&&!ings.concat(steps).some(x=>/\\[object Object\\]|accept cookies|log in to continue/i.test(x));
function social(url){return /instagram|tiktok|facebook/i.test(url)}
function patchFromParsed(item,parsed,source){
  const old=item.recipe, patch={};
  const ingredients=(parsed.ingredients||[]).filter(x=>x&&String(x.item||x.original||x).trim());
  const steps=(parsed.instructions||[]).map(String).map(x=>x.trim()).filter(Boolean);
  const ingredientText=ingredients.map(x=>typeof x==='object'?[x.amount,x.unit,x.item,x.note].filter(Boolean).join(' '):String(x)).join('\\n');
  if(!lines(old.structuredIngredients).length&&!lines(old.ingredientLines).length&&!lines(old.ingredientsText).length&&ingredientText){patch.ingredientsText=ingredientText;patch.structuredIngredients=ingredients}
  if(!lines(old.structuredInstructions).length&&!lines(old.instructionSteps).length&&!lines(old.instructions).length&&steps.length){patch.instructions=steps.map((x,i)=>`${i+1}. ${x}`).join('\\n');patch.structuredInstructions=steps}
  if(!old.servings&&parsed.servings)patch.servings=parsed.servings;
  if(!old.image&&source.image)patch.image=source.image;
  patch.recoveryProvenance={method:social(item.url)?'social-caption-parser':'source-extractor',sourceUrl:item.url,confidence:parsed.confidence||source.importQuality?.status||'unknown',uncertainties:parsed.uncertainties||[]};
  const merged={...old,...patch}; return valid(lines(merged.structuredIngredients).length?lines(merged.structuredIngredients):lines(merged.ingredientsText),lines(merged.structuredInstructions).length?lines(merged.structuredInstructions):lines(merged.instructions))?patch:null;
}
async function processItem(item){
  if(!item.url)return{...item,group:'D',reason:'Ingen kilde lagret',patch:null};
  try{
    const fetched=await fetch('/api/fetch-recipe',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({url:item.url})}).then(r=>r.json());
    if(!fetched.ok)throw new Error(fetched.error||'Kilden kunne ikke hentes');
    const source=fetched.result||{}, direct={ingredients:(source.structuredIngredients||source.ingredientLines||lines(source.ingredientsText)),instructions:(source.structuredInstructions||source.instructionSteps||lines(source.instructions)),servings:source.servings,confidence:source.importQuality?.status};
    let parsed=direct, method='source-extractor';
    if(!valid(lines(direct.ingredients),lines(direct.instructions))&&source.caption&&source.caption.trim().length>=60){
      const response=await fetch('/api/parse-caption',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({caption:source.caption,recipeName:item.title,sourceUrl:item.url,category:item.recipe.category||''})}).then(r=>r.json());
      if(response.ok){parsed=response.parsed||{};method='social-caption-parser'}
    }
    const patch=patchFromParsed(item,parsed,source);
    if(patch)return{...item,group:social(item.url)?'B':'A',method,patch};
    return{...item,group:social(item.url)?'B':'C',reason:social(item.url)?'Kilden inneholder ikke nok oppskriftsinformasjon':'Kilden finnes, men uttrekket ga ikke komplett innhold',patch:null};
  }catch(error){return{...item,group:social(item.url)?'B':'C',reason:String(error.message||error),patch:null}}
}
async function worker(queue){while(queue.length){const item=queue.shift(),result=await processItem(item);plan.push(result);document.querySelector('#progress').textContent=`${plan.length} / ${items.length}`}}
document.querySelector('#start').onclick=async()=>{document.querySelector('#start').disabled=true;const queue=[...items];await Promise.all(Array.from({length:4},()=>worker(queue)));plan.sort((a,b)=>a.title.localeCompare(b.title));const counts=plan.reduce((a,x)=>(a[x.group]=(a[x.group]||0)+1,a),{});const recoverable=plan.filter(x=>x.patch).length;document.querySelector('#summary').textContent=JSON.stringify({total:plan.length,recoverable,remaining:plan.length-recoverable,groups:counts},null,2);document.querySelector('#plan').value=JSON.stringify(plan,null,2);document.querySelector('#progress').textContent='Complete'};
</script></html>""".replace("__PAYLOAD__", payload)


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            query = urllib.parse.urlencode({"app_id": "eq." + APP_ID, "select": "*", "order": "name.asc", "limit": "5000"})
            rows = supabase_request("GET", "recipes", query=query) or []
            body = workbench_html(work_items(rows)).encode("utf-8")
            self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store"); self.send_header("Content-Length", str(len(body)))
            self.end_headers(); self.wfile.write(body)
        except Exception as exc:
            send_json(self, {"ok": False, "error": f"{type(exc).__name__}: {exc}"}, 500)
