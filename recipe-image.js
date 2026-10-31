(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  if (root) root.RecipeImage = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  const MAX_BYTES = 750000;
  async function decode(file) {
    if (typeof createImageBitmap === "function") {
      try { return await createImageBitmap(file, {imageOrientation: "from-image"}); } catch (_) { /* Safari can decode more formats through Image. */ }
    }
    const url = URL.createObjectURL(file), image = new Image();
    try {
      await new Promise((resolve, reject) => {
        image.onload = resolve;
        image.onerror = () => reject(new Error("Bildet kunne ikke leses. Prøv JPEG, PNG eller et skjermbilde."));
        image.src = url;
      });
      return image;
    } finally { URL.revokeObjectURL(url); }
  }
  function encode(canvas, type, quality) {
    return new Promise((resolve, reject) => {
      try { canvas.toBlob(resolve, type, quality); } catch (error) { reject(error); }
    });
  }
  async function prepare(file) {
    if (!file || !String(file.type).startsWith("image/")) throw new Error("Velg en gyldig bildefil.");
    if (file.size > 50 * 1024 * 1024) throw new Error("Originalbildet kan ikke være større enn 50 MB.");
    const image = await decode(file), canvas = document.createElement("canvas");
    try {
      const width = image.naturalWidth || image.width, height = image.naturalHeight || image.height;
      if (!(width > 0 && height > 0)) throw new Error("Bildet er tomt eller skadet.");
      let webpSupported = true;
      for (const maxEdge of [1600, 1280, 1024, 800, 640]) {
        const scale = Math.min(1, maxEdge / Math.max(width, height));
        canvas.width = Math.max(1, Math.round(width * scale));
        canvas.height = Math.max(1, Math.round(height * scale));
        const ctx = canvas.getContext("2d");
        if (!ctx) throw new Error("Nettleseren kunne ikke behandle bildet.");
        ctx.fillStyle = "#fff";
        ctx.fillRect(0, 0, canvas.width, canvas.height);
        ctx.drawImage(image, 0, 0, canvas.width, canvas.height);
        for (const quality of [.84, .72, .6]) {
          if (webpSupported) {
            const blob = await encode(canvas, "image/webp", quality);
            // Safari may return a large PNG instead of the requested WebP.
            webpSupported = blob?.type === "image/webp";
            if (webpSupported && blob.size > 0 && blob.size <= MAX_BYTES) return blob;
          }
          const jpeg = await encode(canvas, "image/jpeg", quality);
          if (jpeg?.type === "image/jpeg" && jpeg.size > 0 && jpeg.size <= MAX_BYTES) return jpeg;
        }
      }
      throw new Error("Bildet kunne ikke tilpasses. Prøv et skjermbilde av bildet.");
    } finally {
      image.close?.();
      canvas.width = canvas.height = 1;
    }
  }
  return {prepare, MAX_BYTES};
});
