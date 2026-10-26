import {readVideoContext,collectVideo} from './video-capture.mjs';
// No persistent content script: only user-triggered capture.
async function capture(tab) {
  if (!tab?.id) return;
  try {
    const [{result}] = await chrome.scripting.executeScript({target: {tabId: tab.id}, func: readVideoContext});
    await saveContext(tab.windowId, result);
  } catch {
    await chrome.storage.session.set({['context-' + tab.windowId]: {error: '此页面不允许读取。可以手动填写需要核验的说法。'}});
  }
}
async function saveContext(windowId, value) {
  let url = '';
  try {
    const parsed = new URL(value.url);
    if (['https:', 'http:'].includes(parsed.protocol) && !parsed.username && !parsed.password) {
      const video = parsed.searchParams.get('modal_id');
      parsed.search = ''; parsed.hash = '';
      if (parsed.hostname.endsWith('.douyin.com') && video && /^\d+$/.test(video)) parsed.searchParams.set('modal_id', video);
      url = parsed.href;
    }
  } catch {}
  await chrome.storage.session.set({['context-' + windowId]: {text: value.text || '', title: value.title || '', url, videoFound:Boolean(value.videoFound), videoBound:Boolean(value.videoBound), capturedAt: Date.now()}});
}
chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({id: 'evidence-check', title: '用证链核验这段话', contexts: ['selection'], documentUrlPatterns: ['https://*/*', 'http://*/*']});
});
chrome.action.onClicked.addListener(tab => {
  // Call open before asynchronous work so the browser retains the user gesture.
  chrome.sidePanel.open({windowId: tab.windowId}).catch(() => {});
  capture(tab);
});
chrome.contextMenus.onClicked.addListener((info, tab) => {
  if (info.menuItemId !== 'evidence-check' || !tab) return;
  chrome.sidePanel.open({windowId: tab.windowId}).catch(() => {});
  saveContext(tab.windowId, {text: String(info.selectionText || '').slice(0, 6000), title: tab.title || '', url: info.pageUrl || tab.url || ''});
});
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (sender.id !== chrome.runtime.id) return;
  if (message?.type === 'collect-video') {
    chrome.tabs.query({active:true,currentWindow:true}).then(async ([tab])=>{
      const [{result:current}]=await chrome.scripting.executeScript({target:{tabId:tab.id},func:readVideoContext});
      if(!current.videoFound)throw Error('没有找到当前可见的视频，请打开视频后重试');
      if(!current.videoBound)throw Error('已找到播放器，但未取得当前视频的独立链接。请从分享菜单打开视频详情后重新读取');
      if(!chrome.tabCapture?.getMediaStreamId)throw Error('请重新加载新版插件，允许当前标签页声音采样');
      if(!(await chrome.runtime.getContexts({contextTypes:['OFFSCREEN_DOCUMENT']})).length)
        await chrome.offscreen.createDocument({url:'audio-offscreen.html',reasons:['USER_MEDIA'],justification:'用户主动分析当前视频时，采集最多35秒标签页声音用于转写'});
      const streamId=await chrome.tabCapture.getMediaStreamId({targetTabId:tab.id});
      const started=await chrome.runtime.sendMessage({target:'audio-offscreen',type:'audio-start',streamId,videoTime:current.video_time});
      if(!started?.ok)throw Error(started?.error||'声音采样未启动');
      try{
        const video=await collectVideo(chrome,tab);
        const stopped=await chrome.runtime.sendMessage({target:'audio-offscreen',type:'audio-stop'});
        if(!stopped?.ok||!stopped.audio)throw Error(stopped?.error||'未取得声音片段');
        video.audio=stopped.audio;
        await saveContext(tab.windowId,{...video,videoFound:true,videoBound:true});
        return {ok:true,capture:video};
      }catch(error){await chrome.runtime.sendMessage({target:'audio-offscreen',type:'audio-stop',cancel:true}).catch(()=>{});throw error;}
    }).then(sendResponse).catch(error=>sendResponse({ok:false,error:error.message}));
    return true;
  }
  if(message?.type !== 'capture-current') return;
  chrome.tabs.query({active: true, currentWindow: true}).then(([tab]) => capture(tab)).then(() => sendResponse({ok: true})).catch(() => sendResponse({ok: false}));
  return true;
});
