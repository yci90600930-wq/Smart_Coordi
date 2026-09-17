let transcriber=null;
let loading=false;
async function loadModel(){
  if(transcriber) return transcriber;
  if(loading){while(!transcriber) await new Promise(r=>setTimeout(r,250)); return transcriber;}
  loading=true;
  postMessage({type:'status',message:'로컬 Whisper 모델을 불러오는 중입니다. 최초 1회는 모델 다운로드로 시간이 걸립니다.'});
  const mod=await import('https://cdn.jsdelivr.net/npm/@xenova/transformers@2.17.2/+esm');
  mod.env.allowLocalModels=false; mod.env.useBrowserCache=true;
  transcriber=await mod.pipeline('automatic-speech-recognition','Xenova/whisper-small',{quantized:true,progress_callback:x=>{if(x?.progress!=null)postMessage({type:'progress',progress:x.progress});}});
  loading=false;
  postMessage({type:'status',message:'로컬 Whisper 준비 완료'});
  return transcriber;
}
onmessage=async(e)=>{
  if(e.data?.type==='warmup'){try{await loadModel();postMessage({type:'ready'});}catch(err){postMessage({type:'error',message:String(err?.message||err)});}return;}
  if(e.data?.type==='transcribe'){
    try{const pipe=await loadModel();postMessage({type:'status',message:'브라우저에서 녹음 전체를 고정밀 전사 중입니다.'});const out=await pipe(e.data.audio,{language:'korean',task:'transcribe',chunk_length_s:30,stride_length_s:5,return_timestamps:false});postMessage({type:'result',text:(out?.text||'').trim()});}
    catch(err){postMessage({type:'error',message:String(err?.message||err)});}
  }
};
