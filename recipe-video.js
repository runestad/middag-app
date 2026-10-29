/* Only known provider URLs can become embedded players. */
function recipeVideoEmbed(value) {
  try {
    const url=new URL(value); if(url.protocol!=='https:')return null;
    const host=url.hostname.toLowerCase(),path=url.pathname;
    let id;
    if((host==='tiktok.com'||host.endsWith('.tiktok.com'))&&(id=path.match(/\/video\/(\d+)/)?.[1]))return {url:`https://www.tiktok.com/player/v1/${id}`,portrait:true};
    if((host==='instagram.com'||host==='www.instagram.com')&&(id=path.match(/^\/(?:reel|reels|p)\/([\w-]+)\/?$/)?.[1]))return {url:`https://www.instagram.com/p/${id}/embed/`,portrait:true};
    if(host==='youtu.be')id=path.slice(1);
    else if(host==='youtube.com'||host==='www.youtube.com'||host==='m.youtube.com')id=url.searchParams.get('v')||path.match(/^\/shorts\/([\w-]+)/)?.[1];
    if(id&&/^[\w-]{11}$/.test(id))return {url:`https://www.youtube-nocookie.com/embed/${id}`,portrait:false};
  }catch(_){}
  return null;
}
(() => {
  const previous=window.openRecipeDetails,cache=new Map();
  window.openRecipeDetails=function(id){
    previous(id);
    const recipe=recipeById(id),body=document.getElementById('recipeDialogBody');
    if(!recipe||!body)return;
    const source=originalRecipeSourceUrlV31(recipe);
    const candidates=[recipe.resolvedSourceUrl,recipe.sourceMetadata?.resolvedSourceUrl,source];
    let embed=candidates.map(recipeVideoEmbed).find(Boolean)||cache.get(source);
    let shortLink=false;
    try{shortLink=['vm.tiktok.com','vt.tiktok.com','www.tiktok.com'].includes(new URL(source).hostname)&&!embed;}catch(_){}
    if(!embed&&!shortLink)return;
    const section=document.createElement('section');section.className='recipe-video';
    const button=document.createElement('button');button.type='button';button.className='primary';button.textContent='▶ Se video';
    const status=document.createElement('p');status.className='hint';status.setAttribute('role','status');
    const slot=document.createElement('div');
    section.append(button,status,slot);body.querySelector('.recipe-hero-image')?.after(section);
    if(!section.isConnected)body.prepend(section);
    button.addEventListener('click',async()=>{
      if(slot.firstChild){slot.replaceChildren();button.textContent='▶ Se video';return;}
      button.disabled=true;status.textContent='Laster video …';
      try{
        if(!embed){
          const response=await fetch('/api/fetch-recipe',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({url:source}),signal:AbortSignal.timeout(30000)});
          const data=await response.json();embed=recipeVideoEmbed(data.result?.resolvedSourceUrl||data.result?.resolvedUrl);if(embed)cache.set(source,embed);
        }
        if(!section.isConnected)return;
        if(!embed)throw new Error('unavailable');
        const frame=document.createElement('iframe');frame.src=embed.url;frame.title=`Video: ${recipe.name}`;
        frame.className=embed.portrait?'portrait':'landscape';frame.allow='fullscreen; autoplay; encrypted-media; picture-in-picture';frame.allowFullscreen=true;
        slot.append(frame);button.textContent='Skjul video';status.textContent='Hvis videoen ikke kan spilles, bruk «Åpne kilde». Kilden kan kreve innlogging eller ha begrenset avspilling.';
      }catch(_){status.textContent='Videoen kunne ikke åpnes her. Bruk «Åpne kilde» eller prøv igjen.';}
      finally{button.disabled=false;}
    });
    const dialog=document.getElementById('recipeDialog');
    dialog.addEventListener('close',()=>slot.replaceChildren(),{once:true});
  };
})();
