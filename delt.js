(() => {
  const byId = id => document.getElementById(id);
  const initialHash = location.hash;
  const fragment = new URLSearchParams(initialHash.slice(1));
  const scope = fragment.get("scope"), proof = fragment.get("key"), singleId = fragment.get("id");
  const book = scope === "book";
  const detail = byId("detail"), browse = byId("browse"), title = byId("title"), status = byId("status");
  const search = byId("search"), categories = byId("category"), sort = byId("sort");
  const compare = new Intl.Collator("nb", {sensitivity: "base", numeric: true}).compare;
  let library = null, version = 0;

  function element(tag, text, className) {
    const node = document.createElement(tag);
    if (text != null) node.textContent = text;
    if (className) node.className = className;
    return node;
  }

  async function read(id) {
    const query = new URLSearchParams({shared: scope});
    if (id) query.set("id", id);
    const response = await fetch("/api/recipes?" + query, {
      headers: {"X-Sult-Share": proof}, credentials: "omit", cache: "no-store", referrerPolicy: "no-referrer"
    });
    if (!response.ok) {
      if (response.status === 403) throw new Error("Delingslenken er ugyldig. Be om en ny lenke.");
      if (response.status === 404) throw new Error("Oppskriften finnes ikke lenger.");
      throw new Error("Kunne ikke hente oppskriftene. Prøv å laste siden på nytt.");
    }
    return response.json();
  }

  function photo(recipe, hero = false) {
    const img = element("img", null, hero ? "shared-hero" : "");
    img.alt = ""; img.loading = hero ? "eager" : "lazy"; img.referrerPolicy = "no-referrer";
    const urls = [...recipe.images];
    if (!hero) urls.push("/assets/sult-symbol-sage.svg");
    function next() {
      if (urls.length) img.src = urls.shift();
      else img.hidden = true;
    }
    img.onerror = next;
    next();
    return img;
  }

  function showList() {
    const query = search.value.toLocaleLowerCase("nb").trim();
    const matches = library.filter(r => (!categories.value || categories.value === r.category) &&
      [r.name, r.category, r.source, ...r.tags].join(" ").toLocaleLowerCase("nb").includes(query));
    matches.sort((a, b) => (sort.value === "category" && compare(a.category, b.category)) || compare(a.name, b.name));
    byId("count").textContent = matches.length === 1 ? "1 oppskrift" : matches.length + " oppskrifter";
    const results = byId("results");
    results.replaceChildren();
    for (const r of matches) {
      const button = element("button", null, "shared-item");
      button.type = "button";
      const info = element("span");
      info.append(element("strong", r.name), element("small", r.category));
      button.append(photo(r), info);
      button.onclick = () => {
        const next = new URL(location.href);
        next.searchParams.set("rett", r.id);
        history.pushState({fromList:true}, "", next);
        render();
        window.scrollTo(0, 0);
      };
      results.append(button);
    }
    if (!matches.length) results.append(element("p", "Ingen oppskrifter passer søket."));
  }

  function addList(label, tag, lines, empty) {
    const section = element("section"), list = element(tag);
    section.append(element("h2", label));
    for (const line of lines) {
      const text = tag === "ol" ? line.replace(/^\s*\d+[.)]\s*/, "") : line.replace(/\s*\[[^\]]+\]\s*$/, "");
      list.append(element("li", text));
    }
    section.append(lines.length ? list : element("p", empty, "hint"));
    detail.append(section);
  }

  function sourceLink(url, label) {
    const link = element("a", label, "source-link-inline");
    link.href = url; link.target = "_blank"; link.rel = "noopener noreferrer";
    return link;
  }

  function showVideo(recipe) {
    const candidates = [recipe.videoUrl, recipe.videoSource, recipe.link].filter(Boolean);
    const embed = candidates.map(recipeVideoEmbed).find(Boolean);
    const file = candidates.find(url => /\.(mp4|webm|mov|m3u8)(?:[?#]|$)/i.test(url));
    const providerLink = candidates.find(url => /(^|\.)(tiktok\.com|instagram\.com|youtube\.com|youtu\.be)$/.test(new URL(url).hostname));
    if (!embed && !file && !providerLink && !recipe.videoUrl) return;
    const section = element("section");
    if (embed || file) {
      const button = element("button", "▶ Se video", "primary");
      button.type = "button";
      button.onclick = () => {
        const media = element(embed ? "iframe" : "video");
        if (embed) {
          media.title = "Video til " + recipe.name;
          media.className = embed.portrait ? "portrait" : "landscape";
          media.allowFullscreen = true; media.allow = "fullscreen; encrypted-media; picture-in-picture";
          media.referrerPolicy = "strict-origin-when-cross-origin";
          media.src = embed.url;
        } else {media.controls = true; media.playsInline = true; media.src = file;}
        button.replaceWith(media);
      };
      section.append(button);
    } else section.append(sourceLink(providerLink || recipe.videoUrl, "Se video hos kilden ↗"));
    detail.append(section);
  }

  function showRecipe(r) {
    title.textContent = r.name;
    document.title = r.name + " · SULT";
    detail.hidden = false;
    if (r.images.length) {
      detail.append(photo(r, true));
      if (r.imageIsIllustration) detail.append(element("p", "Illustrasjonsbilde", "hint"));
    }
    const serving = String(r.servings || "");
    const portion = /^\d+([.,]\d+)?$/.test(serving) ? serving + (serving === "1" ? " porsjon" : " porsjoner") : serving;
    detail.append(element("p", [r.category, portion].filter(Boolean).join(" · "), "recipe-meta"));
    if (r.link) detail.append(sourceLink(r.link, "Åpne kilde ↗"));
    showVideo(r);
    addList("Ingredienser", "ul", r.ingredients, "Ingredienser er ikke oppgitt.");
    addList("Fremgangsmåte", "ol", r.steps, "Fremgangsmåte er ikke oppgitt.");
  }

  async function render() {
    const generation = ++version;
    const id = book ? new URLSearchParams(location.search).get("rett") : singleId;
    byId("back").hidden = !book || !id;
    browse.hidden = detail.hidden = true;
    detail.replaceChildren();
    title.textContent = book && !id ? "Oppskriftslisten" : "Delt oppskrift";
    document.title = title.textContent + " · SULT";
    status.textContent = "Henter …";
    try {
      if ((!book && (scope !== "recipe" || !id)) || !/^[a-f0-9]{64}$/.test(proof || ""))
        throw new Error("Delingslenken er ufullstendig. Be om hele lenken.");
      if (id) {
        const data = await read(id);
        if (generation !== version) return;
        showRecipe(data.recipe);
      } else {
        if (!library) {
          const data = await read();
          if (generation !== version) return;
          library = data.recipes;
          for (const c of [...new Set(library.map(r => r.category).filter(Boolean))].sort(compare))
            categories.add(new Option(c, c));
        }
        browse.hidden = false;
        showList();
      }
      status.textContent = "";
    } catch (error) {if (generation === version) status.textContent = error.message;}
  }
  search.oninput = categories.onchange = sort.onchange = showList;
  byId("back").onclick = () => {
    if (history.state?.fromList) history.back();
    else {const url = new URL(location.href); url.searchParams.delete("rett"); history.replaceState(null, "", url); render();}
  };
  function navigate() {
    // A different share link can open in the same tab without loading a new document.
    if (location.hash !== initialHash) location.reload();
    else render();
  }
  window.addEventListener("hashchange", navigate);
  window.addEventListener("popstate", navigate);
  render();
})();
