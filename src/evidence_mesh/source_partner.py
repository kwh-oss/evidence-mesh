from .aip_partner import build_partner_app
from .processors import verify_source
from .contracts import MISSING_SOURCE_EXCERPT
from .partner_input import partner_product
from .public_evidence import configured_collector, public_url
from .message_intake import assess_message
from .retrieval_archive import RetrievalArchive
from .source_delivery import source_delivery, retrieval_question, retrieval_search_text
import json


async def source_product(request, collector=None):
    from .collaboration_input import retrieval_request
    upstream_handoff = None
    if request.task_type != 'supplied_material_only':
        request, upstream_handoff = retrieval_request(request)
    output = json.loads(partner_product('source-check', verify_source, request))
    if upstream_handoff:
        output['upstream_handoff'] = upstream_handoff
    if request.source_excerpt != MISSING_SOURCE_EXCERPT:
        return json.dumps(output, ensure_ascii=False)
    question = retrieval_question(request.claim_text)
    from .video_search_context import focused_video_query
    focused_query=focused_video_query(request.goal)
    query_options={'focused_query':focused_query} if focused_query else {}
    # A caller can explicitly opt out; never infer network permission from web text.
    if request.task_type == 'supplied_material_only' or any(
            marker in constraint for constraint in request.constraints
            for marker in ('不联网', '禁止联网', 'no-network')):
        output['retrieval'] = {'status': 'not-requested', 'sources': [], 'claim_verified': False}
    else:
        try:
            seed_urls = ()
            locator = request.source.locator.strip()
            if locator.startswith('https://'):
                try:
                    seed_urls = (public_url(locator),)
                except ValueError:
                    pass  # Invalid metadata is not authority to fetch it.
            intake = assess_message(question, provided_link=bool(seed_urls))
            if intake['clarification_required']:
                output['retrieval'] = {'status': 'needs-clarification', 'sources': [],
                                       'claim_verified': False, 'message_intake': intake}
            else:
                collector = collector or configured_collector()
                output['retrieval'] = (await collector.collect(retrieval_search_text(question), seed_urls=seed_urls, **query_options)
                    if collector and seed_urls else await collector.collect(retrieval_search_text(question), **query_options) if collector else
                    {'status': 'disabled', 'sources': [], 'claim_verified': False})
                if collector:
                    output['retrieval']['message_intake'] = intake
        except Exception as exc:
            output['retrieval'] = {'status': 'incomplete', 'sources': [],
                                   'claim_verified': False, 'error_type': type(exc).__name__}
    if output['retrieval']['status'] in ('disabled', 'not-requested'):
        output['answer'] = ('本次未联网：检索服务未启用。' if output['retrieval']['status'] == 'disabled'
                            else '按本次任务要求未进行联网检索。')
        return json.dumps(output, ensure_ascii=False)
    output['source_delivery'] = source_delivery(output['retrieval'], question)
    output['answer'] = output['source_delivery']['answer']
    output['role_scope'] = 'public-material-acquisition-and-context-delivery'
    available = output['source_delivery']['material_available']
    output['output_assessment'] = {'material_available': available,
        'scope': 'retrieved-public-text', 'semantic_answer_produced': False,
        'source_authenticity_verified': False,
        'next_action': 'semantic-answer-integration' if available else 'acquire-substantive-material'}
    output['collaboration'].update(
        material_origin='retrieved-public-unverified' if available else 'missing-substantive-material',
        next_action=output['output_assessment']['next_action'],
        requires_our_leader=False, standalone_callable=True,
        recommended_followup='由调用方或具备语义审查能力的成员基于引文形成答案；没有材料时先补读正文。')
    if output['retrieval']['status'] == 'needs-clarification':
        output['answer'] = '\n'.join(output['retrieval']['message_intake']['questions'])
    retrieval = output['retrieval']
    bibliography = retrieval.get('scholarly_metadata', {})
    if bibliography.get('records'):
        output['answer'] += ('\n\n已找到%d条学术书目线索，实际读取%d个网页。书目/摘要与网页正文分别列出；'
            '尚未完成全文综述或结论核验。' % (len(bibliography['records']), len(retrieval.get('sources', []))))
        for row in bibliography['records']:
            scope = '含登记摘要' if row.get('abstract') else '仅书目信息'
            output['answer'] += '\n- %s；%s；DOI: %s；%s；%s' % (
                row['title'], row.get('container_title', ''), row['doi'], scope, row['url'])
        if retrieval.get('search_complete') is False:
            output['answer'] += '\n部分检索未完成，结果可能遗漏。'
    if 'legal' in retrieval.get('search_plan', {}).get('profile', {}).get('domains', []):
        pages = retrieval.get('sources', [])
        located = [p for p in pages if p.get('legal_context', {}).get('article_window_located')]
        requested = [p for p in pages if p.get('legal_context', {}).get('requested_article')]
        if located:
            output['answer'] += '\n已定位到指定条号附近的原文摘录，尚未确认是否为所需法规及适用版本：'
            for page in located:
                output['answer'] += '\n- ' + page.get('title', '') + '：' + page['url'] + '\n' + page['text'][:700]
        elif requested:
            output['answer'] += '\n已读网页中尚未唯一定位指定条文，不能用相关文章替代该条法律原文。'
        output['answer'] += '\n法律资料需核对适用地区、条号、修订版本和施行/废止状态；未核实的项目已明确标注，不作为法律意见。'
    archive = getattr(collector, 'archive', None)
    if isinstance(archive, RetrievalArchive):
        try:
            output['retrieval']['archive'] = archive.finish(output)
        except (OSError, ValueError):
            output['retrieval']['archive'] = {'status': 'incomplete', 'semantic_acceptance': False}
            output['answer'] += '\n原始证据归档未完整保存，本次不能作为可追溯验收通过。'
    return json.dumps(output, ensure_ascii=False)


app = build_partner_app(
    service_name="source-verifier",
    product_type="source-check",
    processor=verify_source,
    product_builder=source_product,
)
