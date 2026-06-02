const DAYS = ["mandag", "tirsdag", "onsdag", "torsdag", "fredag", "lørdag", "søndag"];
const CATEGORIES = [
  "Frukt og grønt", "Kjøtt", "Kjølevarer", "Meieri", "Frys", "Hermetikk/halvfabrikat",
  "Tørrvarer", "Krydder", "Glutenfritt", "Bakevarer", "Annet"
];

let recipes = [];
let plan = {};
let customRecipes = JSON.parse(localStorage.getItem("middag_custom_recipes") || "{}");
let activeImportId = null;
let shoppingItems = [];
let currentView = "viewPlan";

const $ = (id) => document.getElementById(id);

function normalize(s) { return String(s || "").toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "").trim(); }
function hasRecipe(r) { return Boolean((r.ingredientsText && r.ingredientsText.trim()) || (r.ingredientLines && r.ingredientLines.length)); }
function recipeById(id) { return recipes.find(r => String(r.id) === String(id)); }

function mergeCustomData() {
  recipes = recipes.map(r => ({...r, ...(customRecipes[r.id] || {})}));
}

function bind(id, event, fn) {
  const el = $(id);
  if (!el) {
    console.warn(`[Middag] Fant ikke element #${id}`);
    return;
  }
  el.addEventListener(event, fn);
}

async function init() {
  const recipeResponse = await fetch("/api/recipes").then(r => r.json());
  recipes = recipeResponse.recipes || [];
  const planResponse = await fetch("/api/plan").then(r => r.json()).catch(() => ({plan:{}}));
  plan = planResponse.plan?.items || planResponse.plan || {};
  mergeCustomData();
  fillDaySelectors();
  $("recipeCount").textContent = `${recipes.length} oppskrifter`;
  bind("createDaysBtn", "click", createDayRows);
  bind("generateListBtn", "click", generateShoppingList);
  $("resetPlanBtn").addEventListener("click", () => { plan = {}; savePlan(); createDayRows(); $("shoppingList").innerHTML = ""; });
  bind("recipeSearch", "input", renderRecipeResults);
  bind("addRecipeBtn", "click", openAddRecipe);
  document.querySelectorAll(".nav-btn").forEach(btn => btn.addEventListener("click", () => showView(btn.dataset.view)));
  bind("parseCaptionBtn", "click", parseCaption);
  bind("saveParsedBtn", "click", saveParsedRecipe);
  if ($("readScreenshotsBtn")) $("readScreenshotsBtn").addEventListener("click", readScreenshotsWithOCR);
  if ($("aiParseCaptionBtn")) $("aiParseCaptionBtn").addEventListener("click", parseCaptionAI);
  if ($("clearCaptionBtn")) $("clearCaptionBtn").addEventListener("click", () => {
    $("captionInput").value = "";
  window.lastAiParsedRecipe = null;
    if ($("ocrPreview")) $("ocrPreview").innerHTML = "";
    if ($("ocrStatus")) $("ocrStatus").textContent = "Caption-feltet er tømt.";
  });
  if ($("aiParseCaptionBtn")) $("aiParseCaptionBtn").onclick = parseCaptionAI;
  if ($("parseCaptionBtn")) $("parseCaptionBtn").onclick = parseCaption;
  if ($("saveParsedBtn")) $("saveParsedBtn").onclick = saveParsedRecipe;
  console.log("[Middag] v14 stabil init ferdig. Bunnmeny/import/lagring koblet.");
  createDayRows();
  renderRecipeResults();
}


function showView(viewId) {
  currentView = viewId;
  document.querySelectorAll(".view").forEach(v => v.classList.toggle("active", v.id === viewId));
  document.querySelectorAll(".nav-btn").forEach(b => b.classList.toggle("active", b.dataset.view === viewId));
}

function openAddRecipe() {
  const id = `custom-${Date.now()}`;
  const newRecipe = {
    id,
    name: "Ny oppskrift",
    category: "Annet",
    source: "Manuell",
    link: "",
    ingredientsText: "",
    instructions: "",
    status: "Mangler oppskrift",
    manualCheck: "Ja"
  };
  recipes.push(newRecipe);
  activeImportId = id;
  $("importTarget").textContent = "Lagrer som ny oppskrift";
  $("importLinkWrap").innerHTML = "Legg inn navn, lenke og caption/oppskriftstekst.";
  $("importName").value = "";
  if ($("importLink")) $("importLink").value = "";
  if ($("importCategory")) $("importCategory").value = "Annet";
  $("importServings").value = "";
  $("captionInput").value = "";
  window.lastAiParsedRecipe = null;
  if ($("screenshotInput")) $("screenshotInput").value = "";
  if ($("ocrPreview")) $("ocrPreview").innerHTML = "";
  if ($("ocrStatus")) $("ocrStatus").textContent = "Du kan velge flere screenshots samtidig. Trykk “Les tekst fra skjermbilder”.";
  $("parsedIngredients").value = "";
  $("parsedInstructions").value = "";
  $("importDialog").showModal();
}

function fillDaySelectors() {
  for (const id of ["startDay", "endDay"]) {
    $(id).innerHTML = DAYS.map(d => `<option value="${d}">${capitalize(d)}</option>`).join("");
  }
  $("startDay").value = "mandag";
  $("endDay").value = "fredag";
}
function capitalize(s) { return s.charAt(0).toUpperCase() + s.slice(1); }
function selectedDays() {
  const start = DAYS.indexOf($("startDay").value);
  const end = DAYS.indexOf($("endDay").value);
  const out = [];
  let i = start;
  while (true) {
    out.push(DAYS[i]);
    if (i === end) break;
    i = (i + 1) % DAYS.length;
  }
  return out;
}
function savePlan() {
  localStorage.setItem("middag_plan", JSON.stringify(plan));
  fetch("/api/plan", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({plan: {items: plan, updatedAt: new Date().toISOString()}})
  }).catch(err => console.warn("Kunne ikke sync'e plan til server", err));
}

function createDayRows() {
  const container = $("dayRows");
  const days = selectedDays();
  container.innerHTML = "";
  const options = `<option value=""></option>` + recipes
    .slice()
    .sort((a,b) => a.name.localeCompare(b.name, "no"))
    .map(r => `<option value="${r.id}">${escapeHtml(r.name)} — ${escapeHtml(r.category || "")}</option>`).join("");

  for (const day of days) {
    const row = document.createElement("div");
    row.className = "day-row";
    row.innerHTML = `
      <div class="day-name">${day}</div>
      <div class="recipe-cell">
        <select data-day="${day}" class="recipe-select">${options}</select>
        <div class="selected-source"></div>
      </div>
      <div class="day-actions"><span class="status empty">Velg rett</span></div>
    `;
    container.appendChild(row);
    const select = row.querySelector("select");
    select.value = plan[day] || "";
    select.addEventListener("change", () => {
      plan[day] = select.value;
      savePlan();
      updateRowStatus(row, select.value);
    });
    updateRowStatus(row, select.value);
  }
}

function updateRowStatus(row, recipeId) {
  const actions = row.querySelector(".day-actions");
  const sourceBox = row.querySelector(".selected-source");
  if (sourceBox) sourceBox.innerHTML = "";
  if (!recipeId) { actions.innerHTML = `<span class="status empty">Velg rett</span>`; return; }
  const r = recipeById(recipeId);
  if (!r) { actions.innerHTML = `<span class="status missing">Ikke funnet</span>`; return; }

  const sourceName = r.source ? String(r.source) : "Kilde";
  const sourceLink = r.link
    ? `<a class="source-link-inline" href="${escapeAttr(r.link)}" target="_blank" rel="noopener">Åpne ${escapeHtml(sourceName)} / original</a>`
    : `<span class="no-link">Ingen kildelenke registrert</span>`;
  if (sourceBox) {
    sourceBox.innerHTML = sourceLink;
  }

  if (hasRecipe(r)) {
    actions.innerHTML = `<span class="status ok">Oppskrift funnet</span>`;
  } else {
    actions.innerHTML = `<button class="import-btn" data-import="${r.id}">Oppskrift mangler / importer</button>`;
    actions.querySelector("button").addEventListener("click", () => openImport(r.id));
  }
}
function openImport(id) {
  activeImportId = id;
  const r = recipeById(id);
  $("importTarget").textContent = `Lagrer på: ${r.name}`;
  $("importLinkWrap").innerHTML = r.link ? `Kilde: <a href="${escapeAttr(r.link)}" target="_blank" rel="noopener">åpne originaloppskrift</a>` : "Ingen kilde registrert";
  $("importName").value = r.name || "";
  if ($("importLink")) $("importLink").value = r.link || "";
  if ($("importCategory")) $("importCategory").value = r.category || "Annet";
  $("importServings").value = r.servings || "";
  $("captionInput").value = "";
  window.lastAiParsedRecipe = null;
  if ($("screenshotInput")) $("screenshotInput").value = "";
  if ($("ocrPreview")) $("ocrPreview").innerHTML = "";
  if ($("ocrStatus")) $("ocrStatus").textContent = "Du kan velge flere screenshots samtidig. Trykk “Les tekst fra skjermbilder”. Hvis ingenting skjer, sjekk status her.";
  $("parsedIngredients").value = r.ingredientsText || "";
  $("parsedInstructions").value = r.instructions || "";
  $("importDialog").showModal();
}


async function readScreenshotsWithOCR() {
  const input = $("screenshotInput");
  const files = Array.from(input?.files || []);
  const status = $("ocrStatus");
  const preview = $("ocrPreview");
  const btn = $("readScreenshotsBtn");

  function setStatus(msg) {
    console.log("[OCR]", msg);
    if (status) status.textContent = msg;
  }

  if (!files.length) {
    setStatus("Ingen bilder valgt. Velg ett eller flere screenshots først.");
    alert("Velg ett eller flere skjermbilder først.");
    return;
  }

  if (!window.Tesseract) {
    setStatus("OCR-biblioteket er ikke lastet. Sjekk internett på iPhone/Mac, last inn siden på nytt, eller bruk Live Text manuelt.");
    alert("OCR-biblioteket ble ikke lastet. Sjekk internett og last siden på nytt.");
    return;
  }

  if (preview) preview.innerHTML = "";
  if (btn) {
    btn.disabled = true;
    btn.textContent = "Leser bilder …";
  }

  const existingText = $("captionInput").value.trim();
  const chunks = [];

  try {
    const worker = await Tesseract.createWorker("eng", 1, {
      workerPath: "https://cdn.jsdelivr.net/npm/tesseract.js@5/dist/worker.min.js",
      corePath: "https://cdn.jsdelivr.net/npm/tesseract.js-core@5/tesseract-core.wasm.js",
      langPath: "https://tessdata.projectnaptha.com/4.0.0",
      logger: (m) => {
        if (m.status) {
          const pct = typeof m.progress === "number" ? ` ${Math.round(m.progress * 100)}%` : "";
          setStatus(`${m.status}${pct}`);
        }
      }
    });

    for (let i = 0; i < files.length; i++) {
      const file = files[i];
      setStatus(`OCR: forbereder bilde ${i + 1} av ${files.length} …`);

      const imageUrl = await fileToDataUrl(file);

      setStatus(`OCR: leser bilde ${i + 1} av ${files.length} …`);
      const result = await worker.recognize(imageUrl);
      const text = cleanOcrText(result?.data?.text || "");

      if (text) {
        chunks.push(`=== SKJERMBILDE ${i + 1} ===\n${text}`);
        if (preview) {
          const block = document.createElement("details");
          block.open = i === 0;
          block.innerHTML = `<summary>Tekst fra skjermbilde ${i + 1}</summary><pre>${escapeHtml(text)}</pre>`;
          preview.appendChild(block);
        }
      } else if (preview) {
        const block = document.createElement("details");
        block.open = true;
        block.innerHTML = `<summary>Skjermbilde ${i + 1}: ingen tekst funnet</summary><pre>Prøv skarpere screenshot eller bruk Live Text manuelt.</pre>`;
        preview.appendChild(block);
      }
    }

    await worker.terminate();

    const joined = chunks.join("\n\n").trim();
    if (!joined) {
      setStatus("Fant ikke lesbar tekst. Prøv skarpere screenshots, eller bruk iPhone Live Text og lim inn tekst manuelt.");
      return;
    }

    $("captionInput").value = [existingText, joined].filter(Boolean).join("\n\n");
    setStatus(`Ferdig! La inn tekst fra ${chunks.length} skjermbilde(r). Se over teksten og trykk “Parse caption”.`);
  } catch (err) {
    console.error("[OCR error]", err);
    setStatus("OCR feilet. Prøv Chrome/Safari på nytt, færre bilder, eller Live Text manuelt. Feil: " + (err?.message || err));
    alert("OCR feilet. Se statusfeltet under bildeknappen.");
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = "Les tekst fra skjermbilder";
    }
  }
}

function fileToDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(reader.error);
    reader.onload = () => resolve(reader.result);
    reader.readAsDataURL(file);
  });
}

function cleanOcrText(text) {
  return String(text || "")
    .replace(/\r/g, "\n")
    .replace(/[ \t]+/g, " ")
    .replace(/\n{3,}/g, "\n\n")
    .split("\n")
    .map(l => l.trim())
    .filter(l => l && !/^(\d{1,2}:\d{2}|instagram|tiktok|follow|like|comment|share)$/i.test(l))
    .join("\n")
    .trim();
}




function getCurrentImportRecipe() {
  if (activeImportId !== undefined && activeImportId !== null) {
    const match = recipes.find(x => String(x.id) === String(activeImportId));
    if (match) return match;
  }
  const name = ($("importName")?.value || "").trim().toLowerCase();
  if (name) {
    const match = recipes.find(x => String(x.name || x.title || "").trim().toLowerCase() === name);
    if (match) return match;
  }
  return {};
}


async function parseCaptionAI() {
  console.log("[AI parser] button clicked");
  const caption = $("captionInput").value.trim();
  const status = $("aiStatus");
  const btn = $("aiParseCaptionBtn");
  const r = getCurrentImportRecipe();
  if (!caption) {
    alert("Lim inn caption/oppskriftstekst først.");
    return;
  }

  function setStatus(msg) {
    console.log("[AI parser]", msg);
    if (status) status.textContent = msg;
  }

  try {
    if (btn) {
      btn.disabled = true;
      btn.textContent = "AI parser …";
    }
    setStatus("Sender tekst til AI-parser …");

    const res = await fetch("/api/parse-caption", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({
        caption,
        recipeName: $("importName").value.trim() || r.name || r.title || "",
        sourceUrl: $("importLink")?.value?.trim() || r.link || r.source || "",
        category: $("importCategory")?.value || r.category || ""
      })
    });

    const data = await res.json();
    if (!data.ok) {
      setStatus("AI-parser feilet: " + (data.error || "ukjent feil"));
      alert("AI-parser feilet. Sjekk .env/API-nøkkel eller bruk lokal parser.");
      return;
    }

    const p = data.parsed || {};
    const ingredients = Array.isArray(p.ingredients) ? p.ingredients : [];
    const instructions = Array.isArray(p.instructions) ? p.instructions : [];

    $("parsedIngredients").value = ingredients.map(formatAiIngredient).join("\n");
    $("parsedInstructions").value = instructions.map((step, i) => `${i + 1}. ${step}`).join("\n");

    if ($("parsedServings")) $("parsedServings").value = p.servings || "";
    if ($("parsedTime")) $("parsedTime").value = p.timeMinutes || "";

    // Store structured AI data temporarily for saveParsedRecipe to include.
    window.lastAiParsedRecipe = p;

    setStatus(`AI-parsing ferdig (${p.confidence || "ukjent"} confidence). Se over og trykk “Lagre i oppskrift”.`);
  } catch (err) {
    console.error(err);
    setStatus("AI-parser feilet: " + (err?.message || err));
    alert("AI-parser feilet. Se statusfelt.");
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = "AI-parse caption";
    }
  }
}

function formatAiIngredient(ing) {
  if (typeof ing === "string") return ing;
  const amount = ing.amount || "";
  const unit = ing.unit || "";
  const item = ing.item || "";
  const note = ing.note ? ` (${ing.note})` : "";
  const cat = ing.shoppingCategory ? ` [${ing.shoppingCategory}]` : "";
  return `${amount} ${unit} ${item}${note}${cat}`.replace(/\s+/g, " ").trim();
}


function parseCaption() {
  const text = $("captionInput").value.trim();
  const parsed = parseRecipeText(text);
  if (parsed.title && !$('importName').value.trim()) $('importName').value = parsed.title;
  if (parsed.servings && !$('importServings').value.trim()) $('importServings').value = parsed.servings;
  $("parsedIngredients").value = parsed.ingredients.join("\n");
  $("parsedInstructions").value = parsed.instructions.join("\n");
}

function parseRecipeText(text) {
  const rawLines = text
    .replace(/===\s*SKJERMBILDE\s*\d+\s*===/gi, "\n")
    .split(/\r?\n/)
    .map(l => l.trim())
    .filter(Boolean);
  const lines = rawLines.map(cleanBullet).filter(Boolean);
  const norm = lines.map(normalize);

  const title = guessTitle(lines);
  const servings = guessServings(text);

  const ingredientHeaders = [
    "ingredients", "ingredient", "ingredienser", "salad ingredients", "dressing ingredients", "recipe"
  ];
  const methodHeaders = [
    "instructions", "instruction", "method", "directions", "how to make", "how to make it", "fremgangsmate", "slik gjor", "slik gjør"
  ];

  const sections = [];
  let current = {type: "intro", lines: []};
  for (let i = 0; i < lines.length; i++) {
    const l = lines[i];
    const n = norm[i].replace(/:$/, "");
    const isIngredientHeader = ingredientHeaders.some(h => n === normalize(h) || n.includes(normalize(h + ":")) || n.startsWith(normalize(h)));
    const isMethodHeader = methodHeaders.some(h => n === normalize(h) || n.includes(normalize(h + ":")) || n.startsWith(normalize(h)));
    if (isIngredientHeader) {
      sections.push(current);
      current = {type: "ingredients", lines: []};
      continue;
    }
    if (isMethodHeader) {
      sections.push(current);
      current = {type: "instructions", lines: []};
      continue;
    }
    current.lines.push(l);
  }
  sections.push(current);

  let ingredientLines = sections.filter(s => s.type === "ingredients").flatMap(s => s.lines);
  let instructionLines = sections.filter(s => s.type === "instructions").flatMap(s => s.lines);

  // If no explicit ingredient block was found, infer from lines before first numbered instruction.
  if (!ingredientLines.length) {
    const firstInstructionIndex = lines.findIndex(l => isInstructionLine(l));
    const candidateEnd = firstInstructionIndex >= 0 ? firstInstructionIndex : lines.length;
    ingredientLines = lines.slice(0, candidateEnd).filter(isLikelyIngredient);
  }
  // If no explicit method block was found, collect numbered/bulleted sentences after ingredients.
  if (!instructionLines.length) {
    const firstInstructionIndex = lines.findIndex(l => isInstructionLine(l));
    if (firstInstructionIndex >= 0) instructionLines = lines.slice(firstInstructionIndex).map(stripInstructionNumber);
  }

  ingredientLines = ingredientLines
    .map(stripIngredientNoise)
    .filter(isLikelyIngredient)
    .map(convertIngredientLine)
    .filter(Boolean);

  instructionLines = instructionLines
    .map(stripInstructionNumber)
    .map(l => l.trim())
    .filter(l => l.length > 8)
    .map((l, idx) => `${idx + 1}. ${translateInstructionLine(l)}`);

  return { title, servings, ingredients: ingredientLines, instructions: instructionLines };
}


function translateInstructionLine(line) {
  let s = line.trim();
  const replacements = [
    [/\bcook the pasta according to the package instructions until al dente\b/gi, "kok pasta etter anvisning på pakken til al dente"],
    [/\bdrain and set aside\b/gi, "hell av vannet og sett til side"],
    [/\bin a skillet\b/gi, "i en stekepanne"],
    [/\badd\b/gi, "tilsett"],
    [/\bmelt the butter\b/gi, "smelt smøret"],
    [/\bover medium heat\b/gi, "på middels varme"],
    [/\bminced garlic\b/gi, "finhakket hvitløk"],
    [/\bchopped onions?\b/gi, "hakket løk"],
    [/\bstirring frequently\b/gi, "rør jevnlig"],
    [/\bto avoid burning\b/gi, "så det ikke brenner seg"],
    [/\bsliced mushrooms?\b/gi, "skivet sopp"],
    [/\bpasta water\b/gi, "pastavann"],
    [/\bcook until\b/gi, "kok/stek til"],
    [/\breduce the heat to low\b/gi, "senk varmen"],
    [/\bheavy cream\b/gi, "kremfløte"],
    [/\bstir well to combine\b/gi, "rør godt sammen"],
    [/\blet the mixture simmer\b/gi, "la blandingen småkoke"],
    [/\bseason with salt and pepper to taste\b/gi, "smak til med salt og pepper"],
    [/\bslowly sprinkle in\b/gi, "dryss sakte inn"],
    [/\bgrated parmesan cheese\b/gi, "revet parmesan"],
    [/\bwhile stirring continuously\b/gi, "mens du rører hele tiden"],
    [/\bthe cheese is melted\b/gi, "osten er smeltet"],
    [/\bsauce is smooth and creamy\b/gi, "sausen er glatt og kremet"],
    [/\bcooked pasta\b/gi, "kokt pasta"],
    [/\btoss\b/gi, "vend sammen"],
    [/\bwell coated\b/gi, "godt dekket"],
    [/\bcook for an additional\b/gi, "kok/stek i ytterligere"],
    [/\bminutes?\b/gi, "minutter"],
    [/\bgarnish with\b/gi, "topp med"],
    [/\bfresh chopped parsley\b/gi, "fersk hakket persille"],
  ];
  for (const [re, repl] of replacements) s = s.replace(re, repl);
  s = s.replace(/\s{2,}/g, " ").trim();
  return s.charAt(0).toUpperCase() + s.slice(1);
}

function guessTitle(lines) {
  const bad = /follow|save this|comment|macros|protein|calories|ingredients|instructions|method|recipe\s*\(/i;
  const candidate = lines.find(l => l.length > 3 && l.length < 80 && !bad.test(l));
  return candidate || "";
}

function guessServings(text) {
  const m = text.match(/serves\s*(\d+)|servings?\s*:?\s*(\d+)|per\s*(\d+)\s*servings?/i);
  return m ? (m[1] || m[2] || m[3] || "") : "";
}

function isInstructionLine(line) {
  return /^\d+\s*[\.)]/.test(line) || /^(heat|add|stir|cook|bring|serve|slice|mix|drain|rinse|pat|season|garnish|prepare|sauté|saute|let|turn|pour|blend|combine|chop|preheat)\b/i.test(line);
}

function stripInstructionNumber(line) {
  return line
    .replace(/^\d+\s*[\.)]\s*/, "")
    .replace(/^[-*•]+\s*/, "")
    .replace(/^\.\s*/, "")
    .trim();
}

function stripIngredientNoise(line) {
  return line
    .replace(/^ingredients:?\s*/i, "")
    .replace(/^salad ingredients:?\s*/i, "")
    .replace(/^dressing ingredients:?\s*/i, "")
    .replace(/^to top:?\s*/i, "Topping: ")
    .trim();
}

function isLikelyIngredient(line) {
  const l = line.trim();
  const n = normalize(l);
  if (!l || l.length < 2) return false;
  if (/^(instructions|method|how to|directions|macros|protein|carbs|fat|calories|save this|follow|comment|enjoy|method)$/i.test(l)) return false;
  if (isInstructionLine(l) && !/^\d+(?:[\s.,\/½¼¾⅓⅔⅛⅜⅝⅞]+)?\s*(g|kg|ml|l|dl|cup|cups|tbsp|tablespoons?|tsp|teaspoons?|oz|ounces?|can|cans)\b/i.test(l)) return false;
  const ingredientSignals = ["g ", "kg", "ml", "dl", "cup", "cups", "tbsp", "tablespoon", "tsp", "teaspoon", "oz", "ounce", "can ", "cans", "clove", "cloves", "onion", "garlic", "salt", "pepper", "oil", "pasta", "butter", "cream", "cheese", "mushroom", "carrot", "cucumber", "soy", "sauce", "lime", "lemon", "broth", "stock", "milk", "beans", "tofu", "noodles", "rice", "ginger", "chilli", "chili", "parsley", "coriander", "sesame"];
  return /^([\d¼½¾⅓⅔⅛⅜⅝⅞]|a\s|an\s|one\s|two\s|three\s|four\s|five\s|six\s|seven\s|eight\s|nine\s|ten\s|½|¼|¾)/i.test(l)
    || ingredientSignals.some(sig => n.includes(normalize(sig)))
    || /^topping:/i.test(l);
}

function cleanBullet(s) {
  return String(s || "")
    .replace(/^[-*•🌶️🍠🥜🔥📊\s]+/, "")
    .replace(/^\.\s*/, "")
    .trim();
}

function parseAmount(str) {
  if (!str) return null;
  const vulgar = {"¼":0.25,"½":0.5,"¾":0.75,"⅓":1/3,"⅔":2/3,"⅛":0.125,"⅜":0.375,"⅝":0.625,"⅞":0.875};
  let s = String(str).trim().replace(',', '.');
  if (vulgar[s] != null) return vulgar[s];
  for (const [ch,val] of Object.entries(vulgar)) {
    if (s.includes(ch)) {
      const whole = parseFloat(s.replace(ch, '').trim()) || 0;
      return whole + val;
    }
  }
  const mixed = s.match(/^(\d+)\s+(\d+)\/(\d+)$/);
  if (mixed) return Number(mixed[1]) + Number(mixed[2]) / Number(mixed[3]);
  const frac = s.match(/^(\d+)\/(\d+)$/);
  if (frac) return Number(frac[1]) / Number(frac[2]);
  const num = parseFloat(s);
  return Number.isFinite(num) ? num : null;
}

function amountPattern() {
  return "(\\d+(?:[.,]\\d+)?(?:\\s+\\d+\\/\\d+)?|\\d+\\/\\d+|[¼½¾⅓⅔⅛⅜⅝⅞])";
}

function convertIngredientLine(line) {
  let s = line.trim();
  const A = amountPattern();

  // US volume/weight units -> norske kjøkkenmål.
  s = s.replace(new RegExp(A + "\\s*(?:cups?)\\b", "gi"), (_, n) => `${fmtNum(parseAmount(n) * 2.4)} dl`);
  s = s.replace(new RegExp(A + "\\s*(?:tablespoons?|tbsp\\.?)\\b", "gi"), (_, n) => `${fmtNum(parseAmount(n))} ss`);
  s = s.replace(new RegExp(A + "\\s*(?:teaspoons?|tsp\\.?)\\b", "gi"), (_, n) => `${fmtNum(parseAmount(n))} ts`);
  s = s.replace(new RegExp(A + "\\s*(?:ounces?|oz)\\b", "gi"), (_, n) => `${Math.round(parseAmount(n) * 28.35)} g`);
  s = s.replace(new RegExp(A + "\\s*(?:pounds?|lbs?|lb)\\b", "gi"), (_, n) => `${fmtNum(parseAmount(n) * 0.454)} kg`);
  s = s.replace(new RegExp(A + "\\s*(?:inch|inches)\\b", "gi"), (_, n) => `${fmtNum(parseAmount(n) * 2.54)} cm`);

  // Common food words to make handlelisten easier in Norwegian.
  const replacements = [
    [/\bfettuccine\b/gi, "fettuccine"],
    [/\bdry pasta\b/gi, "tørr pasta"],
    [/\bpasta water\b/gi, "pastavann"],
    [/\bheavy cream\b/gi, "kremfløte"],
    [/\bgrated parmesan cheese\b/gi, "revet parmesan"],
    [/\bparmesan cheese\b/gi, "parmesan"],
    [/\bbutter\b/gi, "smør"],
    [/\bolive oil\b/gi, "olivenolje"],
    [/\bonion\b/gi, "løk"],
    [/\bwhite onion\b/gi, "gul løk"],
    [/\bgarlic\b/gi, "hvitløk"],
    [/\bcloves?\b/gi, "fedd"],
    [/\bmushrooms?\b/gi, "sopp"],
    [/\bsea salt\b/gi, "salt"],
    [/\bsalt and pepper\b/gi, "salt og pepper"],
    [/\bfreshly ground black pepper\b/gi, "nykvernet sort pepper"],
    [/\bblack pepper\b/gi, "sort pepper"],
    [/\bfresh parsley\b/gi, "fersk persille"],
    [/\bchopped\b/gi, "hakket"],
    [/\bminced\b/gi, "finhakket"],
    [/\bfinely chopped\b/gi, "finhakket"],
    [/\bsliced\b/gi, "skivet"],
    [/\bfor garnish\b/gi, "til topping"],
    [/\boptional\b/gi, "valgfritt"],
  ];
  for (const [re, repl] of replacements) s = s.replace(re, repl);

  // Clean spacing and odd punctuation from copied captions.
  s = s.replace(/\s+,/g, ",").replace(/\s{2,}/g, " ").trim();
  return s;
}

// Backwards-compatible alias used by old saved data/tests.
function convertToMetric(line) { return convertIngredientLine(line); }

function fmtNum(n) {
  if (!Number.isFinite(n)) return "";
  const rounded = Math.round(n * 10) / 10;
  return String(rounded).replace('.', ',');
}

async function saveParsedRecipe() {
  if (!activeImportId) {
    alert("Ingen oppskrift er valgt for lagring. Lukk og åpne importvinduet på nytt.");
    return;
  }

  const name = $("importName").value.trim() || "Ny oppskrift";
  const link = $("importLink")?.value?.trim() || "";
  const category = $("importCategory")?.value || "Annet";

  const patch = {
    name,
    link,
    category,
    source: link.includes("instagram") ? "Instagram" : link.includes("tiktok") ? "TikTok" : link ? "Nettside" : "Manuell",
    servings: $("importServings").value.trim(),
    ingredientsText: $("parsedIngredients").value.trim(),
    instructions: $("parsedInstructions").value.trim(),
    structuredIngredients: window.lastAiParsedRecipe?.ingredients || [],
    structuredInstructions: window.lastAiParsedRecipe?.instructions || [],
    aiParsed: !!window.lastAiParsedRecipe,
    aiConfidence: window.lastAiParsedRecipe?.confidence || "",
    status: "Fullført",
    manualCheck: "Nei"
  };

  const idx = recipes.findIndex(r => String(r.id) === String(activeImportId));
  if (idx >= 0) recipes[idx] = {...recipes[idx], ...patch};
  else recipes.push({id: activeImportId, ...patch});

  let savedPermanently = false;
  let saveError = "";
  try {
    const response = await fetch("/api/save-recipe", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({id: activeImportId, patch})
    });
    const saveResult = await response.json().catch(() => ({}));
    if (!response.ok || saveResult.ok === false) {
      throw new Error(saveResult.error || JSON.stringify(saveResult) || "Ukjent lagringsfeil");
    }
    savedPermanently = true;
  } catch (err) {
    saveError = err?.message || String(err);
    console.warn("Kunne ikke lagre til Supabase/server. Faller tilbake til localStorage.", err);
    customRecipes[activeImportId] = {...(customRecipes[activeImportId] || {}), ...patch};
    localStorage.setItem("middag_custom_recipes", JSON.stringify(customRecipes));
  }

  $("importDialog").close();
  createDayRows();
  renderRecipeResults();
  alert(savedPermanently
    ? "Oppskriften er lagret permanent i Supabase ✅"
    : "Oppskriften vises nå i denne nettleseren, men Supabase-lagring feilet. Feil: " + saveError);
}

function generateShoppingList() {
  const dayIds = selectedDays().map(d => plan[d]).filter(Boolean);
  const list = [];
  for (const id of dayIds) {
    const r = recipeById(id);
    if (!r || !hasRecipe(r)) continue;
    const lines = extractIngredientLines(r);
    for (const line of lines) list.push({ text: line, category: categorize(line), recipe: r.name });
  }
  shoppingItems = list;
  renderShoppingList(shoppingItems);
  showView("viewShopping");
}

function extractIngredientLines(r) {
  if (r.ingredientLines && r.ingredientLines.length) return r.ingredientLines.map(x => x.raw || x).filter(Boolean);
  const txt = r.ingredientsText || "";
  return txt.split(/;|\n/).map(s => s.trim()).filter(s => s.length > 1);
}

function categorize(line) {
  const s = normalize(line);
  const map = [
    ["Frukt og grønt", ["agurk","gulrot","løk","hvitløk","ingefær","potet","søtpotet","squash","zucchini","tomat","paprika","sopp","brokkoli","blomkål","kål","spinat","salat","lime","sitron","koriander","persille","selleri","avokado","aubergine","chili","vårløk","bønner grønne","green beans"]],
    ["Kjøtt", ["kylling","biff","okse","kjøttdeig","svin","kotelett","pølse","kalkun","bacon"]],
    ["Meieri", ["melk","fløte","rømme","ost","parmesan","feta","cottage cheese","yoghurt","yogurt","smør","butter"]],
    ["Frys", ["frossen","frosne","edamame"]],
    ["Hermetikk/halvfabrikat", ["boks","can ","canned","kokosmelk","kidney","kikerter","chickpeas","tomatpuré","diced tomatoes","bønner","beans"]],
    ["Tørrvarer", ["pasta","nudler","noodles","ris","orzo","bulgur","quinoa","peanøttsmør","peanut butter","olje","soy sauce","soyasaus","tamari","riseddik","vinegar","stock","kraft","broth"]],
    ["Krydder", ["salt","pepper","oregano","basilikum","basil","gochugaru","paprika","chili flakes","chiliflak","curry paste","currypaste","bay leaves","laurbær","sesame seeds","sesamfrø","sukker","sugar"]],
    ["Glutenfritt", ["glutenfri","gluten free"]],
    ["Bakevarer", ["brød","pita","tortilla","burgerbrød","wrap"]]
  ];
  for (const [cat, words] of map) if (words.some(w => s.includes(normalize(w)))) return cat;
  if (["tofu"].some(w => s.includes(w))) return "Kjølevarer";
  return "Annet";
}

function renderShoppingList(items) {
  const grouped = Object.fromEntries(CATEGORIES.map(c => [c, []]));
  for (const item of items) {
    if (!grouped[item.category]) grouped[item.category] = [];
    grouped[item.category].push(item);
  }

  const html = CATEGORIES.map(cat => {
    const arr = grouped[cat] || [];
    return `<div class="category" data-category="${escapeAttr(cat)}">
      <div class="category-head">
        <h3>${cat}</h3>
        <button class="tiny-add" onclick="addCustomShoppingItem('${escapeAttr(cat)}')">+ Legg til</button>
      </div>
      <div class="category-items">
        ${arr.length ? arr.map((it) => shoppingItemHtml(it)).join("") : `<p class="hint small-hint">Ingen varer enda.</p>`}
      </div>
    </div>`;
  }).join("");

  $("shoppingList").innerHTML = html;
}

function shoppingItemHtml(it) {
  return `<div class="item">
    <input type="checkbox" onchange="this.closest('.item').classList.toggle('done', this.checked)">
    <input type="text" value="${escapeAttr(it.text)}" title="Fra: ${escapeAttr(it.recipe || 'Egen vare')}">
    <button class="remove-btn" title="Fjern" onclick="this.closest('.item').remove()">×</button>
  </div>`;
}

function addCustomShoppingItem(category) {
  const text = prompt(`Legg til vare i ${category}:`);
  if (!text || !text.trim()) return;
  const section = [...document.querySelectorAll(".category")].find(el => el.dataset.category === category);
  const itemsBox = section?.querySelector(".category-items");
  if (!itemsBox) return;
  const empty = itemsBox.querySelector(".small-hint");
  if (empty) empty.remove();
  itemsBox.insertAdjacentHTML("beforeend", shoppingItemHtml({text: text.trim(), category, recipe: "Egen vare"}));
}

function renderRecipeResults() {
  const q = normalize($("recipeSearch").value);
  const filtered = recipes.filter(r => !q || normalize(`${r.name} ${r.category} ${r.source} ${r.status}`).includes(q)).slice(0, 80);
  $("recipeResults").innerHTML = filtered.map(r => `
    <div class="recipe-card">
      <div class="recipe-thumb">${r.imageUrl ? `<img src="${escapeAttr(r.imageUrl)}" alt="">` : "🍽️"}</div>
      <div>
        <strong>${escapeHtml(r.name)}</strong>
        <div class="recipe-meta">${escapeHtml(r.category || "Ukjent")} · ${hasRecipe(r) ? "✅ Oppskrift funnet" : "🟡 Mangler oppskrift"} · ${escapeHtml(r.source || "")}</div>
        <div class="recipe-meta recipe-actions">${r.link ? `<a href="${escapeAttr(r.link)}" target="_blank" rel="noopener">Åpne kilde</a>` : "Ingen lenke"} · <button class="link-button" onclick="openImport('${escapeAttr(r.id)}')">${hasRecipe(r) ? "Rediger" : "Importer"}</button></div>
      </div>
    </div>
  `).join("");
}

function escapeHtml(s) { return String(s ?? "").replace(/[&<>"]/g, m => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[m])); }
function escapeAttr(s) { return escapeHtml(s).replace(/'/g, "&#39;"); }

init();
