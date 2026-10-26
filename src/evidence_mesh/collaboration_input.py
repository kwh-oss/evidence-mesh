"""Explicit upstream handoffs. Never recover unseen chat history or open URLs."""
import json
import re

UPSTREAM_KEYS = ('upstream_results', 'previous_results', 'upstream_products')


def split_scheduler_handoff(text):
    """Recognize the platform's appended block, never a marker inside a quote."""
    quoted = list(re.finditer(r'“[^”]*”|「[^」]*」|『[^』]*』|"[^"\n]*"', text))
    for match in re.finditer(r'\s+(DAG\s*指定的上游产物摘要\s*[:：])', text):
        if not any(q.start() <= match.start(1) < q.end() for q in quoted):
            head, tail = text[:match.start()].strip(), text[match.end():].strip()
            if head:
                return head, tail
    return text.strip(), ''


def _report_text(text):
    # Exact scheduler acknowledgements contain no material. Do not infer their
    # evidence value from length or from words such as "completed" in reports.
    status = r'(?:叮当)?(?:已完成协作规划并开始按\s*DAG\s*派发|已开始派发|已开始调度|已开始执行|已完成协作规划)[。.!！\s]*'
    return '' if re.fullmatch(status, text) else text


def normalize_text_handoff(text):
    head, tail = split_scheduler_handoff(text)
    from .caller_document import quoted_comparison
    comparison = quoted_comparison(head)
    if not tail and head == text.strip():
        return json.dumps(comparison, ensure_ascii=False) if comparison else text
    try:
        first = json.loads(head)
    except ValueError:
        first = comparison or {'claim_text': head}
    if not isinstance(first, dict):
        return text
    report = _report_text(tail)
    if report:
        first.setdefault('upstream_results', [])
        existing = first['upstream_results']
        first['upstream_results'] = (existing if isinstance(existing, list) else [existing]) + [{'report': report}]
    return json.dumps(normalize_handoff(first), ensure_ascii=False)


def retrieval_request(request):
    """A report may supply a fetch lead, never authenticated original text."""
    if not request.source_excerpt.startswith('【调用方传入的上游产物'):
        return request, None
    if request.task_type == 'supplied_material_only' or any(
            marker in constraint for constraint in request.constraints
            for marker in ('不联网', '禁止联网', 'no-network')):
        return request, None
    # Reviewing supplied wording is different from verifying the real-world
    # event behind a report. Do not erase a DAG report and replace it with an
    # unrelated web search when the assigned operation is text review.
    operation = str(request.goal or '') + '\n' + request.claim_text
    operation = re.sub(r'“[^”]*”|「[^」]*」|『[^』]*』|"[^"\n]*"', '', operation)
    review = request.task_type in ('cross_text_conflict', 'claim_boundary_check', 'answer_grounding_check') or bool(
        re.search(r'语义|含义.{0,8}(?:比较|比对|冲突)|一致性|审查现有|现有材料|上述材料|基于.{0,12}材料|两(?:句|段).{0,8}(?:矛盾|冲突|比较)', operation))
    acquire = bool(re.search(r'联网|检索|查找|核实出处|读取原始', operation))
    if review and not acquire:
        return request, {'report': request.source_excerpt,
            'trust': 'caller-upstream-unverified', 'used_as_primary_evidence': False,
            'used_as_supplied_material': True, 'seed_url': None,
            'acquisition': 'not-required-for-requested-text-review'}
    from dataclasses import replace
    from .contracts import MISSING_SOURCE_EXCERPT
    from .models import SourceRef
    from .public_evidence import public_url
    report = request.source_excerpt
    locator = ''
    for match in re.finditer(r'https://[^\s<>"，。；]+', report):
        try:
            locator = public_url(match[0].rstrip(')）]】、;'))
            break
        except ValueError:
            continue
    return replace(request, source_excerpt=MISSING_SOURCE_EXCERPT,
        source=SourceRef('caller:upstream-lead', '上游报告提供的未认证检索线索', locator)), {
            'report': report, 'trust': 'caller-upstream-unverified',
            'used_as_primary_evidence': False, 'seed_url': locator or None}


def material_text(value):
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        return '\n\n'.join(filter(None, (material_text(v) for v in value)))
    if not isinstance(value, dict):
        return ''
    # Status, task descriptions, titles and links alone are never evidence.
    for key in ('source_excerpt', 'excerpt', 'text', 'answer', 'report'):
        if key in value:
            text = material_text(value[key])
            if text:
                meta = {k: value[k] for k in ('source_id', 'title', 'url', 'locator', 'agent_aic')
                        if isinstance(value.get(k), str) and value[k].strip()}
                return (json.dumps(meta, ensure_ascii=False) + '\n' if meta else '') + text
    for key in ('sources', 'materials', 'dataItems'):
        if isinstance(value.get(key), list):
            return material_text(value[key])
    if isinstance(value.get('retrieval'), dict):
        return material_text(value['retrieval'])
    return ''


def normalize_handoff(value):
    """Only explicit handoff keys; a prior report is supplied text, not truth."""
    normalized = dict(value)
    for key in ('payload', 'input', 'data', 'request'):
        if isinstance(normalized.get(key), dict):
            inner = normalize_handoff(normalized[key])
            normalized[key] = inner
    if any(material_text(normalized.get(k)) for k in
           ('source_excerpt', 'evidence_excerpt', 'excerpt', 'evidence', 'context', 'materials')):
        return normalized
    texts = [material_text(normalized[k]) for k in UPSTREAM_KEYS if k in normalized]
    text = '\n\n'.join(filter(None, texts))
    if text:
        normalized['source_excerpt'] = '【调用方传入的上游产物；未独立认证，报告结论不等于事实】\n' + text
        normalized.setdefault('source', {'source_id': 'caller:upstream-report',
            'title': '调用方提供的上游报告（未独立认证）', 'locator': '上游报告正文'})
    return normalized


def command_text(command):
    from acps_sdk.aip import TextDataItem
    texts = [item.text for item in command.dataItems or []
             if isinstance(item, TextDataItem) and item.text.strip()]
    if not texts:
        raise ValueError('nonempty text input required')
    if sum(len(s.encode('utf-8')) for s in texts) > 64 * 1024:
        raise ValueError('input exceeds 64 KiB')
    texts[0] = normalize_text_handoff(texts[0])
    if len(texts) == 1:
        return texts[0]
    try:
        first = json.loads(texts[0])
    except ValueError:
        first = {'claim_text': texts[0]}
    if not isinstance(first, dict):
        raise ValueError('first text item must describe the claim')
    upstream = []
    for text in texts[1:]:
        try:
            value = json.loads(text)
        except ValueError:
            # Unlabelled follow-up instructions are not inferred as evidence.
            from .caller_document import document_sections
            section = document_sections(text)
            value = {'source_excerpt': section['source_excerpt']} if section and section.get('source_excerpt') else {}
        if isinstance(value, (dict, list)) and material_text(value):
            upstream.append(value)
    if upstream:
        existing = first.get('upstream_results', [])
        first['upstream_results'] = ([existing] if not isinstance(existing, list) else existing) + upstream
    return json.dumps(normalize_handoff(first), ensure_ascii=False)
