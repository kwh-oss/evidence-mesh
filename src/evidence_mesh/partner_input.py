"""Caller-friendly partner input, with explicit material-gap boundaries."""
from dataclasses import replace
import json

from .contracts import (
    MISSING_SOURCE_EXCERPT, ContradictionStatus, product_json,
    request_from_caller_text, request_from_json,
)
from .models import EvidenceLevel


def partner_request(text, *, default_claim_id):
    if not isinstance(text, str) or not text.strip():
        raise ValueError('nonempty text input required')
    try:
        if len(text.encode('utf-8')) > 64 * 1024:
            raise ValueError('input exceeds 64 KiB')
    except UnicodeEncodeError as exc:
        raise ValueError('invalid UTF-8 input') from exc
    from .collaboration_input import normalize_text_handoff
    text = normalize_text_handoff(text)
    try:
        value = json.loads(text)
    except RecursionError as exc:
        raise ValueError('JSON nesting exceeds parser limit') from exc
    except json.JSONDecodeError:
        if text.lstrip().startswith(('{', '[')):
            raise ValueError('malformed JSON input')
        return request_from_caller_text(text, default_claim_id=default_claim_id)
    if not isinstance(value, dict):
        raise ValueError('JSON input must be an object')
    from .collaboration_input import normalize_handoff
    value = normalize_handoff(value)
    text = json.dumps(value, ensure_ascii=False)
    # Validate source shape before either normalization path; do not turn a
    # malformed object into a processing error or invented source fields.
    for envelope in (value, *(value.get(k) for k in ('payload', 'input', 'data', 'request'))):
        if isinstance(envelope, dict) and 'source' in envelope and envelope['source'] is not None:
            if not isinstance(envelope['source'], dict):
                raise ValueError('source must be an object')
    if 'schema_version' in value and 'claim_text' in value and 'source_excerpt' in value:
        return request_from_json(text, default_claim_id=default_claim_id)
    return request_from_caller_text(text, default_claim_id=default_claim_id)


def partner_product(product_type, processor, request):
    evidence = request.source_excerpt != MISSING_SOURCE_EXCERPT
    payload = processor(request)
    if not evidence and product_type == 'evidence-finding':
        payload = replace(payload, level=EvidenceLevel.UNSUPPORTED,
            rationale='No supporting material was supplied; support strength was not inspected.', confidence=0.0)
    if not evidence and product_type == 'contradiction-check':
        payload = replace(payload, status=ContradictionStatus.NONE_FOUND,
            indicators=('not-inspected: supporting material is missing',))
    output = json.loads(product_json(product_type, payload))
    missing = []
    if not evidence:
        missing.append('source_excerpt')
    for field in ('source_id', 'title', 'locator'):
        if not getattr(request.source, field).strip():
            missing.append('source.' + field)
    output['input_assessment'] = {
        'evidence_provided': evidence, 'missing_fields': missing,
        'inspection_performed': evidence or product_type == 'source-check',
        'inspection_scope': ('source-field-completeness' if product_type == 'source-check'
                             else 'supplied-text-rules' if evidence else 'not-inspected'),
        'claim_verified': False,
        'interpretation': 'Rule output is not independent fact verification; none-found does not prove absence of conflict.',
    }
    output['collaboration'] = {
        'standalone_callable': True, 'requires_our_leader': False,
        'material_origin': ('caller-upstream-unverified' if request.source_excerpt.startswith('【调用方传入的上游产物')
                            else 'caller-supplied' if evidence else 'missing'),
        'next_action': 'inspect-supplied-material' if evidence else 'provide-material-and-start-new-task',
        'required_input': {'claim_text': '待核验的具体说法',
                           'source_excerpt': '实际原文或明确标为未认证的上游报告',
                           'source': {'source_id': '实际来源编号或链接', 'title': '实际标题', 'locator': '段落、页码或时间点'}},
        'upstream_example': {'claim': '活动对所有人免费', 'upstream_results': [
            {'title': '活动规则', 'text': '仅登记会员免费，其他人需购票。', 'locator': '参与条件'}]},
        'history_access': False, 'source_authenticity_verified': False,
    }
    from .partner_answer import partner_answer
    output['answer'], output['role_scope'] = partner_answer(product_type, request, output)
    return json.dumps(output, ensure_ascii=False, sort_keys=True)
