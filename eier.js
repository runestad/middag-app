(() => {
  const input = document.getElementById("ownerLink");
  const status = document.getElementById("ownerStatus");
  const form = document.getElementById("ownerForm");
  const keyFrom = text => new URLSearchParams(text.includes("#") ? text.split("#").pop() : text).get("eier");
  async function activate(key) {
    if (!/^[a-f0-9]{64}$/.test(key || "")) {
      status.textContent = "Lim inn hele den private eierlenken.";
      return;
    }
    status.textContent = "Åpner appen …";
    form.querySelector("button").disabled = true;
    try {
      const response = await fetch("/api/health", {method: "POST", headers: {"Content-Type":"application/json"},
        body: JSON.stringify({ownerKey: key}), cache:"no-store"});
      if (!response.ok) throw new Error(response.status === 401 ? "Eierlenken er ugyldig." : "Prøv igjen om litt.");
      input.value = "";
      location.replace("/");
    } catch (error) { status.textContent = error.message; }
    finally { form.querySelector("button").disabled = false; }
  }
  form.onsubmit = event => { event.preventDefault(); activate(keyFrom(input.value.trim())); };
  function openLink() {
    const key = keyFrom(location.hash);
    if (location.hash) history.replaceState(null, "", location.pathname);
    if (key) activate(key);
  }
  window.addEventListener("hashchange", openLink);
  openLink();
})();
