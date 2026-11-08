(() => {
  const get = id => document.getElementById(id);
  const dialog = get("shareDialog");
  const input = get("shareUrl");
  const status = get("shareStatus");
  const copy = get("shareCopy");
  const native = get("shareNative");
  const openDetails = window.openRecipeDetails;
  let recipeId, requestNumber = 0;
  window.openRecipeDetails = function (id) {
    recipeId = id;
    return openDetails(id);
  };

  async function openShare(single) {
    const request = ++requestNumber;
    const title = single ? recipeById(recipeId)?.name : "SULT – Oppskriftslisten";
    get("shareTitle").textContent = single ? "Del oppskrift" : "Del oppskriftslisten";
    get("shareScope").textContent = single
      ? 'Alle med lenken kan lese «' + title + '».'
      : "Alle med lenken kan lese hele oppskriftslisten, også oppskrifter dere legger til senere.";
    input.value = "";
    status.textContent = "Henter lenken …";
    copy.disabled = native.disabled = true;
    native.hidden = typeof navigator.share !== "function";
    dialog.showModal();
    const params = new URLSearchParams({shareLink: single ? "recipe" : "book"});
    if (single) params.set("id", recipeId);
    try {
      const response = await fetch("/api/recipes?" + params, {cache: "no-store"});
      const data = await response.json();
      if (!response.ok || !data.path) throw new Error(data.error || "Prøv igjen.");
      if (request !== requestNumber) return;
      input.value = new URL(data.path, location.origin).href;
      status.textContent = "";
      copy.disabled = native.disabled = false;
      native.onclick = async () => {
        try { await navigator.share({title, url: input.value}); }
        catch (error) { if (error.name !== "AbortError") status.textContent = "Bruk «Kopier lenke» for å dele."; }
      };
    } catch (error) {
      if (request === requestNumber) status.textContent = "Kunne ikke lage delingslenken. " + error.message;
    }
  }

  copy.onclick = async () => {
    try {
      await navigator.clipboard.writeText(input.value);
      status.textContent = "Lenken er kopiert.";
    } catch {
      input.focus();
      input.select();
      status.textContent = "Lenken er markert. Velg Kopier.";
    }
  };
  get("shareBook").onclick = () => openShare(false);
  get("shareRecipe").onclick = () => openShare(true);
  get("shareClose").onclick = () => dialog.close();
})();
