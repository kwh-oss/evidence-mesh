// Focused DOM-adapter test: pending recovery must never POST a new /audit.
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const html = fs.readFileSync('src/evidence_mesh/web_message.html', 'utf8');
const block = html.slice(html.indexOf('let pendingResume=null;'), html.indexOf("el('form').addEventListener('submit'"));
const elements = new Map();
const calls = [];
const el = id => {
  if (!elements.has(id)) elements.set(id, {hidden: true, disabled: false, value: '', addEventListener(event, callback) {this[event] = callback;}});
  return elements.get(id);
};
const task = 'web-test-11111111-1111-4111-8111-111111111111';
const pending = {state:'pending',recoverable:true,recovery_url:`/audit/${task}/resume`,leader_task_id:task};
let next = pending;
let rendered;
const context = vm.createContext({el, JSON, Error, Boolean, fetch:async(url, options)=>{
  calls.push({url,method:options.method,body:options.body});
  return {ok:true,json:async()=>next};
},renderResult:data=>{rendered=data;}});
vm.runInContext(block, context);
context.pending = pending;
vm.runInContext('acceptAudit(pending)', context);
assert.equal(el('submit').disabled, true);
assert.equal(el('resume').hidden, false);
(async()=>{
  await el('resume').click();
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, pending.recovery_url);
  assert.equal(calls[0].method, 'POST');
  assert.equal(calls[0].body, undefined);
  assert.equal(el('submit').disabled, true);
  next = {state:'completed',passport:{answer:'Recovered original result'}};
  await el('resume').click();
  assert.equal(rendered, next);
  assert.equal(el('submit').disabled, false);
  assert.equal(el('resume').hidden, true);
  assert(calls.every(call=>call.url!== '/audit'));
  console.log('PASS: pending and completed UI; recovery never submits a new audit');
})().catch(error=>{console.error(error);process.exitCode=1;});
