export function automaticClaims(observation){
  const plan=observation?.verification_plan;
  if(plan&&plan.status!=='search')return [];
  const rows=observation?.understanding_version==='video-understanding/2' ? observation.verification_targets||[] : observation?.candidate_claims||[];
  const claims=[...new Set(rows.slice(0,3).filter(r=>observation?.understanding_version!=='video-understanding/2'||(r.role==='core'&&r.kind==='fact'&&!['danmaku','uncertain'].includes(r.origin))).map(r=>String(r.text||'').trim()).filter(Boolean))];
  return claims.length&&plan?.question?[plan.question]:claims;
}
