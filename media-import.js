// Video remains on the device; only sampled JPEG frames and mono audio are sent.
let mediaEvidenceV52 = null;
const mediaDataURLV52 = blob => new Promise((resolve,reject)=>{const r=new FileReader();r.onload=()=>resolve(r.result);r.onerror=()=>reject(new Error('Filen kunne ikke leses.'));r.readAsDataURL(blob)});
function mediaEventV52(element,event,action){return new Promise((resolve,reject)=>{const timer=setTimeout(()=>done(new Error('Videoen kunne ikke leses på denne enheten.')),15000);const success=()=>done();const failure=()=>done(new Error('Videoformatet støttes ikke på denne enheten.'));function done(error){clearTimeout(timer);element.removeEventListener(event,success);element.removeEventListener('error',failure);error?reject(error):resolve()}element.addEventListener(event,success,{once:true});element.addEventListener('error',failure,{once:true});action()})}
function mediaWavV52(samples){const buffer=new ArrayBuffer(44+samples.length*2),v=new DataView(buffer);const str=(p,s)=>{for(let i=0;i<s.length;i++)v.setUint8(p+i,s.charCodeAt(i))};str(0,'RIFF');v.setUint32(4,36+samples.length*2,true);str(8,'WAVE');str(12,'fmt ');v.setUint32(16,16,true);v.setUint16(20,1,true);v.setUint16(22,1,true);v.setUint32(24,16000,true);v.setUint32(28,32000,true);v.setUint16(32,2,true);v.setUint16(34,16,true);str(36,'data');v.setUint32(40,samples.length*2,true);for(let i=0;i<samples.length;i++){const s=Math.max(-1,Math.min(1,samples[i]));v.setInt16(44+i*2,s<0?s*32768:s*32767,true)}return new Blob([buffer],{type:'audio/wav'})}
async function importMediaV52(file){
  if(!file||importBusyV50||importSavingV50)return;
  const status=$('mediaImportStatus'),id=activeImportId,run=++importRunV26;
  const active=()=>run===importRunV26&&currentImportV50(id);
  const check=()=>{if(!active())throw new Error('Avbrutt')};
  if(file.size>150*1024*1024){status.textContent='Velg et opptak under 150 MB og tre minutter.';return}
  const isVideo=file.type.startsWith('video/')||/\.(mp4|mov|m4v|webm)$/i.test(file.name);
  const evidence=[],warnings=[];let video,url,context,thumbnail='';
  setImportBusyV50(true);status.textContent='Leser opptaket … Hold appen åpen mens analysen pågår.';
  try{
    // Decode/resample locally to avoid Vercel request limits even for large iPhone recordings.
    try{
      const Audio=window.AudioContext||window.webkitAudioContext;context=new Audio();
      const decoded=await context.decodeAudioData(await file.arrayBuffer());check();
      if(decoded.duration>180)throw new Error('TOO_LONG');
      const Offline=window.OfflineAudioContext||window.webkitOfflineAudioContext;
      const offline=new Offline(1,Math.ceil(decoded.duration*16000),16000),source=offline.createBufferSource();source.buffer=decoded;source.connect(offline.destination);source.start();
      const mono=(await offline.startRendering()).getChannelData(0);check();
      for(let start=0;start<mono.length;start+=16000*60){
        check();setImportProgressV26('Leser lyden …',15+30*start/mono.length);
        const result=await importRequestV50('/api/parse-caption?media=1',{kind:'audio',audio:await mediaDataURLV52(mediaWavV52(mono.slice(start,start+16000*60)))});check();
        if(result.text)evidence.push(`LYD ved ${start/16000} sekunder:\n${result.text}`);
      }
    }catch(error){check();if(error.message==='TOO_LONG')throw new Error('Videoen må være kortere enn tre minutter. Klipp opptaket og prøv igjen.');warnings.push('Lyden kunne ikke analyseres. Kontroller oppskriften mot lyden selv.');}
    if(isVideo){
      try{
        video=document.createElement('video');video.muted=true;video.playsInline=true;video.preload='auto';url=URL.createObjectURL(file);
        await mediaEventV52(video,'loadeddata',()=>{video.src=url;video.load()});check();
        if(!Number.isFinite(video.duration)||video.duration>180)throw new Error('Videoen må være kortere enn tre minutter.');
        const canvas=document.createElement('canvas'),scale=Math.min(1,960/Math.max(video.videoWidth,video.videoHeight));canvas.width=Math.round(video.videoWidth*scale);canvas.height=Math.round(video.videoHeight*scale);const ctx=canvas.getContext('2d');let frames=[];
        for(let second=0.1;second<video.duration;second+=2){
          check();await mediaEventV52(video,'seeked',()=>{video.currentTime=Math.min(second,video.duration-0.05)});check();ctx.drawImage(video,0,0,canvas.width,canvas.height);
          const image=canvas.toDataURL('image/jpeg',0.65);if(!thumbnail)thumbnail=image;frames.push({seconds:second,image});
          if(frames.length===8||second+2>=video.duration){setImportProgressV26('Leser tekst og handlinger i videoen …',45+35*second/video.duration);const result=await importRequestV50('/api/parse-caption?media=1',{kind:'frames',frames});check();if(result.text)evidence.push('VIDEOBILDER:\n'+result.text);frames=[];}
        }
      }catch(error){check();warnings.push(error.message+' Videobildene ble ikke fullstendig analysert.');}
    }
    check();if(!evidence.length)throw new Error(warnings.join(' ')||'Fant ingen tydelig tale eller oppskriftstekst. Prøv skjermbilder eller lim inn teksten.');
    mediaEvidenceV52={method:'uploaded-media',sampleIntervalSeconds:isVideo?2:null,warnings};
    $('captionInput').value=['KILDE: Tale og utvalgte videobilder. Kan inneholde feil. Ikke gjett manglende mengder, porsjoner eller steg. Slå sammen gjentatte omtaler av samme ingrediens; ikke summer gjentatte undertekster.',...evidence].join('\n\n');
    if(thumbnail){importSourceMediaV27=thumbnail;importImageMethodV50='video';renderRecipeImageEditorV43()}
    status.textContent=['Video/lyd er analysert. Kontroller mengder og steg mot opptaket. Videobilder leses hvert andre sekund.',...warnings].join(' ');
    setImportBusyV50(false);await parseCaptionAI({automatic:true});
  }catch(error){if(active()){status.textContent=error.message;setImportProgressV26('Videoimporten trenger hjelp',100)}}
  finally{if(context)await context.close().catch(()=>{});if(video){video.removeAttribute('src');video.load()}if(url)URL.revokeObjectURL(url);if(active())setImportBusyV50(false);}
}
$('chooseRecipeMediaBtn').addEventListener('click',()=>$('recipeMediaInput').click());
$('recipeMediaInput').addEventListener('change',event=>{const file=event.target.files[0];event.target.value='';importMediaV52(file)});
$('newRecipeVideoBtn').addEventListener('click',()=>{beginNewRecipeImportV31('video');$('recipeMediaInput').click()});
