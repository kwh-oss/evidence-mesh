// Self-contained function: Chrome serializes it into the selected page.
export function readVideoContext() {
  const url = new URL(location.href);
  const isDouyin = url.hostname === 'douyin.com' || url.hostname.endsWith('.douyin.com');
  let id = url.searchParams.get('modal_id') || url.pathname.match(/\/video\/(\d+)/)?.[1];
  let videoBinding=/^\d+$/.test(id||'')?'page-url':'unresolved';
  let originalUrl = url.origin + url.pathname;
  if (isDouyin && /^\d+$/.test(id || '')) originalUrl = `https://www.douyin.com/video/${id}`;
  const videos = [...document.querySelectorAll('video')].map((v,index) => {
    const r=v.getBoundingClientRect(),style=getComputedStyle(v);
    const left=Math.max(0,r.left),top=Math.max(0,r.top),right=Math.min(innerWidth,r.right),bottom=Math.min(innerHeight,r.bottom);
    const area=Math.max(0,right-left)*Math.max(0,bottom-top);
    return {v,index,area,active:Boolean(v.closest('[data-e2e="feed-active-video"]')),rect:{left,top,width:right-left,height:bottom-top},visible:style.display!=='none'&&style.visibility!=='hidden'&&Number(style.opacity)!==0};
  }).filter(x=>x.visible&&x.area>10000).sort((a,b)=>Number(b.active)-Number(a.active)||(Number(!b.v.paused)-Number(!a.v.paused)) || b.area-a.area);
  const chosen=videos[0];
  if (!chosen) return {url:originalUrl,title:document.title,text:String(getSelection()||'').slice(0,6000),videoFound:false};
  if(isDouyin){
    // Recommendation feeds keep the homepage URL. Use only the selected
    // player's public DOM, never other cards or private framework state.
    const active=chosen.v.closest('[data-e2e="feed-active-video"]');
    const player=active||chosen.v.closest('.xgplayer');
    const classIds=active?[...active.classList].map(x=>x.match(/^video_(\d+)$/)?.[1]).filter(Boolean):[];
    let ids=[...new Set(classIds)];
    if(!ids.length&&player){
      const found=[];
      for(const a of player.querySelectorAll('a[href]')){
        try{
          const link=new URL(a.getAttribute('href'),location.href);
          if(link.hostname!=='douyin.com'&&!link.hostname.endsWith('.douyin.com'))continue;
          const value=link.pathname.match(/\/video\/(\d+)(?:\/|$)/)?.[1]||link.searchParams.get('aweme_id')||link.searchParams.get('modal_id');
          if(/^\d+$/.test(value||''))found.push(value);
        }catch{}
      }
      ids=[...new Set(found)];
    }
    if(ids.length===1){id=ids[0];videoBinding=classIds.length?'active-container':'player-links';}
    else if(ids.length>1){id=null;videoBinding='ambiguous';}
    originalUrl=/^\d+$/.test(id||'')?`https://www.douyin.com/video/${id}`:url.origin+url.pathname;
  }
  const intersects=element=>{const r=element.getBoundingClientRect(),s=getComputedStyle(element);return s.display!=='none'&&s.visibility!=='hidden'&&r.width>0&&r.height>0&&r.left<chosen.rect.left+chosen.rect.width&&r.right>chosen.rect.left&&r.top<chosen.rect.top+chosen.rect.height&&r.bottom>chosen.rect.top;};
  // Passive danmaku/subtitles belong to the visible video context. Small text
  // controls are redacted before upload instead of blocking the whole player.
  const inputs=[...document.querySelectorAll('input:not([type="range"]):not([type="checkbox"]):not([type="radio"]):not([type="hidden"]):not([type="button"]):not([type="submit"]),textarea,[contenteditable="true"]')].filter(el=>!el.contains(chosen.v)&&intersects(el));
  const maskRects=inputs.map(el=>{const r=el.getBoundingClientRect();return {
    left:Math.max(chosen.rect.left,r.left-4),top:Math.max(chosen.rect.top,r.top-4),
    width:Math.min(chosen.rect.left+chosen.rect.width,r.right+4)-Math.max(chosen.rect.left,r.left-4),
    height:Math.min(chosen.rect.top+chosen.rect.height,r.bottom+4)-Math.max(chosen.rect.top,r.top-4)};});
  const blockedOverlay=[...document.querySelectorAll('[role="dialog"],[aria-modal="true"]')].some(el=>!el.contains(chosen.v)&&intersects(el))
    ||inputs.some(el=>el.type==='password')
    ||maskRects.reduce((area,r)=>area+r.width*r.height,0)>chosen.rect.width*chosen.rect.height*.15;
  const captions=[];
  for(const track of chosen.v.textTracks || []) for(const cue of track.activeCues || []) {
    const text=String(cue.text||'').trim();if(text&&!captions.includes(text))captions.push(text.slice(0,500));
  }
  return {url:originalUrl,title:document.title.slice(0,180),text:String(getSelection()||'').slice(0,6000),
    videoFound:true,blockedOverlay,maskRects,videoBound:!isDouyin||/^\d+$/.test(id||''),videoBinding,videoIndex:chosen.index,
    video_time:chosen.v.currentTime,paused:chosen.v.paused,rect:chosen.rect,
    viewport:{width:innerWidth,height:innerHeight},captions:captions.slice(0,20)};
}

export async function cropVideoFrame(screenshot, rect, viewport, maskRects=[]) {
  const bitmap=await createImageBitmap(await (await fetch(screenshot)).blob());
  try {
    const ratioX=bitmap.width/viewport.width,ratioY=bitmap.height/viewport.height;
    const w=Math.round(rect.width*ratioX),h=Math.round(rect.height*ratioY);
    if(w<16||h<16)throw Error('视频画面区域过小');
    const scale=Math.min(1,960/Math.max(w,h));
    const canvas=new OffscreenCanvas(Math.round(w*scale),Math.round(h*scale));
    canvas.getContext('2d').drawImage(bitmap,Math.round(rect.left*ratioX),Math.round(rect.top*ratioY),w,h,0,0,canvas.width,canvas.height);
    const ctx=canvas.getContext('2d');ctx.fillStyle='#202020';
    for(const mask of maskRects){
      const x=Math.floor((mask.left-rect.left)*canvas.width/rect.width),y=Math.floor((mask.top-rect.top)*canvas.height/rect.height);
      ctx.fillRect(x,y,Math.ceil(mask.width*canvas.width/rect.width)+2,Math.ceil(mask.height*canvas.height/rect.height)+2);
    }
    let blob=await canvas.convertToBlob({type:'image/jpeg',quality:.82});
    for(const quality of [.7,.55,.4]){if(blob.size<=200000)break;blob=await canvas.convertToBlob({type:'image/jpeg',quality});}
    const raw=new Uint8Array(await blob.arrayBuffer());
    if(raw.length>200000)throw Error('采样帧超过大小上限');
    let binary='';for(let i=0;i<raw.length;i+=8192)binary+=String.fromCharCode(...raw.subarray(i,i+8192));
    return 'data:image/jpeg;base64,'+btoa(binary);
  } finally {bitmap.close();}
}

export async function collectVideo(chromeAPI, tab) {
  if (!tab?.id)throw Error('没有可读取的当前标签页');
  const read=async()=>{
    const [current]=await chromeAPI.tabs.query({active:true,windowId:tab.windowId});
    if(current?.id!==tab.id)throw Error('采集中切换了标签页，已停止');
    return (await chromeAPI.scripting.executeScript({target:{tabId:tab.id},func:readVideoContext}))[0].result;
  };
  const first=await read();
  if(!first.videoFound)throw Error('没有找到当前可见的视频，请打开视频播放器后重试');
  if(first.blockedOverlay)throw Error('视频区域有弹窗或输入框遮挡，请关闭后再采集');
  if(!first.videoBound)throw Error('尚未定位具体抖音视频，请先打开该视频详情页再采集');
  const frames=[],captions=new Set(); let previous=-1;
  for(let i=0;i<6;i++){
    if(i)await new Promise(resolve=>setTimeout(resolve,6000));
    const current=await read();
    if(current.blockedOverlay)throw Error('采集中出现弹窗或输入框，已停止上传');
    if(!current.videoFound||current.url!==first.url||current.videoIndex!==first.videoIndex)throw Error('视频发生切换，已停止采集，请重新读取');
    if(i&&current.video_time<previous)break; // End at a loop/seek; keep only the original segment.
    if(i&&current.video_time===previous)break; // Paused video: one still, not six invented moments.
    const screenshot=await chromeAPI.tabs.captureVisibleTab(tab.windowId,{format:'jpeg',quality:85});
    const after=await read();
    if(after.blockedOverlay||!after.videoFound||after.url!==current.url||after.videoIndex!==current.videoIndex||JSON.stringify(after.maskRects)!==JSON.stringify(current.maskRects)||after.viewport.width!==current.viewport.width||after.viewport.height!==current.viewport.height||Math.abs(after.rect.left-current.rect.left)>2||Math.abs(after.rect.top-current.rect.top)>2||Math.abs(after.rect.width-current.rect.width)>2||Math.abs(after.rect.height-current.rect.height)>2)throw Error('视频区域发生变化或被遮挡，已停止采集');
    frames.push({video_time:current.video_time,data_url:await cropVideoFrame(screenshot,current.rect,current.viewport,current.maskRects)});
    for(const text of current.captions)captions.add(text);
    previous=current.video_time;
  }
  return {url:first.url,title:first.title,frames,captions:[...captions].slice(0,20)};
}
