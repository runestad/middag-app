/* Quantity parsing shared by display, scaling and shopping-list merging. */
(function(root,factory){const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;root.ShoppingIngredients=api;})(globalThis,function(){
  const fractions={'½':.5,'¼':.25,'¾':.75,'⅓':1/3,'⅔':2/3,'⅛':.125,'⅜':.375,'⅝':.625,'⅞':.875};
  const numberSource='(?:\\d+\\s+\\d+\\/\\d+|\\d+\\/\\d+|\\d*['+Object.keys(fractions).join('')+']|\\d+(?:[.,]\\d+)?)';
  const start=new RegExp('^('+numberSource+')(?![\\d/.,])\\s*(.*)$');
  const units={cups:'cup',cup:'cup',tbsp:'ss',tablespoon:'ss',tablespoons:'ss',tsp:'ts',teaspoon:'ts',teaspoons:'ts',oz:'oz',ounce:'oz',ounces:'oz',lb:'lb',lbs:'lb',pound:'lb',pounds:'lb',kg:'kg',g:'g',gram:'g',grams:'g',ml:'ml',dl:'dl',l:'l',liter:'l',litre:'l',ss:'ss',ts:'ts',stk:'stk',pk:'pk',pakke:'pakke',pakker:'pakke',pose:'pose',poser:'pose',boks:'boks',bokser:'boks',fedd:'fedd',clove:'fedd',cloves:'fedd',stilk:'stilk',stilker:'stilk',bunt:'bunt',bunter:'bunt',potte:'potte',potter:'potte',skive:'skive',skiver:'skive',klype:'klype',klyper:'klype',håndfull:'håndfull',neve:'neve',hode:'hode',hoder:'hode',pint:'pint',pints:'pint',kvist:'kvist',kvister:'kvist',dash:'klype',handful:'håndfull',handfuls:'håndfull',håndfuller:'håndfull'};
  const unitPattern=new RegExp('^('+Object.keys(units).sort((a,b)=>b.length-a.length).join('|')+')(?=\\s|$)\\s*','i');
  function number(token){
    if(/[½¼¾⅓⅔⅛⅜⅝⅞]$/.test(token))return Number(token.slice(0,-1)||0)+fractions[token.slice(-1)];
    const parts=token.split(/\s+/),fraction=parts.at(-1).split('/');
    if(fraction.length===2)return Number(fraction[1])?Number(parts.length>1?parts[0]:0)+Number(fraction[0])/Number(fraction[1]):null;
    const n=Number(token.replace(',','.'));return Number.isFinite(n)?n:null;
  }
  function clean(text){return String(text??'').replace(/^\s*(?:null|undefined|nan)\s+/i,'').replace(/\s*\[[^\]]+\]\s*$/,'').trim();}
  function parse(text){
    const original=clean(text),m=original.match(start);
    if(!m||/^\s*[-–—/]/.test(m[2]))return {amount:null,unit:'',name:original,original};
    const amount=number(m[1]),rest=m[2],unitMatch=rest.match(unitPattern);
    // Require a boundary after the number unless it is followed by a known unit (500g).
    if(!unitMatch&&!new RegExp('^'+numberSource+'\\s+').test(original))return {amount:null,unit:'',name:original,original};
    const name=(unitMatch?rest.slice(unitMatch[0].length):rest).trim();
    if(amount==null||!name)return {amount:null,unit:'',name:original,original};
    return {amount,unit:unitMatch?units[unitMatch[1].toLowerCase()]:'',name,original};
  }
  function fmt(n){return String(Math.round(n*1000)/1000).replace('.',',');}
  function convert(text){
    const p=parse(text);if(p.amount==null)return p.original;
    const conversion={cup:[2.4,'dl'],oz:[28.35,'g'],lb:[453.592,'g']};
    if(conversion[p.unit]){const [factor,unit]=conversion[p.unit];p.amount*=factor;p.unit=unit;}
    return [fmt(p.amount),p.unit,p.name].filter(Boolean).join(' ');
  }
  function scale(text,factor){const p=parse(text);return p.amount==null||!Number.isFinite(factor)||factor===1?clean(text):[fmt(p.amount*factor),p.unit,p.name].filter(Boolean).join(' ');}
  function heading(text){return /:\s*$/.test(text)||/^(?:for the|til)\s+(?:sauce|dressing|slaw|saus|marinade)\s*:?$/i.test(text);}
  function categoryName(value){return ({'Kjøtt':'Kjøtt og fisk','Frys':'Frysevarer'})[value]||value;}
  function category(text){
    const name=parse(text).name.toLowerCase();
    const qualifiers=[...name.matchAll(/\((fersk|frisk|fresh|malt|ground|tørket|tørkede|dried|frossen|frosne)\)/g)].map(match=>match[1]);
    const s=(qualifiers.join(' ')+' '+name.replace(/\([^)]*\)/g,'')).trim();
    // Prepared products must precede their vegetable/meat components.
    if(/glutenfri|gluten.free/.test(s))return 'Glutenfritt';
    if(/proteinpulver|protein powder/.test(s))return 'Tørrvarer';
    if(/bakepulver|baking powder|kakaopulver|cocoa powder/.test(s))return 'Bakevarer';
    if(/olje|\boil\b|oljespray|\beddik\b|vinegar|soyasaus|soy sauce|tamari|fiskesaus|fish sauce|hoisin|worcestershire|worcestersaus|sriracha|currypast[ae]|curry paste|hvitløkspasta|garlic paste|peanøttsmør|peanut butter|mandelsmør|sennep|mustard|dijon|miso|gochujang|tahini|pesto|østerssaus|oyster sauce|teriyaki|ketchup|kecap|mirin|hot sauce|bbq.saus|majones|mayonnaise/.test(s))return 'Tørrvarer';
    if(/kraft|buljong|\bstock\b|\bbroth\b|kokosmelk|coconut milk|kokoskrem|hakkede tomater|tomatpur[eé]|tomato paste|passata|salsa|artisjokk|soltørk|sun.?dried tomat/.test(s))return 'Hermetikk/halvfabrikat';
    if(/(?:havre|soya|mandel|ris)melk|(?:vegan|vegansk|plantebasert).*?(?:yoghurt|yogurt|ost|cheese)/.test(s))return 'Kjølevarer';
    if(/\b(?:tofu|tempeh)\b/.test(s))return 'Kjølevarer';
    if(!/frossen|frosne|frozen|fryste|hermetisk|canned|tørket|dried/.test(s)&&/sukkererter|sugar snap peas|grønne bønner|green beans|aspargesbønner|maiskolber|(?:thai|thailandsk) basilikum/.test(s))return 'Frukt og grønt';
    if(/(?:fersk|frisk|fresh|potte|bunt|kvist|håndfull|blad).*?(?:basil|timian|thyme|koriander|coriander|persille|parsley|rosmarin|rosemary|dill|mynte|mint)/.test(qualifiers.join(' ')+' '+clean(text).toLowerCase().replace(/\([^)]*\)/g,'')))return 'Frukt og grønt';
    if(/\b(?:malt|ground)\s+(?:koriander|coriander|ingefær|ginger|kanel|cinnamon|spisskummen|cumin)|(?:tørke[td]e?|dried)\s+(?:urter|herbs|basil|oregano|timian|thyme|rosmarin|rosemary|dill|persille|parsley|ingefær|ginger)|(?:koriander|løk|hvitløk|ingefær|chili|paprika|mango)\s*pulver|paprikapulver|chilipulver|hvitløkspulver|løkpulver|ingefærpulver|chili powder|garlic powder|onion powder|smoked paprika|røkt paprika|chili flakes|chiliflak|korianderfrø|coriander seeds|knuste røde pepperflak|røde? pepperflak|red pepper flakes|spisskummen|cumin|gurkemeie|turmeric|gochugaru|krydder|seasoning|masala|muskatnøtt|cayenne|chipotle.pulver|curry pulver|spisskumin|sumak|zaatar|dukkah|stjerneanis|nellikspiker|kardemommefrø|fennikelfrø|sennepsfrø|flaksalt|\b(?:salt|pepper|oregano|timian|basilikum|kanel|muskat|karri|kardemomme|kajenne|laurbær)\b/.test(s)&&!/bell pepper|red pepper|green pepper|yellow pepper/.test(s))return 'Krydder';
    if(/sukker|sugar|honning|honey|sirup|syrup|sesamfrø|sesame seeds/.test(s))return 'Tørrvarer';
    if(/frossen|frosne|frozen|fryste/.test(s))return 'Frysevarer';
    if(/hermetisk|canned|på boks/.test(s))return 'Hermetikk/halvfabrikat';
    if(/\b(?:oliven|kalamata|olives|kapers|capers)\b/.test(s))return 'Hermetikk/halvfabrikat';
    if(/(?:^|[^a-zæøå])(?:rødvin|hvitvin|vin|red wine|white wine|wine|øl|beer|juice|kaffe|coffee|te|tea|mineralvann)(?=$|[^a-zæøå])/.test(s))return 'Drikke';
    if(/ansjos|blåskjell|krabbeklor|scampi|reker|shrimp|prawn|laks|salmon|ørret|trout|torsk|cod|tunfisk|tuna|sardiner|fisk|fish/.test(s))return 'Kjøtt og fisk';
    if(/\begg\b|\beggs\b|eggehvit|cr[eè]me fra[iî]che|kesam|keso|halloumi|melk|milk|fløte|cream|rømme|parmesan|feta|cottage cheese|yoghurt|yogurt|smør|butter|mozzarella|cheddar|\bost\b/.test(s))return 'Meieri';
    if(/kylling|chicken|biff|flankstek|høyrygg|short rib|indrefilet|storfe|sirloin|beef|okse|kjøttdeig|karbonadedeig|svin|pork|pølse|kalkun|bacon|\blam\b|skinke/.test(s))return 'Kjøtt og fisk';
    if(/frossen|frosne|frozen|fryste|edamame/.test(s))return 'Frysevarer';
    if(/bønner|beans|kikerter|chickpeas|hermetisk|mais/.test(s))return 'Hermetikk/halvfabrikat';
    if(/pasta|linguine|fettuccine|rigatoni|lasagneplater|tortellini|havregryn|panko|brødsmuler|nudler|noodles|\bris\b|\brice\b|quinoa|couscous|linser|lentils|bulgur|orzo|maizena|mel\b|flour|nøtter|nuts|mandler|almonds|cashew/.test(s))return 'Tørrvarer';
    if(/brød|bread|tortilla|pita|wrap|naan|lefser|taco trays|pizzabunn|natron/.test(s))return 'Bakevarer';
    if(/gulrøtter|gulrot|løk|purre|potet|squash|tomat|agurk|paprika|chili|jalape[nñ]o|brokkoli|blomkål|kål|selleri|spinat|salat|ruccola|sopp|sjampinjong|avokado|ingefær|fennikel|pak choi|bok choy|slaw|bønnespirer|rødbet|gresskar|daikon|persille|koriander|cilantro|dill|mynte|gressløk|sitron|lime|eple|epler|mango|fersken|nektarin|ananas|appelsin|jordbær|granateple|vannmelon|bananpepper/.test(s))return 'Frukt og grønt';
    return null;
  }
  // Preparation is not a different product. Unknown/type notes remain distinct.
  function mergeName(value){
    const preparation=/^(?:(?:finely|roughly|thinly|freshly|grovt|fint|tynt)\s+)?(?:chopped|minced|diced|grated|sliced|shredded|hakket|finhakket|grovhakket|revet|finrevet|skivet|finsnittet|strimlet|presset|knust|i terninger|kuttet i terninger|skåret i terninger|skjært i terninger)$/i;
    const note=value=>{
      const text=value.trim();
      if(text.split(/\s+(?:og|and)\s+|,\s*/).every(part=>preparation.test(part)))return '';
      if(/^(?:til|for) (?:pynt|servering|saus|sausen|dressing|dressingen|marinade|marinaden|topping|garnish|serving)$/i.test(text))return '';
      if(/^(?:saft(?:en)?(?: av(?: (?:en halv|en|halv) lime)?)?|juiced|juice)$/i.test(text))return '(saft)';
      if(/^(?:revet skall|skall(?:et)?|zest|zested)$/i.test(text))return '(skall)';
      return '('+text+')';
    };
    let name=String(value).toLowerCase();
    // Nested usage notes can expose a preparation note on the next pass.
    // Normalize fully now so a second merge never changes product identity.
    for(let depth=0;depth<10;depth++){
      const next=name.replace(/\(([^()]*)\)/g,(_,text)=>note(text));
      if(next===name)break;
      name=next;
    }
    // A trailing comma often introduces preparation; do not discard product types.
    name=name.replace(/,\s*([^,()]*)$/,(_,text)=>' '+note(text));
    name=name.replace(/\([^)]*\)|\b(?:finhakket|grovhakket|finrevet|finsnittet|chopped|minced|diced|grated|sliced|shredded|hakket|revet|skivet)\b/g,part=>part.startsWith('(')?part:'');
    return name.replace(/\s+/g,' ').trim();
  }
  function recoverLegacyGroup(text,candidates){
    if(!/\d+\/\d+,\d+ dl/.test(text))return null;
    const parts=text.split(' + ');if(parts.length<2)return null;
    const restored=[];
    for(const part of parts){
      const matches=[...new Set(candidates.filter(x=>x.legacy===part).map(x=>x.current))];
      if(matches.length!==1)return null;
      restored.push(matches[0]);
    }
    return restored;
  }
  function registryKey(text){
    const key=mergeName(parse(text).name);
    return /[a-zæøå]/i.test(key)?key:'';
  }
  return {parse,convert,scale,clean,heading,category,categoryName,fmt,mergeName,registryKey,recoverLegacyGroup};
});
