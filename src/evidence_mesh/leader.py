"""AIP Leader orchestration for the three evidence Partners."""

import asyncio
from dataclasses import dataclass, replace
import json
import ssl
import uuid
from typing import Any
import time

import httpx

from acps_sdk.aip import TaskState, TextDataItem
from acps_sdk.aip.aip_rpc_client import AipRpcClient

from .amp_observability import AmpObservability
from .contracts import MISSING_SOURCE_EXCERPT, request_from_json, request_json as serialize_request
from .models import SourceRef
from .message_result import assess_public_message
from .caller_document import numbered_claims
from .human_result import human_summary
from .text_comparison import compare_text
from .semantic_review import SemanticReviewer, run_semantic_review, render_review, semantic_decision, bind_source_quotes
from .intent import analyze_request, safe_utterance
from .rule_signals import effective_contradiction_status, rule_signal_explanation
from .product_presentation import read_product


@dataclass(frozen=True, slots=True)
class PartnerTarget:
    name: str
    url: str
    transport: httpx.AsyncBaseTransport | None = None
    leader_aic: str = "evidence-audit-leader"
    expected_partner_aic: str | None = None
    identity_binding_enabled: bool = False
    ssl_context: ssl.SSLContext | None = None


async def audit_claim(
    request_json: str,
    targets: list[PartnerTarget],
    amp: AmpObservability | None = None,
    *, _allow_batch: bool = True, semantic_reviewer: SemanticReviewer | None = None,
    external_collaborator=None, collaboration_root: str | None = None,
) -> dict[str, Any]:
    """Delegate one claim in parallel and return a fail-closed Evidence Passport."""
    expected = {"source-verifier", "evidence-grader", "contradiction-scout"}
    names = {target.name for target in targets}
    if names != expected or len(targets) != len(expected):
        raise ValueError(f"targets must be exactly {sorted(expected)}; got {sorted(names)}")

    request = request_from_json(request_json)
    from .external_consultation import matches_fixed_public_request
    public_match=matches_fixed_public_request(request,external_collaborator)
    external_only=(external_collaborator is not None and
        getattr(external_collaborator,'config',{}).get('external_only_auto_routes') is True)
    if request.task_type == 'external_consultation' or (public_match and external_only):
        from .external_consultation import consult_external
        return await consult_external(request, external_collaborator)
    if public_match:
        from .hybrid_collaboration import audit_with_supplement
        return await audit_with_supplement(
            replace(request,claim_id=collaboration_root or request.claim_id),external_collaborator,
            lambda:audit_claim(request_json,targets,amp,_allow_batch=_allow_batch,
                semantic_reviewer=semantic_reviewer,external_collaborator=None,
                collaboration_root=collaboration_root))
    claims = numbered_claims(request.claim_text) if _allow_batch else []
    if claims:
        rows = []
        # Sequential bounded batches prevent a 20-claim request fanning out at once.
        for index, claim in enumerate(claims, 1):
            item = replace(request, claim_text=claim, claim_id=f'{request.claim_id}-{index}')
            rows.append(await audit_claim(serialize_request(item), targets, amp, _allow_batch=False,
                                          semantic_reviewer=semantic_reviewer,
                                          external_collaborator=external_collaborator,
                                          collaboration_root=f'{collaboration_root or request.claim_id}-{index}'))
        precedence = ['conflicting', 'incomplete', 'no-evidence', 'needs-review', 'supported']
        if semantic_reviewer is not None:
            precedence = ['incomplete', 'conflicting', 'no-evidence', 'needs-review', 'supported']
        result = {'schema_version': '1.0', 'product_type': 'evidence-passport',
            'claim_id': request.claim_id, 'batch': True, 'claim_results': rows,
            'decision': next(d for d in precedence if any(r['decision'] == d for r in rows)),
            'atomic_claims': [dict(claim_id=r['claim_id'], original_span=r['checked_claim']) for r in rows],
            'task_ids': {}, 'partner_products': {},
            'risk_flags': sorted({flag for row in rows for flag in row['risk_flags']}),
            'missing_information': sorted({v for row in rows for v in row['missing_information']})}
        result['human_summary'] = human_summary(result)
        result['answer'] = '\n\n'.join(f'{i}. {row["answer"]}' for i,row in enumerate(rows, 1))
        result['safe_utterance'] = result['human_summary']
        if semantic_reviewer is not None:
            result['decision_scope'] = 'supplied-text-only-not-fact-authentication'
            result['human_summary'] = result['answer']
            result['safe_utterance'] = result['answer']
        return result
    analysis = analyze_request(request)
    declared = request.task_type.strip().lower().replace("-", "_")
    # Legacy/auto requests retain the complete audit. Explicit modes opt in
    # to lightweight routing without changing the caller's evidence contract.
    routes = {
        "intent_and_claims": set(),
        "answer_grounding_check": {"source-verifier", "evidence-grader"},
        "claim_boundary_check": {"evidence-grader", "contradiction-scout"},
        "cross_text_conflict": {"source-verifier", "contradiction-scout"},
    }
    required = routes.get(declared, expected)
    selected = [target for target in targets if target.name in required]
    # Missing-material flow is sequential: source acquisition must happen
    # before graders receive text. Existing supplied-material flow is unchanged.
    acquired = None
    if request.source_excerpt == MISSING_SOURCE_EXCERPT and 'source-verifier' in required:
        source_target = next(t for t in selected if t.name == 'source-verifier')
        try:
            acquired = await _call_partner(source_target, request_json, amp)
        except Exception as exc:
            acquired = exc
        if isinstance(acquired, dict) and acquired['state'] == TaskState.Completed.value:
            retrieval = acquired['product'].get('retrieval', {})
            if retrieval.get('status') == 'needs-clarification':
                intake = retrieval.get('message_intake', {})
                questions = intake.get('questions', [])
                if (intake.get('clarification_required') is True and isinstance(questions, list)
                        and questions and all(isinstance(q, str) and q.strip() for q in questions)):
                    answer = '\n'.join(questions) + '\n本次尚未检索或核验消息。'
                    return {
                        'schema_version': '1.0', 'product_type': 'evidence-passport',
                        'claim_id': request.claim_id, 'checked_claim': request.claim_text,
                        'decision': 'needs-review', 'decision_scope': 'clarification-only',
                        'task_type': analysis['task_type'], 'intent': analysis['intent'],
                        'atomic_claims': analysis['atomic_claims'],
                        'missing_information': ['entity identity'], 'clarification_required': True,
                        'message_intake': intake, 'public_retrieval': retrieval,
                        'task_ids': {'source-verifier': acquired['task_id']},
                        'partner_products': {'source-verifier': acquired['product']},
                        'routing': {'selected_partners': ['source-verifier'],
                                    'skipped_partners': ['evidence-grader', 'contradiction-scout'],
                                    'scope': 'clarification-only',
                                    'unperformed_checks': sorted(expected)},
                        'risk_flags': ['claim:not-inspected-ambiguous-entity'],
                        'semantic_review': {'status': 'not-inspected'},
                        'source_authenticity_verified': False,
                        'answer': answer, 'human_summary': answer, 'safe_utterance': answer,
                    }
            pages = retrieval.get('sources', [])
            if (retrieval.get('status') == 'retrieved' and 1 <= len(pages) <= 3
                    and acquired['product'].get('output_assessment', {}).get('material_available') is not False):
                # Keep provenance attached to each excerpt. No snippet fallback.
                if all(isinstance(p, dict) and isinstance(p.get('text'), str)
                       and 40 <= len(p['text']) <= 5000 and p.get('source_id')
                       and p.get('url', '').startswith('https://') for p in pages):
                    material = '\n\n'.join(p['text'] for p in pages)
                    request = replace(request, source_excerpt=material,
                        source=SourceRef('retrieved-bundle', '自动检索的公开网页，真实性待核验',
                            json.dumps([{'source_id': p['source_id'], 'url': p['url'],
                                         'fetched_at': p.get('fetched_at'), 'published_at': p.get('published_at'),
                                         'page_metadata_hints': p.get('page_metadata_hints', [])[:16],
                                         'publication_date_conflict': p.get('publication_date_conflict', False),
                                         'source_review': next((s for s in retrieval.get('source_review', {}).get('sources', [])
                                                                if s.get('source_id') == p['source_id']), {}),
                                         'source_relations': [r for r in retrieval.get('source_relations', [])[:3]
                                                             if r.get('from_url') == p['url']
                                                             or r.get('to_url') == p['url']],
                                         'independence': 'unknown'} for p in pages], ensure_ascii=False)))
                    request_json = serialize_request(request)
        selected = [t for t in selected if t.name != 'source-verifier']
    results = await asyncio.gather(
        *(_call_partner(target, request_json, amp) for target in selected),
        return_exceptions=True,
    )
    if acquired is not None:
        selected.insert(0, next(t for t in targets if t.name == 'source-verifier'))
        results.insert(0, acquired)

    products: dict[str, dict[str, Any]] = {}
    task_ids: dict[str, str] = {}
    risks: list[str] = []

    for target, result in zip(selected, results, strict=True):
        if isinstance(result, Exception):
            risks.append(f"{target.name}:call-failed:{type(result).__name__}")
            continue
        task_ids[target.name] = result["task_id"]
        if result["state"] != TaskState.Completed.value:
            risks.append(f"{target.name}:state-{result['state']}")
            continue
        products[target.name] = result["product"]

    decision = _decide(products, risks, required)
    result = {
        "schema_version": "1.0",
        "product_type": "evidence-passport",
        "claim_id": request.claim_id,
        "checked_claim": request.claim_text,
        "decision": decision,
        "task_type": analysis["task_type"],
        "intent": analysis["intent"],
        "atomic_claims": analysis["atomic_claims"],
        "missing_information": analysis["missing_information"],
        "clarification_required": analysis["clarification_required"],
        "routing": {
            "selected_partners": sorted(required),
            "skipped_partners": sorted(expected - required),
            "scope": "analysis-only" if not required else "scoped-audit",
            "unperformed_checks": sorted((expected - required) | {
                name for name in required if name not in products or
                products[name].get('input_assessment', {}).get('inspection_performed') is False}),
        },
        "safe_utterance": (
            f"仅完成意图与主张解析，以下内容尚未核验：{request.claim_text}"
            if not required else
            f"规则识别到有限或条件性支持的线索，仍需复核：{request.claim_text}"
            if 'claim:evidence-conditional' in risks else safe_utterance(request.claim_text, decision)
        ),
        "risk_flags": sorted(risks),
        "task_ids": task_ids,
        "partner_products": products,
    }
    result['human_summary'] = human_summary(result)
    result['text_comparison'] = compare_text(request.claim_text, request.source_excerpt)
    if not required or decision == 'incomplete':
        result['text_comparison']['status'] = 'not-inspected'
        result['text_comparison']['answer'] = '本次核验未完成，不能给出核验结论。请查看执行详情并重试。'
        result['text_comparison']['suggested_wording'] = None
    result['answer'] = result['text_comparison']['answer']
    scout = products.get('contradiction-scout', {})
    if scout:
        result['rule_signal_assessment'] = {
            'reported_status': scout.get('payload', {}).get('status'),
            'effective_status': effective_contradiction_status(scout),
            'basis': 'leader-weak-rule-signal-boundary-v1',
            'independent_fact_verification': False,
        }
    explanation = rule_signal_explanation(scout)
    if result['text_comparison']['status'] == 'undetermined' and explanation:
        result['answer'] += '\n' + explanation
        result['safe_utterance'] = result['answer']
    result['semantic_review'] = {'status': 'disabled' if semantic_reviewer is None else 'not-inspected'}
    if required and decision != 'incomplete' and semantic_reviewer is not None:
        review = await run_semantic_review(request.claim_text, request.source_excerpt, semantic_reviewer,
            source_metadata={**{key: getattr(request.source, key) for key in ('source_id', 'title', 'locator')},
                **({'video_context':request.goal} if request.goal.startswith('原视频核验上下文（') else {})},
            source_pages=products['source-verifier']['retrieval']['sources']
                if acquired is not None and request.source.source_id == 'retrieved-bundle' else None)
        if acquired is not None and request.source.source_id == 'retrieved-bundle':
            review = bind_source_quotes(review, products['source-verifier']['retrieval']['sources'])
        result['semantic_review'] = review
        if review['status'] in ('model-suggestion', 'partial-model-suggestion') or review.get('rejected_claims'):
            result['answer'] = render_review(review)
        elif review['status'] in ('failed-or-invalid', 'input-limit'):
            result['answer'] = '语义核验未完成；以下仅为原有有限规则结果，不是完整语义判断。\n' + result['answer']
    if semantic_reviewer is not None and required:
        result['legacy_rule_assessment'] = {
            'decision': result['decision'], 'risk_flags': result['risk_flags'],
            'human_summary': result['human_summary'], 'safe_utterance': result['safe_utterance'],
            'atomic_claims': result['atomic_claims']}
        result['decision'] = ('incomplete' if decision == 'incomplete'
                              else semantic_decision(result['semantic_review']))
        result['decision_scope'] = 'supplied-text-only-not-fact-authentication'
        result['source_authenticity_verified'] = False
        result['risk_flags'] = [r for r in result['risk_flags']
                                if not r.startswith('claim:') or r == 'claim:source-not-verified']
        if 'claim:source-not-verified' not in result['risk_flags']:
            result['risk_flags'].append('claim:source-not-verified')
        review = result['semantic_review']
        result['decision_basis'] = 'semantic-review-with-source-authenticity-unverified'
        result['semantic_assessment'] = {
            'status': review['status'], 'decision': result['decision'],
            'coverage_complete': review.get('coverage_complete', False),
            'claim_statuses': [row['status'] for row in review.get('claims', [])],
            'scope': 'supplied-material-only',
        }
        if review.get('claims'):
            result['atomic_claims'] = [
                {'claim_id': f'semantic-claim-{index}', 'original_span': row['claim_span'],
                 'normalized_claim': row['claim_span'], 'claim_type': row['kind'],
                 'checkability': 'subjective' if row['kind'] == 'opinion' else 'requires-evidence',
                 'assessment_status': row['status'], 'basis': 'semantic-review'}
                for index, row in enumerate(review['claims'], 1)]
        if result['decision'] == 'incomplete':
            result['risk_flags'].append('semantic:incomplete')
        result['human_summary'] = result['answer']
        result['safe_utterance'] = result['answer']
    if acquired is not None and products.get('source-verifier', {}).get('retrieval', {}).get('status') not in (None, 'disabled', 'not-requested'):
        retrieval = products.get('source-verifier', {}).get('retrieval', {})
        result['public_retrieval'] = retrieval
        result['decision_scope'] = 'retrieved-public-text-not-independent-fact-authentication'
        result['source_authenticity_verified'] = False
        result['risk_flags'].append('public-sources:authenticity-and-independence-unverified')
        if request.source_excerpt != MISSING_SOURCE_EXCERPT:
            result['answer'] = ('已自动检索并读取公开网页。以下判断仅针对读到的材料；'
                                '尚未证明消息真实、来源独立或检索完整。\n' + result['answer'])
            result['answer'] += '\n\n本次读取的来源：\n' + '\n'.join(
                f"{p.get('title') or '未提取到标题'}：{p['url']}（抓取时间：{p.get('fetched_at', '未知')}）"
                for p in retrieval.get('sources', []))
            if any(p.get('publication_date_conflict') for p in retrieval.get('sources', [])):
                result['answer'] += '\n注意：有页面的发布日期线索互相不一致，未采用单一日期作为确定依据。'
            if retrieval.get('source_relations'):
                result['answer'] += '\n\n出处追溯线索：\n' + '\n'.join(
                    f"{r['from_url']} 在页面中指向 {r['to_url']}；已读取目标页，"
                    '首发身份待确认。'
                    for r in retrieval['source_relations'])
            if result['decision'] == 'supported':
                result['decision'] = 'needs-review'
        else:
            from .message_result import retrieval_progress
            result['answer'] = (retrieval_progress(retrieval) +
                                '暂未形成核验结论。')
        intake = retrieval.get('message_intake', {})
        if intake:
            result['message_intake'] = intake
            result['clarification_required'] = intake.get('clarification_required', False)
            if retrieval.get('status') == 'needs-clarification':
                result['answer'] = '\n'.join(intake.get('questions', [])) + '\n本次尚未检索或核验消息。'
            if intake.get('hints'):
                result['answer'] += '\n' + '\n'.join(intake['hints'])
        result['message_assessment'] = assess_public_message(result['semantic_review'], retrieval, intake)
        interpretation = result['message_assessment']['interpretation']
        result['answer'] = (interpretation['title'] + '\n' + interpretation['summary'] +
                            '\n\n执行与逐项说明：\n' + result['answer'])
        if retrieval.get('search_complete') is False:
            result['answer'] += '\n检索限制：部分查询或引擎失败，本次只依据已读取的材料，支持与反证检索尚未完整完成。'
        source_review = result['message_assessment']['source_review']
        if any(len(group) > 1 for group in source_review['observed_dependency_groups']):
            result['answer'] += '\n来源审查：部分页面有正文或出处关联，不能作为多份独立证据计数。'
        if any(s['anonymous_attribution_marker'] for s in source_review['sources']):
            result['answer'] += '\n来源审查：页面含匿名或网传表述；这可能也是辟谣引用，尚未据此判定消息真假。'
        result['human_summary'] = result['answer']
        result['safe_utterance'] = result['answer']
    if external_collaborator is not None:
        try:
            external = await external_collaborator.review(
                replace(request, claim_id=collaboration_root or request.claim_id), result)
        except Exception as exc:
            external = {'status': 'unavailable', 'invoked': False, 'error_type': type(exc).__name__}
        result['external_collaboration'] = external
        for peer in external.get('reviews', [external]):
            if not peer.get('task_id'):
                continue
            result['answer'] += '\n\n外部独立复核：' + peer.get('partner_name', '外部伙伴')
            if peer.get('status') == 'grounded-suggestions':
                result['answer'] += '\n外部复核意见：\n'
                result['answer'] += '\n'.join(f'• {i["explanation"]}（材料原文：{i["quote"]}）' for i in peer['issues'])
            elif peer.get('status') == 'no-additional-issues-reported':
                result['answer'] += '\n伙伴未报告额外问题。'
            elif peer.get('status') in ('pending', 'unknown-outcome', 'completion-outcome-unknown'):
                result['answer'] += '\n伙伴尚未交付完成结果，本次主体分析未采用其意见。'
            else:
                result['answer'] += '\n本次未取得合格的外部复核意见，以上主体分析未将其作为依据。'
            result['human_summary'] = result['answer']
            result['safe_utterance'] = result['answer']
    return result


async def _call_partner(
    target: PartnerTarget,
    request_json: str,
    amp: AmpObservability | None = None,
) -> dict[str, Any]:
    session_id = f"session-{uuid.uuid4()}"
    task_id = f"task-{uuid.uuid4()}"
    started_at = time.monotonic() * 1000
    status_code = 500
    client = AipRpcClient(
        target.url,
        target.leader_aic,
        transport=target.transport,
        ssl_context=target.ssl_context,
        expected_partner_aic=target.expected_partner_aic,
        identity_binding_enabled=target.identity_binding_enabled,
    )
    try:
        started = await client.start_task(session_id, request_json, task_id=task_id)
        if started.status.state == TaskState.Failed:
            status_code = 422
            return {
                "task_id": task_id,
                "state": TaskState.Failed.value,
                "product": {},
            }
        if started.status.state != TaskState.AwaitingCompletion:
            status_code = 409
            return {
                "task_id": task_id,
                "state": started.status.state.value,
                "product": {},
            }
        completed = await client.complete_task(task_id, session_id)
        product = read_product(completed.products)
        status_code = 200
        return {
            "task_id": task_id,
            "state": completed.status.state.value,
            "product": product,
        }
    finally:
        await client.close()
        if amp is not None:
            await amp.emit_access(
                caller_aic=target.leader_aic,
                caller_service="evidence-audit-leader",
                callee_aic=target.expected_partner_aic,
                callee_service=target.name,
                task_id=task_id,
                session_id=session_id,
                url=target.url,
                duration_ms=(time.monotonic() * 1000) - started_at,
                status_code=status_code,
            )


def _decide(
    products: dict[str, dict[str, Any]], risks: list[str],
    required: set[str] | None = None,
) -> str:
    required = required if required is not None else {
        "source-verifier", "evidence-grader", "contradiction-scout"
    }
    if risks or not required.issubset(products):
        return "incomplete"

    if not required:
        risks.append("claim:analysis-only-not-verified")
        return "needs-review"

    source_status = products.get("source-verifier", {}).get("payload", {}).get("status")
    evidence_level = products.get("evidence-grader", {}).get("payload", {}).get("level")
    contradiction = products.get("contradiction-scout", {}).get("payload", {}).get("status")

    statuses = {
        "source-verifier": (source_status, {"verified", "incomplete", "invalid"}),
        "evidence-grader": (evidence_level, {"direct", "indirect", "conditional", "unsupported", "conflicting"}),
        "contradiction-scout": (contradiction, {"none-found", "possible", "confirmed"}),
    }
    for name in sorted(required):
        value, allowed = statuses[name]
        if not isinstance(value, str) or value not in allowed:
            risks.append(f"{name}:invalid-product-status")
    if risks:
        return "incomplete"

    if any(products[name].get('input_assessment', {}).get('evidence_provided') is False
           for name in required if name != 'source-verifier'):
        risks.append('claim:not-inspected-missing-evidence')
        return 'no-evidence'

    contradiction = effective_contradiction_status(products.get('contradiction-scout', {}))

    if contradiction == "confirmed" or evidence_level == "conflicting":
        risks.append("claim:confirmed-contradiction")
        return "conflicting"
    if contradiction == "possible":
        risks.append("claim:possible-contradiction")
        return "needs-review"
    # A partial check must not masquerade as a complete supported passport.
    if len(required) < 3:
        if evidence_level == "unsupported":
            risks.append("claim:unsupported")
            return "no-evidence"
        risks.append("claim:partial-audit-not-full-verification")
        return "needs-review"
    if source_status != "verified":
        risks.append("claim:source-not-verified")
        return "needs-review"
    if evidence_level == "direct":
        return "supported"
    if evidence_level == "unsupported":
        risks.append("claim:unsupported")
        return "no-evidence"

    risks.append(f"claim:evidence-{evidence_level}")
    return "needs-review"
