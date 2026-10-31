/* Code 128 is drawn locally: customer numbers are never sent to a barcode service. */
(function(root) {
  const patterns = ["212222", "222122", "222221", "121223", "121322", "131222", "122213", "122312", "132212", "221213", "221312", "231212", "112232", "122132", "122231", "113222", "123122", "123221", "223211", "221132", "221231", "213212", "223112", "312131", "311222", "321122", "321221", "312212", "322112", "322211", "212123", "212321", "232121", "111323", "131123", "131321", "112313", "132113", "132311", "211313", "231113", "231311", "112133", "112331", "132131", "113123", "113321", "133121", "313121", "211331", "231131", "213113", "213311", "213131", "311123", "311321", "331121", "312113", "312311", "332111", "314111", "221411", "431111", "111224", "111422", "121124", "121421", "141122", "141221", "112214", "112412", "122114", "122411", "142112", "142211", "241211", "221114", "413111", "241112", "134111", "111242", "121142", "121241", "114212", "124112", "124211", "411212", "421112", "421211", "212141", "214121", "412121", "111143", "111341", "131141", "114113", "114311", "411113", "411311", "113141", "114131", "311141", "411131", "211412", "211214", "211232", "2331112"];
  function barcodeSvg(value) {
    if (!/^\d{6,30}$/.test(String(value||''))) return '';
    const code=String(value), evenLength=code.length-code.length%2, symbols=[105];
    for(let i=0;i<evenLength;i+=2) symbols.push(Number(code.slice(i,i+2)));
    if(code.length%2) symbols.push(100,code.charCodeAt(code.length-1)-32);
    symbols.push(symbols.reduce((sum,value,i)=>sum+value*(i||1),0)%103,106);
    let x=12, bars='';
    for(const symbol of symbols) [...patterns[symbol]].forEach((width,index)=>{
      const w=Number(width); if(index%2===0) bars+=`<rect x="${x}" y="10" width="${w}" height="56"/>`; x+=w;
    });
    return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${x+12} 80" role="img" aria-label="REMA-kundestrekkode" shape-rendering="crispEdges"><rect width="100%" height="100%" fill="white"/><g fill="black">${bars}</g></svg><span class="loyalty-number">${code}</span>`;
  }
  root.renderLoyaltyCard=function(value) {
    const card=document.getElementById('remaCustomerCard'); if(!card)return;
    const markup=barcodeSvg(value); card.hidden=!markup;
    for(const id of ['remaBarcode','remaBarcodeLarge']) {const el=document.getElementById(id);if(el)el.innerHTML=markup;}
  };
  if(typeof module==='object' && module.exports)module.exports={barcodeSvg};
  if(typeof document!=='undefined')document.getElementById('expandRemaCard')?.addEventListener('click',()=>document.getElementById('remaCardDialog').showModal());
})(typeof window!=='undefined'?window:globalThis);
