(function (root, factory) {
  const model = factory();
  if (typeof module === "object" && module.exports) module.exports = model;
  root.ShoppingListModel = model;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  const EPOCH = "2000-01-01T00:00:00.000Z";

  function normalizedName(value) {
    return String(value || "").trim().toLocaleLowerCase("nb-NO").replace(/\s+/g, " ");
  }

  function itemTime(item) {
    return Date.parse(item?.updatedAt || EPOCH) || 0;
  }

  function withMetadata(items, {idFactory, categorize} = {}) {
    const makeId = idFactory || ((index, item) => `shop-legacy-${index}-${normalizedName(item?.text)}`);
    const categoryFor = categorize || (() => "Annet");
    return (Array.isArray(items) ? items : []).map((item, index) => ({
      ...item,
      id: item?.id || makeId(index, item),
      text: String(item?.text || "").trim(),
      category: item?.category || categoryFor(item?.text || ""),
      done: Boolean(item?.done),
      deleted: Boolean(item?.deleted),
      updatedAt: item?.updatedAt || EPOCH
    }));
  }

  function mergeStates(localItems, remoteItems, options) {
    const merged = new Map();
    for (const item of [...withMetadata(remoteItems, options), ...withMetadata(localItems, options)]) {
      const current = merged.get(item.id);
      if (!current || itemTime(item) >= itemTime(current)) merged.set(item.id, item);
    }
    return [...merged.values()];
  }

  function duplicateKey(item) {
    return `${normalizedName(item?.text)}|${normalizedName(item?.category)}`;
  }

  function mergeWeekMenuItems(existingItems, generatedItems, options) {
    const existing = withMetadata(existingItems, options);
    const visibleKeys = new Set(existing.filter(item => !item.deleted).map(duplicateKey));
    const additions = [];
    for (const candidate of withMetadata(generatedItems, options)) {
      const key = duplicateKey(candidate);
      if (!candidate.text || visibleKeys.has(key)) continue;
      visibleKeys.add(key);
      additions.push(candidate);
    }
    return [...existing, ...additions];
  }

  return {EPOCH, normalizedName, itemTime, withMetadata, mergeStates, mergeWeekMenuItems};
});
