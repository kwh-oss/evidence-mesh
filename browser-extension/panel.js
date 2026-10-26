import {resultView, safeUrl, roles, labels} from './model.mjs';
import {automaticClaims} from './video-claims.mjs';
const $ = id => document.getElementById(id), API = 'https://api.linsixuan.cn/extension/jobs';
const retry = document.createElement('button'); retry.type = 'button'; retry.className = 'text-button';
retry.textContent = '用原编号重新确认提交'; retry.hidden = true; $('refresh').after(retry);
let windowId, context, job, timer, busy = false, observation;
const videoStage=node('section','','video-stage'),readVideo=node('button','分析并核验当前视频','secondary'),originalBox=node('div','','original-observation');
readVideo.type='button';originalBox.hidden=true;
const restoreVideo=node('button','查看上次分析','text-button');restoreVideo.type='button';
videoStage.append(node('p','01 · 理解观点并查证','eyebrow'),readVideo,node('p','播放视频后点击，采集当前标签页约30秒声音与画面，自动提取核心观点并查证其中的事实。','footnote'),originalBox);
readVideo.after(restoreVideo);
restoreVideo.addEventListener('click',async()=>{
  if(busy)return;
  if(!context?.url)return notice('请先点击“重新读取”定位当前视频。');
  busyState(true);
  try{
    const status=await request('/latest?video_url='+encodeURIComponent(context.url));
    job={id:status.job_id,mode:status.result?.video_observation?'observe-video':'fact-check',text:'上次视频分析',autoVerify:false,state:status.state,startedAt:Date.parse(status.created_at)};
    await persist();await accept(status);notice('已恢复上次分析。');
  }catch(error){busyState(false);notice(error.message);}
});
$('check-form').before(videoStage);
const manual=node('details'),manualTitle=node('summary','补充或修改主张（可选）');manual.append(manualTitle);$('check-form').before(manual);manual.append($('check-form'));
const textOnly=node('input');textOnly.type='checkbox';textOnly.id='text-only';
const textOnlyLabel=node('label','','confirm');textOnlyLabel.append(textOnly,node('span','这次只核验输入文字，不分析原视频'));$('check-form').prepend(textOnlyLabel);
const key = () => 'job-' + windowId;
  function jobBody(j){return j.mode==='observe-video'?{job_id:j.id,mode:'observe-video',video_capture:j.capture}:{job_id:j.id,task_text:j.text,...(j.originalId?{original_observation_job_id:j.originalId}:{}),...(j.automaticVideoCheck?{automatic_video_check:true}:{})};}
function needsOriginal(){let videoSite=false;try{const host=new URL(context?.url).hostname;videoSite=host==='douyin.com'||host.endsWith('.douyin.com');}catch{}return Boolean(context?.videoFound||videoSite)&&!textOnly.checked&&!observation;}
function notice(text) { $('notice').textContent = text; $('notice').hidden = !text; }
function busyState(value) {
  busy=value;$('submit').disabled=value||needsOriginal();readVideo.disabled=value;restoreVideo.disabled=value;
  $('submit').firstElementChild.textContent=value?'正在处理，请稍候…':needsOriginal()?'请先读取原视频画面':observation&&!textOnly.checked?'继续查证这条说法':'核验这条消息';
}
function count() { $('count').textContent = `${$('claim').value.length} / 6000`; $('confirm').checked = false; }
function node(tag, text, className) { const n = document.createElement(tag); n.textContent = String(text || ''); if (className) n.className = className; return n; }
async function credential() { return (await chrome.storage.session.get('credential')).credential || ''; }
async function updateCredentialState() { $('credential-state').textContent = await credential() ? '本次会话已配置' : '未配置'; }
async function request(path = '', options = {}) {
  const token = await credential();
  if (!token) { $('settings').open = true; throw Error('请先在访问设置中导入插件访问文件。'); }
  const response = await fetch(API + path, {...options, credentials: 'omit', cache: 'no-store', redirect: 'error', headers: {'Authorization': 'Bearer ' + token, ...(options.body ? {'Content-Type': 'application/json'} : {})}, signal: AbortSignal.timeout(15000)});
  const data = await response.json();
  if (!response.ok) { const error = Error(typeof data.detail === 'string' ? data.detail : `访问失败（HTTP ${response.status}）`); error.status = response.status; throw error; }
  return data;
}
function showContext(value) {
  context = value;
  if(observation&&value?.url&&value.url!==observation.value.source.url){observation=null;$('confirm').checked=false;originalBox.replaceChildren();originalBox.hidden=true;chrome.storage.session.remove('observation-'+windowId);}
  $('page-title').textContent = value?.error || value?.title || '还没有读取当前页面';
  const url = safeUrl(value?.url); $('page-url').hidden = !url;
  if (url) { $('page-url').href = url; $('page-url').textContent = url; } else $('page-url').removeAttribute('href');
  $('use-selection').hidden = !value?.text;
  $('context-hint').textContent=value?.videoFound?(value.videoBound===false?'已找到播放器，尚未取得当前视频链接；请打开视频详情后重新读取。':'已定位可见视频，点击上方按钮自动分析并查证，无需填写主张。'):'尚未采集视频画面；文字输入可作为单独核验任务。';
  if (value?.text && !$('claim').value && !busy) { $('claim').value = value.text; count(); }
  busyState(busy);
}
function showObservation(record){
  originalBox.replaceChildren();originalBox.hidden=false;const value=record.value;
  originalBox.append(node('h3',value.main_point?'视频主要观点':'原视频片段观察（模型建议）'),node('p',value.main_point||value.summary));
  if(value.analysis)originalBox.append(node('h3','观点分析'),node('p',value.analysis));
  if(value.verification_plan){const plan=value.verification_plan;originalBox.append(node('h3','本次核验问题'),node('p',plan.question));if(plan.status==='needs-details')originalBox.append(node('p','还需确认：'+plan.missing_information.join('、')));}
  if(value.main_point&&value.main_point!==value.summary){const overview=node('details');overview.append(node('summary','片段概况'),node('p',value.summary));originalBox.append(overview);}
  const source=node('a',value.source.url);source.href=safeUrl(value.source.url)||'#';source.target='_blank';source.rel='noreferrer';originalBox.append(source);
  originalBox.append(node('p',`已分析${value.source.frames.length}个采样帧；${value.speech?.segments?.length?'已结合声音转写':'本次无可用声音转写'}。`,'footnote'));
  if(value.speech?.segments?.length){const speech=node('details');speech.append(node('summary','查看声音转写'));for(const segment of value.speech.segments)speech.append(node('p',`${Number(value.speech.video_time+segment.start).toFixed(1)}秒 · ${segment.text}`));originalBox.append(speech);}
  const observedDetails=node('details');observedDetails.append(node('summary','逐帧观察与时间位置'));
  for(const row of value.observations||[])observedDetails.append(node('p',row.text+'（'+row.frame_indices.map(x=>`第${x+1}帧 · ${Number(value.source.frames[x]?.video_time||0).toFixed(1)}秒`).join('、')+'）'));
  originalBox.append(observedDetails);
  if(job?.mode==='observe-video'&&job.id===record.jobId&&job.capture?.frames){
    const previews=node('details'),summary=node('summary','查看本次采样画面'),grid=node('div','','frame-grid');
    for(const frame of job.capture.frames){if(!/^data:image\/(jpeg|png);base64,/.test(frame.data_url))continue;const box=node('figure'),image=document.createElement('img');image.src=frame.data_url;image.alt=`视频${Number(frame.video_time).toFixed(1)}秒处采样帧`;box.append(image,node('figcaption',`${Number(frame.video_time).toFixed(1)}秒`));grid.append(box);}
    if(grid.children.length){previews.append(summary,grid);originalBox.append(previews);}
  }
  for(const row of (value.understanding_version==='video-understanding/2'?value.verification_targets||[]:value.candidate_claims||[])){const button=node('button','核验：'+row.text,'candidate');button.type='button';button.disabled=Boolean(context?.url&&context.url!==value.source.url);button.addEventListener('click',()=>{if(busy)return;$('claim').value=row.text;count();$('claim').focus();});originalBox.append(button);}
  if(automaticClaims(value).length){const automatic=node('button','自动核验已提取的主张','secondary');automatic.type='button';automatic.addEventListener('click',()=>{if(!busy)autoVerify(record);});originalBox.append(automatic);}
  const limits=node('details'),gaps=node('ul');limits.append(node('summary','分析范围与限制'));for(const item of value.limitations||[])gaps.append(node('li',item));limits.append(gaps);originalBox.append(limits);
}
textOnly.addEventListener('change',()=>busyState(busy));
readVideo.addEventListener('click',async()=>{
  if(busy)return;if(!await credential()){$('settings').open=true;notice('请先导入插件访问文件。');return;}
  busyState(true);notice('正在采集当前视频的声音与画面（约30秒），请保持视频播放。');
  try{
    const captured=await chrome.runtime.sendMessage({type:'collect-video'});if(!captured?.ok)throw Error(captured?.error||'没有取得原视频画面');
    job={id:crypto.randomUUID(),mode:'observe-video',autoVerify:true,text:'原视频画面观察',capture:captured.capture,state:'submitting',startedAt:Date.now()};
    observation=null;count();await chrome.storage.session.remove('observation-'+windowId);originalBox.hidden=true;await persist();$('result').hidden=true;
    notice('画面已采集，正在分析原视频片段；尚未检索外部材料。');
    await accept(await request('',{method:'POST',body:JSON.stringify(jobBody(job))}));
  }catch(error){busyState(false);notice('原视频分析未完成：'+error.message+'。未启动外部核验。');}
});
function render(data) {
  const view = resultView(data);
  $('result').hidden = false; $('result-kind').textContent = '本次核验结果';
  $('result-time').textContent = new Date().toLocaleTimeString('zh-CN', {hour:'2-digit',minute:'2-digit'});
  $('checked-claim').textContent = job?.text || '';
  $('verdict').textContent = view.title; $('conclusion').textContent = view.summary;
  $('scope').textContent = view.scope;
  $('claim-results').replaceChildren();
  for (const row of view.details) {
    const box = node('article', '', 'claim-row');
    box.append(node('span', labels[row.status] || '尚未判断', 'status-tag'), node('h3', row.claim_span), node('p', row.explanation));
    for (const quote of row.quotes || []) box.append(node('blockquote', quote.text));
    $('claim-results').append(box);
  }
  $('sources').replaceChildren(); $('source-count').textContent = view.sources.length ? `${view.sources.length}页` : '未返回可读来源';
  for (const source of view.sources) {
    const item = node('div', '', 'source'), link = node('a', source.title || source.url);
    link.href = source.url; link.target = '_blank'; link.rel = 'noopener noreferrer';
    item.append(link, node('small', '实际读取页面 · 发布者及首发身份未认证')); $('sources').append(item);
  }
  $('gaps').replaceChildren(...view.gaps.map(g => node('li', g)));
  $('trace').replaceChildren();
  const root = node('div', '', 'trace-item'); root.append(node('strong', '总控任务'), node('small', view.rootTask || '未返回编号')); $('trace').append(root);
  for (const entry of view.trace) { const row = node('div', '', 'trace-item'); row.append(node('strong', roles[entry.role] || entry.role), node('small', entry.task_id)); $('trace').append(row); }
}
async function persist() { await chrome.storage.session.set({[key()]: job}); }
async function accept(status) {
  if (!job) return;
  job.state = status.state; job.result = status.result; await persist();
  retry.hidden = true;
  if (status.state === 'done') {
    clearTimeout(timer);
    if(status.result?.video_observation){$('result').hidden=true;const automatic=job.autoVerify;const record={jobId:job.id,value:status.result.video_observation};await chrome.storage.session.set({['observation-'+windowId]:record});showObservation(record);observation=context?.url&&context.url!==record.value.source.url?null:record;busyState(false);if(observation&&automatic)await autoVerify(record);else notice(observation?'已完成片段观察，可点击“自动核验已提取的主张”继续，无需填写。':'返回的是上一个视频的观察结果，请重新读取当前视频。');}
    else{busyState(false);render(status.result);notice('');}
  } else if (['failed', 'interrupted'].includes(status.state)) {
    busyState(false); clearTimeout(timer);
    notice(status.result?.detail || status.result?.message || '本次分析未完成。');$('result').hidden=false;$('refresh').hidden=false;
  } else {
    busyState(true); notice('正在核对这条主张。可关闭侧栏，重新打开后继续查询同一任务。');
    clearTimeout(timer); timer = setTimeout(poll, 2500);
  }
}
async function poll() {
  if (!job) return;
  clearTimeout(timer);
  try { await accept(await request('/' + job.id)); }
  catch (error) { busyState(true); retry.hidden = error.status !== 404; notice('暂时无法确认任务结果：' + error.message + '。请查询原任务状态；若服务器确认未找到，可用原编号重新确认提交。'); $('result').hidden = false; $('refresh').hidden = false; }
}
$('claim').addEventListener('input', count);
$('capture').addEventListener('click', async () => {
  try { await chrome.runtime.sendMessage({type:'capture-current'}); showContext((await chrome.storage.session.get('context-' + windowId))['context-' + windowId]); }
  catch { notice('未能读取此页面，请点击浏览器工具栏的证链图标后重试，或手动输入主张。'); }
});
$('use-selection').addEventListener('click', () => {
  if (busy) return notice('当前任务仍在执行，请先等待结果。');
  if ($('claim').value && !confirm('用当前选中文字替换输入框内容？')) return;
  $('claim').value = context?.text || ''; count(); $('claim').focus();
});
async function autoVerify(record){
  if(busy)return;
  if(!context?.url||context.url!==record.value.source.url)return notice('当前视频已变化，请重新分析当前视频。');
  const claims=automaticClaims(record.value);
  if(!claims.length)return notice(record.value.verification_plan?.status==='needs-details'?'已完成观点分析；补查需要：'+record.value.verification_plan.missing_information.join('、')+'。':record.value.verification_plan?.status==='clip-only'?'已完成观点与依据分析。':record.value.rejected_items?.some(x=>x.field==='candidate_claims')?'已完成片段分析，候选事实的引文校验未通过。':['debate','opinion'].includes(record.value.content_type)?'本片段以观点讨论为主，未提取到需要查证的核心事实。':'本片段没有识别出明确可核验的核心事实。');
  busyState(true);record.followupId ||= crypto.randomUUID();
  await submitVerification(claims.join('\n'),record.jobId,record.followupId,record);
}
async function submitVerification(text,originalId,id=crypto.randomUUID(),record){
  if(!await credential()){busyState(false);$('settings').open=true;notice('请先导入插件访问文件。');return;}
  busyState(true);
  if(record){record.followupId=id;await chrome.storage.session.set({['observation-'+windowId]:record});}
  job={id,text,context,originalId,automaticVideoCheck:Boolean(record?.value?.verification_plan),state:'submitting',startedAt:Date.now()};
  await persist();$('result').hidden=true;notice('已提取具体主张，正在检索材料并核验…');
  retry.hidden=true;
  try{await accept(await request('',{method:'POST',body:JSON.stringify(jobBody(job))}));}
  catch(error){
    if([401,403,413,422,429].includes(error.status)){job.state='rejected';job.result={detail:error.message};await persist();busyState(false);}
    notice(error.message+'。未自动重发；请查询原任务状态。');$('result').hidden=false;
  }
}
$('check-form').addEventListener('submit', async event => {
  event.preventDefault(); if (busy || !$('confirm').checked || needsOriginal()) return;
  if (!await credential()) { $('settings').open = true; notice('请先导入插件访问文件，再发起核验。'); return; }
  job = {id: crypto.randomUUID(), text: $('claim').value.trim(), context, originalId:!textOnly.checked?observation?.jobId:undefined, state:'submitting', startedAt:Date.now()};
  if (!job.text) return;
  await persist(); busyState(true); $('result').hidden = true; notice('正在提交你确认的主张…');
  $('checked-claim').textContent = job.text;
  for (const id of ['verdict','conclusion','scope','source-count','result-time']) $(id).textContent = '';
  for (const id of ['claim-results','sources','gaps','trace']) $(id).replaceChildren();
  retry.hidden = true;
  try { await accept(await request('', {method:'POST', body:JSON.stringify(jobBody(job))})); }
  catch (error) {
    if ([401,403,413,422,429].includes(error.status)) { job.state = 'rejected'; job.result = {detail:error.message}; await persist(); busyState(false); }
    notice(error.message + '。未自动重发。可使用下方查询按钮确认同一任务状态。'); $('result').hidden = false;
  }
});
$('refresh').addEventListener('click', poll);
retry.addEventListener('click', async () => {
  if (!job) return;
  retry.hidden = true; busyState(true);
  try { await accept(await request('', {method:'POST', body:JSON.stringify(jobBody(job))})); }
  catch (error) { notice('仍未确认任务提交状态：' + error.message + '。请继续查询原任务。'); }
});
$('save-credential').addEventListener('click', async () => {
  const value = $('credential').value.trim(); if (value.length < 32 || /\s/.test(value)) return notice('插件凭证格式不正确。请使用独立的插件访问文件。');
  await chrome.storage.session.set({credential:value}); $('credential').value = ''; $('settings').open = false; await updateCredentialState(); notice('插件凭证已保存到本次浏览器会话。'); if (job && !['done','failed','interrupted','rejected'].includes(job.state)) poll();
});
$('credential-file').addEventListener('change', async event => {
  const file = event.target.files?.[0]; if (!file) return;
  if (file.size > 256) { event.target.value = ''; return notice('请选择插件专用的短文本访问文件。'); }
  $('credential').value = (await file.text()).trim(); event.target.value = '';
  $('save-credential').click();
});
$('forget').addEventListener('click', async () => { clearTimeout(timer); await chrome.storage.session.remove('credential'); $('credential').value = ''; await updateCredentialState(); notice('本次会话的插件凭证已忘记。'); });
async function init() {
  if (!globalThis.chrome?.storage?.session) { notice('这是插件界面预览。请在Chrome或Edge中加载插件后使用。'); $('submit').disabled = true; return; }
  windowId = (await chrome.windows.getCurrent()).id;
  const saved=await chrome.storage.session.get(['context-'+windowId,key(),'observation-'+windowId]);
  job=saved[key()];observation=saved['observation-'+windowId];showContext(saved['context-'+windowId]);if(observation)showObservation(observation);await updateCredentialState();
  chrome.storage.onChanged.addListener((changes, area) => { const next = changes['context-' + windowId]; if (area === 'session' && next) showContext(next.newValue); });
  if (job) {
    if(job.mode!=='observe-video'){$('claim').value=job.text;count();}
    if(job.state==='done'&&job.result){if(job.result.video_observation){const record={...observation,jobId:job.id,value:job.result.video_observation};showObservation(record);observation=context?.url&&context.url!==record.value.source.url?null:record;busyState(false);if(observation&&job.autoVerify)await autoVerify(record);}else render(job.result);}
    else if (['failed','interrupted','rejected'].includes(job.state)) {notice(job.result?.detail || '上次分析未完成。');$('result').hidden=false;await poll();}
    else { busyState(true); poll(); }
  }
}
init().catch(() => notice('插件初始化失败，请关闭侧栏后重新打开。'));
