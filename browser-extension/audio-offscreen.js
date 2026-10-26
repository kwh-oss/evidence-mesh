// Bounded current-tab audio only. No microphone, background monitoring or API keys.
let active;
async function finish(cancel=false){
  if(!active)return null;
  const state=active;active=null;clearTimeout(state.timer);
  if(state.recorder.state!=='inactive')state.recorder.stop();
  await state.stopped;
  state.stream.getTracks().forEach(t=>t.stop());await state.context.close();
  if(cancel)return null;
  const blob=new Blob(state.chunks,{type:state.recorder.mimeType});
  if(blob.size>256000)throw Error('声音片段过大，请重试');
  const bytes=new Uint8Array(await blob.arrayBuffer());let raw='';for(let i=0;i<bytes.length;i+=8192)raw+=String.fromCharCode(...bytes.subarray(i,i+8192));
  return {data_url:'data:audio/webm;base64,'+btoa(raw),duration_seconds:Math.min(35,(Date.now()-state.started)/1000),video_time:state.videoTime};
}
chrome.runtime.onMessage.addListener((m,sender,reply)=>{
  if(sender.id!==chrome.runtime.id||m.target!=='audio-offscreen')return;
  (async()=>{
    if(m.type==='audio-start'){
      if(active)throw Error('已有声音采样正在进行');
      const stream=await navigator.mediaDevices.getUserMedia({audio:{mandatory:{chromeMediaSource:'tab',chromeMediaSourceId:m.streamId}},video:false});
      const context=new AudioContext();context.createMediaStreamSource(stream).connect(context.destination);
      try{
        const recorder=new MediaRecorder(stream,{mimeType:'audio/webm;codecs=opus',audioBitsPerSecond:32000});
        const state={stream,context,recorder,chunks:[],started:Date.now(),videoTime:m.videoTime};
        state.stopped=new Promise(resolve=>recorder.addEventListener('stop',resolve,{once:true}));
        recorder.addEventListener('dataavailable',e=>{if(e.data.size)state.chunks.push(e.data)});
        active=state;recorder.start(1000);
        // Timeout releases all capture resources even if the side panel closes.
        state.timer=setTimeout(()=>finish(true).catch(()=>{}),35000);
        return {ok:true};
      }catch(e){stream.getTracks().forEach(t=>t.stop());await context.close();throw e;}
    }
    if(m.type==='audio-stop')return {ok:true,audio:await finish(Boolean(m.cancel))};
    return {ok:false,error:'未知声音采样操作'};
  })().then(reply).catch(e=>reply({ok:false,error:e.message}));return true;
});
