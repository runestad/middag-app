/* A practical store route, not an exact plan of every REMA store. */
(function(root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.ShoppingOrder = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function() {
  const sections = {
    'Frukt og grønt': [
      ['Frukt', /banan|epl(?:e|er)|pære|appelsin|klementin|mandarin|sitron|lime|mango|ananas|melon|kiwi|druer|fersken|nektarin|plomme|granateple|pasjonsfrukt/],
      ['Grønnsaker · uten kjøling', /avokado|tomat|agurk|paprika|chili|potet|søtpotet|hvitløk|rødløk|sjalottløk|gul løk|\bløk\b|ingefær|gresskar|aubergine|squash/],
      ['Grønnsaker · kjøl', /salat|spinat|ruccola|brokkoli|blomkål|kål|gulrot|purre|vårløk|asparges|sopp|sjampinjong|selleri|reddik|sukkerert|bønne|rødbet|pastinakk|spirer/],
      ['Bær og friske urter', /bær|basilikum|persille|koriander|dill|gressløk|mynte|timian|rosmarin/]
    ],
    'Kjøtt og fisk': [['Kylling og kalkun', /kylling|kalkun/], ['Kjøtt', /kjøtt|biff|storfe|svin|lam|bacon|pølse|karbonade/], ['Fisk og sjømat', /fisk|laks|ørret|torsk|sei\b|reker|scampi|skalldyr|tunfisk/]],
    'Meieri': [['Melk og fløte', /melk|fløte/], ['Yoghurt og syrnet meieri', /yoghurt|yogurt|skyr|kesam|rømme|creme fraiche|crème fraîche|kefir/], ['Ost', /ost|mozzarella|feta|parmesan|cheddar/], ['Smør og egg', /smør|margarin|egg/]],
    'Kjølevarer': [['Pålegg', /skinke|salami|pålegg|leverpostei/], ['Fersk pasta og ferdigmat', /pasta|tortellini|ravioli|fersk|ferdig/], ['Dipper og planteprodukter', /hummus|tofu|dipp|pesto/]],
    'Hermetikk/halvfabrikat': [['Grønnsaker og belgvekster', /tomat|mais|bønne|kikert|linse|ert/], ['Fisk på boks', /tunfisk|makrell|sardin/], ['Sauser og supper', /saus|suppe|kraft|buljong|kokosmelk/]],
    'Tørrvarer': [['Ris, pasta og nudler', /ris\b|pasta|spaghetti|nudl|orzo|couscous|quinoa|bulgur/], ['Mel og baking', /mel\b|sukker|bake|gjær|kakao|vanilje/], ['Frokost og gryn', /havre|gryn|müsli|musli|granola|knekkebrød/], ['Nøtter, frø og tørket frukt', /nøtt|mandel|frø|rosin|daddel/], ['Olje, eddik og sauser', /olje|eddik|saus|soya|sennep|ketchup/]],
    'Frysevarer': [['Grønnsaker og bær', /grønnsak|brokkoli|spinat|ert|bær|frukt|blanding/], ['Fisk og kjøtt', /fisk|laks|torsk|kylling|kjøtt|scampi/], ['Ferdigretter og tilbehør', /pizza|pommes|rett|potet/], ['Is og dessert', /iskrem|is\b|sorbet|dessert/]],
    'Drikke': [['Vann og brus', /vann|brus|cola|pepsi|fanta/], ['Juice og saft', /juice|saft/], ['Kaffe og te', /kaffe|\bte\b/]]
  };
  function name(item) {
    const text = String(item.text || '').toLocaleLowerCase('nb-NO');
    return text.replace(/\([^)]*\)|\[[^\]]*\]/g, '').replace(/^[\d\s.,/¼½¾–-]+(?:kg|g|dl|ml|l|ss|ts|stk|pk|boks|fedd)?\s*/, '').trim();
  }
  function section(item, category) {
    const rules = sections[category] || [];
    const index = rules.findIndex(([, pattern]) => pattern.test(name(item)));
    return {rank: index < 0 ? rules.length : index, label: index < 0 ? 'Øvrige varer' : rules[index][0]};
  }
  function group(items, category) {
    const sorted = [...items].sort((a,b) => section(a,category).rank-section(b,category).rank || name(a).localeCompare(name(b),'nb') || String(a.id).localeCompare(String(b.id)));
    const groups = [];
    for (const item of sorted) {
      const key = section(item,category);
      if (!groups.length || groups[groups.length-1].rank !== key.rank) groups.push({...key, items:[]});
      groups[groups.length-1].items.push(item);
    }
    return groups;
  }
  return {group, section};
});
