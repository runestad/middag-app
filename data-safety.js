(function (root) {
  "use strict";

  function isPlainObject(value) {
    return Boolean(value) && typeof value === "object" && !Array.isArray(value);
  }

  function hasMeaningfulDataValue(value) {
    if (value === null || value === undefined) return false;
    if (typeof value === "string") return value.trim().length > 0;
    if (Array.isArray(value)) return value.length > 0;
    if (isPlainObject(value)) return Object.keys(value).length > 0;
    return true;
  }

  function mergePreservingExistingData(existing, incoming) {
    const current = isPlainObject(existing) ? existing : {};
    const candidate = isPlainObject(incoming) ? incoming : {};
    const merged = {...current};

    for (const [key, value] of Object.entries(candidate)) {
      if (!hasMeaningfulDataValue(value)) continue;
      if (isPlainObject(value) && isPlainObject(current[key])) {
        merged[key] = mergePreservingExistingData(current[key], value);
      } else {
        merged[key] = value;
      }
    }
    return merged;
  }

  function meaningfulPatch(incoming) {
    if (!isPlainObject(incoming)) return {};
    const patch = {};
    for (const [key, value] of Object.entries(incoming)) {
      if (!hasMeaningfulDataValue(value)) continue;
      if (isPlainObject(value)) {
        const nested = meaningfulPatch(value);
        if (Object.keys(nested).length) patch[key] = nested;
      } else {
        patch[key] = value;
      }
    }
    return patch;
  }

  function firstMeaningfulValue(values) {
    return values.find(hasMeaningfulDataValue);
  }

  function resolveRecipeSourceUrl(recipe) {
    const row = isPlainObject(recipe) ? recipe : {};
    const data = isPlainObject(row.data) ? row.data : {};
    const value = firstMeaningfulValue([
      row.link, row.sourceUrl, row.sourceURL, row.source_url, row.sourceLink, row.source_link,
      data.link, data.sourceUrl, data.sourceURL, data.source_url, data.sourceLink, data.source_link,
    ]);
    return typeof value === "string" ? value.trim() : "";
  }

  function sourceTypeFromUrl(url) {
    const value = String(url || "").trim().toLowerCase();
    if (!value) return "";
    if (value.includes("instagram.com")) return "Instagram";
    if (value.includes("tiktok.com")) return "TikTok";
    return /^https?:\/\//.test(value) ? "Nettside" : "";
  }

  function cloneRecipeForRecovery(recipe) {
    if (!isPlainObject(recipe)) return {};
    if (typeof structuredClone === "function") return structuredClone(recipe);
    return JSON.parse(JSON.stringify(recipe));
  }

  function selectImportResolvedUrl(originalUrl, candidateUrl) {
    const original = String(originalUrl || "").trim();
    const candidate = String(candidateUrl || "").trim();
    if (!candidate) return original;
    let originalParsed;
    let candidateParsed;
    try {
      originalParsed = new URL(original);
      candidateParsed = new URL(candidate);
    } catch (_) {
      return original;
    }
    if (!["http:", "https:"].includes(candidateParsed.protocol)) return original;

    const originalType = sourceTypeFromUrl(original);
    const candidateType = sourceTypeFromUrl(candidate);
    if (originalType === "TikTok") {
      const path = candidateParsed.pathname.replace(/\/+$/, "");
      if (candidateType !== "TikTok" || !path || path === "/") return original;
    }
    if (originalType === "Instagram") {
      const path = candidateParsed.pathname.toLowerCase();
      if (candidateType !== "Instagram" || !/^\/(reel|reels|p)\//.test(path)) return original;
    }
    return candidate;
  }

  function prepareRecoverySource(recipe) {
    const recoveryRecipe = cloneRecipeForRecovery(recipe);
    const sourceUrl = resolveRecipeSourceUrl(recoveryRecipe);
    return {
      recipe: recoveryRecipe,
      sourceUrl,
      sourceType: sourceTypeFromUrl(sourceUrl),
    };
  }

  const api = {
    hasMeaningfulDataValue,
    mergePreservingExistingData,
    meaningfulPatch,
    resolveRecipeSourceUrl,
    sourceTypeFromUrl,
    cloneRecipeForRecovery,
    selectImportResolvedUrl,
    prepareRecoverySource,
  };
  Object.assign(root, api);
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof globalThis !== "undefined" ? globalThis : window);
