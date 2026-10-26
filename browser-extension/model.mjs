export function safeUrl(value) {
  try { const url = new URL(value); return ['https:', 'http:'].includes(url.protocol) && !url.username && !url.password ? url.href : null; } catch { return null; }
}
export const roles = {'source-verifier': '来源核验', 'evidence-grader': '证链分级', 'contradiction-scout': '证链冲突'};
export const labels = {supported:'材料支持', unsupported:'材料不支持', overstated:'表述超出材料', contradicted:'存在反证', conflicting:'材料存在冲突', insufficient:'证据不足', opinion:'评价表达', unknown:'尚未判断'};
export function resultView(data) {
  if (data?.state !== 'completed' || !data.passport || typeof data.passport !== 'object') throw Error('任务没有返回有效结果，不能采用核验结论。');
  const p = data.passport, rows = p.batch ? (p.claim_results || []) : [p];
  const interpretations = rows.map(r => r.message_assessment?.interpretation).filter(Boolean);
  const incomplete = rows.some(r => r.semantic_review?.coverage_complete === false || r.semantic_review?.status === 'partial-model-suggestion' || r.semantic_review?.rejected_claims?.length);
  const sources = [], gaps = [], seen = new Set();
  for (const row of rows) {
    for (const source of row.public_retrieval?.sources || []) {
      const url = safeUrl(source.url); if (!url || seen.has(url)) continue;
      seen.add(url); sources.push({...source, url});
    }
    for (const gap of row.message_assessment?.unresolved || []) if (typeof gap === 'string' && !gaps.includes(gap)) gaps.push(gap);
  }
  const hasSemantic = rows.some(r => ['model-suggestion', 'partial-model-suggestion'].includes(r.semantic_review?.status));
  const claims = rows.flatMap(row => row.semantic_review?.claims || []);
  const oneComplete = !incomplete && hasSemantic && claims.length === 1;
  const direct = oneComplete && typeof claims[0].explanation === 'string' ? claims[0].explanation.match(/^结论[：:]\s*([^\n]+)/u) : null;
  const readFailed = interpretations.length === 1 && interpretations[0].code === 'execution-incomplete';
  return {
    title: incomplete ? '部分内容未完成核验' : (p.batch ? '分项核验结果' : interpretations[0]?.title || (oneComplete && labels[claims[0].status]) || '本次核验结果'),
    summary: readFailed ? '本次未能读取相关正文，暂时无法核验。' : direct?.[1] || (p.batch ? p.answer || interpretations.map(x => x.summary).join('\n\n') : interpretations[0]?.summary || p.answer) || '没有形成可展示的结论。',
    claims, sources, gaps,
    details: claims.map(row => ({...row, explanation: direct ? row.explanation.replace(/^结论[：:][^\n]*\n*/u, '') : row.explanation})),
    scope: readFailed ? '' : hasSemantic ? '基于本次取得的材料。' : '本次尚未完成内容核验。',
    trace: (data.partner_trace || []).filter(x => x.task_id), rootTask: data.leader_task_id || '', incomplete
  };
}
