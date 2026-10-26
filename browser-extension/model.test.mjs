import test from 'node:test';
import assert from 'node:assert/strict';
import {safeUrl,resultView} from './model.mjs';
test('rejects credential URLs and executable links',()=>{
  for(const value of ['javascript:alert(1)','https://user:secret@example.org','file:///x']) assert.equal(safeUrl(value),null);
  assert.equal(safeUrl('https://example.org/a'),'https://example.org/a');
});
test('failed transport never becomes a conclusion',()=>{
  assert.throws(()=>resultView({state:'failed',passport:{answer:'untrusted success'}}));
});
test('partial coverage, independent sources, and actual tasks are preserved',()=>{
  const r=resultView({state:'completed',leader_task_id:'root',partner_trace:[{role:'a',task_id:'actual'},{role:'b'}],passport:{message_assessment:{interpretation:{title:'材料不足',summary:'缺少关键原文'},unresolved:['未找到首发']},semantic_review:{status:'partial-model-suggestion',coverage_complete:false,claims:[]},public_retrieval:{sources:[{url:'javascript:alert(1)'},{url:'https://example.org/a',title:'<script>bad</script>'},{url:'https://example.org/a'}]}}});
  assert.equal(r.incomplete,true); assert.equal(r.title,'部分内容未完成核验');
  assert.equal(r.sources.length,1); assert.equal(r.sources[0].title,'<script>bad</script>');
  assert.equal(r.trace.length,1); assert.equal(r.summary,'缺少关键原文');
});
test('rule-only output does not claim semantic verification',()=>{
  assert.match(resultView({state:'completed',passport:{answer:'rule'}}).scope,/尚未完成内容核验/);
});
test('single complete judgment leads with the existing conclusion, without repeating the report',()=>{
  const r=resultView({state:'completed',passport:{answer:'长报告不应重复',semantic_review:{status:'model-suggestion',coverage_complete:true,claims:[{status:'contradicted',explanation:'结论：该说法与材料相矛盾。\n依据：仅限周三。\n边界：其他日期未知。'}]}}});
  assert.equal(r.summary,'该说法与材料相矛盾。');assert.equal(r.title,'存在反证');
  assert.equal(r.details[0].explanation,'依据：仅限周三。\n边界：其他日期未知。');
  assert.match(r.claims[0].explanation,/^结论/);
});
