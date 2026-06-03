
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
function mergeCustomData(){recipes=recipes.map(r=>({...r,...(customRecipes[r.id]||{})}))}
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
function openImport(id){activeImportId=id;const r=recipeById(id);$("importTarget").textContent=`Lagrer på: ${r.name}`;$("importLinkWrap").innerHTML=r.link?`Kilde: <a href="${escapeAttr(r.link)}" target="_blank" rel="noopener">åpne originaloppskrift</a>`:"Ingen kilde registrert";$("importName").value=r.name||"";$("importLink").value=r.link||"";$("importCategory").value=r.category||"Annet";$("importServings").value=r.servings||"";$("captionInput").value="";$("parsedIngredients").value=ingredientsToText(r);$("parsedInstructions").value=instructionsToText(r);window.lastAiParsedRecipe=null;$("importDialog").showModal()}
async function parseCaptionAI(){const caption=$("captionInput").value.trim(),status=$("aiStatus"),btn=$("aiParseCaptionBtn"),r=recipeById(activeImportId)||{};if(!caption)return alert("Lim inn caption/oppskriftstekst først.");try{btn.disabled=true;btn.textContent="AI parser …";status.textContent="Sender tekst til AI-parser …";const res=await fetch("/api/parse-caption",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({caption,recipeName:$("importName").value.trim()||r.name||"",sourceUrl:$("importLink").value.trim()||r.link||"",category:$("importCategory").value||r.category||""})});const data=await res.json();if(!data.ok)throw new Error(data.error||"AI-parser feilet");const p=data.parsed||{};$("importName").value=$("importName").value.trim()||p.title||r.name||"";$("importCategory").value=p.category||$("importCategory").value||"Annet";$("importServings").value=p.servings||$("importServings").value||"";$("parsedIngredients").value=(p.ingredients||[]).map(formatAiIngredient).join("\n");$("parsedInstructions").value=(p.instructions||[]).map((s,i)=>`${i+1}. ${s}`).join("\n");p.tags=enrichTags({...r,...p,name:p.title||$("importName").value});p.emoji=emojiForRecipe({...r,...p,name:p.title||$("importName").value});window.lastAiParsedRecipe=p;status.textContent=`AI-parsing ferdig. Tags: ${(p.tags||[]).join(", ")}`}catch(err){status.textContent="AI-parser feilet: "+(err?.message||err);alert("AI-parser feilet. Se statusfelt.")}finally{btn.disabled=false;btn.textContent="AI-parse caption"}}
function formatAiIngredient(ing){if(typeof ing==="string")return ing;const amount=ing.amount||"",unit=ing.unit||"",item=ing.item||"",note=ing.note?` (${ing.note})`:"",cat=ing.shoppingCategory?` [${ing.shoppingCategory}]`:"";return`${amount} ${unit} ${item}${note}${cat}`.replace(/\s+/g," ").trim()}
function parseCaption(){const text=$("captionInput").value.trim(),lines=text.split(/\r?\n/).map(l=>l.trim()).filter(Boolean),ing=[],inst=[];let mode="";for(const line of lines){if(/ingredients|ingredienser/i.test(line)){mode="ing";continue}if(/instructions|method|fremgangsmåte|slik gjør/i.test(line)){mode="inst";continue}if(mode==="inst"||/^\d+[\.)]/.test(line))inst.push(line);else if(mode==="ing"||/^[-*•]?\s*[\d¼½¾]/.test(line))ing.push(convertIngredientLine(line.replace(/^[-*•]\s*/,"")))}$("parsedIngredients").value=ing.join("\n");$("parsedInstructions").value=inst.join("\n")}
async function saveParsedRecipe(){if(!activeImportId)return alert("Ingen oppskrift valgt.");const name=$("importName").value.trim()||"Ny oppskrift",link=$("importLink").value.trim(),category=$("importCategory").value||"Annet",ai=window.lastAiParsedRecipe||{},base=recipeById(activeImportId)||{};const patch={name,link,category,source:link.includes("instagram")?"Instagram":link.includes("tiktok")?"TikTok":link?"Nettside":"Manuell",servings:$("importServings").value.trim(),ingredientsText:$("parsedIngredients").value.trim(),instructions:$("parsedInstructions").value.trim(),structuredIngredients:ai.ingredients||[],structuredInstructions:ai.instructions||[],tags:ai.tags||enrichTags({...base,name,category,ingredientsText:$("parsedIngredients").value,instructions:$("parsedInstructions").value}),emoji:ai.emoji||emojiForRecipe({...base,name,category}),aiParsed:!!window.lastAiParsedRecipe,aiConfidence:ai.confidence||"",status:"Fullført",manualCheck:"Nei",updatedAt:new Date().toISOString()};const idx=recipes.findIndex(r=>String(r.id)===String(activeImportId));if(idx>=0)recipes[idx]={...recipes[idx],...patch};else recipes.push({id:activeImportId,...patch});try{const response=await fetch("/api/save-recipe",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({id:activeImportId,patch})});const saveResult=await response.json().catch(()=>({}));if(!response.ok||saveResult.ok===false)throw new Error(saveResult.error||"Lagring feilet");$("importDialog").close();createDayRows();renderRecipeResults();alert("Oppskriften er lagret permanent i Supabase ✅")}catch(err){customRecipes[activeImportId]={...(customRecipes[activeImportId]||{}),...patch};localStorage.setItem("middag_custom_recipes",JSON.stringify(customRecipes));alert("Oppskriften vises nå i denne nettleseren, men Supabase-lagring feilet: "+(err?.message||err))}}
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
async function cleanupVisibleRecipes(){if(!confirm("Rydde tags, emoji og norske mål for oppskriftene?"))return;const btn=$("cleanupRecipesBtn");if(btn){btn.disabled=true;btn.textContent="Rydder …"}let updated=0;for(const r of recipes){const patch={tags:enrichTags(r),emoji:emojiForRecipe(r),ingredientsText:ingredientsToText(r).split(/\n/).map(convertIngredientLine).join("\n"),updatedAt:new Date().toISOString()};try{const response=await fetch("/api/save-recipe",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({id:r.id,patch})});const data=await response.json().catch(()=>({}));if(response.ok&&data.ok!==false){Object.assign(r,patch);updated++}}catch(e){console.warn("rydd feilet",r.name,e)}}renderRecipeResults();createDayRows();if(btn){btn.disabled=false;btn.textContent="Rydd tags/mål"}alert(`Ryddet ${updated} oppskrifter. Kategorisering av handleliste er forbedret.`)}
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
    const patch={
      tags:enrichTags(r),
      emoji:emojiForRecipe(r),
      ingredientsText:ingredientsToText(r).split(/\n/).map(normalizeIngredientLineForDisplay).join("\n"),
      updatedAt:new Date().toISOString()
    };
    try{
      const response=await fetch("/api/save-recipe",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({id:r.id,patch})});
      const data=await response.json().catch(()=>({}));
      if(response.ok&&data.ok!==false){Object.assign(r,patch);updated++}
    }catch(e){console.warn("rydd feilet",r.name,e)}
  }
  renderRecipeResults();createDayRows();
  if(btn){btn.disabled=false;btn.textContent="Rydd/oversett oppskrifter"}
  alert(`Ryddet/oversatte ${updated} oppskrifter.`);
}

init();
