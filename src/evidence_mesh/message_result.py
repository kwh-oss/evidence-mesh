"""Aggregate anchored public-material assessments without inventing certainty."""
from urllib.parse import urlsplit
from .source_review import review_sources


def retrieval_progress(retrieval):
    """Describe observed stages, without treating search hits as evidence."""
    searches = len(retrieval.get('search_diagnostics', []))
    attempts = retrieval.get('page_attempt_count', len(retrieval.get('leads', [])))
    sources = len(retrieval.get('sources', []))
    if searches:
        search = f'已收到{searches}轮联网搜索返回'
        if retrieval.get('search_complete') is False:
            search += '，部分查询或引擎失败'
    elif retrieval.get('search_complete') is True:
        search = '搜索阶段已完成'
    else:
        search = '搜索阶段未确认完成'
    text = f'{search}；尝试读取{attempts}个网页，取得{sources}份可读正文。'
    if not sources:
        if any(x.get('stage') == 'page' for x in retrieval.get('failures', [])):
            text += '候选网页读取失败，尚无正文可供核验。'
        else:
            text += '尚未取得可用于核验的正文。'
    return text


def interpret_public_result(review, retrieval, claims, complete):
    """Keep execution limits separate from anchored material-level conclusions."""
    sources = retrieval.get('sources', [])
    failures = [x for x in retrieval.get('failures', [])
                if x.get('stage') in ('page', 'search', 'search-engine')]
    execution = ('partial' if failures and sources else 'failed' if failures else
                 'bounded-search-completed' if retrieval.get('search_complete') is True else 'unconfirmed')
    statuses = {c['status'] for c in claims if c['status'] != 'opinion'}
    if not sources and failures:
        code, title = 'execution-incomplete', '搜索或网页读取未完成'
        summary = '本次未能读取相关正文，暂时无法核验。'
    elif not sources and retrieval.get('search_complete') is True:
        code, title = 'no-evidence-found', '本次限定范围检索暂未找到可用依据'
        summary = '本次检索暂未找到直接依据。'
    elif not sources:
        code, title = 'undetermined', '尚未取得可供核验的正文'
        summary = '尚未取得可用正文，暂时无法核验。'
    elif not claims and review.get('failure_stage') == 'provider':
        code, title = 'analysis-failed', '本次未生成核验结论：模型分析未完成'
        summary = {
            'model-budget-exhausted': '已读取网页，但模型测试调用额度已用尽，未生成分析结论。',
            'model-budget-unavailable': '已读取网页，但模型调用额度暂时无法核验，未生成分析结论。',
            'model-timeout': '已读取网页，但模型分析超时，未生成分析结论。',
        }.get(review.get('failure_code'), '已读取网页，但模型服务调用失败，未生成分析结论。')
    elif not claims and review.get('failure_stage') == 'output-validation':
        code, title = 'analysis-rejected', '本次未生成可采用的核验结论'
        summary = '模型输出或引文未通过校验，暂未形成结论。'
    elif 'contradicted' in statuses:
        code, title = 'counterevidence', '发现与部分主张相反的材料（模型建议）'
        summary = '材料中有与该说法相反的信息，依据如下。'
    elif 'overstated' in statuses:
        code, title = 'beyond-evidence', '部分表述可能超出了材料依据（模型建议）'
        summary = '原说法超出了材料中的适用范围，具体差异如下。'
    elif claims and not complete:
        code, title = 'partial-assessment', '仅完成部分内容核验'
        summary = '已完成的判断如下，其余内容尚未核验。'
    elif complete and statuses == {'supported'}:
        code, title = 'material-support', '本次材料提供支持（模型建议）'
        summary = '本次材料支持该说法，依据如下。'
    elif complete and statuses == {'unsupported'}:
        code, title = 'no-direct-support', '本次材料未提供直接支持（模型建议）'
        summary = '已读取相关材料，暂未找到支持该说法的直接依据。'
    elif complete and 'uncertain' in statuses:
        code, title = 'assessed-uncertain', '已分析材料，结论仍有不确定性'
        summary = '已完成材料分析，部分问题仍缺少明确依据。'
    elif sources and not claims:
        code, title = 'material-not-assessed', '已读取材料，尚未完成内容核验'
        summary = '已读取正文，内容分析尚未完成。'
    elif complete and not statuses:
        code, title = 'opinion', '观点表达，不能直接作事实真伪判断'
        summary = '这是评价性表述，以下核对其涉及的具体事实。'
    else:
        code, title = 'undetermined', '现有材料仍不足以形成结论'
        summary = '现有材料不足以形成明确结论。'
    direct_answer = None
    if complete and sources and claims:
        conclusions = []
        for claim in claims:
            lines = claim['explanation'].strip().splitlines()
            first = lines[0].strip() if lines else ''
            if first.startswith(('结论：', '结论:')) and 0 < len(first[3:].strip()) <= 160:
                conclusions.append(first[3:].strip())
        if len(conclusions) == len(claims):
            direct_answer = (conclusions[0] if len(conclusions) == 1 else
                             '\n'.join(f'{i}. {text}' for i, text in enumerate(conclusions, 1)))
            title = '简要结论（模型建议）'
            if code == 'opinion':
                summary = '以下核对该评价所依赖的事实及其证据；不将宣传标签当作已经证实的事实。'
            summary = direct_answer + '\n\n' + summary
    if failures and sources:
        summary += ' 部分搜索或网页读取失败。'
    elif retrieval.get('search_complete') is False and sources:
        summary += ' 部分检索未完成。'
    if claims and not complete and code in ('counterevidence', 'beyond-evidence'):
        summary += ' 其余内容尚未完整核验。'
    return {'schema_version': 'result-interpretation/1', 'code': code, 'title': title,
            'summary': summary, 'execution_status': execution,
            'analysis_status': 'failed' if review.get('failure_stage') else 'completed' if complete else 'incomplete',
            'direct_answer': direct_answer,
            'background_only_established': False, 'claim_verified': False}


def assess_public_message(review, retrieval, intake=None):
    intake = intake or {}
    sources = retrieval.get('sources', [])
    pages_by_id = {}
    for page in sources:
        if isinstance(page, dict) and page.get('source_id'):
            pages_by_id.setdefault(page['source_id'], []).append(page)
    rows = review.get('claims', [])
    accepted = []
    for row in rows:
        if not isinstance(row, dict) or row.get('status') not in ('supported', 'contradicted', 'overstated', 'unsupported', 'opinion', 'uncertain'):
            continue
        quotes = row.get('quotes', [])
        if not isinstance(quotes, list):
            continue
        anchored = True
        for quote in quotes:
            if not isinstance(quote, dict):
                anchored = False
                break
            matches = pages_by_id.get(quote.get('source_id'), [])
            text = quote.get('text')
            if (len(matches) != 1 or not isinstance(text, str) or not text.strip()
                    or not isinstance(matches[0].get('text'), str)
                    or matches[0]['text'].count(text) != 1):
                anchored = False
                break
        if not anchored:
            continue
        if row.get('status') in ('supported', 'contradicted', 'overstated') and not quotes:
            continue
        if not isinstance(row.get('claim_span'), str) or not row['claim_span'].strip() or not isinstance(row.get('explanation'), str):
            continue
        accepted.append({'claim': row['claim_span'], 'status': row['status'],
                         'explanation': row['explanation'], 'quotes': quotes})
    complete = bool(accepted) and len(accepted) == len(rows) and review.get('coverage_complete') is True
    statuses = {row['status'] for row in accepted if row['status'] != 'opinion'}
    if not accepted:
        status, headline = 'unverified', '目前无法确认这条消息。'
    elif not complete:
        status, headline = 'partial', '仅完成部分内容核验，不能给整条消息下结论。'
    elif statuses == {'supported'}:
        status, headline = 'supported-by-material', '材料支持该说法，依据如下。'
    elif statuses == {'contradicted'}:
        status, headline = 'contradicted-by-material', '材料与该说法不符，依据如下。'
    elif 'contradicted' in statuses or 'overstated' in statuses:
        status, headline = 'mixed', '消息中有与公开材料不符或超出材料依据的内容，不能整体采信。'
    else:
        status, headline = 'unverified', '现有公开材料仍不足以确认这条消息。'
    if intake.get('sensitive_allegation'):
        # Current acquisition has not established identity, primary provenance,
        # or independent corroboration. A model's text match cannot fill that gap.
        status, headline = 'unverified-sensitive', '目前无法可靠确认这项涉及个人名誉的指控。'
    interpretation = interpret_public_result(review, retrieval, accepted, complete)
    if intake.get('sensitive_allegation'):
        interpretation.update(code='unverified-sensitive', title=headline,
            summary='材料中的表述或引用不能替代身份、来源及独立佐证核验；本次不对该指控作可靠事实认证。')
    gaps = []
    if retrieval.get('search_complete') is False:
        gaps.append('部分查询或搜索引擎未完成。')
    if any(not p.get('original_source_identified') for p in sources):
        gaps.append('部分或全部材料尚未追溯到可核实的首发出处。')
    gaps.extend(intake.get('hints', []))
    source_review = review_sources(retrieval)
    if any(len(group) > 1 for group in source_review['observed_dependency_groups']):
        gaps.append('部分页面有已观察到的正文或出处关联，不能按网站数量当作多份独立证据。')
    if any(row['anonymous_attribution_marker'] for row in source_review['sources']):
        gaps.append('部分页面含匿名或网传表述，需要核对它是在提供证据还是引用待辟谣说法。')
    return {'schema_version': 'message-assessment/1', 'status': status, 'headline': headline,
            'interpretation': interpretation,
            'scope': 'retrieved-public-material', 'claim_verified': False,
            'coverage_complete': complete, 'claims': accepted,
            'search_complete': retrieval.get('search_complete'),
            'source_count': len(sources),
            'distinct_hosts': sorted({urlsplit(p['url']).hostname for p in sources}),
            'independent_source_count': None, 'unresolved': list(dict.fromkeys(gaps)),
            'source_review': source_review,
            'note': '材料支持或反驳不是独立事实认证；不同网站也可能转载同一来源。'}
