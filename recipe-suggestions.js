(function(root,factory){const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;root.RecipeSuggestions=api;})(globalThis,function(){
  // Pantry and recent cooking affect the odds, never lock the first positions.
  function choose(candidates,count,{seen=new Set(),last=[],random=Math.random}={}){
    const unique=[...new Map(candidates.map(item=>[String(item.recipe.id),item])).values()];
    const limit=Math.min(Math.max(0,count),unique.length),lastIds=new Set(last.map(String));
    const ranked=unique.map(item=>{
      const weight=(1+2*Math.max(0,Math.min(1,item.pantryScore||0)))*(item.recent ? 0.35 : 1);
      return {...item,rank:-Math.log(Math.max(1e-9,random()))/weight};
    }).sort((a,b)=>a.rank-b.rank);
    const fresh=ranked.filter(item=>!seen.has(String(item.recipe.id)));
    const previous=ranked.filter(item=>seen.has(String(item.recipe.id)))
      .sort((a,b)=>Number(lastIds.has(String(a.recipe.id)))-Number(lastIds.has(String(b.recipe.id)))||a.rank-b.rank);
    const selected=[],categories=new Set();
    for(const pool of [fresh,previous]){
      while(pool.length&&selected.length<limit){
        const diverse=pool.findIndex(item=>!categories.has(item.recipe.category));
        const item=pool.splice(diverse<0?0:diverse,1)[0];
        selected.push(item.recipe);categories.add(item.recipe.category);
      }
    }
    if(selected.some(recipe=>seen.has(String(recipe.id))))seen.clear();
    selected.forEach(recipe=>seen.add(String(recipe.id)));
    return selected;
  }
  return {choose};
});
