(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  if (root) root.ServingScaling = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  const UNSTRUCTURED = [
    "etter smak", "en neve", "litt", "til servering", "valgfritt",
    "passe mengde", "så mye du ønsker", "ved behov"
  ];
  const FRACTIONS = {
    "½": 1 / 2, "⅓": 1 / 3, "⅔": 2 / 3, "¼": 1 / 4, "¾": 3 / 4,
    "⅛": 1 / 8, "⅜": 3 / 8, "⅝": 5 / 8, "⅞": 7 / 8
  };

  function parsePositiveServings(value) {
    const number = Number(String(value ?? "").trim().replace(",", "."));
    return Number.isFinite(number) && number > 0 ? number : null;
  }

  function recipeBaseServings(recipe) {
    return parsePositiveServings(recipe?.baseServings) ??
      parsePositiveServings(recipe?.servings);
  }

  function scaleFactorFor(recipe, selectedServings) {
    const base = recipeBaseServings(recipe);
    const selected = parsePositiveServings(selectedServings);
    return base && selected ? selected / base : null;
  }

  function parseAmountToken(value) {
    const text = String(value ?? "").trim().replace(",", ".");
    if (!text) return null;
    if (FRACTIONS[text] != null) return FRACTIONS[text];
    const mixed = text.match(/^(\d+)\s+(\d+)\/(\d+)$/);
    if (mixed && Number(mixed[3])) {
      return Number(mixed[1]) + Number(mixed[2]) / Number(mixed[3]);
    }
    const fraction = text.match(/^(\d+)\/(\d+)$/);
    if (fraction && Number(fraction[2])) return Number(fraction[1]) / Number(fraction[2]);
    const number = Number(text);
    return Number.isFinite(number) ? number : null;
  }

  function formatScaledAmount(value) {
    if (!Number.isFinite(value)) return "";
    const rounded = Math.round(value * 100) / 100;
    if (Math.abs(rounded - Math.round(rounded)) < 0.001) return String(Math.round(rounded));
    const common = [
      [0.125, "⅛"], [0.25, "¼"], [1 / 3, "⅓"], [0.375, "⅜"],
      [0.5, "½"], [0.625, "⅝"], [2 / 3, "⅔"], [0.75, "¾"], [0.875, "⅞"]
    ];
    if (rounded > 0 && rounded < 1) {
      const match = common.find(([number]) => Math.abs(rounded - number) < 0.015);
      if (match) return match[1];
    }
    return String(rounded).replace(".", ",");
  }

  function isUnstructuredAmount(value) {
    const normalized = String(value ?? "").trim().toLowerCase();
    return !normalized || UNSTRUCTURED.some(term => normalized.includes(term));
  }

  function scaleAmountText(value, factor) {
    const original = String(value ?? "").trim();
    if (!Number.isFinite(factor) || factor <= 0 || isUnstructuredAmount(original)) return original;
    const range = original.match(/^(.+?)\s*([–—-])\s*(.+)$/);
    if (range) {
      const low = parseAmountToken(range[1]);
      const high = parseAmountToken(range[3]);
      if (low != null && high != null) {
        return `${formatScaledAmount(low * factor)}–${formatScaledAmount(high * factor)}`;
      }
    }
    const amount = parseAmountToken(original);
    return amount == null ? original : formatScaledAmount(amount * factor);
  }

  function scaleStructuredIngredient(ingredient, factor) {
    const clone = ingredient && typeof ingredient === "object" ? { ...ingredient } : ingredient;
    if (!clone || typeof clone !== "object") return clone;
    clone.amount = scaleAmountText(clone.amount, factor);
    return clone;
  }

  function scaledStructuredIngredients(recipe, selectedServings) {
    const source = Array.isArray(recipe?.structuredIngredients) ? recipe.structuredIngredients : [];
    const factor = scaleFactorFor(recipe, selectedServings);
    return source.map(item => scaleStructuredIngredient(item, factor ?? 1));
  }

  function makePlannedRecipeItem(recipe, selectedServings) {
    const item = { type: "recipe", recipeId: recipe?.id };
    const base = recipeBaseServings(recipe);
    const selected = parsePositiveServings(selectedServings) ?? base;
    if (!base || !selected) return item;
    item.plannedServings = selected;
    item.baseServings = base;
    item.scaleFactor = selected / base;
    return item;
  }

  return {
    parsePositiveServings,
    recipeBaseServings,
    scaleFactorFor,
    parseAmountToken,
    formatScaledAmount,
    isUnstructuredAmount,
    scaleAmountText,
    scaleStructuredIngredient,
    scaledStructuredIngredients,
    makePlannedRecipeItem
  };
});
