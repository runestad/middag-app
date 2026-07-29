
const DAYS=["mandag","tirsdag","onsdag","torsdag","fredag","lørdag","søndag"];
const CATEGORIES=["Frukt og grønt","Kjøtt","Kjølevarer","Meieri","Frys","Hermetikk/halvfabrikat","Tørrvarer","Krydder","Glutenfritt","Bakevarer","Annet"];
let recipes=[],plan={},shoppingItems=[],customRecipes=JSON.parse(localStorage.getItem("middag_custom_recipes")||"{}"),activeImportId=null,activePickerDay=null,pendingAddRecipeId=null;
let appMeta={favorites:[],usageCounts:{},lastUsed:{},updatedAt:""},lastRemoteUpdatedAt="",syncTimer=null;
let freezerItems=[];
const $=id=>document.getElementById(id);
function normalize(s){return String(s||"").toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g,"").trim()}
function capitalize(s){return s.charAt(0).toUpperCase()+s.slice(1)}
function recipeById(id){return recipes.find(r=>String(r.id)===String(id))}
function hasRecipe(r){return Boolean((r?.ingredientsText&&r.ingredientsText.trim())||(r?.instructions&&String(r.instructions).trim())||(r?.structuredIngredients&&r.structuredIngredients.length))}
function getTags(r){const tags=new Set();if(Array.isArray(r.tags))r.tags.forEach(t=>tags.add(String(t).toLowerCase()));if(r.category)tags.add(String(r.category).toLowerCase());const text=normalize(`${r.name} ${r.category} ${r.ingredientsText||""} ${r.instructions||""}`);const rules=[["suppe",["suppe","soup","broth"]],["vegetar",["vegetar","veggie","tofu","linse","kikerter","aubergine"]],["kylling",["kylling","chicken"]],["pasta",["pasta","spaghetti","orzo","tagliatelle","fettuccine"]],["salat",["salat","salad"]],["taco",["taco","wrap","fajita"]],["airfryer",["airfryer","air fryer"]],["fisk",["fisk","shrimp","reker","scampi","ørret","laks"]],["glutenfritt",["glutenfri","gluten free"]],["rask",["15 minute","20 minute","rask","enkel"]],["asiatisk",["soy","soya","sesam","gochujang","thai","ramen","noodle","nudler"]],["indisk",["indisk","curry","masala","butter chicken"]]];for(const[tag,words]of rules)if(words.some(w=>text.includes(normalize(w))))tags.add(tag);return[...tags].slice(0,10)}
function enrichTags(r){const tags=new Set(getTags(r));const text=normalize(`${r.name} ${r.category} ${r.ingredientsText||""} ${r.instructions||""}`);if(text.includes("glutenfri"))tags.add("glutenfritt");return[...tags]}
function emojiForRecipe(r){if(r.emoji)return r.emoji;const t=normalize(`${r.name} ${r.category} ${enrichTags(r).join(" ")}`);if(t.includes("suppe"))return"🍲";if(t.includes("salat"))return"🥗";if(t.includes("pasta")||t.includes("spaghetti"))return"🍝";if(t.includes("taco")||t.includes("wrap")||t.includes("fajita"))return"🌮";if(t.includes("pizza"))return"🍕";if(t.includes("kylling"))return"🍗";if(t.includes("fisk")||t.includes("shrimp")||t.includes("scampi"))return"🍤";if(t.includes("biff")||t.includes("kjøtt"))return"🥩";if(t.includes("ramen")||t.includes("nudler")||t.includes("noodle"))return"🍜";if(t.includes("curry")||t.includes("indisk"))return"🍛";if(t.includes("airfryer"))return"🔥";if(t.includes("vegetar"))return"🥦";return"🍽️"}
function mergeCustomData(){recipes=recipes.map(r=>mergePreservingExistingData(r,customRecipes[r.id]||{}))}
async function init(){const rr=await fetch("/api/recipes").then(r=>r.json());recipes=rr.recipes||[];mergeCustomData();const pr=await fetch("/api/plan").then(r=>r.json()).catch(()=>({plan:{}}));plan=migratePlan(pr.plan?.items||pr.plan||{});shoppingItems=pr.plan?.shoppingItems||[];appMeta=pr.plan?.meta||appMeta;freezerItems=pr.plan?.freezerItems||defaultFreezerItems();lastRemoteUpdatedAt=pr.plan?.updatedAt||"";fillDaySelectorsV20();fillAddToDaySelect();$("recipeCount").textContent=`${recipes.length} oppskrifter`;bindAll();createDayRows();renderRecipeResults();renderShoppingList(shoppingItems);renderFreezer();startRealtimeSync()}
function bindAll(){const binds={createDaysBtn:createDayRows,generateListBtn:generateShoppingList,resetShoppingBtn:resetShoppingList,resetPlanInlineBtn:resetPlan,recipeSearch:renderRecipeResults,recipeSort:renderRecipeResults,addRecipeBtn:openAddRecipe,parseCaptionBtn:parseCaption,saveParsedBtn:saveParsedRecipe,aiParseCaptionBtn:parseCaptionAI,randomWeekBtn:randomWeek,aiWeekBtn:smartWeek,confirmAddToDayBtn:confirmAddToDay,pickerSearch:renderPickerResults,cleanupRecipesBtn:cleanupVisibleRecipes,addFreezerItemBtn:addFreezerItem,freezerSuggestBtn:freezerSuggest};for(const[id,fn]of Object.entries(binds)){const el=$(id);if(!el)continue;el.addEventListener((id==="recipeSearch"||id==="pickerSearch")?"input":"click",fn)}if($("recipeSort"))$("recipeSort").addEventListener("change",renderRecipeResults);if($("readScreenshotsBtn"))$("readScreenshotsBtn").addEventListener("click",readScreenshotsWithOCR);if($("clearCaptionBtn"))$("clearCaptionBtn").addEventListener("click",()=>{$("captionInput").value="";window.lastAiParsedRecipe=null});document.querySelectorAll(".nav-btn").forEach(btn=>btn.addEventListener("click",()=>showView(btn.dataset.view)));
["startDate","endDate"].forEach(id=>{const el=$(id);if(el)el.addEventListener("change",()=>{updateDateLabels();createDayRows();})});
}
function migratePlan(raw){const out={};for(const d of DAYS){const v=raw?.[d];out[d]=Array.isArray(v)?v:(v?[{type:"recipe",recipeId:v}]:[])}return out}
function showView(v){document.querySelectorAll(".view").forEach(x=>x.classList.toggle("active",x.id===v));document.querySelectorAll(".nav-btn").forEach(b=>b.classList.toggle("active",b.dataset.view===v))}
function fillDaySelectors(){for(const id of["startDay","endDay"])$(id).innerHTML=DAYS.map(d=>`<option value="${d}">${capitalize(d)}</option>`).join("");$("startDay").value="mandag";$("endDay").value="fredag"}
function fillAddToDaySelect(){if($("addToDaySelect"))$("addToDaySelect").innerHTML=selectedDays().map(d=>`<option value="${d}">${capitalize(d)}</option>`).join("")}
function selectedDays(){const s=DAYS.indexOf($("startDay").value),e=DAYS.indexOf($("endDay").value),out=[];let i=s;while(true){out.push(DAYS[i]);if(i===e)break;i=(i+1)%DAYS.length}return out}
function setLiveStatus(t,cls=""){const el=$("liveStatus");if(!el)return;el.textContent="● "+t;el.className="live-status"+(cls?` ${cls}`:"")}
function savePlan(){appMeta.updatedAt=new Date().toISOString();localStorage.setItem("middag_plan",JSON.stringify(plan));fetch("/api/plan",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({plan:{items:plan,shoppingItems,freezerItems,meta:appMeta,updatedAt:appMeta.updatedAt}})}).catch(e=>{console.warn(e);setLiveStatus("Sync-feil","error")})}
function startRealtimeSync(){if(syncTimer)clearInterval(syncTimer);syncTimer=setInterval(syncFromServer,5000);setLiveStatus("Live")}
async function syncFromServer(){try{setLiveStatus("Syncer","syncing");const pr=await fetch("/api/plan").then(r=>r.json());const remote=pr.plan?.updatedAt||"";if(remote&&remote!==lastRemoteUpdatedAt&&remote!==appMeta.updatedAt){plan=migratePlan(pr.plan?.items||{});shoppingItems=pr.plan?.shoppingItems||shoppingItems;freezerItems=pr.plan?.freezerItems||freezerItems;appMeta=pr.plan?.meta||appMeta;lastRemoteUpdatedAt=remote;createDayRows();renderShoppingList(shoppingItems);renderRecipeResults()}const rr=await fetch("/api/recipes").then(r=>r.json());if(rr.recipes&&rr.recipes.length!==recipes.length){recipes=rr.recipes;mergeCustomData();renderRecipeResults();createDayRows()}setLiveStatus("Live")}catch(e){setLiveStatus("Offline?","error")}}
function resetPlan(){if(!confirm("Nullstille ukeplanen?"))return;plan={};for(const d of DAYS)plan[d]=[];savePlan();createDayRows()}
function resetShoppingList(){if(!confirm("Nullstille handlelisten?"))return;shoppingItems=[];savePlan();renderShoppingList(shoppingItems)}
function createDayRows(){const c=$("dayRows"),days=selectedDays();fillAddToDaySelect();for(const d of days)if(!Array.isArray(plan[d]))plan[d]=[];c.innerHTML="";for(const day of days){const card=document.createElement("div");card.className="day-row day-card-v16";card.innerHTML=`<div class="day-head-v16"><h3>${day}</h3><button class="ghost" data-picker="${day}">+ Oppskrift</button></div><input class="day-text-input" data-free="${day}" placeholder="Skriv rett manuelt, f.eks. Grillmat"><div class="day-actions-row"><button class="ghost" data-addtext="${day}">+ Legg til tekstrett</button><button class="ghost" data-clear="${day}">Tøm dag</button></div><div class="day-items"></div>`;c.appendChild(card);card.querySelector("[data-picker]").addEventListener("click",()=>openRecipePicker(day));card.querySelector("[data-addtext]").addEventListener("click",()=>addFreeTextToDay(day,card.querySelector("[data-free]").value));card.querySelector("[data-clear]").addEventListener("click",()=>{plan[day]=[];savePlan();createDayRows()});renderDayItems(card,day)}}
function renderDayItems(card,day){const box=card.querySelector(".day-items"),items=plan[day]||[];if(!items.length){box.innerHTML=`<div class="empty-state">Ingen retter lagt til.</div>`;return}box.innerHTML=items.map((item,idx)=>{if(item.type==="text")return`<div class="plan-item text-plan-item"><div><div class="plan-item-title">✍️ ${escapeHtml(item.text)}</div><div class="plan-item-meta">Manuell rett – legg varer manuelt i handlelisten</div></div><div class="plan-actions"><button class="mini-action" onclick="addManualDishToShopping('${escapeAttr(item.text)}')">+ varer</button><button class="remove-btn" onclick="removePlanItem('${day}',${idx})">×</button></div></div>`;const r=recipeById(item.recipeId);if(!r)return`<div class="plan-item missing-plan-item"><div><div class="plan-item-title">Oppskrift ikke funnet</div></div><button class="remove-btn" onclick="removePlanItem('${day}',${idx})">×</button></div>`;const found=hasRecipe(r),cls=found?"recipe-plan-item":"missing-plan-item",meta=`${r.category||"Ukjent"} · brukt ${usageCount(r.id)}× · ${found?"oppskrift funnet":"oppskrift mangler"}`;return`<div class="plan-item ${cls}"><div><div class="plan-item-title">${escapeHtml(emojiForRecipe(r)+" "+r.name)}</div><div class="plan-item-meta">${escapeHtml(meta)}</div></div><div class="plan-actions">${found?`<button class="mini-action" onclick="openRecipeDetails('${escapeAttr(r.id)}')">Se</button>`:`<button class="mini-action" onclick="openImport('${escapeAttr(r.id)}')">Legg inn</button>`}<button class="remove-btn" onclick="removePlanItem('${day}',${idx})">×</button></div></div>`}).join("")}
window.removePlanItem=(day,idx)=>{plan[day].splice(idx,1);savePlan();createDayRows()}
window.addManualDishToShopping=function(dish){const text=prompt(`Legg til vare til "${dish}" i handlelisten:`);if(!text||!text.trim())return;shoppingItems.push({text:text.trim(),category:categorize(text),recipe:dish,done:false});renderShoppingList(shoppingItems);savePlan();showView("viewShopping")}
function addFreeTextToDay(day,text){const t=String(text||"").trim();if(!t)return;plan[day].push({type:"text",text:t});savePlan();createDayRows()}
function openRecipePicker(day){activePickerDay=day;$("pickerSearch").value="";renderPickerResults();$("recipePickerDialog").showModal()}
function renderPickerResults(){const q=normalize($("pickerSearch").value);const f=recipes.filter(r=>!q||searchableText(r).includes(q)).sort((a,b)=>Number(hasRecipe(b))-Number(hasRecipe(a))||a.name.localeCompare(b.name,"no")).slice(0,300);$("pickerResults").innerHTML=f.map(r=>`<div class="recipe-card" onclick="addRecipeToDay('${activePickerDay}','${escapeAttr(r.id)}')"><div class="recipe-thumb recipe-emoji">${emojiForRecipe(r)}</div><div><strong>${escapeHtml(r.name)}</strong><div class="recipe-meta">${escapeHtml(r.category||"Ukjent")} · ${hasRecipe(r)?"✅":"🟡 mangler"}</div></div><button type="button" class="ghost">Legg til</button></div>`).join("")}
window.addRecipeToDay=(day,id)=>{plan[day].push({type:"recipe",recipeId:id});bumpUsage(id);savePlan();createDayRows();renderRecipeResults();$("recipePickerDialog").close()}
function openAddRecipe(){const id=`custom-${Date.now()}`;recipes.push({id,name:"Ny oppskrift",category:"Annet",source:"Manuell",link:"",ingredientsText:"",instructions:"",tags:[]});activeImportId=id;$("importTarget").textContent="Lagrer som ny oppskrift";$("importLinkWrap").innerHTML="Legg inn navn, lenke og caption/oppskriftstekst.";$("importName").value="";$("importLink").value="";$("importCategory").value="Annet";$("importServings").value="";$("captionInput").value="";$("parsedIngredients").value="";$("parsedInstructions").value="";window.lastAiParsedRecipe=null;$("importDialog").showModal()}
function openImport(id){activeImportId=id;const r=recipeById(id),sourceUrl=resolveRecipeSourceUrl(r);$("importTarget").textContent=`Lagrer på: ${r.name}`;$("importLinkWrap").innerHTML=sourceUrl?`Kilde: <a href="${escapeAttr(sourceUrl)}" target="_blank" rel="noopener">åpne originaloppskrift</a>`:"Ingen kilde registrert";$("importName").value=r.name||"";$("importLink").value=sourceUrl;$("importCategory").value=r.category||"Annet";$("importServings").value=r.servings||"";$("captionInput").value="";$("parsedIngredients").value=ingredientsToText(r);$("parsedInstructions").value=instructionsToText(r);window.lastAiParsedRecipe=null;$("importDialog").showModal()}
async function parseCaptionAI(){const caption=$("captionInput").value.trim(),status=$("aiStatus"),btn=$("aiParseCaptionBtn"),r=recipeById(activeImportId)||{};if(!caption)return alert("Lim inn caption/oppskriftstekst først.");try{btn.disabled=true;btn.textContent="AI parser …";status.textContent="Sender tekst til AI-parser …";const res=await fetch("/api/parse-caption",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({caption,recipeName:$("importName").value.trim()||r.name||"",sourceUrl:$("importLink").value.trim()||resolveRecipeSourceUrl(r),category:$("importCategory").value||r.category||""})});const data=await res.json();if(!data.ok)throw new Error(data.error||"AI-parser feilet");const p=data.parsed||{};$("importName").value=$("importName").value.trim()||p.title||r.name||"";$("importCategory").value=p.category||$("importCategory").value||"Annet";$("importServings").value=p.servings||$("importServings").value||"";$("parsedIngredients").value=(p.ingredients||[]).map(formatAiIngredient).join("\n");$("parsedInstructions").value=(p.instructions||[]).map((s,i)=>`${i+1}. ${s}`).join("\n");const context=mergePreservingExistingData(r,{...p,name:p.title||$("importName").value});p.tags=enrichTags(context);p.emoji=emojiForRecipe(context);window.lastAiParsedRecipe=p;status.textContent=`AI-parsing ferdig. Tags: ${(p.tags||[]).join(", ")}`}catch(err){status.textContent="AI-parser feilet: "+(err?.message||err);alert("AI-parser feilet. Se statusfelt.")}finally{btn.disabled=false;btn.textContent="AI-parse caption"}}
function formatAiIngredient(ing){if(typeof ing==="string")return ing;const amount=ing.amount||"",unit=ing.unit||"",item=ing.item||"",note=ing.note?` (${ing.note})`:"",cat=ing.shoppingCategory?` [${ing.shoppingCategory}]`:"";return`${amount} ${unit} ${item}${note}${cat}`.replace(/\s+/g," ").trim()}
function parseCaption(){const text=$("captionInput").value.trim(),lines=text.split(/\r?\n/).map(l=>l.trim()).filter(Boolean),ing=[],inst=[];let mode="";for(const line of lines){if(/ingredients|ingredienser/i.test(line)){mode="ing";continue}if(/instructions|method|fremgangsmåte|slik gjør/i.test(line)){mode="inst";continue}if(mode==="inst"||/^\d+[\.)]/.test(line))inst.push(line);else if(mode==="ing"||/^[-*•]?\s*[\d¼½¾]/.test(line))ing.push(convertIngredientLine(line.replace(/^[-*•]\s*/,"")))}$("parsedIngredients").value=ing.join("\n");$("parsedInstructions").value=inst.join("\n")}
async function saveParsedRecipe(){if(!activeImportId)return alert("Ingen oppskrift valgt.");const base=recipeById(activeImportId)||{},name=$("importName").value.trim()||"Ny oppskrift",link=$("importLink").value.trim()||resolveRecipeSourceUrl(base),category=$("importCategory").value||"Annet",ai=window.lastAiParsedRecipe||{};const patch=meaningfulPatch({name,link,category,source:sourceTypeFromUrl(link)||base.source||"Manuell",servings:$("importServings").value.trim(),ingredientsText:$("parsedIngredients").value.trim(),instructions:$("parsedInstructions").value.trim(),structuredIngredients:ai.ingredients||[],structuredInstructions:ai.instructions||[],tags:ai.tags||enrichTags(mergePreservingExistingData(base,{name,category,ingredientsText:$("parsedIngredients").value,instructions:$("parsedInstructions").value})),emoji:ai.emoji||emojiForRecipe(mergePreservingExistingData(base,{name,category})),aiParsed:!!window.lastAiParsedRecipe,aiConfidence:ai.confidence||"",status:"Fullført",manualCheck:"Nei",updatedAt:new Date().toISOString()});const idx=recipes.findIndex(r=>String(r.id)===String(activeImportId));if(idx>=0)recipes[idx]=mergePreservingExistingData(recipes[idx],patch);else recipes.push({id:activeImportId,...patch});try{const response=await fetch("/api/save-recipe",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({id:activeImportId,patch})});const saveResult=await response.json().catch(()=>({}));if(!response.ok||saveResult.ok===false)throw new Error(saveResult.error||"Lagring feilet");$("importDialog").close();createDayRows();renderRecipeResults();alert("Oppskriften er lagret permanent i Supabase ✅")}catch(err){customRecipes[activeImportId]=mergePreservingExistingData(customRecipes[activeImportId]||{},patch);localStorage.setItem("middag_custom_recipes",JSON.stringify(customRecipes));alert("Oppskriften vises nå i denne nettleseren, men Supabase-lagring feilet: "+(err?.message||err))}}
function generateShoppingList(){const days=selectedDays(),raw=[];for(const day of days){for(const item of(plan[day]||[])){if(item.type==="text")continue;const r=recipeById(item.recipeId);if(!r||!hasRecipe(r))continue;for(const line of extractIngredientLines(r))raw.push({text:line,category:categorize(line),recipe:r.name,done:false})}}shoppingItems=mergeShoppingItems(raw);renderShoppingList(shoppingItems);savePlan();showView("viewShopping")}
function mergeShoppingItems(items){const map=new Map(),pass=[];for(const it of items){const p=parseAmount(it.text);if(!p.name){pass.push(it);continue}const key=normalize(p.name+"|"+(p.unit||""));if(!map.has(key)){map.set(key,{...it,text:formatMergedItem(p),_p:p,_recipes:new Set([it.recipe])})}else{const cur=map.get(key);if(p.amount!=null&&cur._p.amount!=null&&p.unit===cur._p.unit){cur._p.amount+=p.amount;cur.text=formatMergedItem(cur._p)}else cur.text=cur.text+" + "+it.text;cur._recipes.add(it.recipe);cur.recipe=[...cur._recipes].join(", ");cur.merged=true;cur.category=bestCategory(cur.category,it.category)}}return[...map.values(),...pass].map(x=>{delete x._p;delete x._recipes;return x})}
function parseAmount(text){let s=convertIngredientLine(String(text||"").replace(/\s*\[[^\]]+\]\s*$/,"").trim());const m=s.match(/^(\d+(?:[.,]\d+)?)\s*(g|kg|dl|l|ml|ss|ts|stk|pk|boks|fedd)?\s+(.+)$/i);if(!m)return{amount:null,unit:"",name:normalizeIngredientName(s),original:s};let amount=parseFloat(m[1].replace(",",".")),unit=(m[2]||"stk").toLowerCase(),name=normalizeIngredientName(m[3]);if(unit==="kg"){amount*=1000;unit="g"}if(unit==="l"){amount*=10;unit="dl"}return{amount,unit,name,original:s}}
function normalizeIngredientName(name){let s=String(name||"").toLowerCase().trim();s=s.replace(/\([^)]*\)/g,"").replace(/[,].*$/,"").trim();s=s.replace(/\b(chopped|finely|thinly|sliced|diced|minced|grated|fresh|freshly|large|medium|small|heaped|smooth|natural|drained|rinsed|optional|to serve|hakket|finhakket|skivet|revet|fersk|stor|liten|medium|valgfritt|til servering)\b/g,"").replace(/\s+/g," ").trim();const aliases={"garlic":"hvitløk","onion":"løk","carrot":"gulrot","carrots":"gulrot","cucumber":"agurk","tomatoes":"tomat","tomato":"tomat","chickpeas":"kikerter","beans":"bønner","rice noodles":"risnudler","noodles":"nudler","soy sauce":"soyasaus","olive oil":"olivenolje"};return aliases[s]||s}
function formatMergedItem(p){if(p.amount==null)return p.original;return`${(Math.round(p.amount*10)/10).toString().replace(".",",")} ${p.unit} ${p.name}`.trim()}
function bestCategory(a,b){if(a===b)return a;const pr=["Krydder","Kjøtt","Meieri","Frys","Hermetikk/halvfabrikat","Tørrvarer","Glutenfritt","Bakevarer","Frukt og grønt","Kjølevarer","Annet"];return pr.indexOf(a)<=pr.indexOf(b)?a:b}
function renderShoppingList(items){const grouped=Object.fromEntries(CATEGORIES.map(c=>[c,[]]));for(const item of items){if(!grouped[item.category])grouped[item.category]=[];grouped[item.category].push(item)}const total=items.length,merged=items.filter(x=>x.merged).length;$("shoppingList").innerHTML=`<p class="shopping-summary">${total} varer${merged?` · ${merged} slått sammen`:""}</p>`+CATEGORIES.map(cat=>{const arr=grouped[cat]||[];return`<div class="category" data-category="${escapeAttr(cat)}"><div class="category-head"><h3>${cat}</h3><button class="tiny-add" onclick="addCustomShoppingItem('${escapeAttr(cat)}')">+ Legg til</button></div><div class="category-items">${arr.length?arr.map(it=>shoppingItemHtml(it)).join(""):`<p class="hint small-hint">Ingen varer enda.</p>`}</div></div>`}).join("")}
function shoppingItemHtml(it){return`<div class="item"><input type="checkbox" ${it.done?"checked":""} onchange="this.closest('.item').classList.toggle('done', this.checked)"><input type="text" value="${escapeAttr(it.text)}" title="Fra: ${escapeAttr(it.recipe||'Egen vare')}">${it.merged?`<span class="merged-badge">slått sammen</span>`:""}<button class="remove-btn" title="Fjern" onclick="this.closest('.item').remove()">×</button></div>`}
window.addCustomShoppingItem=function(category){const text=prompt(`Legg til vare i ${category}:`);if(!text||!text.trim())return;shoppingItems.push({text:text.trim(),category,recipe:"Egen vare",done:false});renderShoppingList(shoppingItems);savePlan()}
function renderRecipeResults(){const q=normalize($("recipeSearch").value),sort=$("recipeSort")?.value||"az";let filtered=recipes.filter(r=>!q||searchableText(r).includes(q));filtered=sortRecipes(filtered,sort);$("recipeResults").innerHTML=filtered.map(r=>recipeCardHtml(r)).join("")||`<div class="empty-state">Ingen oppskrifter funnet.</div>`}
function sortRecipes(arr,sort){const copy=[...arr];if(sort==="za")return copy.sort((a,b)=>b.name.localeCompare(a.name,"no"));if(sort==="category")return copy.sort((a,b)=>`${a.category||""} ${a.name}`.localeCompare(`${b.category||""} ${b.name}`,"no"));if(sort==="used")return copy.sort((a,b)=>usageCount(b.id)-usageCount(a.id)||a.name.localeCompare(b.name,"no"));if(sort==="favorites")return copy.sort((a,b)=>Number(isFavorite(b.id))-Number(isFavorite(a.id))||a.name.localeCompare(b.name,"no"));if(sort==="recent")return copy.sort((a,b)=>String(appMeta.lastUsed?.[b.id]||b.updatedAt||b.createdAt||"").localeCompare(String(appMeta.lastUsed?.[a.id]||a.updatedAt||a.createdAt||"")));if(sort==="tags")return copy.sort((a,b)=>enrichTags(a).join(",").localeCompare(enrichTags(b).join(","),"no")||a.name.localeCompare(b.name,"no"));if(sort==="missing")return copy.sort((a,b)=>Number(hasRecipe(a))-Number(hasRecipe(b))||a.name.localeCompare(b.name,"no"));return copy.sort((a,b)=>a.name.localeCompare(b.name,"no"))}
function recipeCardHtml(r){const tags=enrichTags(r),fav=isFavorite(r.id)?"★":"☆";return`<div class="recipe-card" onclick="openRecipeDetails('${escapeAttr(r.id)}')"><div class="recipe-thumb recipe-emoji">${emojiForRecipe(r)}</div><div><div class="recipe-topline"><strong>${escapeHtml(r.name)}</strong><button class="favorite-btn" onclick="event.stopPropagation();toggleFavorite('${escapeAttr(r.id)}')" title="Favoritt">${fav}</button></div><div class="recipe-meta">${escapeHtml(r.category||"Ukjent")} · ${hasRecipe(r)?"✅ Oppskrift funnet":"🟡 Mangler oppskrift"} · brukt ${usageCount(r.id)}× · ${escapeHtml(r.source||"")}</div><div class="recipe-tags">${tags.slice(0,6).map(t=>`<span class="tag">${escapeHtml(t)}</span>`).join("")}</div><div class="recipe-meta recipe-actions">${r.link?`<a href="${escapeAttr(r.link)}" target="_blank" rel="noopener" onclick="event.stopPropagation()">Åpne kilde</a>`:"Ingen lenke"} · <button class="link-button" onclick="event.stopPropagation();openImport('${escapeAttr(r.id)}')">${hasRecipe(r)?"Rediger":"Importer"}</button></div></div></div>`}
window.openRecipeDetails=function(id){const r=recipeById(id);if(!r)return;$("recipeDialogTitle").textContent=`${emojiForRecipe(r)} ${r.name}`;const tags=enrichTags(r);$("recipeDialogBody").innerHTML=`<p class="recipe-meta">${escapeHtml(r.category||"Ukjent")} · ${escapeHtml(r.source||"")} · brukt ${usageCount(r.id)}×</p><div class="recipe-tags">${tags.map(t=>`<span class="tag">${escapeHtml(t)}</span>`).join("")}</div><div class="inline-actions"><button type="button" class="favorite-btn" onclick="toggleFavorite('${escapeAttr(r.id)}')">${isFavorite(r.id)?"★ Favoritt":"☆ Favoritt"}</button><button type="button" class="primary" onclick="openAddToDay('${escapeAttr(r.id)}')">+ Legg til i ukesmeny</button><button type="button" class="ghost" onclick="openImport('${escapeAttr(r.id)}');document.getElementById('recipeDialog').close();">Rediger</button>${r.link?`<a class="source-link-inline" href="${escapeAttr(r.link)}" target="_blank" rel="noopener">Åpne kilde</a>`:""}</div><div class="recipe-detail-section"><h3>Ingredienser</h3>${formatList(ingredientsToText(r))}</div><div class="recipe-detail-section"><h3>Fremgangsmåte</h3>${formatSteps(instructionsToText(r))}</div>`;$("recipeDialog").showModal()}
window.openAddToDay=function(id){pendingAddRecipeId=id;const r=recipeById(id);$("addToDayRecipeName").textContent=r?.name||"";fillAddToDaySelect();$("addToDayDialog").showModal()}
function confirmAddToDay(){const day=$("addToDaySelect").value;if(!day||!pendingAddRecipeId)return;plan[day].push({type:"recipe",recipeId:pendingAddRecipeId});bumpUsage(pendingAddRecipeId);savePlan();createDayRows();renderRecipeResults();$("addToDayDialog").close();$("recipeDialog").close();showView("viewPlan")}
function randomWeek(){const days=selectedDays(),usable=recipes.slice().sort((a,b)=>Number(hasRecipe(b))-Number(hasRecipe(a)));for(const day of days){const r=usable[Math.floor(Math.random()*usable.length)];plan[day]=r?[{type:"recipe",recipeId:r.id}]:[];if(r)bumpUsage(r.id)}savePlan();createDayRows();renderRecipeResults()}
async function smartWeek(){const prompt=$("smartPrompt").value.trim(),days=selectedDays();$("smartStatus").textContent="Lager AI-forslag …";try{const payloadRecipes=recipes.map(r=>({id:r.id,name:r.name,category:r.category,tags:enrichTags(r),favorite:isFavorite(r.id),usage:usageCount(r.id),hasRecipe:hasRecipe(r)}));const res=await fetch("/api/smart-week",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({prompt,days,recipes:payloadRecipes})});const data=await res.json();if(!data.ok)throw new Error(data.error||"AI-ukemeny feilet");const items=data.plan?.items||[];for(const day of days)plan[day]=[];for(const row of items){const day=String(row.day||"").toLowerCase();if(!DAYS.includes(day))continue;const ids=row.recipeIds||row.recipe_ids||[];plan[day]=ids.filter(id=>recipeById(id)).map(id=>{bumpUsage(id);return{type:"recipe",recipeId:id}});if(row.note&&!plan[day].length)plan[day]=[{type:"text",text:row.note}]}$("smartStatus").textContent="AI-forslag laget. Du kan justere manuelt.";savePlan();createDayRows();renderRecipeResults()}catch(e){$("smartStatus").textContent="AI feilet, bruker lokal smart velger.";localSmartWeek()}}
function localSmartWeek(){const p=normalize($("smartPrompt").value),days=selectedDays();let pool=recipes.slice();if(p.includes("vegetar"))pool=pool.filter(r=>enrichTags(r).includes("vegetar")||normalize(r.category).includes("vegetar"));if(p.includes("suppe"))pool=pool.filter(r=>enrichTags(r).includes("suppe"));if(p.includes("kylling"))pool=pool.filter(r=>enrichTags(r).includes("kylling"));if(p.includes("rask"))pool=pool.filter(r=>enrichTags(r).includes("rask"));if(pool.length<days.length)pool=recipes.slice();for(const day of days){const r=pool[Math.floor(Math.random()*pool.length)];plan[day]=r?[{type:"recipe",recipeId:r.id}]:[];if(r)bumpUsage(r.id)}savePlan();createDayRows();renderRecipeResults()}
function usageCount(id){return Number(appMeta.usageCounts?.[id]||0)}function bumpUsage(id){if(!id)return;appMeta.usageCounts=appMeta.usageCounts||{};appMeta.lastUsed=appMeta.lastUsed||{};appMeta.usageCounts[id]=Number(appMeta.usageCounts[id]||0)+1;appMeta.lastUsed[id]=new Date().toISOString()}function isFavorite(id){return(appMeta.favorites||[]).includes(id)}function toggleFavorite(id){appMeta.favorites=appMeta.favorites||[];if(isFavorite(id))appMeta.favorites=appMeta.favorites.filter(x=>x!==id);else appMeta.favorites.push(id);savePlan();renderRecipeResults();if($("recipeDialog")?.open)openRecipeDetails(id)}window.toggleFavorite=toggleFavorite
function searchableText(r){return normalize(`${r.name} ${r.category} ${r.source} ${r.status} ${enrichTags(r).join(" ")} ${r.ingredientsText||""}`)}
function ingredientsToText(r){if(r.ingredientsText)return r.ingredientsText;if(Array.isArray(r.structuredIngredients)&&r.structuredIngredients.length)return r.structuredIngredients.map(formatAiIngredient).join("\n");return""}
function instructionsToText(r){if(r.instructions)return Array.isArray(r.instructions)?r.instructions.join("\n"):String(r.instructions);if(Array.isArray(r.structuredInstructions))return r.structuredInstructions.map((x,i)=>`${i+1}. ${x}`).join("\n");return""}
function formatList(text){const lines=String(text||"").split(/\n|;/).map(x=>x.trim()).filter(Boolean);if(!lines.length)return`<p class="hint">Ingen ingredienser lagt inn.</p>`;return`<ul>${lines.map(l=>`<li>${escapeHtml(l)}</li>`).join("")}</ul>`}
function formatSteps(text){const lines=String(text||"").split(/\n/).map(x=>x.trim()).filter(Boolean);if(!lines.length)return`<p class="hint">Ingen fremgangsmåte lagt inn.</p>`;return`<ol>${lines.map(l=>`<li>${escapeHtml(l.replace(/^\d+[\.)]\s*/,""))}</li>`).join("")}</ol>`}
function extractIngredientLines(r){return ingredientsToText(r).split(/;|\n/).map(s=>convertIngredientLine(s.replace(/\s*\[[^\]]+\]\s*$/,"").trim())).filter(s=>s.length>1)}
function categorize(line){const s=normalize(line);const spice=["salt","pepper","oregano","basilikum","basil","gochugaru","paprika","spisskummen","cumin","kanel","chili flakes","chiliflak","curry powder","karri","garam masala","laurbær","sesamfrø","sesame seeds","sukker","sugar","honning","honey"];if(spice.some(w=>s.includes(normalize(w))))return"Krydder";const dry=["soy sauce","soyasaus","soya","tamari","sesamolje","sesame oil","olivenolje","olive oil","olje","oil","riseddik","rice vinegar","vinegar","eddik","sriracha","hot sauce","fish sauce","fiskesaus","stock","kraft","broth","buljong","peanøttsmør","peanut butter","tomatpure","tomato paste"];if(dry.some(w=>s.includes(normalize(w))))return"Tørrvarer";const map=[["Kjøtt",["kylling","chicken","biff","beef","okse","kjøttdeig","svin","pork","kotelett","pølse","sausage","kalkun","bacon"]],["Meieri",["melk","milk","fløte","cream","rømme","ost","cheese","parmesan","feta","cottage cheese","yoghurt","smør","butter"]],["Frys",["frossen","frosne","frozen","edamame"]],["Hermetikk/halvfabrikat",["boks","can ","canned","kokosmelk","coconut milk","kidney","kikerter","chickpeas","diced tomatoes","hakkede tomater","bønner","beans"]],["Tørrvarer",["pasta","nudler","noodles","ris","rice","orzo","bulgur","quinoa","mel","flour","breadcrumbs"]],["Glutenfritt",["glutenfri","gluten free"]],["Bakevarer",["brød","bread","pita","tortilla","burgerbrød","wrap"]],["Frukt og grønt",["agurk","cucumber","gulrot","carrot","løk","onion","hvitløk","garlic","ingefær","ginger","potet","potato","søtpotet","sweet potato","squash","zucchini","tomat","tomato","paprika","pepper","sopp","mushroom","brokkoli","broccoli","blomkål","cauliflower","kål","cabbage","spinat","spinach","salat","lettuce","lime","sitron","lemon","koriander","cilantro","persille","parsley","selleri","celery","avokado","avocado","aubergine","eggplant","chili","vårløk","spring onion"]]];for(const[cat,words]of map)if(words.some(w=>s.includes(normalize(w))))return cat;if(s.includes("tofu"))return"Kjølevarer";return"Annet"}
function convertIngredientLine(line){let s=String(line||"").trim();s=s.replace(/(\d+(?:[.,]\d+)?)\s*cups?\b/gi,(_,n)=>`${String(Math.round(parseFloat(n.replace(",","."))*24)/10).replace(".",",")} dl`);s=s.replace(/(\d+(?:[.,]\d+)?)\s*(tbsp|tablespoons?)\b/gi,"$1 ss");s=s.replace(/(\d+(?:[.,]\d+)?)\s*(tsp|teaspoons?)\b/gi,"$1 ts");s=s.replace(/(\d+(?:[.,]\d+)?)\s*(oz|ounces?)\b/gi,(_,n)=>`${Math.round(parseFloat(n.replace(",","."))*28.35)} g`);return s}
async function cleanupVisibleRecipes(){if(!confirm("Rydde tags, emoji og norske mål for oppskriftene?"))return;const btn=$("cleanupRecipesBtn");if(btn){btn.disabled=true;btn.textContent="Rydder …"}let updated=0;for(const r of recipes){const patch=meaningfulPatch({tags:enrichTags(r),emoji:emojiForRecipe(r),ingredientsText:ingredientsToText(r).split(/\n/).map(convertIngredientLine).join("\n"),updatedAt:new Date().toISOString()});try{const response=await fetch("/api/save-recipe",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({id:r.id,patch})});const data=await response.json().catch(()=>({}));if(response.ok&&data.ok!==false){Object.assign(r,mergePreservingExistingData(r,patch));updated++}}catch(e){console.warn("rydd feilet",r.name,e)}}renderRecipeResults();createDayRows();if(btn){btn.disabled=false;btn.textContent="Rydd tags/mål"}alert(`Ryddet ${updated} oppskrifter. Kategorisering av handleliste er forbedret.`)}
async function readScreenshotsWithOCR(){const input=$("screenshotInput"),files=Array.from(input?.files||[]),status=$("ocrStatus");if(!files.length)return alert("Velg ett eller flere skjermbilder først.");if(!window.Tesseract)return alert("OCR-biblioteket ble ikke lastet.");status.textContent=`Leser ${files.length} bilde(r) …`;const chunks=[];for(let i=0;i<files.length;i++){status.textContent=`OCR bilde ${i+1}/${files.length}`;const result=await Tesseract.recognize(files[i],"eng");if(result?.data?.text)chunks.push(result.data.text.trim())}$("captionInput").value=[$("captionInput").value.trim(),chunks.join("\n\n")].filter(Boolean).join("\n\n");status.textContent="Ferdig. Se over teksten og trykk AI-parse caption."}
function escapeHtml(s){return String(s??"").replace(/[&<>"]/g,m=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[m]))}
function escapeAttr(s){return escapeHtml(s).replace(/'/g,"&#39;")}

/* ===== v20 overrides ===== */
function toISODate(d){return d.toISOString().slice(0,10)}
function parseLocalDate(iso){const [y,m,d]=String(iso).split("-").map(Number);return new Date(y,m-1,d)}
function weekdayName(d){return ["søndag","mandag","tirsdag","onsdag","torsdag","fredag","lørdag"][d.getDay()]}
function formatDateLabel(iso){if(!iso)return"";const d=parseLocalDate(iso);return `${capitalize(weekdayName(d))} ${String(d.getDate()).padStart(2,"0")}.${String(d.getMonth()+1).padStart(2,"0")}.${d.getFullYear()}`}
function fillDaySelectorsV20(){const today=new Date();const end=new Date(today);end.setDate(today.getDate()+4);if($("startDate")&&!$("startDate").value)$("startDate").value=toISODate(today);if($("endDate")&&!$("endDate").value)$("endDate").value=toISODate(end);updateDateLabels()}
function updateDateLabels(){if($("startDateLabel"))$("startDateLabel").textContent=formatDateLabel($("startDate")?.value);if($("endDateLabel"))$("endDateLabel").textContent=formatDateLabel($("endDate")?.value)}
selectedDays=function(){const a=$("startDate")?.value,b=$("endDate")?.value;if(!a||!b)return[];let s=parseLocalDate(a),e=parseLocalDate(b);if(e<s){const t=s;s=e;e=t}const out=[];const d=new Date(s);while(d<=e){const iso=toISODate(d);out.push({key:iso,label:formatDateLabel(iso),weekday:weekdayName(d)});d.setDate(d.getDate()+1)}return out}
fillAddToDaySelect=function(){if($("addToDaySelect"))$("addToDaySelect").innerHTML=selectedDays().map(d=>`<option value="${d.key}">${d.label}</option>`).join("")}
const oldSavePlan=savePlan;
savePlan=function(){appMeta.updatedAt=new Date().toISOString();localStorage.setItem("middag_plan",JSON.stringify(plan));fetch("/api/plan",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({plan:{items:plan,shoppingItems,freezerItems,meta:appMeta,updatedAt:appMeta.updatedAt}})}).catch(e=>{console.warn(e);setLiveStatus("Sync-feil","error")})}
resetPlan=function(){if(!confirm("Nullstille ukeplanen?"))return;for(const d of selectedDays())plan[d.key]=[];savePlan();createDayRows()}
createDayRows=function(){const c=$("dayRows"),days=selectedDays();fillAddToDaySelect();for(const d of days)if(!Array.isArray(plan[d.key]))plan[d.key]=[];c.innerHTML="";for(const d of days){const day=d.key;const card=document.createElement("div");card.className="day-row day-card-v16";card.innerHTML=`<div class="day-head-v16"><h3>${d.label}</h3><button class="ghost" data-picker="${day}">+ Oppskrift</button></div><input class="day-text-input" data-free="${day}" placeholder="Skriv rett manuelt, f.eks. Grillmat"><div class="day-actions-row"><button class="ghost" data-addtext="${day}">+ Legg til tekstrett</button><button class="ghost" data-clear="${day}">Tøm dag</button></div><div class="day-items"></div>`;c.appendChild(card);card.querySelector("[data-picker]").addEventListener("click",()=>openRecipePicker(day));card.querySelector("[data-addtext]").addEventListener("click",()=>addFreeTextToDay(day,card.querySelector("[data-free]").value));card.querySelector("[data-clear]").addEventListener("click",()=>{plan[day]=[];savePlan();createDayRows()});renderDayItems(card,day)}renderWeekOverview()}
renderWeekOverview=function(){const box=$("weekOverview");if(!box)return;box.innerHTML=selectedDays().map(d=>{const items=plan[d.key]||[];const chips=items.length?items.map(item=>{if(item.type==="text")return`<span class="week-chip manual">✍️ ${escapeHtml(item.text)}</span>`;const r=recipeById(item.recipeId);if(!r)return`<span class="week-chip missing">Mangler</span>`;return`<button class="week-chip${hasRecipe(r)?"":" missing"}" onclick="${hasRecipe(r)?`openRecipeDetails('${escapeAttr(r.id)}')`:`openImport('${escapeAttr(r.id)}')`}">${emojiForRecipe(r)} ${escapeHtml(r.name)}</button>`}).join(""):`<span class="hint">Ingen retter</span>`;return`<div class="week-overview-row"><div class="week-overview-day">${d.label}</div><div class="week-overview-items">${chips}</div></div>`}).join("")}
const oldAddFreeTextToDay=addFreeTextToDay;
addFreeTextToDay=function(day,text){const t=String(text||"").trim();if(!t)return;plan[day].push({type:"text",text:t});savePlan();createDayRows()}
const oldAddRecipeToDay=window.addRecipeToDay;
window.addRecipeToDay=function(day,id){plan[day].push({type:"recipe",recipeId:id});bumpUsage(id);savePlan();createDayRows();renderRecipeResults();$("recipePickerDialog").close()}
const oldConfirmAddToDay=confirmAddToDay;
confirmAddToDay=function(){const day=$("addToDaySelect").value;if(!day||!pendingAddRecipeId)return;plan[day].push({type:"recipe",recipeId:pendingAddRecipeId});bumpUsage(pendingAddRecipeId);savePlan();createDayRows();renderRecipeResults();$("addToDayDialog").close();$("recipeDialog").close();showView("viewPlan")}
const oldGenerateShoppingList=generateShoppingList;
generateShoppingList=function(){const raw=[];for(const d of selectedDays()){const day=d.key;for(const item of(plan[day]||[])){if(item.type==="text")continue;const r=recipeById(item.recipeId);if(!r||!hasRecipe(r))continue;for(const line of extractIngredientLines(r))raw.push({text:line,category:categorize(line),recipe:r.name,done:false})}}shoppingItems=typeof mergeShoppingItems==="function"?mergeShoppingItems(raw):raw;renderShoppingList(shoppingItems);savePlan();showView("viewShopping")}
function defaultFreezerItems(){const raw=[["edamame",1,"pk","Grønnsaker"],["rødkål",1,"pose","Grønnsaker"],["frosne bringebær",1,"pose","Frukt/smoothie"],["smoothieblanding mango ananas banan",1,"pose","Frukt/smoothie"],["acai smoothie",1,"pose","Frukt/smoothie"],["paibunner",4,"stk","Bakst"],["erter",4,"poser","Grønnsaker"],["ørretfilet",4,"stk","Fisk"],["søtpotetfries",1,"pose","Grønnsaker"],["broccoli wings",1,"pose","Vegetar"],["lobnobs",4,"pk","Annet"],["granateplekjerner",1,"pk","Frukt/smoothie"],["div skinke",8,"pk","Kjøtt"],["karbonadedeig",12,"pk","Kjøtt"],["kokt scampi",2,"pk","Fisk"],["glutenfritt brød",2.5,"stk","Bakst"],["4-pk kyllingfilet",6,"pk","Kylling"],["3-pk kyllingfilet",3,"pk","Kylling"],["ytrefilet svin 700g",3,"stk","Kjøtt"],["5-pakning kyllinglårfilet",2,"stk","Kylling"],["3-pakning bacon",2,"stk","Kjøtt"],["kylling gyoza",1,"pk","Kylling"],["kylling dumplings",1,"pk","Kylling"],["kyllingboller 2,5 kg",1,"pk","Kylling"],["flintsteak",9,"stk","Kjøtt"],["pork brisket 800g",1,"stk","Kjøtt"],["ytrefilet svin urte/hvitløksmarinert 1kg",1,"stk","Kjøtt"],["veggisfarse 1 kg",2,"pk","Vegetar"],["hvitløksmarinert koteletter",1,"pk","Kjøtt"],["pepper og ramsløk kotelett",1,"pk","Kjøtt"],["kalkunfilet 937g",1,"stk","Kjøtt"]];return raw.map((x,i)=>({id:`freezer-${i+1}`,name:x[0],qty:x[1],unit:x[2],category:x[3],updatedAt:new Date().toISOString()}))}
function renderFreezer(){const box=$("freezerList");if(!box)return;const groups={};for(const item of freezerItems){if(Number(item.qty)<=0)continue;(groups[item.category||"Annet"] ||= []).push(item)}box.innerHTML=Object.keys(groups).sort().map(cat=>`<div class="freezer-category"><h3>${cat}</h3>${groups[cat].map(freezerItemHtml).join("")}</div>`).join("")||`<p class="hint">Fryseren er tom.</p>`}
function freezerItemHtml(item){return`<div class="freezer-item"><div><div class="freezer-name">${escapeHtml(item.name)}</div><div class="freezer-meta">${escapeHtml(item.category||"Annet")} · ${escapeHtml(item.unit||"stk")}</div></div><div class="freezer-controls"><button onclick="changeFreezerQty('${item.id}',-1)">−</button><span class="freezer-qty">${item.qty}</span><button onclick="changeFreezerQty('${item.id}',1)">+</button><button class="remove-btn" onclick="removeFreezerItem('${item.id}')">×</button></div></div>`}
window.changeFreezerQty=function(id,delta){const item=freezerItems.find(x=>x.id===id);if(!item)return;item.qty=Math.max(0,Number(item.qty||0)+delta);savePlan();renderFreezer()}
window.removeFreezerItem=function(id){freezerItems=freezerItems.filter(x=>x.id!==id);savePlan();renderFreezer()}
function addFreezerItem(){const name=prompt("Hva vil du legge til i fryseren?");if(!name||!name.trim())return;const qty=Number(prompt("Antall?","1")||1);const unit=prompt("Enhet? f.eks. pk, pose, stk","stk")||"stk";freezerItems.push({id:`freezer-${Date.now()}`,name:name.trim(),qty:qty||1,unit,category:guessFreezerCategory(name),updatedAt:new Date().toISOString()});savePlan();renderFreezer()}
function guessFreezerCategory(name){const s=normalize(name);if(/kylling|chicken/.test(s))return"Kylling";if(/ørret|fisk|scampi|reker/.test(s))return"Fisk";if(/karbonade|svin|bacon|kotelett|steak|brisket|skinke|kalkun/.test(s))return"Kjøtt";if(/erte|edamame|rødkål|søtpotet|broccoli/.test(s))return"Grønnsaker";if(/bringebær|smoothie|acai|granateple/.test(s))return"Frukt/smoothie";if(/brød|pai/.test(s))return"Bakst";if(/veggis|vegetar/.test(s))return"Vegetar";return"Annet"}
function freezerSuggest(){const a=freezerItems.filter(x=>Number(x.qty)>0);if(!a.length){$("freezerSuggestion").textContent="Fryseren er tom.";return}const pick=a[Math.floor(Math.random()*a.length)],s=normalize(pick.name);let txt=`Du har ${pick.qty} ${pick.unit||"stk"} ${pick.name} i fryseren. `;if(/ørret|fisk/.test(s))txt+="Hvorfor ikke lage ørret med søtpotetfries, erter eller en frisk salat?";else if(/edamame|gyoza|dumpling|scampi/.test(s))txt+="Dette passer perfekt til asiatisk bowl, ramen eller nudler.";else if(/karbonade/.test(s))txt+="Det er kanskje på tide med taco, bolognese, kjøttboller eller burger?";else if(/kylling/.test(s))txt+="Hva med kyllingcurry, fajitas, pasta eller en rask bowl?";else if(/paibunn/.test(s))txt+="Hva med pai med skinke, bacon, kylling eller grønnsaker?";else if(/veggis/.test(s))txt+="Hva med vegetar-taco, vegetar-bolognese eller kjøttfrie kjøttboller?";else txt+="Kanskje du kan bruke dette i ukesmenyen denne uka?";$("freezerSuggestion").textContent=txt}


/* ===== v20.2 robust date-plan overrides ===== */
function toISODateLocal(d){
  const y=d.getFullYear();
  const m=String(d.getMonth()+1).padStart(2,"0");
  const day=String(d.getDate()).padStart(2,"0");
  return `${y}-${m}-${day}`;
}
toISODate=function(d){return toISODateLocal(d)}
parseLocalDate=function(iso){const [y,m,d]=String(iso).split("-").map(Number);return new Date(y,m-1,d,12,0,0)}
weekdayName=function(d){return ["søndag","mandag","tirsdag","onsdag","torsdag","fredag","lørdag"][d.getDay()]}
formatDateLabel=function(iso){if(!iso)return"";const d=parseLocalDate(iso);return `${capitalize(weekdayName(d))} ${String(d.getDate()).padStart(2,"0")}.${String(d.getMonth()+1).padStart(2,"0")}.${d.getFullYear()}`}
fillDaySelectorsV20=function(){
  const today=new Date();
  const start=new Date(today.getFullYear(), today.getMonth(), today.getDate(), 12);
  const end=new Date(start); end.setDate(start.getDate()+4);
  if($("startDate")&&!$("startDate").value)$("startDate").value=toISODateLocal(start);
  if($("endDate")&&!$("endDate").value)$("endDate").value=toISODateLocal(end);
  updateDateLabels();
}
updateDateLabels=function(){
  if($("startDateLabel"))$("startDateLabel").textContent=formatDateLabel($("startDate")?.value);
  if($("endDateLabel"))$("endDateLabel").textContent=formatDateLabel($("endDate")?.value);
}
selectedDays=function(){
  const a=$("startDate")?.value,b=$("endDate")?.value;
  if(!a||!b)return[];
  let s=parseLocalDate(a),e=parseLocalDate(b);
  if(e<s){const t=s;s=e;e=t}
  const out=[];
  const d=new Date(s);
  let guard=0;
  while(d<=e&&guard<45){
    const iso=toISODateLocal(d);
    out.push({key:iso,label:formatDateLabel(iso),weekday:weekdayName(d)});
    d.setDate(d.getDate()+1); guard++;
  }
  return out;
}
fillAddToDaySelect=function(){
  const el=$("addToDaySelect"); if(!el)return;
  el.innerHTML=selectedDays().map(d=>`<option value="${d.key}">${d.label}</option>`).join("");
}
savePlan=function(){
  appMeta.updatedAt=new Date().toISOString();
  lastRemoteUpdatedAt=appMeta.updatedAt;
  localStorage.setItem("middag_plan",JSON.stringify(plan));
  fetch("/api/plan",{
    method:"POST",
    headers:{"Content-Type":"application/json"},
    body:JSON.stringify({plan:{items:plan,shoppingItems,freezerItems,meta:appMeta,updatedAt:appMeta.updatedAt}})
  }).then(()=>setLiveStatus("Live")).catch(e=>{console.warn(e);setLiveStatus("Sync-feil","error")})
}
syncFromServer=async function(){
  try{
    setLiveStatus("Syncer","syncing");
    const pr=await fetch("/api/plan").then(r=>r.json());
    const remote=pr.plan?.updatedAt||"";
    if(remote&&remote!==lastRemoteUpdatedAt&&remote!==appMeta.updatedAt){
      plan=migratePlan(pr.plan?.items||{});
      shoppingItems=pr.plan?.shoppingItems||shoppingItems;
      freezerItems=pr.plan?.freezerItems||freezerItems;
      appMeta=pr.plan?.meta||appMeta;
      lastRemoteUpdatedAt=remote;
      createDayRows();renderShoppingList(shoppingItems);renderRecipeResults();renderFreezer();
    }
    const rr=await fetch("/api/recipes").then(r=>r.json());
    if(rr.recipes&&rr.recipes.length!==recipes.length){recipes=rr.recipes;mergeCustomData();renderRecipeResults();createDayRows()}
    setLiveStatus("Live");
  }catch(e){setLiveStatus("Offline?","error")}
}
createDayRows=function(){
  const c=$("dayRows"),days=selectedDays();
  fillAddToDaySelect();
  if(!c)return;
  for(const d of days)if(!Array.isArray(plan[d.key]))plan[d.key]=[];
  c.innerHTML="";
  for(const d of days){
    const day=d.key;
    const card=document.createElement("div");card.className="day-row day-card-v16";
    card.innerHTML=`<div class="day-head-v16"><h3>${d.label}</h3><button type="button" class="ghost" data-picker="${day}">+ Oppskrift</button></div><input class="day-text-input" data-free="${day}" placeholder="Skriv rett manuelt, f.eks. Grillmat"><div class="day-actions-row"><button type="button" class="ghost" data-addtext="${day}">+ Legg til tekstrett</button><button type="button" class="ghost" data-clear="${day}">Tøm dag</button></div><div class="day-items"></div>`;
    c.appendChild(card);
    card.querySelector("[data-picker]").addEventListener("click",()=>openRecipePicker(day));
    card.querySelector("[data-addtext]").addEventListener("click",()=>addFreeTextToDay(day,card.querySelector("[data-free]").value));
    card.querySelector("[data-clear]").addEventListener("click",()=>{plan[day]=[];savePlan();createDayRows()});
    renderDayItems(card,day);
  }
  renderWeekOverview();
}
renderDayItems=function(card,day){
  const box=card.querySelector(".day-items"),items=plan[day]||[];
  if(!items.length){box.innerHTML=`<div class="empty-state">Ingen retter lagt til.</div>`;return}
  box.innerHTML=items.map((item,idx)=>{
    if(item.type==="text")return`<div class="plan-item text-plan-item"><div><div class="plan-item-title">✍️ ${escapeHtml(item.text)}</div><div class="plan-item-meta">Manuell rett – legg varer manuelt i handlelisten</div></div><div class="plan-actions"><button type="button" class="mini-action" onclick="addManualDishToShopping('${escapeAttr(item.text)}')">+ varer</button><button type="button" class="remove-btn" onclick="removePlanItem('${day}',${idx})">×</button></div></div>`;
    const r=recipeById(item.recipeId);
    if(!r)return`<div class="plan-item missing-plan-item"><div><div class="plan-item-title">Oppskrift ikke funnet</div></div><button type="button" class="remove-btn" onclick="removePlanItem('${day}',${idx})">×</button></div>`;
    const found=hasRecipe(r),cls=found?"recipe-plan-item":"missing-plan-item";
    return`<div class="plan-item ${cls}"><div><div class="plan-item-title">${escapeHtml(emojiForRecipe(r)+" "+r.name)}</div><div class="plan-item-meta">${escapeHtml((r.category||"Ukjent")+" · brukt "+usageCount(r.id)+"× · "+(found?"oppskrift funnet":"oppskrift mangler"))}</div></div><div class="plan-actions">${found?`<button type="button" class="mini-action" onclick="openRecipeDetails('${escapeAttr(r.id)}')">Se</button>`:`<button type="button" class="mini-action" onclick="openImport('${escapeAttr(r.id)}')">Legg inn</button>`}<button type="button" class="remove-btn" onclick="removePlanItem('${day}',${idx})">×</button></div></div>`;
  }).join("");
}
addFreeTextToDay=function(day,text){
  const t=String(text||"").trim(); if(!t)return;
  if(!Array.isArray(plan[day]))plan[day]=[];
  plan[day].push({type:"text",text:t});
  savePlan();createDayRows();
}
window.addRecipeToDay=function(day,id){
  if(!Array.isArray(plan[day]))plan[day]=[];
  plan[day].push({type:"recipe",recipeId:id});
  bumpUsage(id);savePlan();createDayRows();renderRecipeResults();
  if($("recipePickerDialog"))$("recipePickerDialog").close();
}
resetPlan=function(){
  if(!confirm("Nullstille ukeplanen?"))return;
  for(const d of selectedDays())plan[d.key]=[];
  savePlan();createDayRows();
}
generateShoppingList=function(){
  const raw=[];
  for(const d of selectedDays()){
    const day=d.key;
    for(const item of(plan[day]||[])){
      if(item.type==="text")continue;
      const r=recipeById(item.recipeId);
      if(!r||!hasRecipe(r))continue;
      for(const line of extractIngredientLines(r))raw.push({text:line,category:categorize(line),recipe:r.name,done:false});
    }
  }
  shoppingItems=typeof mergeShoppingItems==="function"?mergeShoppingItems(raw):raw;
  renderShoppingList(shoppingItems);savePlan();showView("viewShopping");
}
randomWeek=function(){
  const days=selectedDays(), usable=recipes.slice().sort((a,b)=>Number(hasRecipe(b))-Number(hasRecipe(a)));
  if(!usable.length){alert("Ingen oppskrifter funnet.");return}
  for(const d of days){
    const r=usable[Math.floor(Math.random()*usable.length)];
    plan[d.key]=r?[{type:"recipe",recipeId:r.id}]:[];
    if(r)bumpUsage(r.id);
  }
  savePlan();createDayRows();renderRecipeResults();
}
smartWeek=async function(){
  const prompt=$("smartPrompt")?.value?.trim()||"",days=selectedDays();
  if($("smartStatus"))$("smartStatus").textContent="Lager AI-forslag …";
  try{
    const payloadRecipes=recipes.map(r=>({id:r.id,name:r.name,category:r.category,tags:enrichTags(r),favorite:isFavorite(r.id),usage:usageCount(r.id),hasRecipe:hasRecipe(r)}));
    const res=await fetch("/api/smart-week",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({prompt,days:days.map(d=>({key:d.key,label:d.label,weekday:d.weekday})),recipes:payloadRecipes})});
    const data=await res.json();
    if(!data.ok)throw new Error(data.error||"AI-ukemeny feilet");
    for(const d of days)plan[d.key]=[];
    const items=data.plan?.items||[];
    for(const row of items){
      let day=String(row.day||"").toLowerCase();
      const match=days.find(d=>d.key===day||d.weekday===day||normalize(d.label).includes(normalize(day)));
      if(!match)continue;
      const ids=row.recipeIds||row.recipe_ids||[];
      plan[match.key]=ids.filter(id=>recipeById(id)).map(id=>{bumpUsage(id);return{type:"recipe",recipeId:id}});
      if(row.note&&!plan[match.key].length)plan[match.key]=[{type:"text",text:row.note}];
    }
    if($("smartStatus"))$("smartStatus").textContent="AI-forslag laget. Du kan justere manuelt.";
    savePlan();createDayRows();renderRecipeResults();
  }catch(e){
    console.warn(e);
    if($("smartStatus"))$("smartStatus").textContent="AI feilet, bruker lokal smart velger.";
    localSmartWeek();
  }
}
localSmartWeek=function(){
  const p=normalize($("smartPrompt")?.value||""),days=selectedDays();
  let pool=recipes.slice();
  if(p.includes("vegetar"))pool=pool.filter(r=>enrichTags(r).includes("vegetar")||normalize(r.category).includes("vegetar"));
  if(p.includes("suppe"))pool=pool.filter(r=>enrichTags(r).includes("suppe"));
  if(p.includes("kylling"))pool=pool.filter(r=>enrichTags(r).includes("kylling"));
  if(p.includes("rask"))pool=pool.filter(r=>enrichTags(r).includes("rask"));
  if(!pool.length)pool=recipes.slice();
  for(const d of days){
    const r=pool[Math.floor(Math.random()*pool.length)];
    plan[d.key]=r?[{type:"recipe",recipeId:r.id}]:[];
    if(r)bumpUsage(r.id);
  }
  savePlan();createDayRows();renderRecipeResults();
}
renderWeekOverview=function(){
  const box=$("weekOverview");if(!box)return;
  box.innerHTML=selectedDays().map(d=>{
    const items=plan[d.key]||[];
    const chips=items.length?items.map(item=>{
      if(item.type==="text")return`<span class="week-chip manual">✍️ ${escapeHtml(item.text)}</span>`;
      const r=recipeById(item.recipeId);
      if(!r)return`<span class="week-chip missing">Mangler</span>`;
      return`<button type="button" class="week-chip${hasRecipe(r)?"":" missing"}" onclick="${hasRecipe(r)?`openRecipeDetails('${escapeAttr(r.id)}')`:`openImport('${escapeAttr(r.id)}')`}">${emojiForRecipe(r)} ${escapeHtml(r.name)}</button>`;
    }).join(""):`<span class="hint">Ingen retter</span>`;
    return`<div class="week-overview-row"><div class="week-overview-day">${d.label}</div><div class="week-overview-items">${chips}</div></div>`;
  }).join("");
}


/* ===== v20.3 smarter freezer AI + week title + better categorization ===== */
function formatShortDate(iso){
  const d=parseLocalDate(iso);
  const months=["jan","feb","mars","apr","mai","juni","juli","aug","sep","okt","nov","des"];
  return `${d.getDate()}. ${months[d.getMonth()]}`;
}
function updateWeekOverviewRange(){
  const el=$("weekOverviewRange"); if(!el)return;
  const days=selectedDays();
  if(!days.length){el.textContent="Oversikt";return;}
  const first=days[0].key, last=days[days.length-1].key;
  el.textContent = first===last ? formatShortDate(first) : `${formatShortDate(first)} – ${formatShortDate(last)}`;
}
const oldRenderWeekOverviewV203 = renderWeekOverview;
renderWeekOverview=function(){
  updateWeekOverviewRange();
  const box=$("weekOverview");if(!box)return;
  box.innerHTML=selectedDays().map(d=>{
    const items=plan[d.key]||[];
    const chips=items.length?items.map(item=>{
      if(item.type==="text")return`<span class="week-chip manual">✍️ ${escapeHtml(item.text)}</span>`;
      const r=recipeById(item.recipeId);
      if(!r)return`<span class="week-chip missing">Mangler</span>`;
      return`<button type="button" class="week-chip${hasRecipe(r)?"":" missing"}" onclick="${hasRecipe(r)?`openRecipeDetails('${escapeAttr(r.id)}')`:`openImport('${escapeAttr(r.id)}')`}">${emojiForRecipe(r)} ${escapeHtml(r.name)}</button>`;
    }).join(""):`<span class="hint">Ingen retter</span>`;
    return`<div class="week-overview-row"><div class="week-overview-day">${d.label}</div><div class="week-overview-items">${chips}</div></div>`;
  }).join("");
}
function freezerKeywordText(){
  return freezerItems.filter(x=>Number(x.qty)>0).map(x=>normalize(x.name)).join(" ");
}
function freezerScoreRecipe(r){
  const f=freezerKeywordText();
  const t=normalize(`${r.name} ${r.category} ${enrichTags(r).join(" ")} ${r.ingredientsText||""}`);
  let score=0;
  const pairs=[
    ["kylling",["kylling","chicken","dumpling","gyoza","kyllingfilet","kyllinglårfilet","kyllingboller"]],
    ["karbonade",["karbonadedeig","bolognese","taco","burger","kjøttboller","lasagne"]],
    ["ørret",["ørret","fisk","salmon","laks"]],
    ["scampi",["scampi","shrimp","reker"]],
    ["edamame",["edamame","asiatisk","bowl","nudler","ramen"]],
    ["svin",["svin","pork","kotelett","ytrefilet"]],
    ["bacon",["bacon"]],
    ["veggisfarse",["veggis","vegetar","taco","bolognese"]],
    ["erter",["erter","pea"]],
    ["halloumi",["halloumi"]]
  ];
  for(const [freezerNeedle, recipeWords] of pairs){
    if(f.includes(freezerNeedle) && recipeWords.some(w=>t.includes(normalize(w)))) score+=3;
  }
  if(isFavorite(r.id))score+=2;
  score+=Math.min(usageCount(r.id),4)*0.25;
  return score;
}
randomWeek=function(){
  const days=selectedDays();
  const usable=recipes.filter(hasRecipe).sort((a,b)=>freezerScoreRecipe(b)-freezerScoreRecipe(a)||a.name.localeCompare(b.name,"no"));
  if(!usable.length){alert("Ingen oppskrifter med innhold funnet.");return}
  for(const d of days){
    const weighted=usable.slice(0, Math.max(8, Math.min(usable.length, 25)));
    const r=weighted[Math.floor(Math.random()*weighted.length)];
    plan[d.key]=[{type:"recipe",recipeId:r.id}];
    bumpUsage(r.id);
  }
  savePlan();createDayRows();renderRecipeResults();
}
smartWeek=async function(){
  const prompt=$("smartPrompt")?.value?.trim()||"",days=selectedDays();
  if($("smartStatus"))$("smartStatus").textContent="Lager AI-forslag med fryseren i bakhodet …";
  try{
    const freezer=freezerItems.filter(x=>Number(x.qty)>0).map(x=>({name:x.name,qty:x.qty,unit:x.unit,category:x.category}));
    const payloadRecipes=recipes.filter(hasRecipe).map(r=>({id:r.id,name:r.name,category:r.category,tags:enrichTags(r),favorite:isFavorite(r.id),usage:usageCount(r.id),freezerScore:freezerScoreRecipe(r)}))
      .sort((a,b)=>b.freezerScore-a.freezerScore||b.usage-a.usage)
      .slice(0,180);
    const res=await fetch("/api/smart-week",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({prompt:`${prompt}\nPrioriter gjerne ting vi har i fryseren: ${freezer.map(x=>`${x.qty} ${x.unit} ${x.name}`).join(", ")}. Velg kun retter som har oppskrift.`,days:days.map(d=>({key:d.key,label:d.label,weekday:d.weekday})),recipes:payloadRecipes,freezer})});
    const data=await res.json();
    if(!data.ok)throw new Error(data.error||"AI-ukemeny feilet");
    for(const d of days)plan[d.key]=[];
    const items=data.plan?.items||[];
    for(const row of items){
      let day=String(row.day||"").toLowerCase();
      const match=days.find(d=>d.key===day||d.weekday===day||normalize(d.label).includes(normalize(day)));
      if(!match)continue;
      const ids=(row.recipeIds||row.recipe_ids||[]).filter(id=>hasRecipe(recipeById(id)));
      plan[match.key]=ids.map(id=>{bumpUsage(id);return{type:"recipe",recipeId:id}});
      if(row.note&&!plan[match.key].length)plan[match.key]=[{type:"text",text:row.note}];
    }
    if($("smartStatus"))$("smartStatus").textContent="AI-forslag laget. Den prioriterte oppskrifter og fryserinnhold.";
    savePlan();createDayRows();renderRecipeResults();
  }catch(e){
    console.warn(e);
    if($("smartStatus"))$("smartStatus").textContent="AI feilet, bruker lokal fryser-smart velger.";
    localSmartWeek();
  }
}
localSmartWeek=function(){
  const p=normalize($("smartPrompt")?.value||""),days=selectedDays();
  let pool=recipes.filter(hasRecipe);
  if(p.includes("vegetar"))pool=pool.filter(r=>enrichTags(r).includes("vegetar")||normalize(r.category).includes("vegetar"));
  if(p.includes("suppe"))pool=pool.filter(r=>enrichTags(r).includes("suppe"));
  if(p.includes("kylling"))pool=pool.filter(r=>enrichTags(r).includes("kylling"));
  if(p.includes("rask"))pool=pool.filter(r=>enrichTags(r).includes("rask"));
  if(!pool.length)pool=recipes.filter(hasRecipe);
  pool=pool.sort((a,b)=>freezerScoreRecipe(b)-freezerScoreRecipe(a)||a.name.localeCompare(b.name,"no"));
  for(const d of days){
    const top=pool.slice(0, Math.max(8, Math.min(pool.length, 25)));
    const r=top[Math.floor(Math.random()*top.length)];
    plan[d.key]=r?[{type:"recipe",recipeId:r.id}]:[];
    if(r)bumpUsage(r.id);
  }
  savePlan();createDayRows();renderRecipeResults();
}
function categorize(line){
  const s=normalize(line);
  const spice=["salt","pepper","oregano","basilikum","basil","gochugaru","paprika","spisskummen","cumin","kanel","cinnamon","chili flakes","chiliflak","curry powder","karri","garam masala","laurbær","sesamfrø","sesame seeds","sukker","sugar","honning","honey","timian","thyme","rosmarin","rosemary","kajenne","cayenne"];
  if(spice.some(w=>s.includes(normalize(w))))return"Krydder";
  const dry=["maizena","cornstarch","maisstivelse","soy sauce","soyasaus","soya","tamari","sesamolje","sesame oil","olivenolje","olive oil","olje","oil","riseddik","rice vinegar","vinegar","eddik","sriracha","hot sauce","fish sauce","fiskesaus","stock","kraft","broth","buljong","peanøttsmør","peanut butter","tomatpure","tomato paste","panko","brødsmuler","breadcrumbs","mel","flour","sriracha","hoisin","worcestershire"];
  if(dry.some(w=>s.includes(normalize(w))))return"Tørrvarer";
  const map=[
    ["Kjøtt",["flankestek","flank steak","steak","biff","beef","kylling","chicken","okse","kjøttdeig","karbonadedeig","svin","pork","kotelett","pølse","sausage","kalkun","bacon","lamm","lamb","skinke","ham"]],
    ["Meieri",["halloumi","melk","milk","fløte","cream","rømme","ost","cheese","parmesan","feta","cottage cheese","yoghurt","yogurt","smør","butter","mozzarella","cheddar"]],
    ["Frys",["frossen","frosne","frozen","edamame"]],
    ["Hermetikk/halvfabrikat",["boks","can ","canned","kokosmelk","coconut milk","kidney","kikerter","chickpeas","diced tomatoes","hakkede tomater","bønner","beans","mais","corn"]],
    ["Tørrvarer",["pasta","nudler","noodles","ris","rice","orzo","bulgur","quinoa","couscous","linser","lentils"]],
    ["Glutenfritt",["glutenfri","gluten free"]],
    ["Bakevarer",["brød","bread","pita","tortilla","burgerbrød","wrap","naan"]],
    ["Frukt og grønt",["agurk","cucumber","gulrot","carrot","løk","onion","hvitløk","garlic","ingefær","ginger","potet","potato","søtpotet","sweet potato","squash","zucchini","tomat","tomato","paprika","bell pepper","sopp","mushroom","brokkoli","broccoli","blomkål","cauliflower","kål","cabbage","spinat","spinach","salat","lettuce","lime","sitron","lemon","koriander","cilantro","persille","parsley","selleri","celery","avokado","avocado","aubergine","eggplant","chili","vårløk","spring onion","ruccola","asparges"]]
  ];
  for(const[cat,words]of map)if(words.some(w=>s.includes(normalize(w))))return cat;
  if(s.includes("tofu"))return"Kjølevarer";
  return"Annet";
}


/* ===== v20.4 freezer recipe suggestions ===== */
function freezerCanonicalItems(){
  return freezerItems.filter(x=>Number(x.qty)>0).map(x=>({
    ...x,
    key: normalize(x.name),
    words: normalize(x.name).split(/\s+/).filter(Boolean)
  }));
}
function freezerRecipeMatches(r){
  if(!hasRecipe(r)) return [];
  const recipeText=normalize(`${r.name} ${r.category} ${enrichTags(r).join(" ")} ${r.ingredientsText||""}`);
  const matches=[];
  const freezer=freezerCanonicalItems();
  const rules=[
    {freezer:["edamame"], recipe:["edamame","bowl","asiatisk","nudler","ramen","salat"]},
    {freezer:["rødkål","rodkal"], recipe:["rødkål","rodkal","kål","salat","taco","asiatisk"]},
    {freezer:["ørret","orret"], recipe:["ørret","orret","fisk","salmon","laks"]},
    {freezer:["scampi"], recipe:["scampi","shrimp","reker","asiatisk","pasta","bowl"]},
    {freezer:["karbonadedeig"], recipe:["karbonadedeig","kjøttdeig","taco","burger","bolognese","lasagne","kjøttboller"]},
    {freezer:["kyllingfilet","kylling"], recipe:["kylling","chicken","curry","fajitas","pasta","bowl","taco"]},
    {freezer:["kyllinglårfilet"], recipe:["kylling","chicken","lår","thigh","curry","gryte"]},
    {freezer:["gyoza","dumplings"], recipe:["gyoza","dumpling","asiatisk","bowl","nudler","ramen"]},
    {freezer:["svin","ytrefilet","kotelett"], recipe:["svin","pork","kotelett","ytrefilet","wok","gryte"]},
    {freezer:["bacon"], recipe:["bacon","pasta","pai","carbonara"]},
    {freezer:["veggisfarse"], recipe:["veggis","vegetar","taco","bolognese","lasagne"]},
    {freezer:["erter"], recipe:["erter","pea","fisk","pai","pasta"]},
    {freezer:["paibunner","paibunn"], recipe:["pai","quiche"]},
    {freezer:["søtpotetfries","sotpotetfries"], recipe:["søtpotet","burger","fisk","kylling"]},
    {freezer:["broccoli"], recipe:["brokkoli","broccoli","vegetar","airfryer"]},
    {freezer:["bringebær","smoothie","acai","granateple"], recipe:["smoothie","dessert","frokost","bowl"]}
  ];
  for(const item of freezer){
    let matched=false;
    for(const rule of rules){
      if(rule.freezer.some(f=>item.key.includes(f))){
        if(rule.recipe.some(w=>recipeText.includes(normalize(w)))){
          matches.push(item);
          matched=true;
          break;
        }
      }
    }
    if(!matched){
      const simple=item.words.filter(w=>w.length>3);
      if(simple.some(w=>recipeText.includes(w))) matches.push(item);
    }
  }
  return matches;
}
function freezerSuggestionCandidates(){
  return recipes
    .filter(hasRecipe)
    .map(r=>({recipe:r,matches:freezerRecipeMatches(r)}))
    .filter(x=>x.matches.length)
    .sort((a,b)=>b.matches.length-a.matches.length || freezerScoreRecipe(b.recipe)-freezerScoreRecipe(a.recipe) || usageCount(b.recipe.id)-usageCount(a.recipe.id))
    .slice(0,8);
}
function renderUseFirstCard(){
  const box=$("freezerUseFirst"); if(!box)return;
  const priority=freezerItems.filter(x=>Number(x.qty)>0).sort((a,b)=>{
    const order=["Fisk","Kylling","Kjøtt","Vegetar","Grønnsaker","Bakst","Frukt/smoothie","Annet"];
    return order.indexOf(a.category||"Annet")-order.indexOf(b.category||"Annet") || Number(b.qty)-Number(a.qty);
  }).slice(0,6);
  box.innerHTML=`<div class="use-first-card"><h3>⚠️ Bruk opp dette først</h3><div class="use-first-list">${priority.map(x=>`<span class="use-first-chip">${escapeHtml(x.qty+" "+(x.unit||"stk")+" "+x.name)}</span>`).join("")}</div></div>`;
}
function renderFreezerRecipeSuggestions(){
  const box=$("freezerRecipeSuggestions"); if(!box)return;
  const candidates=freezerSuggestionCandidates();
  if(!candidates.length){
    box.innerHTML=`<div class="freezer-suggestion-card"><strong>Ingen tydelige treff</strong><div class="freezer-match-reason">Jeg fant ingen oppskrifter som matcher fryseren direkte. Prøv å legge til flere tags/oppskrifter.</div></div>`;
    return;
  }
  const days=selectedDays();
  box.innerHTML=candidates.map(({recipe,matches})=>{
    const reason=`Matcher: ${matches.slice(0,3).map(x=>`${x.qty} ${x.unit||"stk"} ${x.name}`).join(", ")}`;
    const dayButtons=days.slice(0,7).map(d=>`<button type="button" onclick="addFreezerSuggestionToDay('${escapeAttr(recipe.id)}','${escapeAttr(d.key)}')">${d.weekday.slice(0,3)} ${formatShortDate(d.key)}</button>`).join("");
    return`<div class="freezer-suggestion-card"><strong>${emojiForRecipe(recipe)} ${escapeHtml(recipe.name)}</strong><div class="freezer-match-reason">${escapeHtml(reason)}</div><div class="freezer-suggestion-actions"><button type="button" onclick="openRecipeDetails('${escapeAttr(recipe.id)}')">Se oppskrift</button>${dayButtons}</div></div>`;
  }).join("");
}
window.addFreezerSuggestionToDay=function(recipeId,day){
  if(!Array.isArray(plan[day])) plan[day]=[];
  plan[day].push({type:"recipe",recipeId});
  bumpUsage(recipeId);
  savePlan();
  createDayRows();
  showView("viewPlan");
}
freezerSuggest=function(){
  renderUseFirstCard();
  renderFreezerRecipeSuggestions();
  const count=freezerSuggestionCandidates().length;
  $("freezerSuggestion").textContent=count?`Jeg fant ${count} konkrete oppskriftsforslag basert på fryseren.`:"Jeg fant ingen konkrete treff i oppskriftsboken akkurat nå.";
}
const oldRenderFreezerV204=renderFreezer;
renderFreezer=function(){
  oldRenderFreezerV204();
  renderUseFirstCard();
}


/* ===== v20.7 stability overrides ===== */
let pendingPickerRecipeId = null;
let pendingPickerDay = null;
let isSavingPlan = false;
let lastLocalSaveAt = 0;

function canonicalPlanPayload(){
  return {
    items: plan || {},
    shoppingItems: shoppingItems || [],
    freezerItems: freezerItems || [],
    meta: appMeta || {},
    updatedAt: appMeta.updatedAt || new Date().toISOString()
  };
}

savePlan = function(){
  appMeta.updatedAt = new Date().toISOString();
  lastRemoteUpdatedAt = appMeta.updatedAt;
  lastLocalSaveAt = Date.now();
  isSavingPlan = true;

  try { localStorage.setItem("middag_plan", JSON.stringify(plan)); } catch(e) { console.warn("Kunne ikke lagre lokalt", e); }

  setLiveStatus("Lagrer", "syncing");

  fetch("/api/plan", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({plan: canonicalPlanPayload()})
  })
  .then(r => r.json().catch(() => ({})))
  .then(data => {
    if (data && data.ok === false) throw new Error(data.error || "Plan-lagring feilet");
    isSavingPlan = false;
    setLiveStatus("Live");
  })
  .catch(e => {
    isSavingPlan = false;
    console.warn("savePlan-feil", e);
    setLiveStatus("Sync-feil", "error");
  });
};

syncFromServer = async function(){
  try {
    if (isSavingPlan || Date.now() - lastLocalSaveAt < 2500) return;

    setLiveStatus("Syncer", "syncing");
    const pr = await fetch("/api/plan?ts=" + Date.now(), {cache: "no-store"}).then(r => r.json());
    const remote = pr.plan?.updatedAt || "";

    if (remote && remote !== lastRemoteUpdatedAt && remote !== appMeta.updatedAt) {
      plan = migratePlan(pr.plan?.items || {});
      shoppingItems = pr.plan?.shoppingItems || [];
      freezerItems = pr.plan?.freezerItems || freezerItems || [];
      appMeta = pr.plan?.meta || appMeta;
      lastRemoteUpdatedAt = remote;
      createDayRows();
      renderShoppingList(shoppingItems);
      renderRecipeResults();
      renderFreezer();
    }

    const rr = await fetch("/api/recipes?ts=" + Date.now(), {cache: "no-store"}).then(r => r.json());
    if (rr.recipes && rr.recipes.length !== recipes.length) {
      recipes = rr.recipes;
      mergeCustomData();
      renderRecipeResults();
      createDayRows();
    }

    setLiveStatus("Live");
  } catch(e) {
    console.warn("sync-feil", e);
    setLiveStatus("Offline?", "error");
  }
};

startRealtimeSync = function(){
  if (syncTimer) clearInterval(syncTimer);
  syncTimer = setInterval(syncFromServer, 2500);
  setLiveStatus("Live");
};

function ensurePlanDay(day){
  if (!plan || typeof plan !== "object") plan = {};
  if (!Array.isArray(plan[day])) plan[day] = [];
}

addFreeTextToDay = function(day, text){
  const t = String(text || "").trim();
  if (!t) return;
  ensurePlanDay(day);
  plan[day].push({type: "text", text: t});
  savePlan();
  createDayRows();
};

window.addRecipeToDay = function(day, id){
  ensurePlanDay(day);
  plan[day].push({type: "recipe", recipeId: id});
  bumpUsage(id);
  savePlan();
  createDayRows();
  renderRecipeResults();
  if ($("recipePickerDialog")) $("recipePickerDialog").close();
  if ($("pickerPreviewDialog")) $("pickerPreviewDialog").close();
};

openRecipePicker = function(day){
  activePickerDay = day;
  pendingPickerDay = day;
  if ($("pickerSearch")) $("pickerSearch").value = "";
  renderPickerResults();
  $("recipePickerDialog").showModal();
};

renderPickerResults = function(){
  const q = normalize($("pickerSearch")?.value || "");
  const filtered = recipes
    .filter(r => !q || searchableText(r).includes(q))
    .sort((a,b) => Number(hasRecipe(b)) - Number(hasRecipe(a)) || a.name.localeCompare(b.name, "no"))
    .slice(0, 300);

  const box = $("pickerResults");
  if (!box) return;

  box.innerHTML = filtered.map(r => `
    <div class="recipe-card" onclick="openPickerPreview('${escapeAttr(r.id)}')">
      <div class="recipe-thumb recipe-emoji">${emojiForRecipe(r)}</div>
      <div>
        <strong>${escapeHtml(r.name)}</strong>
        <div class="recipe-meta">${escapeHtml(r.category || "Ukjent")} · ${hasRecipe(r) ? "✅ Oppskrift funnet" : "🟡 mangler oppskrift"}</div>
        <div class="recipe-tags">${enrichTags(r).slice(0,4).map(t => `<span class="tag">${escapeHtml(t)}</span>`).join("")}</div>
      </div>
      <button type="button" class="ghost" onclick="event.stopPropagation(); openPickerPreview('${escapeAttr(r.id)}')">Se</button>
    </div>
  `).join("") || `<div class="empty-state">Ingen oppskrifter funnet.</div>`;
};

window.openPickerPreview = function(recipeId){
  const r = recipeById(recipeId);
  if (!r) return;
  pendingPickerRecipeId = recipeId;

  const title = $("pickerPreviewTitle");
  const body = $("pickerPreviewBody");
  if (title) title.textContent = `${emojiForRecipe(r)} ${r.name}`;
  if (body) {
    body.innerHTML = `
      <p class="recipe-meta">${escapeHtml(r.category || "Ukjent")} · ${hasRecipe(r) ? "Oppskrift funnet" : "Mangler oppskrift"}</p>
      <div class="recipe-tags">${enrichTags(r).slice(0,8).map(t => `<span class="tag">${escapeHtml(t)}</span>`).join("")}</div>
      <div class="recipe-detail-section">
        <h3>Ingredienser</h3>
        <div class="picker-preview-ingredients">${formatList(ingredientsToText(r))}</div>
      </div>
      <div class="recipe-detail-section">
        <h3>Fremgangsmåte</h3>
        <div class="picker-preview-instructions">${formatSteps(instructionsToText(r))}</div>
      </div>
      ${r.link ? `<a class="source-link-inline" href="${escapeAttr(r.link)}" target="_blank" rel="noopener">Åpne kilde</a>` : ""}
    `;
  }

  const btn = $("pickerPreviewAddBtn");
  if (btn) {
    btn.onclick = () => {
      if (!pendingPickerDay || !pendingPickerRecipeId) return;
      window.addRecipeToDay(pendingPickerDay, pendingPickerRecipeId);
    };
  }

  $("pickerPreviewDialog").showModal();
};

confirmAddToDay = function(){
  const day = $("addToDaySelect")?.value;
  if (!day || !pendingAddRecipeId) return;
  ensurePlanDay(day);
  plan[day].push({type: "recipe", recipeId: pendingAddRecipeId});
  bumpUsage(pendingAddRecipeId);
  savePlan();
  createDayRows();
  renderRecipeResults();
  if ($("addToDayDialog")) $("addToDayDialog").close();
  if ($("recipeDialog")) $("recipeDialog").close();
  showView("viewPlan");
};

const originalCreateDayRowsV207 = createDayRows;
createDayRows = function(){
  originalCreateDayRowsV207();
  renderWeekOverview();
};

document.addEventListener("input", (e) => {
  if (e.target && (e.target.id === "recipeSearch" || e.target.id === "pickerSearch")) {
    e.target.style.height = "42px";
  }
}, true);


/* ===== v20.9 critical fix: preserve date-keyed plans ===== */
migratePlan = function(raw){
  const out = {};
  if (!raw || typeof raw !== "object") return out;

  // Preserve all ISO-date keys, e.g. 2026-06-11.
  for (const [key, val] of Object.entries(raw)) {
    if (/^\d{4}-\d{2}-\d{2}$/.test(key)) {
      if (Array.isArray(val)) out[key] = val;
      else if (val) out[key] = [{type: "recipe", recipeId: val}];
      else out[key] = [];
    }
  }

  // Backwards compatibility: migrate old weekday keys into the currently selected date range.
  const selected = typeof selectedDays === "function" ? selectedDays() : [];
  for (const d of selected) {
    if (!Array.isArray(out[d.key])) {
      const oldVal = raw[d.weekday];
      if (Array.isArray(oldVal)) out[d.key] = oldVal;
      else if (oldVal) out[d.key] = [{type: "recipe", recipeId: oldVal}];
      else out[d.key] = [];
    }
  }

  // Also preserve any non-date custom keys that are arrays, instead of silently dropping them.
  for (const [key, val] of Object.entries(raw)) {
    if (!out[key] && Array.isArray(val) && !DAYS.includes(key)) {
      out[key] = val;
    }
  }

  return out;
};

function clonePlanSafe(p){
  try { return JSON.parse(JSON.stringify(p || {})); }
  catch(e) { return p || {}; }
}

savePlan = function(){
  appMeta.updatedAt = new Date().toISOString();
  lastRemoteUpdatedAt = appMeta.updatedAt;
  lastLocalSaveAt = Date.now();
  isSavingPlan = true;

  const safePlan = clonePlanSafe(plan);

  try {
    localStorage.setItem("middag_plan", JSON.stringify(safePlan));
  } catch(e) {
    console.warn("Kunne ikke lagre lokalt", e);
  }

  setLiveStatus("Lagrer", "syncing");

  fetch("/api/plan", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({
      plan: {
        items: safePlan,
        shoppingItems: shoppingItems || [],
        freezerItems: freezerItems || [],
        meta: appMeta || {},
        updatedAt: appMeta.updatedAt
      }
    })
  })
  .then(r => r.json().catch(() => ({})))
  .then(data => {
    if (data && data.ok === false) throw new Error(data.error || "Plan-lagring feilet");
    isSavingPlan = false;
    setLiveStatus("Live");
  })
  .catch(e => {
    isSavingPlan = false;
    console.warn("savePlan-feil", e);
    setLiveStatus("Sync-feil", "error");
  });
};

syncFromServer = async function(){
  try {
    if (isSavingPlan || Date.now() - lastLocalSaveAt < 3500) return;

    setLiveStatus("Syncer", "syncing");
    const pr = await fetch("/api/plan?ts=" + Date.now(), {cache: "no-store"}).then(r => r.json());
    const remote = pr.plan?.updatedAt || "";

    if (remote && remote !== lastRemoteUpdatedAt && remote !== appMeta.updatedAt) {
      const remoteItems = pr.plan?.items || {};
      const migrated = migratePlan(remoteItems);

      // Safety: never replace a non-empty visible date range with a totally empty one.
      const visibleKeys = selectedDays().map(d => d.key);
      const currentVisibleCount = visibleKeys.reduce((sum,k) => sum + ((plan[k] || []).length), 0);
      const remoteVisibleCount = visibleKeys.reduce((sum,k) => sum + ((migrated[k] || []).length), 0);
      if (currentVisibleCount > 0 && remoteVisibleCount === 0) {
        console.warn("Hoppet over tom remote-plan for å unngå overskriving av lokal ukeplan");
      } else {
        plan = migrated;
      }

      shoppingItems = pr.plan?.shoppingItems || shoppingItems || [];
      freezerItems = pr.plan?.freezerItems || freezerItems || [];
      appMeta = pr.plan?.meta || appMeta;
      lastRemoteUpdatedAt = remote;

      createDayRows();
      renderShoppingList(shoppingItems);
      renderRecipeResults();
      renderFreezer();
    }

    const rr = await fetch("/api/recipes?ts=" + Date.now(), {cache: "no-store"}).then(r => r.json());
    if (rr.recipes && rr.recipes.length !== recipes.length) {
      recipes = rr.recipes;
      mergeCustomData();
      renderRecipeResults();
      createDayRows();
    }

    setLiveStatus("Live");
  } catch(e) {
    console.warn("sync-feil", e);
    setLiveStatus("Offline?", "error");
  }
};


/* ===== v21 shopping model + recipe data cleanup ===== */
let lastShoppingEditAt = 0;

function ensureShoppingIds(){
  let changed=false;
  shoppingItems=(shoppingItems||[]).map((it,idx)=>{
    if(!it.id){changed=true; return {...it,id:`shop-${Date.now()}-${idx}-${Math.random().toString(16).slice(2)}`};}
    return it;
  });
  return changed;
}

function saveShoppingSoon(){
  lastShoppingEditAt=Date.now();
  ensureShoppingIds();
  savePlan();
}

function getShoppingItem(id){
  return (shoppingItems||[]).find(x=>x.id===id);
}

renderShoppingList=function(items){
  shoppingItems=items||[];
  ensureShoppingIds();

  const grouped=Object.fromEntries(CATEGORIES.map(c=>[c,[]]));
  for(const item of shoppingItems){
    const cat=item.category||categorize(item.text||"");
    item.category=cat;
    if(!grouped[cat])grouped[cat]=[];
    grouped[cat].push(item);
  }

  const total=shoppingItems.length, merged=shoppingItems.filter(x=>x.merged).length;
  const summary=`<p class="shopping-summary">${total} varer${merged?` · ${merged} slått sammen`:""}</p>`;

  $("shoppingList").innerHTML=summary+CATEGORIES.map(cat=>{
    const arr=grouped[cat]||[];
    return`<div class="category" data-category="${escapeAttr(cat)}"><div class="category-head"><h3>${cat}</h3><button class="tiny-add" onclick="addCustomShoppingItem('${escapeAttr(cat)}')">+ Legg til</button></div><div class="category-items">${arr.length?arr.map(it=>shoppingItemHtml(it)).join(""):`<p class="hint small-hint">Ingen varer enda.</p>`}</div></div>`;
  }).join("");
}

shoppingItemHtml=function(it){
  return`<div class="item" data-shopping-id="${escapeAttr(it.id)}"><input type="checkbox" ${it.done?"checked":""} onchange="toggleShoppingDone('${escapeAttr(it.id)}', this.checked)"><input type="text" value="${escapeAttr(it.text)}" title="Fra: ${escapeAttr(it.recipe||'Egen vare')}" onblur="updateShoppingText('${escapeAttr(it.id)}', this.value)" onkeydown="if(event.key==='Enter'){this.blur()}">${it.merged?`<span class="merged-badge">slått sammen</span>`:""}<button class="remove-btn" title="Fjern" onclick="removeShoppingItem('${escapeAttr(it.id)}')">×</button></div>`;
}

window.toggleShoppingDone=function(id,checked){
  const it=getShoppingItem(id); if(!it)return;
  it.done=!!checked;
  saveShoppingSoon();
}

window.updateShoppingText=function(id,value){
  const it=getShoppingItem(id); if(!it)return;
  const text=String(value||"").trim();
  if(!text)return;
  it.text=text;
  it.category=categorize(text);
  saveShoppingSoon();
  renderShoppingList(shoppingItems);
}

window.removeShoppingItem=function(id){
  const el=document.querySelector(`[data-shopping-id="${CSS.escape(id)}"]`);
  if(el)el.classList.add("removing");
  shoppingItems=(shoppingItems||[]).filter(x=>x.id!==id);
  saveShoppingSoon();
  renderShoppingList(shoppingItems);
}

window.addCustomShoppingItem=function(category){
  const text=prompt(`Legg til vare i ${category}:`);
  if(!text||!text.trim())return;
  shoppingItems.push({id:`shop-${Date.now()}-${Math.random().toString(16).slice(2)}`,text:normalizeIngredientLineForDisplay(text.trim()),category,recipe:"Egen vare",done:false});
  renderShoppingList(shoppingItems);
  saveShoppingSoon();
}

function normalizeForMergeUnit(unit,name){
  const n=normalize(name);
  const u=String(unit||"").toLowerCase();
  const produce=["stangselleri","selleri","løk","gulrot","paprika","agurk","tomat","sitron","lime","avokado","squash","brokkoli","blomkål","hvitløk"];
  if(produce.some(p=>n.includes(p))){
    if(["dl","ml","cup","cups"].includes(u)) return "stk";
  }
  return u || "stk";
}

function parseAmount(text){
  let s=normalizeIngredientLineForDisplay(String(text||"").replace(/\s*\[[^\]]+\]\s*$/,"").trim());
  const m=s.match(/^(\d+(?:[.,]\d+)?)\s*(g|kg|dl|l|ml|ss|ts|stk|pk|pose|poser|boks|fedd|stilker|stilk)?\s+(.+)$/i);
  if(!m)return{amount:null,unit:"",name:normalizeIngredientName(s),original:s};
  let amount=parseFloat(m[1].replace(",",".")),unit=(m[2]||"stk").toLowerCase(),name=normalizeIngredientName(m[3]);
  if(unit==="kg"){amount*=1000;unit="g"}
  if(unit==="l"){amount*=10;unit="dl"}
  if(unit==="stilker")unit="stilk";
  unit=normalizeForMergeUnit(unit,name);
  return{amount,unit,name,original:s}
}

function normalizeIngredientName(name){
  let s=String(name||"").toLowerCase().trim();
  s=translateIngredientWords(s);
  s=s.replace(/\([^)]*\)/g,"").replace(/[,].*$/,"").trim();
  s=s.replace(/\b(chopped|finely|thinly|sliced|diced|minced|grated|fresh|freshly|large|medium|small|heaped|smooth|natural|drained|rinsed|optional|to serve|hakket|finhakket|skivet|revet|fersk|stor|liten|medium|valgfritt|til servering|i terninger|terninger)\b/g,"");
  s=s.replace(/\s+/g," ").trim();
  const aliases={"garlic":"hvitløk","onion":"løk","yellow onion":"løk","red onion":"rødløk","spring onion":"vårløk","carrot":"gulrot","carrots":"gulrot","celery":"stangselleri","celery stalk":"stangselleri","cucumber":"agurk","tomatoes":"tomat","tomato":"tomat","chickpeas":"kikerter","beans":"bønner","rice noodles":"risnudler","noodles":"nudler","soy sauce":"soyasaus","olive oil":"olivenolje","cornstarch":"maizena","corn starch":"maizena","bell pepper":"paprika"};
  return aliases[s]||s;
}

function translateIngredientWords(s){
  const replacements=[
    [/celery stalks?/g,"stangselleri"],[/celery/g,"stangselleri"],[/garlic cloves?/g,"fedd hvitløk"],[/garlic/g,"hvitløk"],
    [/yellow onion/g,"gul løk"],[/red onion/g,"rødløk"],[/onion/g,"løk"],[/spring onion/g,"vårløk"],
    [/carrots?/g,"gulrot"],[/cucumber/g,"agurk"],[/tomatoes/g,"tomat"],[/tomato/g,"tomat"],
    [/bell pepper/g,"paprika"],[/mushrooms?/g,"sopp"],[/spinach/g,"spinat"],[/lettuce/g,"salat"],
    [/chickpeas/g,"kikerter"],[/beans/g,"bønner"],[/chicken/g,"kylling"],[/beef/g,"biff"],[/pork/g,"svin"],
    [/shrimp/g,"scampi"],[/salmon/g,"laks"],[/halloumi/g,"halloumi"],[/cornstarch|corn starch/g,"maizena"],
    [/soy sauce/g,"soyasaus"],[/olive oil/g,"olivenolje"],[/sesame oil/g,"sesamolje"],[/rice vinegar/g,"riseddik"],
    [/coconut milk/g,"kokosmelk"],[/stock|broth/g,"kraft"],[/noodles/g,"nudler"],[/rice/g,"ris"]
  ];
  let out=String(s||"").toLowerCase();
  for(const [from,to] of replacements)out=out.replace(from,to);
  return out;
}

function normalizeIngredientLineForDisplay(line){
  let s=String(line||"").trim();
  s=s.replace(/\s+/g," ");
  s=translateIngredientWords(s);

  // Avoid nonsense like "4,2 dl stangselleri". Cups of chopped vegetables become approximate pieces/stalks.
  s=s.replace(/(\d+(?:[.,]\d+)?)\s*cups?\s+(?:chopped\s+|diced\s+|sliced\s+)?(celery|stangselleri)\b/gi,(_,n)=>`${Math.max(1,Math.round(parseFloat(n.replace(",","."))*2))} stilker stangselleri`);
  s=s.replace(/(\d+(?:[.,]\d+)?)\s*cups?\s+(?:chopped\s+|diced\s+|sliced\s+)?(onion|løk)\b/gi,(_,n)=>`${Math.max(1,Math.round(parseFloat(n.replace(",","."))))} løk`);
  s=s.replace(/(\d+(?:[.,]\d+)?)\s*cups?\s+(?:chopped\s+|diced\s+|sliced\s+)?(carrot|gulrot|carrots)\b/gi,(_,n)=>`${Math.max(1,Math.round(parseFloat(n.replace(",","."))*2))} gulrot`);
  s=s.replace(/(\d+(?:[.,]\d+)?)\s*cups?\s+(?:chopped\s+|diced\s+|sliced\s+)?(bell pepper|paprika)\b/gi,(_,n)=>`${Math.max(1,Math.round(parseFloat(n.replace(",","."))))} paprika`);

  // Generic cups: keep dl for liquids/dry goods.
  s=s.replace(/(\d+(?:[.,]\d+)?)\s*cups?\b/gi,(_,n)=>`${String(Math.round(parseFloat(n.replace(",","."))*24)/10).replace(".",",")} dl`);
  s=s.replace(/(\d+(?:[.,]\d+)?)\s*(tbsp|tablespoons?)\b/gi,"$1 ss");
  s=s.replace(/(\d+(?:[.,]\d+)?)\s*(tsp|teaspoons?)\b/gi,"$1 ts");
  s=s.replace(/(\d+(?:[.,]\d+)?)\s*(oz|ounces?)\b/gi,(_,n)=>`${Math.round(parseFloat(n.replace(",","."))*28.35)} g`);

  return s.trim();
}

convertIngredientLine=function(line){
  return normalizeIngredientLineForDisplay(line);
}

function mergeShoppingItems(items){
  const map=new Map(),pass=[];
  for(const it of items){
    const normalizedText=normalizeIngredientLineForDisplay(it.text);
    const p=parseAmount(normalizedText);
    if(!p.name){pass.push({...it,text:normalizedText});continue}
    const key=normalize(p.name+"|"+(p.unit||""));
    if(!map.has(key)){
      map.set(key,{...it,id:it.id||`shop-${Date.now()}-${Math.random().toString(16).slice(2)}`,text:formatMergedItem(p),category:categorize(p.name),_p:p,_recipes:new Set([it.recipe])});
    }else{
      const cur=map.get(key);
      if(p.amount!=null&&cur._p.amount!=null&&p.unit===cur._p.unit){
        cur._p.amount+=p.amount;cur.text=formatMergedItem(cur._p)
      }else{
        cur.text=cur.text+" + "+normalizedText
      }
      cur._recipes.add(it.recipe);cur.recipe=[...cur._recipes].join(", ");cur.merged=true;cur.category=bestCategory(cur.category,categorize(p.name))
    }
  }
  return[...map.values(),...pass].map(x=>{delete x._p;delete x._recipes;if(!x.id)x.id=`shop-${Date.now()}-${Math.random().toString(16).slice(2)}`;return x})
}

function categorize(line){
  const s=normalize(line);
  const spice=["salt","pepper","oregano","basilikum","basil","gochugaru","paprika powder","spisskummen","cumin","kanel","cinnamon","chili flakes","chiliflak","curry powder","karri","garam masala","laurbær","sesamfrø","sukker","honning","timian","rosmarin","kajenne"];
  if(spice.some(w=>s.includes(normalize(w))))return"Krydder";
  const dry=["maizena","maisstivelse","cornstarch","soyasaus","soya","tamari","sesamolje","olivenolje","olje","riseddik","eddik","sriracha","hot sauce","fiskesaus","kraft","buljong","peanøttsmør","tomatpure","panko","brødsmuler","mel","hoisin","worcestershire"];
  if(dry.some(w=>s.includes(normalize(w))))return"Tørrvarer";
  const map=[
    ["Kjøtt",["flankestek","flank steak","steak","biff","okse","kjøttdeig","karbonadedeig","svin","kotelett","pølse","kalkun","bacon","lamm","skinke"]],
    ["Kjølevarer",["tofu"]],
    ["Meieri",["halloumi","melk","fløte","rømme","ost","parmesan","feta","cottage cheese","yoghurt","smør","mozzarella","cheddar"]],
    ["Kjøtt",["kylling"]],
    ["Frys",["frossen","frosne","edamame"]],
    ["Hermetikk/halvfabrikat",["boks","kokosmelk","kidney","kikerter","hakkede tomater","bønner","mais"]],
    ["Tørrvarer",["pasta","nudler","ris","orzo","bulgur","quinoa","couscous","linser"]],
    ["Glutenfritt",["glutenfri"]],
    ["Bakevarer",["brød","pita","tortilla","burgerbrød","wrap","naan"]],
    ["Frukt og grønt",["stangselleri","selleri","agurk","gulrot","løk","rødløk","gul løk","vårløk","hvitløk","ingefær","potet","søtpotet","squash","tomat","paprika","sopp","brokkoli","blomkål","kål","spinat","salat","lime","sitron","koriander","persille","avokado","aubergine","chili","ruccola","asparges"]]
  ];
  for(const[cat,words]of map)if(words.some(w=>s.includes(normalize(w))))return cat;
  return"Annet";
}

cleanupVisibleRecipes=async function(){
  if(!confirm("Rydde og oversette ingredienser i oppskriftene? Dette lagrer tilbake til Supabase."))return;
  const btn=$("cleanupRecipesBtn");if(btn){btn.disabled=true;btn.textContent="Rydder/oversetter …"}
  let updated=0;
  for(const r of recipes){
    const patch=meaningfulPatch({
      tags:enrichTags(r),
      emoji:emojiForRecipe(r),
      ingredientsText:ingredientsToText(r).split(/\n/).map(normalizeIngredientLineForDisplay).join("\n"),
      updatedAt:new Date().toISOString()
    });
    try{
      const response=await fetch("/api/save-recipe",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({id:r.id,patch})});
      const data=await response.json().catch(()=>({}));
      if(response.ok&&data.ok!==false){Object.assign(r,mergePreservingExistingData(r,patch));updated++}
    }catch(e){console.warn("rydd feilet",r.name,e)}
  }
  renderRecipeResults();createDayRows();
  if(btn){btn.disabled=false;btn.textContent="Rydd/oversett oppskrifter"}
  alert(`Ryddet/oversatte ${updated} oppskrifter.`);
}


/* ===== v22 remember selected date range + UI stability ===== */
function rememberDateRange(){
  const start=$("startDate")?.value||"";
  const end=$("endDate")?.value||"";
  if(start&&end){
    localStorage.setItem("middag_date_range", JSON.stringify({start,end,updatedAt:new Date().toISOString()}));
  }
}
const oldFillDaySelectorsV22 = fillDaySelectorsV20;
fillDaySelectorsV20=function(){
  let saved=null;
  try{saved=JSON.parse(localStorage.getItem("middag_date_range")||"null")}catch(e){}
  if(saved?.start&&saved?.end){
    if($("startDate"))$("startDate").value=saved.start;
    if($("endDate"))$("endDate").value=saved.end;
    updateDateLabels();
    return;
  }
  oldFillDaySelectorsV22();
}
const oldUpdateDateLabelsV22 = updateDateLabels;
updateDateLabels=function(){
  oldUpdateDateLabelsV22();
  rememberDateRange();
}
const oldCreateDayRowsV22 = createDayRows;
createDayRows=function(){
  rememberDateRange();
  oldCreateDayRowsV22();
}
document.addEventListener("change",(e)=>{
  if(e.target && (e.target.id==="startDate"||e.target.id==="endDate")){
    rememberDateRange();
  }
},true);


/* ===== v23 completeness + safer parser status ===== */
function recipeHasIngredientsV23(r){
  if(!r) return false;
  const d = r.data || r;
  const ingText = d.ingredientsText || r.ingredientsText || "";
  const lines = d.ingredientLines || r.ingredientLines || [];
  const structured = d.structuredIngredients || r.structuredIngredients || [];
  return !!(String(ingText).trim() || (Array.isArray(lines)&&lines.length) || (Array.isArray(structured)&&structured.length));
}
const oldHasRecipeV23 = typeof hasRecipe === "function" ? hasRecipe : null;
hasRecipe = function(r){ return recipeHasIngredientsV23(r); }
function statusTextV23(r){ return recipeHasIngredientsV23(r) ? "✅ Oppskrift funnet" : "⚠️ mangler ingredienser"; }
function statusClassV23(r){ return recipeHasIngredientsV23(r) ? "complete-recipe" : "missing-ingredients"; }

function normalizeNorwegianTextV23(value){
  if(value == null) return value;
  const clean = (line)=>{
    let s=String(line||"");
    const reps=[
      [/\bwhite onion\b/gi,"gul løk"],[/\bwhite\s+løk\b/gi,"gul løk"],[/\byellow onion\b/gi,"gul løk"],[/\byellow\s+løk\b/gi,"gul løk"],[/\bred onion\b/gi,"rødløk"],[/\bred\s+løk\b/gi,"rødløk"],
      [/\bspring onion\b/gi,"vårløk"],[/\bgreen onion\b/gi,"vårløk"],[/\bcelery stalks?\b/gi,"stangselleri"],[/\bcelery\b/gi,"stangselleri"],[/\bgarlic cloves?\b/gi,"fedd hvitløk"],[/\bgarlic\b/gi,"hvitløk"],
      [/\bcarrots?\b/gi,"gulrot"],[/\btomatoes\b/gi,"tomater"],[/\btomato\b/gi,"tomat"],[/\bchicken\b/gi,"kylling"],[/\bcornstarch\b/gi,"maizena"],[/\bcorn starch\b/gi,"maizena"],[/\bsoy sauce\b/gi,"soyasaus"],[/\bolive oil\b/gi,"olivenolje"]
    ];
    for(const [a,b] of reps) s=s.replace(a,b);
    const num=x=>parseFloat(String(x).replace(",","."));
    s=s.replace(/(\d+(?:[.,]\d+)?)\s*cups?\s+(?:chopped\s+|diced\s+|sliced\s+)?(?:celery|stangselleri)\b/gi,(_,n)=>`${Math.max(1,Math.round(num(n)*2))} stilker stangselleri`);
    s=s.replace(/(\d+(?:[.,]\d+)?)\s*cups?\s+(?:chopped\s+|diced\s+|sliced\s+)?(?:onion|løk|gul løk)\b/gi,(_,n)=>`${Math.max(1,Math.round(num(n)))} gul løk`);
    s=s.replace(/(\d+(?:[.,]\d+)?)\s*cups?\b/gi,(_,n)=>`${String(Math.round(num(n)*24)/10).replace(".",",")} dl`);
    s=s.replace(/(\d+(?:[.,]\d+)?)\s*(tbsp|tablespoons?)\b/gi,"$1 ss").replace(/(\d+(?:[.,]\d+)?)\s*(tsp|teaspoons?)\b/gi,"$1 ts");
    return s.replace(/\s+/g," ").trim();
  };
  if(typeof value==="string") return value.split(/\n/).map(clean).filter(Boolean).join("\n");
  if(Array.isArray(value)) return value.map(x=>typeof x==="string"?clean(x):(x&&typeof x==="object"?normalizeNorwegianTextV23(x):x));
  if(typeof value==="object"){const out={...value};for(const k of Object.keys(out))out[k]=normalizeNorwegianTextV23(out[k]);return out;}
  return value;
}
const oldExtractIngredientLinesV23 = typeof extractIngredientLines === "function" ? extractIngredientLines : null;
extractIngredientLines = function(r){ return (oldExtractIngredientLinesV23 ? oldExtractIngredientLinesV23(r) : []).map(x=>normalizeNorwegianTextV23(x)).filter(Boolean); }

const oldRenderRecipeResultsV23 = typeof renderRecipeResults === "function" ? renderRecipeResults : null;
renderRecipeResults = function(){
  if(oldRenderRecipeResultsV23) oldRenderRecipeResultsV23();
  document.querySelectorAll(".recipe-card").forEach(card=>{
    const name=card.querySelector("strong")?.textContent?.trim();
    const r=recipes.find(x=>x.name===name);
    if(!r)return;
    card.classList.add(statusClassV23(r));
    const meta=card.querySelector(".recipe-meta");
    if(meta){
      meta.innerHTML=meta.innerHTML.replace(/✅ Oppskrift funnet|🟡 mangler oppskrift|⚠️ mangler ingredienser/g,statusTextV23(r));
      if(!recipeHasIngredientsV23(r)&&!meta.innerHTML.includes("mangler ingredienser")) meta.innerHTML += ` <span class="missing-ingredients-badge">mangler ingredienser</span>`;
    }
  });
}
const oldRenderPickerResultsV23 = typeof renderPickerResults === "function" ? renderPickerResults : null;
renderPickerResults = function(){
  const q=normalize($("pickerSearch")?.value||"");
  const filtered=recipes.filter(r=>!q||searchableText(r).includes(q)).sort((a,b)=>Number(recipeHasIngredientsV23(b))-Number(recipeHasIngredientsV23(a))||a.name.localeCompare(b.name,"no")).slice(0,300);
  const box=$("pickerResults"); if(!box)return;
  box.innerHTML=filtered.map(r=>`<div class="recipe-card ${statusClassV23(r)}" onclick="openPickerPreview('${escapeAttr(r.id)}')"><div class="recipe-thumb recipe-emoji">${emojiForRecipe(r)}</div><div><strong>${escapeHtml(r.name)}</strong><div class="recipe-meta">${escapeHtml(r.category||"Ukjent")} · ${statusTextV23(r)}</div><div class="recipe-tags">${enrichTags(r).slice(0,4).map(t=>`<span class="tag">${escapeHtml(t)}</span>`).join("")}</div></div><button type="button" class="ghost" onclick="event.stopPropagation(); openPickerPreview('${escapeAttr(r.id)}')">Se</button></div>`).join("")||`<div class="empty-state">Ingen oppskrifter funnet.</div>`;
}
const oldOpenRecipeDetailsV23 = typeof openRecipeDetails === "function" ? openRecipeDetails : null;
openRecipeDetails = function(id){
  if(oldOpenRecipeDetailsV23) oldOpenRecipeDetailsV23(id);
  const r=recipeById(id);
  const body=$("recipeBody")||$("recipeDetailBody")||document.querySelector("#recipeDialog .dialog-form");
  if(r&&body&&!recipeHasIngredientsV23(r)&&!body.querySelector(".recipe-health-panel")) body.insertAdjacentHTML("afterbegin",`<div class="recipe-health-panel">⚠️ Mangler ingredienser. Handlelisten blir ikke komplett før oppskriften repareres/AI-parses på nytt.</div>`);
}
const oldAddRecipeToDayV23 = window.addRecipeToDay;
window.addRecipeToDay = function(day,id){
  const r=recipeById(id);
  if(r&&!recipeHasIngredientsV23(r)&&!confirm("Denne oppskriften mangler ingredienser, så handlelisten blir ikke komplett. Legge til likevel?")) return;
  oldAddRecipeToDayV23(day,id);
}
const oldGenerateShoppingListV23 = typeof generateShoppingList === "function" ? generateShoppingList : null;
generateShoppingList = function(){
  const missing=[];
  for(const d of selectedDays()){
    for(const item of(plan[d.key]||[])){
      if(item.type==="recipe"){const r=recipeById(item.recipeId); if(r&&!recipeHasIngredientsV23(r))missing.push(r.name);}
    }
  }
  if(missing.length) alert("Noen retter mangler ingredienser og kommer ikke komplett på handlelisten:\n\n"+[...new Set(missing)].join("\n"));
  oldGenerateShoppingListV23();
}

/* ===== v25 professional UI, resilient sync and seamless shopping ===== */
const SHOPPING_EPOCH = "2000-01-01T00:00:00.000Z";
let saveRevisionV25 = 0;
let savedRevisionV25 = 0;
let saveWorkerV25 = null;
let saveRetryV25 = null;
let shoppingRenderTimerV25 = null;
const collapsedShoppingCategoriesV25 = new Set();

function nowIsoV25(){ return new Date().toISOString(); }
categorize = function(line){
  const value = normalize(line);
  const has = words => words.some(word => value.includes(normalize(word)));
  if (has(["kylling","biff","flankestek","okse","kjøttdeig","karbonadedeig","svin","kotelett","pølse","kalkun","bacon","lam","skinke"])) return "Kjøtt";
  if (has(["halloumi","melk","fløte","rømme","parmesan","feta","cottage cheese","yoghurt","smør","mozzarella","cheddar","ost"])) return "Meieri";
  if (has(["tofu"])) return "Kjølevarer";
  if (has(["frossen","frosne","edamame"])) return "Frys";
  if (has(["paprikapulver","chilipulver","salt","pepper","oregano","basilikum","gochugaru","spisskummen","kanel","chiliflak","karri","garam masala","laurbær","sesamfrø","timian","rosmarin","kajenne"])) return "Krydder";
  if (has(["boks","kokosmelk","kidneybønner","kikerter","hakkede tomater","hermetisk","mais på boks"])) return "Hermetikk/halvfabrikat";
  if (has(["maizena","maisstivelse","soyasaus","tamari","sesamolje","olivenolje","riseddik","eddik","sriracha","fiskesaus","kraft","buljong","peanøttsmør","tomatpuré","tomatpure","panko","brødsmuler","hvetemel"," hoisin","worcestershire","pasta","nudler","ris","orzo","bulgur","quinoa","couscous","linser"])) return "Tørrvarer";
  if (has(["glutenfri"])) return "Glutenfritt";
  if (has(["brød","pita","tortilla","burgerbrød","wrap","naan"])) return "Bakevarer";
  if (has(["stangselleri","selleri","agurk","gulrot","rødløk","gul løk","vårløk","løk","hvitløk","ingefær","potet","søtpotet","squash","tomat","paprika","sopp","brokkoli","blomkål","kål","spinat","salat","lime","sitron","koriander","persille","avokado","aubergine","chili","ruccola","asparges"])) return "Frukt og grønt";
  return "Annet";
};
function shoppingIdV25(){
  if (globalThis.crypto?.randomUUID) return `shop-${crypto.randomUUID()}`;
  return `shop-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}
function shoppingItemTimeV25(item){ return Date.parse(item?.updatedAt || SHOPPING_EPOCH) || 0; }
function isVisibleShoppingItemV25(item){ return item && !item.deleted; }
function ensureShoppingMetadataV25(items){
  return (Array.isArray(items) ? items : []).map((item, index) => ({
    ...item,
    id: item.id || `shop-legacy-${index}-${normalize(item.text || "")}`,
    text: String(item.text || "").trim(),
    category: item.category || categorize(item.text || ""),
    done: Boolean(item.done),
    deleted: Boolean(item.deleted),
    updatedAt: item.updatedAt || SHOPPING_EPOCH
  }));
}
function mergeShoppingStatesV25(localItems, remoteItems){
  const merged = new Map();
  for (const item of [...ensureShoppingMetadataV25(remoteItems), ...ensureShoppingMetadataV25(localItems)]) {
    const current = merged.get(item.id);
    if (!current || shoppingItemTimeV25(item) >= shoppingItemTimeV25(current)) merged.set(item.id, item);
  }
  return [...merged.values()];
}
function visibleShoppingItemsV25(){ return ensureShoppingMetadataV25(shoppingItems).filter(isVisibleShoppingItemV25); }
function setShoppingStatusV25(text, state = ""){
  const el = $("shoppingSaveStatus");
  if (!el) return;
  el.textContent = text;
  el.className = `save-status${state ? ` ${state}` : ""}`;
}
function updateShoppingRemainingV25(){
  const visible = visibleShoppingItemsV25();
  const remaining = visible.filter(item => !item.done).length;
  const done = visible.length - remaining;
  const el = $("shoppingRemaining");
  if (el) el.textContent = visible.length
    ? `${remaining} ${remaining === 1 ? "vare" : "varer"} gjenstår${done ? ` · ${done} fullført` : ""}`
    : "Legg til en vare, eller hent listen fra ukesmenyen.";
}
function statePayloadV25(){
  return {
    items: clonePlanSafe(plan),
    shoppingItems: ensureShoppingMetadataV25(shoppingItems),
    freezerItems: freezerItems || [],
    meta: appMeta || {},
    updatedAt: appMeta.updatedAt || nowIsoV25()
  };
}
function persistLocalStateV25(){
  try {
    localStorage.setItem("middag_state_v25", JSON.stringify(statePayloadV25()));
    localStorage.setItem("middag_plan", JSON.stringify(plan || {}));
  } catch (error) {
    console.warn("Kunne ikke lagre lokalt", error);
  }
}
async function runSaveWorkerV25(){
  if (saveWorkerV25) return saveWorkerV25;
  saveWorkerV25 = (async () => {
    while (savedRevisionV25 < saveRevisionV25) {
      const revision = saveRevisionV25;
      const payload = statePayloadV25();
      isSavingPlan = true;
      setLiveStatus("Lagrer", "syncing");
      setShoppingStatusV25("Lagrer endringer …", "pending");
      try {
        const response = await fetch("/api/plan", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({plan: payload})
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok || data.ok === false) throw new Error(data.error || "Lagringen feilet");
        savedRevisionV25 = revision;
        lastRemoteUpdatedAt = payload.updatedAt;
        setLiveStatus("Live");
        setShoppingStatusV25("Alle endringer er lagret");
      } catch (error) {
        console.warn("Lagring feilet", error);
        setLiveStatus("Ikke synkronisert", "error");
        setShoppingStatusV25("Kunne ikke lagre. Prøver igjen …", "error");
        clearTimeout(saveRetryV25);
        saveRetryV25 = setTimeout(runSaveWorkerV25, 3500);
        break;
      } finally {
        isSavingPlan = false;
      }
    }
  })().finally(() => { saveWorkerV25 = null; });
  return saveWorkerV25;
}

savePlan = function(){
  appMeta.updatedAt = nowIsoV25();
  lastLocalSaveAt = Date.now();
  saveRevisionV25 += 1;
  persistLocalStateV25();
  void runSaveWorkerV25();
};

function shoppingCategoryOptionsV25(){
  const select = $("shoppingQuickCategory");
  if (!select || select.options.length > 1) return;
  select.insertAdjacentHTML("beforeend", CATEGORIES.map(category =>
    `<option value="${escapeAttr(category)}">${escapeHtml(category)}</option>`
  ).join(""));
}
function findDuplicateShoppingItemV25(text, category){
  const needle = normalize(normalizeIngredientName(text));
  return visibleShoppingItemsV25().find(item =>
    normalize(normalizeIngredientName(item.text)) === needle &&
    (item.category || categorize(item.text)) === category
  );
}
function flashShoppingItemV25(id){
  const row = document.querySelector(`[data-shopping-id="${CSS.escape(String(id))}"]`);
  if (!row) return;
  row.classList.remove("shopping-duplicate");
  requestAnimationFrame(() => row.classList.add("shopping-duplicate"));
  row.scrollIntoView({block: "nearest", behavior: "smooth"});
}
function addShoppingItemV25(text, preferredCategory = ""){
  let cleaned = normalizeIngredientLineForDisplay(String(text || "").trim());
  if (/^[a-zæøå]/i.test(cleaned)) cleaned = capitalize(cleaned);
  if (!cleaned) return false;
  const category = preferredCategory || categorize(cleaned);
  const duplicate = findDuplicateShoppingItemV25(cleaned, category);
  if (duplicate) {
    if (duplicate.done) {
      duplicate.done = false;
      duplicate.updatedAt = nowIsoV25();
      savePlan();
      renderShoppingList(shoppingItems);
    }
    flashShoppingItemV25(duplicate.id);
    setShoppingStatusV25("Varen finnes allerede i listen");
    return false;
  }
  const item = {
    id: shoppingIdV25(),
    text: cleaned,
    category,
    recipe: "Egen vare",
    done: false,
    deleted: false,
    updatedAt: nowIsoV25()
  };
  shoppingItems = [...ensureShoppingMetadataV25(shoppingItems), item];
  renderShoppingList(shoppingItems);
  savePlan();
  requestAnimationFrame(() => flashShoppingItemV25(item.id));
  return true;
}
function bindShoppingComposerV25(){
  shoppingCategoryOptionsV25();
  const form = $("shoppingQuickAdd");
  if (!form || form.dataset.bound === "true") return;
  form.dataset.bound = "true";
  form.addEventListener("submit", event => {
    event.preventDefault();
    const input = $("shoppingQuickInput");
    if (!input) return;
    if (addShoppingItemV25(input.value, $("shoppingQuickCategory")?.value || "")) input.value = "";
    input.focus({preventScroll: true});
  });
  $("shoppingQuickInput")?.addEventListener("keydown", event => {
    if (event.key !== "Enter" || event.isComposing) return;
    event.preventDefault();
    const input = event.currentTarget;
    if (addShoppingItemV25(input.value, $("shoppingQuickCategory")?.value || "")) input.value = "";
    input.focus({preventScroll: true});
  });
}

function shoppingRowHtmlV25(item){
  const source = item.recipe && item.recipe !== "Egen vare" ? item.recipe : "";
  return `<div class="shopping-row${item.done ? " done" : ""}" data-shopping-id="${escapeAttr(item.id)}">
    <input class="shopping-check" type="checkbox" aria-label="${item.done ? "Marker som ikke kjøpt" : "Marker som kjøpt"}" ${item.done ? "checked" : ""} onchange="toggleShoppingDoneV25('${escapeAttr(item.id)}', this.checked)">
    <div class="shopping-item-main">
      <button type="button" class="shopping-item-text" onclick="editShoppingItemV25('${escapeAttr(item.id)}')">${escapeHtml(item.text)}</button>
      ${source ? `<span class="shopping-source">Fra ${escapeHtml(source)}</span>` : ""}
    </div>
    <button type="button" class="shopping-more" aria-label="Flere valg" aria-expanded="false" onclick="toggleShoppingActionsV25('${escapeAttr(item.id)}', this)">•••</button>
    <div class="shopping-actions"><button type="button" class="shopping-delete" onclick="removeShoppingItemV25('${escapeAttr(item.id)}')">Slett vare</button></div>
  </div>`;
}
function renderShoppingCategoryV25(category, items){
  if (!items.length) return "";
  const collapsed = collapsedShoppingCategoriesV25.has(category);
  return `<section class="shopping-category" data-shopping-category="${escapeAttr(category)}">
    <button type="button" class="category-toggle" aria-expanded="${!collapsed}" onclick="toggleShoppingCategoryV25('${escapeAttr(category)}')">
      <span>${escapeHtml(category)}</span><span class="category-count">${items.length}</span>
    </button>
    <div class="category-items" ${collapsed ? "hidden" : ""}>${items.map(shoppingRowHtmlV25).join("")}</div>
  </section>`;
}
renderShoppingList = function(items){
  shoppingItems = ensureShoppingMetadataV25(items || []);
  const box = $("shoppingList");
  if (!box) return;
  const visible = visibleShoppingItemsV25();
  const active = visible.filter(item => !item.done);
  const done = visible.filter(item => item.done);
  const grouped = new Map(CATEGORIES.map(category => [category, []]));
  for (const item of active) {
    const predictedCategory = item.manualCategory ? item.category : categorize(item.text);
    const category = item.manualCategory
      ? (CATEGORIES.includes(item.category) ? item.category : "Annet")
      : predictedCategory !== "Annet"
        ? predictedCategory
        : (CATEGORIES.includes(item.category) ? item.category : "Annet");
    item.category = category;
    if (!grouped.has(category)) grouped.set(category, []);
    grouped.get(category).push(item);
  }
  const activeMarkup = [...grouped.entries()].map(([category, categoryItems]) =>
    renderShoppingCategoryV25(category, categoryItems)
  ).join("");
  box.innerHTML = visible.length
    ? `<p class="shopping-summary">${active.length} ${active.length === 1 ? "vare" : "varer"} igjen</p>
       ${activeMarkup || `<div class="empty-state">Alt er handlet inn.</div>`}
       ${done.length ? `<section class="completed-section">
         <div class="completed-head">
           <button type="button" class="completed-toggle" aria-expanded="false" onclick="toggleCompletedShoppingV25(this)">Fullført (${done.length})</button>
           <button type="button" class="text-button danger-subtle" onclick="clearCompletedShoppingV25()">Fjern fullførte</button>
         </div>
         <div class="completed-items" hidden>${done.map(shoppingRowHtmlV25).join("")}</div>
       </section>` : ""}`
    : `<div class="empty-state"><strong>Handlelisten er tom</strong><br>Legg til en vare over, eller hent ingrediensene fra ukesmenyen.</div>`;
  updateShoppingRemainingV25();
};

window.toggleShoppingCategoryV25 = function(category){
  if (collapsedShoppingCategoriesV25.has(category)) collapsedShoppingCategoriesV25.delete(category);
  else collapsedShoppingCategoriesV25.add(category);
  const section = document.querySelector(`[data-shopping-category="${CSS.escape(category)}"]`);
  const items = section?.querySelector(".category-items");
  const button = section?.querySelector(".category-toggle");
  if (items) items.hidden = collapsedShoppingCategoriesV25.has(category);
  if (button) button.setAttribute("aria-expanded", String(!collapsedShoppingCategoriesV25.has(category)));
};
window.toggleCompletedShoppingV25 = function(button){
  const items = button.closest(".completed-section")?.querySelector(".completed-items");
  if (!items) return;
  items.hidden = !items.hidden;
  button.setAttribute("aria-expanded", String(!items.hidden));
};
window.toggleShoppingDoneV25 = function(id, checked){
  const item = getShoppingItem(id);
  if (!item) return;
  item.done = Boolean(checked);
  item.updatedAt = nowIsoV25();
  const row = document.querySelector(`[data-shopping-id="${CSS.escape(String(id))}"]`);
  if (row) row.classList.toggle("done", item.done);
  updateShoppingRemainingV25();
  savePlan();
  clearTimeout(shoppingRenderTimerV25);
  shoppingRenderTimerV25 = setTimeout(() => renderShoppingList(shoppingItems), 420);
};
window.toggleShoppingActionsV25 = function(id, button){
  const row = document.querySelector(`[data-shopping-id="${CSS.escape(String(id))}"]`);
  if (!row) return;
  document.querySelectorAll(".shopping-row.actions-open").forEach(other => {
    if (other !== row) other.classList.remove("actions-open");
  });
  row.classList.toggle("actions-open");
  button.setAttribute("aria-expanded", String(row.classList.contains("actions-open")));
};
window.editShoppingItemV25 = function(id){
  const item = getShoppingItem(id);
  const row = document.querySelector(`[data-shopping-id="${CSS.escape(String(id))}"]`);
  const container = row?.querySelector(".shopping-item-main");
  if (!item || !container || container.querySelector("input")) return;
  const input = document.createElement("input");
  input.className = "shopping-edit-input";
  input.value = item.text;
  input.setAttribute("aria-label", "Rediger vare");
  const finish = commit => {
    if (!input.isConnected) return;
    const value = input.value.trim();
    if (commit && value) {
      item.text = normalizeIngredientLineForDisplay(value);
      item.category = categorize(item.text);
      item.updatedAt = nowIsoV25();
      savePlan();
    }
    renderShoppingList(shoppingItems);
  };
  input.addEventListener("keydown", event => {
    if (event.key === "Enter") { event.preventDefault(); finish(true); }
    if (event.key === "Escape") finish(false);
  });
  input.addEventListener("blur", () => finish(true), {once: true});
  container.replaceChildren(input);
  input.focus();
  input.select();
};
window.removeShoppingItemV25 = function(id){
  const item = getShoppingItem(id);
  if (!item) return;
  item.deleted = true;
  item.updatedAt = nowIsoV25();
  const row = document.querySelector(`[data-shopping-id="${CSS.escape(String(id))}"]`);
  if (row) {
    row.classList.add("is-pending");
    row.style.opacity = "0";
    row.style.transform = "translateX(12px)";
    setTimeout(() => renderShoppingList(shoppingItems), 180);
  } else renderShoppingList(shoppingItems);
  savePlan();
};
window.clearCompletedShoppingV25 = function(){
  const done = visibleShoppingItemsV25().filter(item => item.done);
  if (!done.length) return;
  if (done.length > 2 && !confirm(`Fjerne ${done.length} fullførte varer?`)) return;
  const timestamp = nowIsoV25();
  done.forEach(item => { item.deleted = true; item.updatedAt = timestamp; });
  renderShoppingList(shoppingItems);
  savePlan();
};
window.retryShoppingSaveV25 = function(){ void runSaveWorkerV25(); };

resetShoppingList = function(){
  const visible = visibleShoppingItemsV25();
  if (visible.length && !confirm("Vil du tømme hele handlelisten?")) return;
  const timestamp = nowIsoV25();
  shoppingItems = ensureShoppingMetadataV25(shoppingItems).map(item =>
    isVisibleShoppingItemV25(item) ? {...item, deleted: true, updatedAt: timestamp} : item
  );
  renderShoppingList(shoppingItems);
  savePlan();
};
generateShoppingList = function(){
  const raw = [];
  const missing = [];
  for (const day of selectedDays()) {
    for (const planItem of (plan[day.key] || [])) {
      if (planItem.type !== "recipe") continue;
      const recipe = recipeById(planItem.recipeId);
      if (!recipe || !hasRecipe(recipe)) {
        if (recipe) missing.push(recipe.name);
        continue;
      }
      for (const line of extractIngredientLines(recipe)) {
        raw.push({
          id: shoppingIdV25(),
          text: line,
          category: categorize(line),
          recipe: recipe.name,
          done: false,
          deleted: false,
          updatedAt: nowIsoV25()
        });
      }
    }
  }
  const timestamp = nowIsoV25();
  const tombstones = ensureShoppingMetadataV25(shoppingItems).map(item =>
    isVisibleShoppingItemV25(item) ? {...item, deleted: true, updatedAt: timestamp} : item
  );
  const generated = (typeof mergeShoppingItems === "function" ? mergeShoppingItems(raw) : raw)
    .map(item => ({...item, id: item.id || shoppingIdV25(), deleted: false, updatedAt: timestamp}));
  shoppingItems = [...tombstones, ...generated];
  renderShoppingList(shoppingItems);
  savePlan();
  showView("viewShopping");
  if (missing.length) {
    setShoppingStatusV25(`${[...new Set(missing)].length} oppskrift mangler ingredienser`, "error");
  }
};

syncFromServer = async function(){
  try {
    if (isSavingPlan || saveRevisionV25 > savedRevisionV25 || Date.now() - lastLocalSaveAt < 1800) return;
    setLiveStatus("Synkroniserer", "syncing");
    const response = await fetch(`/api/plan?ts=${Date.now()}`, {cache: "no-store"});
    if (!response.ok) throw new Error("Kunne ikke hente fellesdata");
    const result = await response.json();
    const remoteState = result.plan || {};
    const remoteUpdatedAt = remoteState.updatedAt || "";
    if (remoteUpdatedAt && remoteUpdatedAt !== lastRemoteUpdatedAt && remoteUpdatedAt !== appMeta.updatedAt) {
      const migrated = migratePlan(remoteState.items || {});
      const visibleKeys = selectedDays().map(day => day.key);
      const currentCount = visibleKeys.reduce((sum, key) => sum + ((plan[key] || []).length), 0);
      const remoteCount = visibleKeys.reduce((sum, key) => sum + ((migrated[key] || []).length), 0);
      if (!(currentCount > 0 && remoteCount === 0)) plan = migrated;
      shoppingItems = mergeShoppingStatesV25(shoppingItems, remoteState.shoppingItems || []);
      freezerItems = remoteState.freezerItems || freezerItems || [];
      appMeta = remoteState.meta || appMeta;
      lastRemoteUpdatedAt = remoteUpdatedAt;
      persistLocalStateV25();
      createDayRows();
      renderShoppingList(shoppingItems);
      renderFreezer();
    }
    setLiveStatus("Live");
  } catch (error) {
    console.warn("Synkronisering feilet", error);
    setLiveStatus("Frakoblet", "error");
    setShoppingStatusV25("Frakoblet – endringer lagres lokalt", "error");
  }
};
startRealtimeSync = function(){
  if (syncTimer) clearInterval(syncTimer);
  syncTimer = setInterval(syncFromServer, 2500);
  setLiveStatus("Live");
};

const oldShowViewV25 = showView;
showView = function(view){
  oldShowViewV25(view);
  localStorage.setItem("middag_active_view", view);
  if (view === "viewShopping") {
    renderShoppingList(shoppingItems);
    setTimeout(() => $("shoppingQuickInput")?.focus({preventScroll: true}), 50);
  }
  window.scrollTo({top: 0, behavior: "smooth"});
};
const oldBindAllV25 = bindAll;
bindAll = function(){
  oldBindAllV25();
  bindShoppingComposerV25();
  document.addEventListener("click", event => {
    if (!event.target.closest(".shopping-row")) {
      document.querySelectorAll(".shopping-row.actions-open").forEach(row => row.classList.remove("actions-open"));
    }
  });
};

init = async function(){
  setLiveStatus("Henter", "syncing");
  let localState = {};
  try { localState = JSON.parse(localStorage.getItem("middag_state_v25") || "{}"); } catch (error) {}
  try {
    const [recipeResponse, planResponse] = await Promise.all([
      fetch("/api/recipes", {cache: "no-store"}),
      fetch("/api/plan", {cache: "no-store"})
    ]);
    if (!recipeResponse.ok || !planResponse.ok) throw new Error("Tjenesten svarte ikke");
    const recipeResult = await recipeResponse.json();
    const planResult = await planResponse.json();
    recipes = recipeResult.recipes || [];
    mergeCustomData();
    const remoteState = planResult.plan || {};
    plan = migratePlan(remoteState.items || localState.items || {});
    shoppingItems = mergeShoppingStatesV25(localState.shoppingItems || [], remoteState.shoppingItems || []);
    freezerItems = remoteState.freezerItems || localState.freezerItems || defaultFreezerItems();
    appMeta = remoteState.meta || localState.meta || appMeta;
    lastRemoteUpdatedAt = remoteState.updatedAt || "";
    savedRevisionV25 = saveRevisionV25;
  } catch (error) {
    console.warn("Starter med lokale data", error);
    plan = migratePlan(localState.items || JSON.parse(localStorage.getItem("middag_plan") || "{}"));
    shoppingItems = ensureShoppingMetadataV25(localState.shoppingItems || []);
    freezerItems = localState.freezerItems || defaultFreezerItems();
    appMeta = localState.meta || appMeta;
    try {
      const fallback = await fetch("recipes.json").then(response => response.json());
      recipes = Array.isArray(fallback) ? fallback : (fallback.recipes || []);
      mergeCustomData();
    } catch (fallbackError) {
      recipes = [];
    }
    setLiveStatus("Frakoblet", "error");
  }
  fillDaySelectorsV20();
  fillAddToDaySelect();
  if ($("recipeCount")) $("recipeCount").textContent = `${recipes.length} oppskrifter`;
  bindAll();
  createDayRows();
  renderRecipeResults();
  renderShoppingList(shoppingItems);
  renderFreezer();
  const savedView = localStorage.getItem("middag_active_view");
  if (savedView && $(savedView)) oldShowViewV25(savedView);
  startRealtimeSync();
};

// ===== v26 seamless image import + field-level uncertainty =====
let importRunV26 = 0;

function setImportProgressV26(label, percent, visible=true) {
  const box = $("importProgress"), bar = $("importProgressBar"), value = Math.max(0, Math.min(100, Math.round(percent || 0)));
  if (!box) return;
  box.hidden = !visible;
  $("importProgressLabel").textContent = label;
  $("importProgressPercent").textContent = `${value} %`;
  bar.style.width = `${value}%`;
}

function clearImportWarningsV26() {
  ["importNameField", "importCategoryField", "ingredientsPreviewField", "instructionsPreviewField"]
    .forEach(id => $(id)?.classList.remove("preview-uncertain"));
  ["nameWarning", "categoryWarning", "ingredientsWarning", "instructionsWarning"].forEach(id => {
    const element = $(id);
    if (element) { element.hidden = true; element.textContent = ""; }
  });
}

function showImportUncertaintiesV26(uncertainties=[]) {
  clearImportWarningsV26();
  const groups = {name: [], category: [], ingredients: [], instructions: []};
  for (const item of uncertainties) {
    const field = String(item?.field || "");
    const reason = String(item?.reason || "Kontroller dette feltet.");
    if (field === "title") groups.name.push(reason);
    else if (field === "category") groups.category.push(reason);
    else if (field.startsWith("ingredients")) groups.ingredients.push(`${field.replace("ingredients.", "Linje ")}: ${reason}`);
    else if (field.startsWith("instructions")) groups.instructions.push(`${field.replace("instructions.", "Steg ")}: ${reason}`);
  }
  const mapping = {
    name: ["importNameField", "nameWarning"],
    category: ["importCategoryField", "categoryWarning"],
    ingredients: ["ingredientsPreviewField", "ingredientsWarning"],
    instructions: ["instructionsPreviewField", "instructionsWarning"]
  };
  Object.entries(groups).forEach(([group, messages]) => {
    if (!messages.length) return;
    const [fieldId, warningId] = mapping[group], warning = $(warningId);
    $(fieldId)?.classList.add("preview-uncertain");
    warning.textContent = messages.join(" · ");
    warning.hidden = false;
  });
}

function previewIngredientsV26() {
  const current = $("parsedIngredients").value.trim();
  const parsed = window.lastAiParsedRecipe || {};
  if (current === (parsed.__displayIngredients || "")) return parsed.ingredients || [];
  return current.split(/\n+/).map(line => {
    const categoryMatch = line.match(/\s*\[([^\]]+)\]\s*$/);
    const withoutCategory = line.replace(/\s*\[[^\]]+\]\s*$/, "").trim();
    const match = withoutCategory.match(/^([\d.,/½¼¾]+|etter smak)?\s*(kg|g|mg|l|dl|ml|ss|ts|stk|boks|pakke|fedd|stilk)?\s*(.*)$/i);
    return {
      amount: (match?.[1] || "").trim(),
      unit: (match?.[2] || "").trim(),
      item: (match?.[3] || withoutCategory).trim(),
      note: "",
      shoppingCategory: categoryMatch?.[1] || "Annet",
      original: line
    };
  }).filter(item => item.item);
}

parseCaptionAI = async function(options={}) {
  const caption = $("captionInput").value.trim(), status = $("aiStatus"), button = $("aiParseCaptionBtn"), recipe = recipeById(activeImportId) || {};
  if (!caption) { if (!options.automatic) alert("Lim inn oppskriftstekst først."); return null; }
  try {
    button.disabled = true;
    setImportProgressV26("AI strukturerer oppskriften …", 88);
    status.textContent = "Analyserer tekst og normaliserer ingredienser …";
    const response = await fetch("/api/parse-caption", {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({caption, recipeName: $("importName").value.trim() || recipe.name || "", sourceUrl: $("importLink").value.trim() || resolveRecipeSourceUrl(recipe), category: $("importCategory").value || recipe.category || ""})
    });
    const data = await response.json();
    if (!response.ok || !data.ok) throw new Error(data.error || "AI-analysen feilet");
    const parsed = data.parsed || {};
    $("importName").value = parsed.title || $("importName").value.trim() || recipe.name || "";
    $("importCategory").value = parsed.category || $("importCategory").value || "Annet";
    $("importServings").value = parsed.servings || $("importServings").value || "";
    const ingredientText = (parsed.ingredients || []).map(formatAiIngredient).join("\n");
    $("parsedIngredients").value = ingredientText;
    $("parsedInstructions").value = (parsed.instructions || []).map((step, index) => `${index + 1}. ${step}`).join("\n");
    parsed.__displayIngredients = ingredientText;
    const parsedContext = mergePreservingExistingData(recipe, {...parsed, name: parsed.title || $("importName").value});
    parsed.tags = enrichTags(parsedContext);
    parsed.emoji = emojiForRecipe(parsedContext);
    window.lastAiParsedRecipe = parsed;
    showImportUncertaintiesV26(parsed.uncertainties || []);
    setImportProgressV26("Ferdig – se over og rediger før lagring", 100);
    status.textContent = parsed.uncertainties?.length ? `${parsed.uncertainties.length} felt bør kontrolleres.` : "Oppskriften er klar til gjennomgang.";
    return parsed;
  } catch (error) {
    setImportProgressV26("Analysen feilet", 100);
    status.textContent = `AI-analysen feilet: ${error?.message || error}`;
    if (!options.automatic) alert("AI-analysen feilet. Se statusfeltet.");
    return null;
  } finally {
    button.disabled = false;
  }
};

async function processScreenshotsV26() {
  const files = Array.from($("screenshotInput")?.files || []);
  if (!files.length) return;
  if (!window.Tesseract) return alert("Tekstleseren kunne ikke lastes.");
  const run = ++importRunV26, chunks = [];
  clearImportWarningsV26();
  $("saveParsedBtn").disabled = true;
  try {
    for (let index = 0; index < files.length; index++) {
      if (run !== importRunV26) return;
      const base = index / files.length;
      const result = await Tesseract.recognize(files[index], "eng", {
        logger: message => {
          if (message.status === "recognizing text") {
            const progress = 5 + (base + (message.progress || 0) / files.length) * 72;
            setImportProgressV26(`Leser bilde ${index + 1} av ${files.length} …`, progress);
          }
        }
      });
      if (result?.data?.text?.trim()) chunks.push(result.data.text.trim());
    }
    if (run !== importRunV26) return;
    $("captionInput").value = chunks.join("\n\n");
    $("ocrStatus").textContent = `Tekst lest fra ${files.length} bilde${files.length === 1 ? "" : "r"}. AI-analyse startet automatisk.`;
    setImportProgressV26("Teksten er lest – starter AI-analyse …", 80);
    await parseCaptionAI({automatic: true});
  } catch (error) {
    setImportProgressV26("Kunne ikke lese bildene", 100);
    $("ocrStatus").textContent = `Feil under tekstlesing: ${error?.message || error}`;
  } finally {
    if (run === importRunV26) $("saveParsedBtn").disabled = false;
  }
}

saveParsedRecipe = async function() {
  if (!activeImportId) return alert("Ingen oppskrift valgt.");
  const ai = window.lastAiParsedRecipe || {}, base = recipeById(activeImportId) || {};
  const ingredients = previewIngredientsV26();
  const instructionsText = $("parsedInstructions").value.trim();
  const enteredUrl = $("importLink").value.trim();
  const sourceUrl = enteredUrl || resolveRecipeSourceUrl(base);
  const candidatePatch = {
    name: $("importName").value.trim() || "Ny oppskrift",
    link: sourceUrl,
    category: $("importCategory").value || "Annet",
    source: sourceTypeFromUrl(sourceUrl) || base.source || "Manuell",
    caption: $("captionInput").value.trim() || base.caption || "",
    image: importSourceMediaV27 || base.image || "",
    servings: $("importServings").value.trim(),
    ingredientsText: $("parsedIngredients").value.trim(),
    instructions: instructionsText,
    structuredIngredients: ingredients,
    structuredInstructions: instructionsText.split(/\n+/).map(line => line.replace(/^\d+[.)]\s*/, "").trim()).filter(Boolean),
    tags: ai.tags || enrichTags({...base, name: $("importName").value, category: $("importCategory").value}),
    emoji: ai.emoji || emojiForRecipe({...base, name: $("importName").value, category: $("importCategory").value}),
    aiParsed: !!window.lastAiParsedRecipe,
    aiConfidence: ai.confidence || "",
    aiUncertainties: ai.uncertainties || [],
    prepMinutes: Number(ai.prepMinutes || base.prepMinutes || 0),
    nutrition: ai.nutrition || base.nutrition || {},
    imageMethod: ai.imageMethod || base.imageMethod || "",
    status: ingredients.length && instructionsText ? "Fullført" : "Må sjekkes manuelt",
    manualCheck: ingredients.length && instructionsText ? "Nei" : "Ja – mangler ingredienser eller fremgangsmåte.",
    updatedAt: new Date().toISOString()
  };
  const patch = meaningfulPatch(candidatePatch);
  try {
    const response = await fetch("/api/save-recipe", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({id: activeImportId, patch})});
    const result = await response.json().catch(() => ({}));
    if (!response.ok || result.ok === false) throw new Error(result.error || "Lagring feilet");
    const index = recipes.findIndex(recipe => String(recipe.id) === String(activeImportId));
    if (index >= 0) recipes[index] = mergePreservingExistingData(recipes[index], patch); else recipes.push({id: activeImportId, ...patch});
    $("importDialog").close(); createDayRows(); renderRecipeResults();
    alert("Oppskriften er lagret ✅");
  } catch (error) {
    alert(`Oppskriften ble ikke lagret: ${error?.message || error}`);
  }
};

const bindAllBeforeV26 = bindAll;
bindAll = function() {
  bindAllBeforeV26();
  $("screenshotInput")?.addEventListener("change", processScreenshotsV26);
};

// ===== v27 permanent Recipe Recovery =====
let recoveryDataV27 = null;
let recoveryHighIndexV27 = 0;
let recoveryUrlIndexV27 = 0;
let recoveryPreviewV27 = null;
let recoveryRollbackPreviewV27 = null;
let recoveryImportContextV27 = null;
let recoveryBatchRemainingV27 = 0;
let recoverySaveInProgressV27 = false;
let importSourceMediaV27 = "";

function recoveryTextV27(value) {
  if (value === null || value === undefined || value === "" || (Array.isArray(value) && !value.length)) {
    return `<span class="recovery-empty">(tomt)</span>`;
  }
  if (typeof value === "string") return escapeHtml(value);
  return escapeHtml(JSON.stringify(value, null, 2));
}

async function recoveryRequestV27(payload) {
  const response = await fetch("/api/recovery", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(payload)
  });
  const result = await response.json().catch(() => ({}));
  if (!response.ok || !result.ok) throw new Error(result.error || "Recovery-handlingen feilet.");
  return result;
}

async function loadRecoveryV27(force=false) {
  if (recoveryDataV27 && !force) return recoveryDataV27;
  let result;
  try {
    const response = await fetch(`/api/recovery?ts=${Date.now()}`, {cache: "no-store"});
    result = await response.json();
    if (!response.ok || !result.ok) throw new Error(result.error || "Kunne ikke hente Recipe Recovery.");
  } catch (error) {
    const manifest = await fetch(`/recovery-manifest.json?ts=${Date.now()}`, {cache: "no-store"}).then(response => {
      if (!response.ok) throw error;
      return response.json();
    });
    result = {ok:true, manifest, state:{items:{}, paused:false}, readOnly:true};
  }
  recoveryDataV27 = result;
  renderRecoveryDashboardV27();
  return result;
}

function recoveryQueueCountsV27() {
  const manifest = recoveryDataV27?.manifest || {};
  const state = recoveryDataV27?.state?.items || {};
  const outstanding = type => (manifest[type] || []).filter(item => state[String(item.id)]?.status !== "recovered").length;
  return {high: outstanding("high"), medium: outstanding("medium"), url: outstanding("url"), manual: outstanding("manual")};
}

function renderRecoveryDashboardV27() {
  if (!recoveryDataV27) return;
  const counts = recoveryQueueCountsV27();
  const total = counts.high + counts.medium + counts.url + counts.manual;
  $("recoverySummary").textContent = `${total} oppskrifter trenger oppfølging`;
  $("recoveryStats").innerHTML = [
    ["Høy", counts.high], ["Middels", counts.medium], ["URL", counts.url], ["Manuell", counts.manual]
  ].map(([label, count]) => `<span class="recovery-stat">${count} ${label}</span>`).join("");
  const cards = [
    {type:"high", icon:"✓", title:"High Confidence", count:counts.high, text:"Historisk kopi funnet", action:"Review"},
    {type:"medium", icon:"?", title:"Medium Confidence", count:counts.medium, text:"Krever manuell vurdering", action:"Review"},
    {type:"url", icon:"↗", title:"URL Reimport", count:counts.url, text:"Instagram · TikTok · Web", action:"Start Recovery"},
    {type:"manual", icon:"⋯", title:"Manual Queue", count:counts.manual, text:"Ingen kjent kilde", action:"Open"}
  ];
  $("recoveryDashboard").innerHTML = cards.map(card => `
    <article class="recovery-card ${card.type}">
      <span class="recovery-card-icon" aria-hidden="true">${card.icon}</span>
      <h3>${card.title}</h3>
      <p><strong>${card.count}</strong> ${card.count === 1 ? "oppskrift" : "oppskrifter"}</p>
      <p>${card.text}</p>
      <button type="button" class="${card.type === "high" || card.type === "url" ? "primary" : "ghost"}" onclick="openRecoveryQueueV27('${card.type}')">${card.action}</button>
    </article>`).join("");
}

function showRecoveryPanelV27(panel) {
  $("recoveryDashboard").hidden = panel !== "dashboard";
  $("recoveryWorkspace").hidden = panel !== "workspace";
  $("recoveryHistory").hidden = panel !== "history";
}

window.openRecoveryQueueV27 = async function(type) {
  await loadRecoveryV27();
  showRecoveryPanelV27("workspace");
  if (type === "high") {
    recoveryHighIndexV27 = 0;
    renderHighRecoveryV27();
  } else if (type === "url") {
    recoveryUrlIndexV27 = 0;
    renderUrlRecoveryV27();
  } else {
    renderSimpleRecoveryQueueV27(type);
  }
};

function highQueueV27() {
  const state = recoveryDataV27?.state?.items || {};
  return (recoveryDataV27?.manifest?.high || []).filter(item => state[String(item.id)]?.status !== "recovered");
}

async function renderHighRecoveryV27() {
  const queue = highQueueV27();
  const item = queue[recoveryHighIndexV27];
  $("recoveryEyebrow").textContent = `High Confidence · ${Math.min(recoveryHighIndexV27 + 1, queue.length)} / ${queue.length}`;
  $("recoveryWorkspaceTitle").textContent = item?.name || "Køen er ferdig";
  if (!item) {
    $("recoveryWorkspaceBody").innerHTML = `<div class="empty-state">Alle historiske kandidater er gjennomgått.</div>`;
    return;
  }
  const detail = await fetch(`/api/recovery?action=item&id=${encodeURIComponent(item.id)}&ts=${Date.now()}`, {cache:"no-store"}).then(response => response.json());
  if (!detail.ok) throw new Error(detail.error || "Kunne ikke hente oppskriften.");
  const production = detail.production || {}, candidate = detail.item?.candidate || {};
  const candidateIngredients = candidate.ingredienser || {};
  const candidateInstructions = candidate.fremgangsmåte || {};
  const fields = [
    ["Navn", production.name, candidate.name],
    ["Kilde / URL", production.link, detail.item.link],
    ["Ingredienser", production.ingredientsText || production.structuredIngredients, candidateIngredients.ingredientsText || candidateIngredients.structuredIngredients],
    ["Fremgangsmåte", production.instructions || production.structuredInstructions, candidateInstructions.instructions || candidateInstructions.structuredInstructions],
    ["Tags", production.tags, candidate.tags],
    ["Kategori", production.category, candidate.category],
    ["AI metadata", {aiParsed:production.aiParsed, aiConfidence:production.aiConfidence, uncertainties:production.aiUncertainties}, candidate.aiMetadata],
    ["OCR metadata", production.ocrMetadata, candidate.ocrMetadata],
  ];
  const pane = (label, kind, index) => `
    <div class="recovery-pane ${kind}">
      <h3>${label}</h3>
      <div class="recovery-image">${index === 1 && production.image ? `<img src="${escapeAttr(production.image)}" alt="">` : index === 2 && candidate.image ? `<img src="${escapeAttr(candidate.image)}" alt="">` : `<span>Ingen bilde lagret</span>`}</div>
      ${fields.map(field => `<div class="recovery-field"><strong>${field[0]}</strong><div class="recovery-value">${recoveryTextV27(field[index])}</div></div>`).join("")}
    </div>`;
  const available = [];
  if (candidateIngredients.ingredientsText || candidateIngredients.structuredIngredients) {
    if (candidateIngredients.ingredientsText) available.push("ingredientsText");
    if (candidateIngredients.structuredIngredients) available.push("structuredIngredients");
  }
  if (candidateInstructions.instructions || candidateInstructions.structuredInstructions) {
    if (candidateInstructions.instructions) available.push("instructions");
    if (candidateInstructions.structuredInstructions) available.push("structuredInstructions");
  }
  const onlyIngredients = available.length && available.every(field => field.includes("Ingredient") || field === "ingredientsText");
  $("recoveryWorkspaceBody").innerHTML = `
    <div class="recovery-compare">${pane("Produksjonsversjon", "production", 1)}${pane("Historisk kandidat", "candidate", 2)}</div>
    <p class="hint">Kilde: ${escapeHtml((detail.item.sources || []).slice(0, 3).join(" · "))}${detail.item.sources?.length > 3 ? ` · +${detail.item.sources.length - 3} like treff` : ""}</p>
    <div class="recovery-actions">
      ${available.some(field => field.includes("Ingredient") || field === "ingredientsText") ? `<button class="primary" onclick='previewRestoreV27(${JSON.stringify(String(item.id))}, ${JSON.stringify(available.filter(field => field.includes("Ingredient") || field === "ingredientsText"))})'>Restore Ingredients</button>` : ""}
      ${available.some(field => field.includes("Instruction") || field === "instructions") ? `<button class="primary" onclick='previewRestoreV27(${JSON.stringify(String(item.id))}, ${JSON.stringify(available.filter(field => field.includes("Instruction") || field === "instructions"))})'>Restore Instructions</button>` : ""}
      ${!onlyIngredients && available.length > 1 ? `<button class="primary" onclick='previewRestoreV27(${JSON.stringify(String(item.id))}, ${JSON.stringify(available)})'>Restore Both</button>` : ""}
      <button class="ghost" onclick="skipHighRecoveryV27()">Skip</button>
      <button class="ghost" onclick="nextHighRecoveryV27()">Next</button>
    </div>`;
}

window.nextHighRecoveryV27 = function() {
  recoveryHighIndexV27 = Math.min(recoveryHighIndexV27 + 1, highQueueV27().length);
  renderHighRecoveryV27().catch(error => alert(error.message));
};
window.skipHighRecoveryV27 = async function() {
  const item = highQueueV27()[recoveryHighIndexV27];
  if (item) await recoveryRequestV27({action:"queue-state", id:item.id, status:"skipped"});
  nextHighRecoveryV27();
};

window.previewRestoreV27 = async function(id, fields) {
  try {
    const result = await recoveryRequestV27({action:"preview", id, fields});
    recoveryPreviewV27 = {...result.preview, requestedFields: fields};
    $("recoveryConfirmTitle").textContent = `Bekreft: ${result.preview.recipeName}`;
    $("recoveryConfirmBody").innerHTML = recoveryDiffHtmlV27(result.preview.fields);
    $("recoveryConfirmBtn").disabled = false;
    $("recoveryConfirmBtn").textContent = "Confirm Restore";
    $("recoveryConfirmDialog").showModal();
  } catch (error) {
    alert(error.message);
  }
};

function recoveryDiffHtmlV27(fields) {
  return `<div class="recovery-diff-list">${(fields || []).map(change => `
    <div class="recovery-diff-row">
      <strong>${escapeHtml(change.field)}</strong>
      <div class="recovery-diff-values">
        <pre>Før\n${escapeHtml(change.before === undefined || change.before === null || change.before === "" ? "(tomt)" : typeof change.before === "string" ? change.before : JSON.stringify(change.before, null, 2))}</pre>
        <pre>Etter\n${escapeHtml(typeof change.after === "string" ? change.after : JSON.stringify(change.after, null, 2))}</pre>
      </div>
    </div>`).join("")}</div>`;
}

async function confirmRecoveryV27() {
  if (!recoveryPreviewV27) return;
  const button = $("recoveryConfirmBtn");
  try {
    button.disabled = true;
    button.textContent = "Gjenoppretter …";
    await recoveryRequestV27({
      action:"confirm",
      id:recoveryPreviewV27.recipeId,
      fields:recoveryPreviewV27.requestedFields,
      previewToken:recoveryPreviewV27.previewToken
    });
    $("recoveryConfirmDialog").close();
    recoveryPreviewV27 = null;
    await refreshRecipesV27();
    await loadRecoveryV27(true);
    recoveryHighIndexV27 = Math.min(recoveryHighIndexV27, Math.max(0, highQueueV27().length - 1));
    await renderHighRecoveryV27();
  } catch (error) {
    alert(error.message);
  } finally {
    button.disabled = false;
    button.textContent = "Confirm Restore";
  }
}

async function refreshRecipesV27() {
  const result = await fetch(`/api/recipes?ts=${Date.now()}`, {cache:"no-store"}).then(response => response.json());
  if (result.ok && result.recipes) {
    recipes = result.recipes;
    mergeCustomData();
    renderRecipeResults();
    createDayRows();
  }
}

function urlQueueV27() {
  const state = recoveryDataV27?.state?.items || {};
  return (recoveryDataV27?.manifest?.url || []).filter(item => state[String(item.id)]?.status !== "recovered");
}

function renderUrlRecoveryV27() {
  const queue = urlQueueV27();
  if (recoveryUrlIndexV27 >= queue.length) recoveryUrlIndexV27 = Math.max(0, queue.length - 1);
  const item = queue[recoveryUrlIndexV27];
  const recovered = (recoveryDataV27.manifest.url || []).length - queue.length;
  $("recoveryEyebrow").textContent = `URL Recovery · ${item ? recoveryUrlIndexV27 + 1 : 0} / ${queue.length}`;
  $("recoveryWorkspaceTitle").textContent = item?.name || "URL-køen er ferdig";
  if (!item) {
    $("recoveryWorkspaceBody").innerHTML = `<div class="empty-state">Ingen URL-oppskrifter gjenstår.</div>`;
    return;
  }
  const percent = Math.round((recovered / Math.max(1, recoveryDataV27.manifest.url.length)) * 100);
  $("recoveryWorkspaceBody").innerHTML = `
    <div class="recovery-progress">
      <div class="section-title"><strong>Recovered</strong><span>${recovered} / ${recoveryDataV27.manifest.url.length}</span></div>
      <div class="recovery-progress-track"><span style="width:${percent}%"></span></div>
    </div>
    <article class="recovery-queue-item">
      <span class="recovery-source">${escapeHtml(item.source || "Web")}</span>
      <h3>${escapeHtml(item.name)}</h3>
      <a class="recovery-url" href="${escapeAttr(item.link)}" target="_blank" rel="noopener">${escapeHtml(item.link)}</a>
      <p class="hint">Mangler: ${escapeHtml((item.missingFields || []).join(", "))}</p>
      <div class="queue-actions">
        <button class="primary" onclick="startRecoveryImportV27()">Start Import</button>
        <button class="ghost" onclick="recoverNextUrlV27()">Recover Next</button>
        <button class="ghost" onclick="startRecoveryBatchV27()">Recover Next 10</button>
        <button class="ghost" onclick="pauseRecoveryQueueV27()">${recoveryDataV27.state?.paused ? "Fortsett kø" : "Pause Queue"}</button>
        <a class="ghost button-link" href="${escapeAttr(item.link)}" target="_blank" rel="noopener">Open URL</a>
        <button class="ghost" onclick="markUrlRecoveryV27('skipped')">Skip</button>
        <button class="ghost" onclick="markUrlRecoveryV27('manual')">Manual</button>
      </div>
    </article>`;
}

window.nextUrlRecoveryV27 = function(delta=1) {
  recoveryUrlIndexV27 = Math.max(0, recoveryUrlIndexV27 + delta);
  renderUrlRecoveryV27();
};
window.recoverNextUrlV27 = function() {
  nextUrlRecoveryV27(1);
  startRecoveryImportV27();
};
window.markUrlRecoveryV27 = async function(status) {
  const item = urlQueueV27()[recoveryUrlIndexV27];
  if (!item) return;
  await recoveryRequestV27({action:"queue-state", id:item.id, status});
  recoveryDataV27.state.items[String(item.id)] = {status};
  renderUrlRecoveryV27();
};
window.pauseRecoveryQueueV27 = async function() {
  const paused = !recoveryDataV27.state?.paused;
  const result = await recoveryRequestV27({action:"queue-state", paused});
  recoveryDataV27.state = result.state;
  recoveryBatchRemainingV27 = paused ? 0 : recoveryBatchRemainingV27;
  renderUrlRecoveryV27();
};
window.startRecoveryBatchV27 = function() {
  recoveryBatchRemainingV27 = Math.min(10, urlQueueV27().length);
  startRecoveryImportV27();
};
window.startRecoveryImportV27 = async function() {
  const item = urlQueueV27()[recoveryUrlIndexV27];
  if (!item) return;
  const recipe = recipeById(item.id) || {};
  const sourceUrl = resolveRecipeSourceUrl(mergePreservingExistingData(item, recipe));
  if (!sourceUrl) {
    alert("Denne oppskriften har ingen lagret kilde-URL og kan derfor ikke gjenopprettes automatisk.");
    return;
  }
  recoveryImportContextV27 = {id:String(item.id), queue:"url"};
  openImport(item.id);
  $("importLink").value = sourceUrl;
  setImportProgressV26("Henter metadata fra originalkilden …", 8);
  $("ocrStatus").textContent = "Prøver automatisk metadata, caption og tilgjengelige bilder.";
  await autoFetchRecipeUrlV27(sourceUrl, true);
};

async function autoFetchRecipeUrlV27(url, automatic=false) {
  const clean = String(url || "").trim();
  if (!/^https?:\/\//i.test(clean)) return null;
  try {
    setImportProgressV26("Henter metadata fra originalkilden …", 12);
    const response = await fetch("/api/fetch-recipe", {
      method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({url:clean})
    });
    const data = await response.json();
    if (!response.ok || !data.ok) throw new Error(data.error || "Kilden kunne ikke leses automatisk.");
    const result = data.result || {};
    importSourceMediaV27 = result.image || "";
    if (!importSourceMediaV27 && result.video && typeof captureVideoFrameV28 === "function") {
      importSourceMediaV27 = await captureVideoFrameV28(result.video).catch(() => "");
      if (importSourceMediaV27) result.imageMethod = "first-video-frame";
    }
    if (result.title && (!$("importName").value.trim() || $("importName").value === "Ny oppskrift")) $("importName").value = result.title;
    const resolvedUrl = String(result.resolvedUrl || "").trim();
    if (resolvedUrl) $("importLink").value = resolvedUrl;
    let sourceText = result.caption || "";
    if (!sourceText && result.image && window.Tesseract) {
      try {
        setImportProgressV26("Leser tilgjengelig kildebilde …", 48);
        const ocr = await Tesseract.recognize(result.image, "eng");
        sourceText = ocr?.data?.text?.trim() || "";
      } catch (ocrError) {
        console.warn("OCR av kildebilde var ikke tilgjengelig", ocrError);
      }
    }
    if (sourceText) {
      $("captionInput").value = sourceText;
      $("ocrStatus").textContent = `Kilden ble lest via ${result.method || "metadata"}. AI-analyse startet automatisk.`;
      setImportProgressV26("Metadata funnet – starter AI-analyse …", 70);
      const parsed = await parseCaptionAI({automatic:true});
      if (parsed) parsed.imageMethod = result.imageMethod || result.method || "";
      return parsed;
    }
    setImportProgressV26("Kilden krever litt hjelp", 35);
    $("ocrStatus").innerHTML = `Caption var ikke tilgjengelig automatisk. Åpne kilden, lim inn caption eller velg skjermbilder. Resten går automatisk.`;
    return null;
  } catch (error) {
    setImportProgressV26("Automatisk henting var ikke tilgjengelig", 30);
    $("ocrStatus").textContent = `Bruk Open URL, lim inn caption eller velg skjermbilder. ${error.message}`;
    if (!automatic) console.warn(error);
    return null;
  }
}

function renderSimpleRecoveryQueueV27(type) {
  const queue = recoveryDataV27.manifest[type] || [];
  $("recoveryEyebrow").textContent = type === "medium" ? "Medium Confidence" : "Manuell kø";
  $("recoveryWorkspaceTitle").textContent = type === "medium" ? "Krever manuell vurdering" : "Ingen kjent kilde";
  $("recoveryWorkspaceBody").innerHTML = queue.map(item => `
    <article class="recovery-queue-item">
      <span class="recovery-source">${escapeHtml(item.source || "Manuell")}</span>
      <h3>${escapeHtml(item.name)}</h3>
      ${item.link ? `<a class="recovery-url" href="${escapeAttr(item.link)}" target="_blank" rel="noopener">${escapeHtml(item.link)}</a>` : ""}
      <p class="hint">Mangler: ${escapeHtml((item.missingFields || []).join(", ") || "oppskriftsdata")}</p>
      ${item.link ? `<button class="primary" onclick="recoveryImportByIdV27('${escapeAttr(item.id)}','${escapeAttr(item.link)}')">Åpne import</button>` : ""}
    </article>`).join("") || `<div class="empty-state">Køen er tom.</div>`;
}
window.recoveryImportByIdV27 = async function(id, link) {
  const sourceUrl = resolveRecipeSourceUrl(mergePreservingExistingData(recipeById(id), {link}));
  if (!sourceUrl) {
    alert("Denne oppskriften har ingen lagret kilde-URL og kan derfor ikke gjenopprettes automatisk.");
    return;
  }
  recoveryImportContextV27 = {id:String(id), queue:"manual"};
  openImport(id);
  $("importLink").value = sourceUrl;
  await autoFetchRecipeUrlV27(sourceUrl, true);
};

async function showRecoveryHistoryV27() {
  showRecoveryPanelV27("history");
  const result = await fetch(`/api/recovery?action=history&ts=${Date.now()}`, {cache:"no-store"}).then(response => response.json());
  const entries = result.entries || [];
  $("recoveryHistoryList").innerHTML = entries.map(entry => `
    <div class="history-row">
      <div><strong>${escapeHtml(entry.recipeName)}</strong><p>${new Date(entry.createdAt).toLocaleString("no-NO")} · ${entry.fields.map(field => field.field).join(", ")}${entry.rolledBackAt ? " · rullet tilbake" : ""}</p></div>
      <div class="history-actions"><button class="ghost" onclick='showHistoryDiffV27(${JSON.stringify(entry.id)})'>Se diff</button></div>
    </div>`).join("") || `<div class="empty-state">Ingen gjenopprettinger er gjennomført ennå.</div>`;
  window.recoveryHistoryEntriesV27 = entries;
}

window.showHistoryDiffV27 = function(historyId) {
  const entry = (window.recoveryHistoryEntriesV27 || []).find(item => item.id === historyId);
  if (!entry) return;
  $("recoveryDiffTitle").textContent = entry.recipeName;
  $("recoveryDiffBody").innerHTML = recoveryDiffHtmlV27(entry.fields);
  $("recoveryRollbackActions").innerHTML = entry.rollbackAvailable && !entry.rolledBackAt
    ? `<button type="button" class="ghost danger-subtle" onclick='previewRollbackV27(${JSON.stringify(entry.id)})'>Forhåndsvis rollback</button>`
    : `<span class="hint">${entry.rolledBackAt ? "Denne endringen er rullet tilbake." : "Rollback er ikke tilgjengelig."}</span>`;
  $("recoveryDiffDialog").showModal();
};

window.previewRollbackV27 = async function(historyId) {
  try {
    const result = await recoveryRequestV27({action:"rollback-preview", historyId});
    recoveryRollbackPreviewV27 = result.preview;
    $("recoveryDiffBody").innerHTML = `<p class="safety-note">Kontroller tilbakeføringen. Nyere data blir aldri overskrevet.</p>${recoveryDiffHtmlV27(result.preview.fields)}`;
    $("recoveryRollbackActions").innerHTML = `<button type="button" class="primary" onclick="confirmRollbackV27()">Bekreft rollback</button>`;
  } catch (error) { alert(error.message); }
};
window.confirmRollbackV27 = async function() {
  if (!recoveryRollbackPreviewV27) return;
  try {
    await recoveryRequestV27({action:"rollback-confirm", historyId:recoveryRollbackPreviewV27.historyId, previewToken:recoveryRollbackPreviewV27.previewToken});
    recoveryRollbackPreviewV27 = null;
    $("recoveryDiffDialog").close();
    await refreshRecipesV27();
    await showRecoveryHistoryV27();
  } catch (error) { alert(error.message); }
};

const showViewBeforeV27 = showView;
showView = function(view) {
  showViewBeforeV27(view);
  const path = view === "viewRecovery" ? "/recovery" : "/";
  if (window.location.pathname !== path) history.pushState({view}, "", path);
  if (view === "viewRecovery") {
    showRecoveryPanelV27("dashboard");
    loadRecoveryV27().catch(error => {
      $("recoverySummary").textContent = error.message;
    });
  }
};

const openImportBeforeV27 = openImport;
openImport = function(id) {
  importSourceMediaV27 = "";
  return openImportBeforeV27(id);
};

const openAddRecipeBeforeV27 = openAddRecipe;
openAddRecipe = function() {
  importSourceMediaV27 = "";
  recoveryImportContextV27 = null;
  return openAddRecipeBeforeV27();
};

const bindAllBeforeV27 = bindAll;
bindAll = function() {
  bindAllBeforeV27();
  $("recoveryHistoryBtn")?.addEventListener("click", () => showRecoveryHistoryV27().catch(error => alert(error.message)));
  for (const id of ["recoveryCloseWorkspaceBtn", "recoveryCloseHistoryBtn"]) {
    $(id)?.addEventListener("click", () => showRecoveryPanelV27("dashboard"));
  }
  $("recoveryConfirmBtn")?.addEventListener("click", confirmRecoveryV27);
  $("importLink")?.addEventListener("paste", () => {
    setTimeout(() => autoFetchRecipeUrlV27($("importLink").value, true), 40);
  });
  $("importDialog")?.addEventListener("close", () => {
    if (recoverySaveInProgressV27) return;
    recoveryImportContextV27 = null;
    recoveryBatchRemainingV27 = 0;
  });
  window.addEventListener("popstate", () => {
    showViewBeforeV27(window.location.pathname === "/recovery" ? "viewRecovery" : "viewPlan");
  });
};

const saveParsedRecipeBeforeV27 = saveParsedRecipe;
saveParsedRecipe = async function() {
  const context = recoveryImportContextV27 ? {...recoveryImportContextV27} : null;
  recoverySaveInProgressV27 = true;
  try {
    await saveParsedRecipeBeforeV27();
  } finally {
    recoverySaveInProgressV27 = false;
  }
  if (!context || $("importDialog")?.open) return;
  try {
    const result = await recoveryRequestV27({action:"queue-state", id:context.id, status:"recovered"});
    if (recoveryDataV27) recoveryDataV27.state = result.state;
    recoveryImportContextV27 = null;
    await loadRecoveryV27(true);
    if (context.queue === "url") {
      if (recoveryBatchRemainingV27 > 1 && !recoveryDataV27.state?.paused) {
        recoveryBatchRemainingV27 -= 1;
        recoveryUrlIndexV27 = 0;
        renderUrlRecoveryV27();
        setTimeout(startRecoveryImportV27, 350);
      } else {
        recoveryBatchRemainingV27 = 0;
        recoveryUrlIndexV27 = 0;
        renderUrlRecoveryV27();
      }
    }
  } catch (error) {
    console.warn("Oppskriften ble lagret, men Recovery-status kunne ikke oppdateres.", error);
  }
};

const initBeforeV27 = init;
init = async function() {
  await initBeforeV27();
  if (window.location.pathname === "/recovery") {
    showViewBeforeV27("viewRecovery");
    localStorage.setItem("middag_active_view", "viewRecovery");
    await loadRecoveryV27().catch(error => { $("recoverySummary").textContent = error.message; });
  }
};

/* ===== v28 daily UX, quality metadata and Pantry ===== */
const RECIPE_FILTERS_V28 = [
  ["glutenfree","Glutenfri"],["vegetarian","Vegetar"],["vegan","Vegansk"],
  ["highProtein","Høyt protein"],["under500","Under 500 kcal"],["under30","Under 30 min"],
  ["childFriendly","Barnevennlig"],["freezerFriendly","Frysevennlig"],
  ["dinner","Middag"],["breakfast","Frokost"],["lunch","Lunsj"],["dessert","Dessert"],
  ["canMakeNow","Kan lages nå"],["missingMax2","Mangler maks 2"],["avoidRecent14","Ikke laget siste 14 dager"]
];
let randomOrderV28 = new Map();
let shoppingCategoryTargetV28 = null;

function ensureMetaV28() {
  appMeta = appMeta || {};
  appMeta.recipeMeta = appMeta.recipeMeta || {};
  appMeta.pantryItems = Array.isArray(appMeta.pantryItems) ? appMeta.pantryItems : [];
  appMeta.ingredientRegistryOverrides = appMeta.ingredientRegistryOverrides || {};
  appMeta.recipeFilters = Array.isArray(appMeta.recipeFilters) ? appMeta.recipeFilters : [];
}
function recipeMetaV28(id) { ensureMetaV28(); return appMeta.recipeMeta[String(id)] || {}; }
function recipeNutritionV28(recipe) {
  const value = recipe?.nutrition || recipe?.nutritionEstimate || {};
  return {
    protein:Number(value.protein||0), calories:Number(value.calories||0), fat:Number(value.fat||0),
    carbohydrates:Number(value.carbohydrates||value.carbs||0), fiber:Number(value.fiber||0)
  };
}
function recipeMinutesV28(recipe) { return Number(recipe?.prepMinutes || recipe?.totalMinutes || recipe?.cookTimeMinutes || 0); }
function recipeLastCookedV28(recipe) { return recipeMetaV28(recipe.id).lastCooked || recipe.lastCooked || appMeta.lastUsed?.[recipe.id] || ""; }
function setLastCookedV28(id, dateValue=new Date().toISOString()) {
  ensureMetaV28();
  appMeta.recipeMeta[String(id)] = {...recipeMetaV28(id), lastCooked:dateValue};
}
function markCookedV28(id, silent=false, dateValue=new Date().toISOString()) {
  setLastCookedV28(id,dateValue);
  savePlan();
  renderRecipeResults();
  if (!silent) alert("Lagret som laget i dag.");
}
window.markCookedV28 = markCookedV28;

function imageForRecipeV28(recipe) {
  const image = recipe?.image || recipe?.thumbnail || "";
  return image ? `<img src="${escapeAttr(image)}" alt="" loading="lazy" onerror="this.parentElement.classList.add('image-failed');this.remove()">` : `<span>${emojiForRecipe(recipe)}</span>`;
}
function captureVideoFrameV28(url) {
  return new Promise(resolve => {
    const video=document.createElement("video"),timer=setTimeout(()=>resolve(""),2500);
    video.crossOrigin="anonymous";video.muted=true;video.playsInline=true;video.preload="metadata";
    video.onloadeddata=()=>{try{video.currentTime=Math.min(.2,video.duration||.2)}catch(error){clearTimeout(timer);resolve("")}};
    video.onseeked=()=>{try{const canvas=document.createElement("canvas");canvas.width=Math.min(video.videoWidth||640,960);canvas.height=Math.round(canvas.width*(video.videoHeight||360)/(video.videoWidth||640));canvas.getContext("2d").drawImage(video,0,0,canvas.width,canvas.height);clearTimeout(timer);resolve(canvas.toDataURL("image/jpeg",.78))}catch(error){clearTimeout(timer);resolve("")}};
    video.onerror=()=>{clearTimeout(timer);resolve("")};video.src=url;
  });
}
function ingredientObjectsV28(recipe) {
  if (Array.isArray(recipe?.structuredIngredients) && recipe.structuredIngredients.length) return recipe.structuredIngredients;
  return String(recipe?.ingredientsText || "").split(/\n+/).map(line => {
    const category = line.match(/\[([^\]]+)\]\s*$/)?.[1] || categorize(line);
    const clean = line.replace(/\s*\[[^\]]+\]\s*$/, "").trim();
    const match = clean.match(/^([\d.,/½¼¾]+|etter smak)?\s*(kg|g|mg|l|dl|ml|ss|ts|stk|boks|pk|pakke|fedd|stilk)?\s*(.*)$/i);
    return {amount:match?.[1]||"",unit:match?.[2]||"",item:(match?.[3]||clean).trim(),shoppingCategory:category,original:line};
  }).filter(item => item.item);
}
function pantryKeyV28(value) { return normalizeIngredientName(String(value||"")).replace(/\b(fedd|stilker?|boks|pakke)\b/g,"").replace(/\s+/g," ").trim(); }
function pantryAnalysisV28(recipe) {
  ensureMetaV28();
  const available = new Set(appMeta.pantryItems.map(item => pantryKeyV28(item.name)));
  const ingredients = ingredientObjectsV28(recipe);
  const present=[], missing=[];
  for (const ingredient of ingredients) {
    const key = pantryKeyV28(ingredient.item);
    const match = [...available].some(value => value===key || (value.length>3 && (value.includes(key)||key.includes(value))));
    (match ? present : missing).push(ingredient);
  }
  return {present,missing,total:ingredients.length,score:ingredients.length ? present.length/ingredients.length : 0};
}
function pantryStatusV28(recipe, detailed=false) {
  const result=pantryAnalysisV28(recipe);
  if (!result.total) return detailed ? "" : `<span class="pantry-status neutral">Pantry-status ukjent</span>`;
  const state=result.missing.length===0?"ready":result.missing.length<=2?"close":"missing";
  const label=result.missing.length===0?"Kan lages med det du har hjemme":`Mangler ${result.missing.length} ingrediens${result.missing.length===1?"":"er"}`;
  if (!detailed) return `<span class="pantry-status ${state}">${state==="ready"?"🟢":state==="close"?"🟡":"🔴"} ${label}</span>`;
  return `<details class="pantry-detail"><summary>${state==="ready"?"🟢":state==="close"?"🟡":"🔴"} ${label}</summary>
    <div>${result.present.map(item=>`<p>✓ ${escapeHtml(item.item)}</p>`).join("")}${result.missing.map(item=>`<p>✗ ${escapeHtml(item.item)}</p>`).join("")}</div></details>`;
}

function recipeFlagsV28(recipe) {
  const text=normalize(`${recipe.category||""} ${(recipe.tags||[]).join(" ")} ${recipe.name||""}`);
  const nutrition=recipeNutritionV28(recipe), minutes=recipeMinutesV28(recipe), pantry=pantryAnalysisV28(recipe);
  return {
    glutenfree:text.includes("glutenfri"), vegetarian:text.includes("vegetar"),
    vegan:text.includes("vegansk"), highProtein:nutrition.protein>=25,
    under500:nutrition.calories>0&&nutrition.calories<500, under30:minutes>0&&minutes<=30,
    childFriendly:text.includes("barnevennlig"), freezerFriendly:text.includes("frysevennlig")||text.includes("frys"),
    dinner:!/(frokost|lunsj|dessert)/.test(text)||text.includes("middag"), breakfast:text.includes("frokost"),
    lunch:text.includes("lunsj"), dessert:text.includes("dessert"), canMakeNow:pantry.total>0&&!pantry.missing.length,
    missingMax2:pantry.total>0&&pantry.missing.length<=2,
    avoidRecent14:!recipeLastCookedV28(recipe)||Date.now()-new Date(recipeLastCookedV28(recipe)).getTime()>14*86400000
  };
}
function activeFiltersV28(scope) {
  const box=$(scope==="picker"?"pickerFilterChips":"recipeFilterChips");
  return [...(box?.querySelectorAll("button.active")||[])].map(button=>button.dataset.filter);
}
function recipeMatchesV28(recipe, scope="recipes") {
  const search=normalize($(scope==="picker"?"pickerSearch":"recipeSearch")?.value||"");
  const category=$(scope==="picker"?"pickerCategoryFilter":"recipeCategoryFilter")?.value||"";
  if (search&&!searchableText(recipe).includes(search)) return false;
  if (category&&recipe.category!==category) return false;
  const flags=recipeFlagsV28(recipe);
  return activeFiltersV28(scope).every(filter=>flags[filter]);
}
function sortRecipesV28(items, sort) {
  const list=[...items], date=value=>new Date(value||0).getTime()||0;
  if(sort==="random") return list.sort((a,b)=>(randomOrderV28.get(String(a.id))||0)-(randomOrderV28.get(String(b.id))||0));
  if(sort==="newest") return list.sort((a,b)=>date(b.createdAt||b.created_at)-date(a.createdAt||a.created_at));
  if(sort==="oldest") return list.sort((a,b)=>date(a.createdAt||a.created_at)-date(b.createdAt||b.created_at));
  if(sort==="protein") return list.sort((a,b)=>recipeNutritionV28(b).protein-recipeNutritionV28(a).protein);
  if(sort==="glutenfree") return list.sort((a,b)=>Number(recipeFlagsV28(b).glutenfree)-Number(recipeFlagsV28(a).glutenfree));
  if(sort==="vegetarian") return list.sort((a,b)=>Number(recipeFlagsV28(b).vegetarian)-Number(recipeFlagsV28(a).vegetarian));
  if(sort==="shortest") return list.sort((a,b)=>(recipeMinutesV28(a)||9999)-(recipeMinutesV28(b)||9999));
  if(sort==="longest") return list.sort((a,b)=>recipeMinutesV28(b)-recipeMinutesV28(a));
  if(sort==="lastCooked") return list.sort((a,b)=>date(recipeLastCookedV28(b))-date(recipeLastCookedV28(a)));
  if(sort==="favorites") return list.sort((a,b)=>Number(isFavorite(b.id))-Number(isFavorite(a.id))||a.name.localeCompare(b.name,"no"));
  return list.sort((a,b)=>a.name.localeCompare(b.name,"no"));
}
function recipeCardHtmlV28(recipe, scope="recipes") {
  const n=recipeNutritionV28(recipe), minutes=recipeMinutesV28(recipe);
  const action=scope==="picker"?`openPickerPreview('${escapeAttr(recipe.id)}')`:`openRecipeDetails('${escapeAttr(recipe.id)}')`;
  return `<article class="recipe-card rich ${statusClassV23(recipe)}" onclick="${action}">
    <div class="recipe-thumb">${imageForRecipeV28(recipe)}</div><div class="recipe-card-copy">
      <div class="recipe-topline"><strong>${escapeHtml(recipe.name)}</strong>${scope==="recipes"?`<button class="favorite-btn" onclick="event.stopPropagation();toggleFavorite('${escapeAttr(recipe.id)}')">${isFavorite(recipe.id)?"★":"☆"}</button>`:""}</div>
      <div class="recipe-meta">${escapeHtml(recipe.category||"Ukjent")} · ${statusTextV23(recipe)}${minutes?` · ${minutes} min`:""}${n.protein?` · ${n.protein} g protein`:""}</div>
      ${pantryStatusV28(recipe)}
      <div class="recipe-tags">${enrichTags(recipe).slice(0,4).map(tag=>`<span class="tag">${escapeHtml(tag)}</span>`).join("")}</div>
    </div><button type="button" class="ghost compact-action" onclick="event.stopPropagation();${action}">${scope==="picker"?"Se":"Åpne"}</button></article>`;
}
function renderRecipeResultsV28(scope="recipes") {
  const sort=$(scope==="picker"?"pickerSort":"recipeSort")?.value||"az";
  const items=sortRecipesV28(recipes.filter(recipe=>recipeMatchesV28(recipe,scope)),sort).slice(0,300);
  const box=$(scope==="picker"?"pickerResults":"recipeResults");
  if(box) box.innerHTML=items.map(recipe=>recipeCardHtmlV28(recipe,scope)).join("")||`<div class="empty-state">Ingen oppskrifter passer filtrene.</div>`;
}
renderRecipeResults=()=>renderRecipeResultsV28("recipes");
renderPickerResults=()=>renderRecipeResultsV28("picker");

function nutritionHtmlV28(recipe) {
  const n=recipeNutritionV28(recipe);
  if(!Object.values(n).some(Boolean)) return "";
  return `<section class="nutrition-panel"><h3>Omtrentlig næring per porsjon</h3><div class="nutrition-grid">
    ${[["Protein",n.protein,"g"],["Kalorier",n.calories,"kcal"],["Fett",n.fat,"g"],["Karbohydrater",n.carbohydrates,"g"],["Fiber",n.fiber,"g"]].map(([label,value,unit])=>`<div><strong>${value||"–"} ${unit}</strong><span>${label}</span></div>`).join("")}
  </div><p class="hint">AI-estimat basert på ingrediensene.</p></section>`;
}
window.openRecipeDetails=function(id){
  const recipe=recipeById(id); if(!recipe)return;
  const missingCentral=!recipeHasIngredientsV23(recipe)||!String(recipe.instructions||"").trim();
  $("recipeDialogTitle").textContent=`${emojiForRecipe(recipe)} ${recipe.name}`;
  $("recipeDialogBody").innerHTML=`${recipe.image?`<div class="recipe-hero-image"><img src="${escapeAttr(recipe.image)}" alt=""></div>`:""}
    ${missingCentral&&resolveRecipeSourceUrl(recipe)?`<section class="recovery-inline-card"><strong>⚠ Denne oppskriften mangler data.</strong><p>Bruk originalkilden og eksisterende Recovery-pipeline. Ingenting lagres uten forhåndsvisning.</p><button type="button" class="primary" onclick="recoverRecipeFromUrlV28('${escapeAttr(recipe.id)}')">Recover from URL</button></section>`:""}
    <p class="recipe-meta">${escapeHtml(recipe.category||"Ukjent")} · ${escapeHtml(recipe.source||"")} · brukt ${usageCount(recipe.id)}×</p>
    ${pantryStatusV28(recipe,true)}
    <div class="inline-actions"><button type="button" class="primary" onclick="openAddToDay('${escapeAttr(recipe.id)}')">+ Legg til i ukesmeny</button>
    <button type="button" class="ghost" onclick="markCookedV28('${escapeAttr(recipe.id)}')">Marker som laget</button>
    <button type="button" class="ghost" onclick="addMissingIngredientsV28('${escapeAttr(recipe.id)}')">Legg kun til manglende ingredienser</button>
    <button type="button" class="ghost" onclick="openImport('${escapeAttr(recipe.id)}');$('recipeDialog').close()">Rediger</button></div>
    ${nutritionHtmlV28(recipe)}
    <div class="recipe-detail-section"><h3>Ingredienser</h3>${formatList(ingredientsToText(recipe))}</div>
    <div class="recipe-detail-section"><h3>Fremgangsmåte</h3>${formatSteps(instructionsToText(recipe))}</div>`;
  $("recipeDialog").showModal();
};
window.recoverRecipeFromUrlV28=async function(id){
  const recipe=recipeById(id),sourceUrl=resolveRecipeSourceUrl(recipe);
  if(!sourceUrl)return alert("Denne oppskriften har ingen lagret kilde-URL og kan derfor ikke gjenopprettes automatisk.");
  $("recipeDialog")?.close(); openImport(id); $("importLink").value=sourceUrl;
  await autoFetchRecipeUrlV27(sourceUrl,true);
};

function populateRecipeControlsV28() {
  const categories=[...new Set(recipes.map(recipe=>recipe.category).filter(Boolean))].sort((a,b)=>a.localeCompare(b,"no"));
  for(const id of ["recipeCategoryFilter","pickerCategoryFilter"]){
    const select=$(id); if(!select)continue;
    const selected=select.value; select.innerHTML=`<option value="">Alle kategorier</option>`+categories.map(category=>`<option>${escapeHtml(category)}</option>`).join(""); select.value=selected;
  }
  for(const [scope,id] of [["recipes","recipeFilterChips"],["picker","pickerFilterChips"]]){
    const box=$(id); if(!box)continue;
    box.innerHTML=RECIPE_FILTERS_V28.map(([key,label])=>`<button type="button" class="filter-chip" data-filter="${key}">${label}</button>`).join("");
    box.querySelectorAll("button").forEach(button=>button.addEventListener("click",()=>{button.classList.toggle("active");renderRecipeResultsV28(scope)}));
  }
}
function variedSuggestionsV28(count=5) {
  const candidates=recipes.filter(recipe=>recipeMatchesV28(recipe,"recipes")&&recipeHasIngredientsV23(recipe));
  const ranked=candidates.map(recipe=>({recipe,pantry:pantryAnalysisV28(recipe),recent:recipeFlagsV28(recipe).avoidRecent14?0:1,random:Math.random()}))
    .sort((a,b)=>b.pantry.score-a.pantry.score||a.recent-b.recent||a.random-b.random);
  const selected=[],categories=new Set();
  for(const item of ranked){if(selected.length>=count)break;if(!categories.has(item.recipe.category)||ranked.length-selected.length<=count-selected.length){selected.push(item.recipe);categories.add(item.recipe.category)}}
  return selected;
}
function showSuggestionsV28(count=5){
  const suggestions=variedSuggestionsV28(count),box=$("recipeSuggestions"); if(!box)return;
  box.innerHTML=suggestions.map(recipe=>recipeCardHtmlV28(recipe)).join("")||`<div class="empty-state">Ingen oppskrifter passer filtrene.</div>`;
}

function renderPantryV28(){
  ensureMetaV28(); const query=normalize($("pantrySearch")?.value||"");
  const items=appMeta.pantryItems.filter(item=>!query||normalize(item.name).includes(query));
  if($("pantryCount")) $("pantryCount").textContent=`${appMeta.pantryItems.length} ${appMeta.pantryItems.length===1?"vare":"varer"}`;
  if($("pantryList")) $("pantryList").innerHTML=items.map(item=>`<article class="pantry-row">
    <div><strong>${escapeHtml(item.name)}</strong><p>${escapeHtml([item.quantity,item.unit].filter(Boolean).join(" ")||"Mengde ikke oppgitt")} · ${item.zone==="fridge"?"Kjøleskap":item.zone==="freezer"?"Fryser":"Tørrlager"}${item.always?" · alltid tilgjengelig":""}</p></div>
    <div class="inline-actions"><button class="ghost" onclick="editPantryV28('${escapeAttr(item.id)}')">Endre</button><button class="ghost danger-subtle" onclick="removePantryV28('${escapeAttr(item.id)}')">Slett</button></div></article>`).join("")||`<div class="empty-state">Pantry er tomt. Legg inn det dere har hjemme.</div>`;
}
let pantryEditingIdV29=null;
window.removePantryV28=function(id){ensureMetaV28();appMeta.pantryItems=appMeta.pantryItems.filter(item=>item.id!==id);savePlan();renderPantryV28();renderRecipeResults()};
window.editPantryV28=function(id){const item=appMeta.pantryItems.find(entry=>entry.id===id);if(!item)return;pantryEditingIdV29=id;$("pantryName").value=item.name;$("pantryQuantity").value=item.quantity||"";$("pantryUnit").value=item.unit||"";$("pantryZone").value=item.zone||"pantry";$("pantryAlways").checked=!!item.always};
function addMissingIngredientsV28(id){
  const recipe=recipeById(id),missing=pantryAnalysisV28(recipe).missing;
  if(!missing.length)return alert("Dere har allerede alle registrerte ingredienser hjemme.");
  for(const ingredient of missing)addShoppingItemV25(formatAiIngredient(ingredient),ingredient.shoppingCategory||categorize(ingredient.item));
  alert(`${missing.length} ${missing.length===1?"manglende ingrediens er":"manglende ingredienser er"} lagt til.`);
}
window.addMissingIngredientsV28=addMissingIngredientsV28;

const categorizeBeforeV28=categorize;
categorize=function(line){
  ensureMetaV28(); const key=pantryKeyV28(line),override=appMeta.ingredientRegistryOverrides[key];
  if(override&&CATEGORIES.includes(override))return override;
  const text=normalize(line);
  if(/\b(salt|pepper|oregano|timian|basilikum|spisskummen|kanel|muskat|karri|kardemomme|kajenne|laurbær)\b/.test(text)||/\b(pulver|flak|krydder|masala)\b/.test(text))return"Krydder";
  return categorizeBeforeV28(line);
};
shoppingRowHtmlV25=function(item){
  const source=item.recipe&&item.recipe!=="Egen vare"?item.recipe:"";
  return `<div class="shopping-row${item.done?" done":""}" data-shopping-id="${escapeAttr(item.id)}">
    <input class="shopping-check" type="checkbox" ${item.done?"checked":""} onchange="toggleShoppingDoneV25('${escapeAttr(item.id)}',this.checked)">
    <div class="shopping-item-main"><button type="button" class="shopping-item-text" onclick="editShoppingItemV25('${escapeAttr(item.id)}')">${escapeHtml(item.text)}</button>${source?`<span class="shopping-source">Fra ${escapeHtml(source)}</span>`:""}</div>
    <button type="button" class="shopping-more" onclick="toggleShoppingActionsV25('${escapeAttr(item.id)}',this)">•••</button>
    <div class="shopping-actions"><button type="button" class="shopping-delete category-action" onclick="openShoppingCategoryV28('${escapeAttr(item.id)}')">Endre kategori</button><button type="button" class="shopping-delete" onclick="removeShoppingItemV25('${escapeAttr(item.id)}')">Slett vare</button></div></div>`;
};
const renderShoppingListBeforeV28=renderShoppingList;
renderShoppingList=function(items){
  for(const item of items||[])if(item.manualCategory&&CATEGORIES.includes(item.category))item.__manualCategory=item.category;
  renderShoppingListBeforeV28(items);
  for(const item of shoppingItems||[])if(item.__manualCategory){item.category=item.__manualCategory;delete item.__manualCategory}
};
window.openShoppingCategoryV28=function(id){
  const item=shoppingItems.find(entry=>entry.id===id);if(!item)return;shoppingCategoryTargetV28=id;
  $("shoppingCategoryItemName").textContent=item.text;$("shoppingCategorySelect").innerHTML=CATEGORIES.map(cat=>`<option>${cat}</option>`).join("");$("shoppingCategorySelect").value=item.category||"Annet";
  $("registryUpdateChoice").hidden=categorizeBeforeV28(item.text)==="Annet";$("shoppingCategoryDialog").showModal();
};

function structuredPreviewV28(){
  const box=$("structuredIngredientPreview"),ingredients=window.lastAiParsedRecipe?.ingredients||previewIngredientsV26();
  const uncertainties=window.lastAiParsedRecipe?.uncertainties||[];
  if(!box)return;box.innerHTML=ingredients.map((ingredient,index)=>{const warning=uncertainties.find(item=>item.field===`ingredients.${index}`);
    return `<div class="structured-ingredient-row${warning?" uncertain":""}" data-index="${index}">
    <input data-field="amount" value="${escapeAttr(ingredient.amount||"")}" aria-label="Mengde">
    <input data-field="unit" value="${escapeAttr(ingredient.unit||"")}" aria-label="Enhet">
    <input data-field="item" value="${escapeAttr(ingredient.item||"")}" aria-label="Ingrediens">
    <select data-field="shoppingCategory">${CATEGORIES.map(category=>`<option${category===(ingredient.shoppingCategory||categorize(ingredient.item))?" selected":""}>${category}</option>`).join("")}</select>
    ${warning?`<p class="ingredient-warning">Kontroller: ${escapeHtml(warning.reason)}</p>`:""}</div>`}).join("")||`<p class="hint">Ingrediensene vises her etter analyse.</p>`;
}
function syncStructuredPreviewV28(){
  const rows=[...($("structuredIngredientPreview")?.querySelectorAll(".structured-ingredient-row")||[])];
  if(!rows.length)return;
  const previous=window.lastAiParsedRecipe?.ingredients||[];
  const ingredients=rows.map((row,index)=>mergePreservingExistingData(previous[index],Object.fromEntries([...row.querySelectorAll("[data-field]")].map(input=>[input.dataset.field,input.value.trim()]))));
  window.lastAiParsedRecipe=window.lastAiParsedRecipe||{};window.lastAiParsedRecipe.ingredients=ingredients;
  window.lastAiParsedRecipe.__displayIngredients=ingredients.map(formatAiIngredient).join("\n");$("parsedIngredients").value=window.lastAiParsedRecipe.__displayIngredients;
}
const parseCaptionAIBeforeV28=parseCaptionAI;
parseCaptionAI=async function(options={}){const result=await parseCaptionAIBeforeV28(options);if(result)structuredPreviewV28();return result};
const saveParsedRecipeBeforeV28=saveParsedRecipe;
saveParsedRecipe=async function(){
  syncStructuredPreviewV28();
  const ai=window.lastAiParsedRecipe||{};
  if(!ai.nutrition&&previewIngredientsV26().length){
    $("aiStatus").textContent="Estimerer næringsinnhold …";
    try{const response=await fetch("/api/nutrition",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({ingredients:previewIngredientsV26(),servings:$("importServings").value})});const result=await response.json();if(result.ok)ai.nutrition=result.nutrition}catch(error){console.warn("Næringsestimat kunne ikke beregnes",error)}
  }
  return saveParsedRecipeBeforeV28();
};

const addRecipeToDayBeforeV28=window.addRecipeToDay;
window.addRecipeToDay=function(day,id){const before=(plan[day]||[]).length;addRecipeToDayBeforeV28(day,id);if((plan[day]||[]).length>before)markCookedV28(id,true,day)};
const confirmAddToDayBeforeV28=confirmAddToDay;
confirmAddToDay=function(){const id=pendingAddRecipeId,day=$("addToDaySelect")?.value;confirmAddToDayBeforeV28();if(id&&day)markCookedV28(id,true,day)};
randomWeek=function(){
  const days=selectedDays(),pool=variedSuggestionsV28(Math.max(days.length,5));
  if(!pool.length)return alert("Ingen oppskrifter passer de valgte filtrene.");
  days.forEach((day,index)=>{const recipe=pool[index%pool.length];plan[day.key]=recipe?[{type:"recipe",recipeId:recipe.id}]:[];if(recipe){bumpUsage(recipe.id);setLastCookedV28(recipe.id,day.key)}});
  savePlan();createDayRows();renderRecipeResults();
};
localSmartWeek=function(){
  const days=selectedDays(),suggestions=variedSuggestionsV28(Math.max(days.length,5));
  if(!suggestions.length)return alert("Ingen oppskrifter passer de valgte filtrene.");
  days.forEach((day,index)=>{const recipe=suggestions[index%suggestions.length];plan[day.key]=recipe?[{type:"recipe",recipeId:recipe.id}]:[];if(recipe){bumpUsage(recipe.id);setLastCookedV28(recipe.id,day.key)}});
  savePlan();createDayRows();renderRecipeResults();
};
smartWeek=async function(){
  const days=selectedDays(),prompt=$("smartPrompt")?.value?.trim()||"";
  if($("smartStatus"))$("smartStatus").textContent="Lager et variert forslag med Pantry i bakhodet …";
  try{
    const payloadRecipes=recipes.filter(recipe=>recipeHasIngredientsV23(recipe)&&recipeMatchesV28(recipe,"recipes")).map(recipe=>{
      const pantry=pantryAnalysisV28(recipe),flags=recipeFlagsV28(recipe);
      return {id:recipe.id,name:recipe.name,category:recipe.category,tags:enrichTags(recipe),favorite:isFavorite(recipe.id),usage:usageCount(recipe.id),pantryScore:pantry.score,missingIngredients:pantry.missing.length,recentlyCooked:!flags.avoidRecent14};
    }).sort((a,b)=>b.pantryScore-a.pantryScore||a.missingIngredients-b.missingIngredients).slice(0,180);
    const response=await fetch("/api/smart-week",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({prompt:`${prompt}\nPrioriter variasjon, minst mulig innkjøp og oppskrifter som ikke nylig er laget. Unngå samme hovedprotein eller kategori flere dager på rad.`,days:days.map(day=>({key:day.key,label:day.label,weekday:day.weekday})),recipes:payloadRecipes})});
    const result=await response.json();if(!response.ok||!result.ok)throw new Error(result.error||"AI-forslaget feilet");
    days.forEach(day=>plan[day.key]=[]);
    for(const row of result.plan?.items||[]){const match=days.find(day=>day.key===row.day||day.weekday===normalize(row.day));if(!match)continue;const ids=(row.recipeIds||row.recipe_ids||[]).filter(id=>recipeById(id));plan[match.key]=ids.map(id=>{bumpUsage(id);setLastCookedV28(id,match.key);return{type:"recipe",recipeId:id}})}
    savePlan();createDayRows();renderRecipeResults();$("smartStatus").textContent="Forslaget er klart. Du kan justere det fritt.";
  }catch(error){console.warn(error);$("smartStatus").textContent="AI-forslaget feilet – bruker smart lokal variasjon.";localSmartWeek()}
};

const bindAllBeforeV28=bindAll;
bindAll=function(){
  bindAllBeforeV28();ensureMetaV28();populateRecipeControlsV28();renderPantryV28();
  for(const id of ["recipeCategoryFilter","pickerCategoryFilter","pickerSort"])$(id)?.addEventListener("change",()=>renderRecipeResultsV28(id.startsWith("picker")?"picker":"recipes"));
  $("recipeSuggestionsBtn")?.addEventListener("click",()=>showSuggestionsV28(5));
  $("surpriseRecipeBtn")?.addEventListener("click",()=>showSuggestionsV28(1));
  $("pantrySearch")?.addEventListener("input",renderPantryV28);
  $("pantryForm")?.addEventListener("submit",event=>{event.preventDefault();ensureMetaV28();const name=$("pantryName").value.trim();if(!name)return;const candidate={id:pantryEditingIdV29||`pantry-${Date.now()}`,name,quantity:$("pantryQuantity").value.trim(),unit:$("pantryUnit").value,zone:$("pantryZone").value,always:$("pantryAlways").checked};const index=appMeta.pantryItems.findIndex(item=>item.id===pantryEditingIdV29);if(index>=0)appMeta.pantryItems[index]=mergePreservingExistingData(appMeta.pantryItems[index],candidate);else appMeta.pantryItems.push(candidate);pantryEditingIdV29=null;event.currentTarget.reset();savePlan();renderPantryV28();renderRecipeResults()});
  $("structuredIngredientPreview")?.addEventListener("input",syncStructuredPreviewV28);
  $("structuredIngredientPreview")?.addEventListener("change",syncStructuredPreviewV28);
  $("confirmShoppingCategoryBtn")?.addEventListener("click",()=>{const item=shoppingItems.find(entry=>entry.id===shoppingCategoryTargetV28);if(!item)return;const category=$("shoppingCategorySelect").value;item.category=category;item.manualCategory=true;item.updatedAt=nowIsoV25();const scope=document.querySelector('input[name="registryScope"]:checked')?.value;if(scope==="registry"){if(!confirm(`Oppdater Ingredient Registry slik at «${item.text}» alltid får kategorien ${category}?`))return;appMeta.ingredientRegistryOverrides[pantryKeyV28(item.text)]=category}savePlan();renderShoppingList(shoppingItems);$("shoppingCategoryDialog").close()});
};
const initBeforeV28=init;
init=async function(){await initBeforeV28();ensureMetaV28();randomOrderV28=new Map(recipes.map(recipe=>[String(recipe.id),Math.random()]));renderRecipeResults();renderPantryV28()};

init();
