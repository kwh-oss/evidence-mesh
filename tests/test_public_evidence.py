from evidence_mesh.product_presentation import read_product
"""Offline acquisition tests, not proof of real search or semantic accuracy."""
import asyncio
import hashlib
import json
import unittest
import uuid
import threading
from email.message import Message
from io import BytesIO
from unittest.mock import AsyncMock, patch

import httpx

from evidence_mesh.public_evidence import (
    public_url, public_addresses, VisibleHTML, PublicEvidenceCollector,
    SearxSearch, configured_collector, fetch_page, bind_public_quotes, bounded_fetch,
)
from evidence_mesh.contracts import MISSING_SOURCE_EXCERPT, request_from_caller_text, request_json
from evidence_mesh.source_partner import source_product
from evidence_mesh.source_partner import app as source_app
from acps_sdk.aip import TaskState, TextDataItem
from acps_sdk.aip.aip_rpc_client import AipRpcClient
from evidence_mesh.leader import PartnerTarget, audit_claim
from evidence_mesh.group_partner import process_group_command
from evidence_mesh.processors import verify_source
from acps_sdk.aip import TaskCommand, TaskCommandType
from types import SimpleNamespace


def page(url):
    text = '本条为离线模拟的公开公告正文，不是互联网检索结果。' * 5
    return {'url': url, 'title': '离线公告', 'text': text, 'fetched_at': '2026-10-11T00:00:00Z',
            'text_sha256': hashlib.sha256(text.encode()).hexdigest(),
            'body_sha256': 'fixture', 'independence': 'unknown', 'publisher_authenticated': False}


class CallerLinkTests(unittest.IsolatedAsyncioTestCase):
    async def test_caller_link_read_even_when_search_unavailable(self):
        result = await PublicEvidenceCollector(AsyncMock(side_effect=TimeoutError), page).collect(
            '公告是真的吗', seed_urls=('https://example.com/original',))
        self.assertEqual(result['status'], 'retrieved')
        self.assertFalse(result['search_complete'])
        self.assertEqual(result['sources'][0]['discovery'], 'caller-link')
        self.assertFalse(result['sources'][0]['publisher_authenticated'])
        self.assertFalse(result['claim_verified'])

    async def test_unsafe_link_rejected_before_search(self):
        search = AsyncMock()
        with self.assertRaises(ValueError):
            await PublicEvidenceCollector(search, page).collect('公告是真的吗', seed_urls=('https://127.0.0.1/private',))
        search.assert_not_awaited()

    async def test_caller_link_uses_existing_three_page_budget(self):
        seen = []
        def unique_page(url):
            seen.append(url)
            value = page(url)
            value['text'] += url
            value['text_sha256'] = hashlib.sha256(value['text'].encode()).hexdigest()
            return value
        search = AsyncMock(return_value=[{'url': f'https://example.com/{i}'} for i in range(8)])
        await PublicEvidenceCollector(search, unique_page).collect('公告是真的吗', seed_urls=('https://example.com/original',))
        self.assertEqual(seen[0], 'https://example.com/original')
        self.assertEqual(len(seen), 3)

    async def test_source_passes_caller_metadata_link_without_authenticating_identity(self):
        collector = AsyncMock()
        collector.collect.return_value = {'status': 'no-readable-evidence', 'sources': [], 'claim_verified': False}
        request = request_from_caller_text(json.dumps({'claim_text': '博主甲出轨是真的吗',
            'source': {'locator': 'https://example.com/original'}}), default_claim_id='offline-link')
        value = json.loads(await source_product(request, collector))
        collector.collect.assert_awaited_once_with('博主甲出轨是真的吗', seed_urls=('https://example.com/original',))
        self.assertFalse(value['retrieval']['message_intake']['entity_identity_resolved'])


class PublicSafetyTests(unittest.TestCase):
    def test_unicode_urls_are_ascii_and_equivalent_without_decoding_delimiters(self):
        expected = 'https://example.com/%E5%85%AC%E5%91%8A?q=%E6%B7%B1%E5%9C%B3&path=%2F'
        self.assertEqual(public_url('https://EXAMPLE.com:443/公告?q=深圳&path=%2f#x'), expected)
        self.assertEqual(public_url('https://example.com/%e5%85%ac%e5%91%8a?q=%e6%b7%b1%e5%9c%b3&path=%2f'), expected)
        self.assertEqual(public_url('https://example.com/a%2fb'), 'https://example.com/a%2Fb')
        expected.encode('ascii')
        self.assertEqual(public_url(expected), expected)
        with self.assertRaises(ValueError):
            public_url('https://example.com/bad%zz')

    def test_reject_unsafe_urls(self):
        for url in ('http://example.com', 'https://127.0.0.1', 'https://10.1.2.3',
                    'https://[::1]', 'https://169.254.169.254', 'https://user:pw@example.com',
                    'https://example.com:8459', 'https://host.local', 'https://localhost',
                    'https://example.com\\@127.0.0.1', 'https://example.com/\n'):
            with self.subTest(url=url), self.assertRaises(ValueError):
                public_url(url)

    def test_public_url_strips_fragment(self):
        self.assertEqual(public_url('https://example.com/news#foo'), 'https://example.com/news')

    def test_mixed_dns_rejected(self):
        def resolver(*args, **kwargs):
            return [(2, 1, 6, '', ('8.8.8.8', 443)), (2, 1, 6, '', ('10.0.0.1', 443))]
        with self.assertRaises(ValueError):
            public_addresses('example.com', resolver)

    def test_html_does_not_execute_or_include_scripts(self):
        parser = VisibleHTML()
        parser.feed('<title>公告</title><script>steal()</script><style>bad</style><p>可读正文</p>')
        self.assertIn('可读正文', ''.join(parser.parts))
        self.assertNotIn('steal', ''.join(parser.parts))
        self.assertNotIn('bad', ''.join(parser.parts))

    def test_default_disabled_without_network(self):
        with patch.dict('os.environ', {}, clear=True):
            self.assertIsNone(configured_collector())

    def test_enabled_without_endpoint_fails(self):
        with patch.dict('os.environ', {'PUBLIC_RETRIEVAL_ENABLED': 'true'}, clear=True):
            with self.assertRaises(ValueError):
                configured_collector()

    def test_cross_source_quote_rejected(self):
        review = {'status': 'model-suggestion', 'claims': [{'quotes': [{'text': '甲材料\n\n乙材料'}]}]}
        result = bind_public_quotes(review, [{'text': '甲材料'}, {'text': '乙材料'}])
        self.assertEqual(result['status'], 'failed-or-invalid')

    def test_quote_bound_to_actual_page(self):
        source = page('https://example.com/a')
        source['source_id'] = 'web-fixture'
        review = {'claims': [{'quotes': [{'text': source['text']}]}]}
        result = bind_public_quotes(review, [source])
        self.assertEqual(result['claims'][0]['quotes'][0]['source_url'], source['url'])

    def test_ambiguous_quote_not_used(self):
        review = {'claims': [{'quotes': [{'text': '共有句子'}]}]}
        self.assertEqual(bind_public_quotes(review, [{'text': '共有句子'}, {'text': '共有句子'}])['status'],
                         'failed-or-invalid')

    def test_redirect_to_private_network_rejected_before_connect(self):
        class Response:
            status = 302
            def getheader(self, name):
                return 'https://127.0.0.1/secret'
        class Connection:
            def __init__(self, *args): pass
            def request(self, *args, **kwargs): pass
            def getresponse(self): return Response()
            def close(self): pass
        def resolver(*args, **kwargs):
            return [(2, 1, 6, '', ('8.8.8.8', 443))]
        with self.assertRaises(ValueError):
            fetch_page('https://example.com/a', resolver=resolver, connection_factory=Connection)

    def test_fetch_records_actual_text_hash_and_unverified_reference(self):
        raw = ('<title>公开公告</title><meta property="article:published_time" content="2025-01-01">'
               '<script>不应进入证据</script><article><p>'
               + '公开公告正文仅用于离线测试，不是真实的互联网检索。' * 4
               + '</p><a href="/original">原始出处线索</a></article>').encode()
        connections = []
        class Response:
            status = 200
            headers = Message()
            headers['Content-Type'] = 'text/html; charset=utf-8'
            def __init__(self): self.body = BytesIO(raw)
            def getheader(self, name, default=None): return self.headers.get(name, default)
            def read1(self, count): return self.body.read1(count)
        class Connection:
            sock = None
            def __init__(self, host, address): connections.append((host, address))
            def request(self, *args, **kwargs): pass
            def getresponse(self): return Response()
            def close(self): pass
        def resolver(*args, **kwargs): return [(2, 1, 6, '', ('8.8.8.8', 443))]
        result = fetch_page('https://example.com/a', resolver=resolver, connection_factory=Connection)
        self.assertEqual(connections, [('example.com', '8.8.8.8')])
        self.assertNotIn('不应进入证据', result['text'])
        self.assertEqual(result['body_sha256'], hashlib.sha256(raw).hexdigest())
        self.assertIn('https://example.com/original', result['reference_links'])
        self.assertFalse(result['original_source_identified'])
        self.assertEqual(result['extraction_method'], 'semantic-article')
        self.assertFalse(result['extraction_verified'])
        self.assertIsNone(result['published_at'])
        self.assertEqual(result['page_metadata_hints'][0]['value'], '2025-01-01')
        self.assertFalse(result['page_metadata_hints'][0]['verified'])


class PublicFlowTests(unittest.IsolatedAsyncioTestCase):
    async def test_holiday_question_searches_arrangement_and_reporting_without_extra_calls(self):
        search = AsyncMock(return_value=[])
        result = await PublicEvidenceCollector(search, page).collect('某会议期间深圳会放假吗')
        self.assertEqual(search.await_count, 2)
        queries = [call.args[0] for call in search.await_args_list]
        self.assertEqual(queries[0], '某会议期间深圳会放假吗')
        self.assertIn('调休', queries[1])
        self.assertIn('报道', queries[1])
        self.assertNotIn('site:', queries[1])
        self.assertFalse(result['claim_verified'])

    async def test_same_host_does_not_take_all_slots_before_other_hosts(self):
        seen = []
        def fetch(url):
            seen.append(url)
            value = page(url)
            value['text_sha256'] = hashlib.sha256(url.encode()).hexdigest()
            return value
        leads = [{'url':'https://a.example.com/'+str(i)} for i in range(3)]
        leads += [{'url':'https://media.example.com/report'},{'url':'https://department.example.com/notice'}]
        result = await PublicEvidenceCollector(AsyncMock(return_value=leads), fetch).collect('某消息是真的吗')
        self.assertEqual(seen, ['https://a.example.com/0','https://media.example.com/report','https://department.example.com/notice'])
        self.assertFalse(result['source_selection']['independence_established'])
        self.assertIsNone(result['source_review']['independent_source_count'])

    async def test_arrangement_titles_precede_conference_background_without_trusting_snippets(self):
        seen = []
        def fetch(url):
            seen.append(url)
            value = page(url)
            value['text_sha256'] = hashlib.sha256(url.encode()).hexdigest()
            return value
        leads = [
            {'url':'https://event.example.com/background','title':'会议举办时间公布','content':'深圳放假调休休假假期'},
            {'url':'https://news.example.com/report','title':'会议期间是否放假？当地回应'},
            {'url':'https://agency.example.com/notice','title':'调休安排相关通知'}]
        result = await PublicEvidenceCollector(AsyncMock(return_value=leads), fetch).collect('会议期间深圳放假吗')
        self.assertEqual(seen[:2], ['https://news.example.com/report','https://agency.example.com/notice'])
        self.assertEqual(result['page_attempt_count'], 3)
        self.assertNotIn('content', result['leads'][0])
        self.assertFalse(result['claim_verified'])

    async def test_failed_site_does_not_prevent_other_candidate_inside_existing_budget(self):
        seen = []
        def fetch(url):
            seen.append(url)
            if 'agency.example' in url:
                raise TimeoutError('offline fixture')
            value = page(url)
            value['text_sha256'] = hashlib.sha256(url.encode()).hexdigest()
            return value
        search = AsyncMock(return_value=[{'url':'https://agency.example.com/a','title':'调休公告'},
            {'url':'https://agency.example.com/b','title':'调休报道'},
            {'url':'https://news.example.com/report','title':'放假回应'}])
        result = await PublicEvidenceCollector(search, fetch).collect('某会议放假吗')
        self.assertEqual(seen[1], 'https://news.example.com/report')
        self.assertEqual(search.await_count, 2)
        self.assertLessEqual(result['page_attempt_count'], 3)
        self.assertEqual(result['sources'][0]['url'], seen[1])
        self.assertFalse(result['sources'][0]['publisher_authenticated'])

    async def test_leader_explains_search_completed_but_all_pages_failed(self):
        request = request_from_caller_text('2026年某地会议期间会放假吗', default_claim_id='offline-page-failure')
        targets = [PartnerTarget(name, 'http://unused.test/rpc') for name in
                   ('source-verifier', 'evidence-grader', 'contradiction-scout')]
        async def fake(target, *_):
            product = {'payload': {'status':'none-found', 'level':'unsupported'}}
            if target.name == 'source-verifier':
                product['retrieval'] = {'status':'incomplete', 'sources':[],
                    'search_complete':True, 'search_diagnostics':[{},{}],
                    'page_attempt_count':3, 'leads':[{}, {}, {}],
                    'failures':[{'stage':'page','error_type':'SSLError'}]}
            return {'task_id':target.name, 'state':'completed', 'product':product}
        with patch('evidence_mesh.leader._call_partner', side_effect=fake):
            result = await audit_claim(request_json(request), targets)
        self.assertIn('2轮联网搜索返回', result['answer'])
        self.assertIn('3个网页，取得0份可读正文', result['answer'])
        self.assertNotIn('检索可能未开启', result['answer'])
        self.assertEqual(result['message_assessment']['source_count'], 0)
        self.assertFalse(result['message_assessment']['claim_verified'])

    async def test_equivalent_chinese_leads_do_not_use_two_page_slots(self):
        seen = []
        def fetch(url):
            seen.append(url)
            if url.endswith('/%E5%85%AC%E5%91%8A'):
                raise ValueError('offline unavailable')
            return page(url)
        search = AsyncMock(return_value=[{'url':'https://example.com/公告'},
            {'url':'https://example.com/%e5%85%ac%e5%91%8a'},
            {'url':'https://gov.example.com/notice'}, {'url':'https://other.example.com/notice'}])
        result = await PublicEvidenceCollector(search, fetch).collect('离线重放')
        self.assertEqual(len(seen), 3)
        self.assertEqual(seen[1:], ['https://gov.example.com/notice','https://other.example.com/notice'])
        self.assertEqual(result['page_attempt_count'], 3)
        self.assertGreater(result['duplicate_candidate_count'], 0)
        self.assertEqual(result['failures'][0]['url'], seen[0])
        self.assertTrue(result['sources'])
        self.assertFalse(result['claim_verified'])

    async def test_tls_failure_records_url_without_exposing_exception_text(self):
        import ssl
        def fetch(url):
            raise ssl.SSLError('untrusted secret exception message')
        result = await PublicEvidenceCollector(AsyncMock(return_value=[{'url':'https://example.com/a'}]), fetch).collect('离线TLS失败')
        self.assertEqual(result['failures'][0]['reason'], 'tls-handshake-failed')
        self.assertEqual(result['failures'][0]['url'], 'https://example.com/a')
        self.assertNotIn('secret', json.dumps(result['failures']))
        self.assertEqual(result['page_attempt_count'], 1)
        self.assertTrue(result['search_complete'])
        self.assertEqual(result['sources'], [])

    async def test_source_link_followed_inside_three_page_limit(self):
        seen = []
        def fetch(url):
            seen.append(url)
            value = page(url)
            value['text'] += url
            value['text_sha256'] = hashlib.sha256(value['text'].encode()).hexdigest()
            if url.endswith('/report'):
                value['source_link_hints'] = [{'url': 'https://origin.example.com/notice',
                    'label': '查看原文'}]
            elif url.endswith('/notice'):
                value['source_link_hints'] = [{'url': 'https://other.example.com/deep',
                    'label': '原文'}]
            return value
        search = AsyncMock(return_value=[{'url': 'https://example.com/report'},
                                        {'url': 'https://example.com/another'}])
        result = await PublicEvidenceCollector(search, fetch).collect('公告是否真实')
        self.assertEqual(seen, ['https://example.com/report',
                              'https://origin.example.com/notice', 'https://example.com/another'])
        relation = result['source_relations'][0]
        self.assertTrue(relation['target_read'])
        self.assertFalse(relation['original_source_verified'])
        self.assertFalse(relation['independence_verified'])

    async def test_source_link_private_address_never_fetched(self):
        seen = []
        def fetch(url):
            seen.append(url)
            value = page(url)
            value['source_link_hints'] = [{'url': 'https://127.0.0.1/private', 'label': '原文'}]
            return value
        result = await PublicEvidenceCollector(
            AsyncMock(return_value=[{'url': 'https://example.com/report'}]), fetch).collect('公告')
        self.assertEqual(seen, ['https://example.com/report'])
        self.assertEqual(result['source_relations'], [])

    async def test_source_link_failure_does_not_claim_target_read(self):
        def fetch(url):
            if url.endswith('/unavailable'):
                raise TimeoutError('offline fixture')
            value = page(url)
            value['source_link_hints'] = [{'url': 'https://origin.example.com/unavailable', 'label': '原文'}]
            return value
        result = await PublicEvidenceCollector(
            AsyncMock(return_value=[{'url': 'https://example.com/report'}]), fetch).collect('公告')
        self.assertEqual(result['source_relations'], [])
        self.assertEqual(result['status'], 'retrieved')
        self.assertTrue(any(f.get('error_type') == 'TimeoutError' for f in result['failures']))

    async def test_group_uses_same_async_source_retrieval_builder(self):
        collector = PublicEvidenceCollector(AsyncMock(return_value=[{'url': 'https://example.com/a'}]), page)
        client = SimpleNamespace(accept_task=AsyncMock(), start_working=AsyncMock(),
                                 submit_for_completion=AsyncMock(), fail_task=AsyncMock())
        command = TaskCommand(id='offline-group-msg', sentAt='2026-10-11T00:00:00Z',
            senderRole='leader', senderId='offline-leader', mentions=['offline-source'],
            dataItems=[TextDataItem(text='公告是真的吗')], groupId='offline-group',
            sessionId='offline-group-session', command=TaskCommandType.Start, taskId='offline-group-task')
        async def build(request):
            return await source_product(request, collector)
        await process_group_command(client=client, command=command, is_mentioned=True,
            service_name='source-verifier', product_type='source-check', processor=verify_source,
            product_builder=build)
        client.fail_task.assert_not_awaited()
        products = client.submit_for_completion.await_args.args[2]
        result = read_product(products)
        self.assertEqual(result['retrieval']['status'], 'retrieved')
        self.assertFalse(result['retrieval']['claim_verified'])

    async def test_timed_out_workers_keep_slots_until_they_finish(self):
        release = threading.Event()
        def stalled(url):
            release.wait(2)
            return page(url)
        try:
            outcomes = await asyncio.gather(
                bounded_fetch(stalled, 'https://example.com/a', timeout=.02),
                bounded_fetch(stalled, 'https://example.com/b', timeout=.02),
                return_exceptions=True)
            self.assertTrue(all(isinstance(v, TimeoutError) for v in outcomes))
            with self.assertRaises(RuntimeError):
                await bounded_fetch(page, 'https://example.com/c')
        finally:
            release.set()
            # Explicit worker completion, not another network attempt.
            await asyncio.to_thread(__import__('evidence_mesh.public_evidence', fromlist=['_PAGE_EXECUTOR'])
                                    ._PAGE_EXECUTOR.submit(lambda: None).result)
        self.assertIn('text', await bounded_fetch(page, 'https://example.com/d'))

    async def test_collect_capacity_shared_across_instances(self):
        started, release = asyncio.Event(), asyncio.Event()
        count = 0
        async def stalled(query):
            nonlocal count
            count += 1
            if count == 4:
                started.set()
            await release.wait()
            return []
        one = PublicEvidenceCollector(stalled, page)
        two = PublicEvidenceCollector(stalled, page)
        tasks = [asyncio.create_task(one.collect('甲消息')), asyncio.create_task(two.collect('乙消息'))]
        try:
            await asyncio.wait_for(started.wait(), timeout=1)
            result = await PublicEvidenceCollector(AsyncMock(), page).collect('丙消息')
            self.assertEqual(result['status'], 'capacity-limited')
        finally:
            release.set()
            await asyncio.gather(*tasks)

    async def test_source_retrieval_product_over_real_local_aip_lifecycle(self):
        collector = PublicEvidenceCollector(AsyncMock(return_value=[{'url': 'https://example.com/a'}]), page)
        client = AipRpcClient('http://partner.test/rpc', 'offline-leader',
            transport=httpx.ASGITransport(app=source_app), identity_binding_enabled=False)
        task_id, session = 'offline-' + str(uuid.uuid4()), 'offline-session-' + str(uuid.uuid4())
        try:
            with patch('evidence_mesh.source_partner.configured_collector', return_value=collector):
                started = await client.start_task(session, '公告是真的吗', task_id=task_id)
                self.assertEqual(started.status.state, TaskState.AwaitingCompletion)
                completed = await client.complete_task(task_id, session)
            output = read_product(completed.products)
            self.assertEqual(output['retrieval']['status'], 'retrieved')
            self.assertFalse(output['retrieval']['claim_verified'])
        finally:
            await client.close()

    async def test_snippet_cannot_become_evidence_on_fetch_failure(self):
        search = AsyncMock(return_value=[{'url': 'https://example.com/a', 'content': '绝对真实'}])
        def fail(url):
            raise ValueError('blocked')
        result = await PublicEvidenceCollector(search, fail).collect('这条消息是真的吗')
        self.assertEqual(result['sources'], [])
        self.assertNotIn('绝对真实', json.dumps(result, ensure_ascii=False))
        self.assertFalse(result['claim_verified'])

    async def test_identical_text_not_independent_evidence(self):
        search = AsyncMock(return_value=[{'url': 'https://example.com/a'}, {'url': 'https://another.com/b'}])
        result = await PublicEvidenceCollector(search, page).collect('查询公告')
        self.assertEqual(len(result['sources']), 1)
        self.assertEqual(result['sources'][0]['independence'], 'unknown')
        self.assertIn('duplicate_of', result['failures'][0])

    async def test_empty_search_is_not_false_verdict(self):
        result = await PublicEvidenceCollector(AsyncMock(return_value=[]), page).collect('查询公告')
        self.assertEqual(result['status'], 'no-readable-evidence')
        self.assertFalse(result['claim_verified'])

    async def test_search_failure_is_explicit(self):
        result = await PublicEvidenceCollector(AsyncMock(side_effect=TimeoutError), page).collect('查询公告')
        self.assertEqual(result['status'], 'incomplete')
        self.assertFalse(result['search_complete'])

    async def test_source_collects_missing_not_supplied(self):
        collector = PublicEvidenceCollector(AsyncMock(return_value=[{'url': 'https://example.com/a'}]), page)
        request = request_from_caller_text('公告是真的吗', default_claim_id='local')
        result = json.loads(await source_product(request, collector))
        self.assertEqual(result['retrieval']['status'], 'retrieved')
        self.assertFalse(result['input_assessment']['claim_verified'])
        supplied = request_from_caller_text('主张：公告有效。原文：公告有效且仍在试行阶段。', default_claim_id='supplied')
        await source_product(supplied, collector)
        self.assertEqual(collector.search.await_count, 2)

    async def test_opt_out_does_not_search(self):
        collector = PublicEvidenceCollector(AsyncMock(), page)
        request = request_from_caller_text(json.dumps({'claim_text': '公告是真的吗',
            'constraints': ['不联网']}), default_claim_id='local')
        result = json.loads(await source_product(request, collector))
        collector.search.assert_not_awaited()
        self.assertEqual(result['retrieval']['status'], 'not-requested')

    async def test_searx_uses_documented_json_contract(self):
        def handler(request):
            self.assertEqual(request.url.params['format'], 'json')
            return httpx.Response(200, json={'results': [{'url': 'https://example.com/a'}]})
        search = SearxSearch('http://search:8080/search', httpx.MockTransport(handler))
        self.assertEqual(len(await search('查询公告')), 1)

    async def test_searx_partial_failure_keeps_leads_but_not_complete(self):
        def handler(request):
            return httpx.Response(200, json={'query': request.url.params['q'],
                'results': [{'url': 'https://example.com/a'}],
                'unresponsive_engines': [['duckduckgo', 'CAPTCHA']]})
        search = SearxSearch('http://search:8080/search', httpx.MockTransport(handler))
        result = await PublicEvidenceCollector(search, page).collect('公告')
        self.assertTrue(result['sources'])
        self.assertFalse(result['search_complete'])
        self.assertTrue(any(f.get('error_type') == 'Captcha' for f in result['failures']))
        self.assertFalse(result['claim_verified'])
        request = request_from_caller_text('北京2024课间安排是真的吗', default_claim_id='partial')
        product = json.loads(await source_product(request, PublicEvidenceCollector(search, page)))
        self.assertIn('检索尚未完整完成', product['answer'])

    async def test_searx_query_mismatch_rejected(self):
        search = SearxSearch('http://search:8080/search', httpx.MockTransport(
            lambda request: httpx.Response(200, json={'query': '别的查询', 'results': []})))
        with self.assertRaises(ValueError):
            await search('公告')

    async def test_searx_bad_engine_diagnostics_rejected(self):
        for failure in ('CAPTCHA', [['bing']], [[1, 'timeout']], [['bing', 'timeout']] * 65):
            with self.subTest(failure=type(failure).__name__):
                search = SearxSearch('http://search:8080/search', httpx.MockTransport(
                    lambda request: httpx.Response(200, json={
                        'results': [], 'unresponsive_engines': failure})))
                with self.assertRaises(ValueError):
                    await search('公告')

    async def test_leader_acquires_before_grading_and_retains_links(self):
        request = request_from_caller_text('公告是真的吗', default_claim_id='local')
        targets = [PartnerTarget(name, 'http://unused.test/rpc') for name in
                   ('source-verifier', 'evidence-grader', 'contradiction-scout')]
        calls = []
        async def fake(target, request_text, *_):
            body = json.loads(request_text)
            calls.append(target.name)
            if target.name == 'source-verifier':
                self.assertEqual(body['source_excerpt'], MISSING_SOURCE_EXCERPT)
                source = page('https://example.com/a')
                source['source_id'] = 'web-fixture'
                relation = {'from_url': source['url'], 'to_url': 'https://origin.example.com/notice',
                            'relationship': 'page-declared-source-link', 'target_read': True,
                            'original_source_verified': False, 'independence_verified': False}
                product = {'payload': {'status': 'incomplete'}, 'retrieval': {
                    'status': 'retrieved', 'sources': [source], 'claim_verified': False, 'search_complete': False,
                    'source_relations': [relation]}}
            else:
                self.assertIn('web-fixture', body['source']['locator'])
                self.assertIn('page-declared-source-link', body['source']['locator'])
                product = {'payload': {'level': 'unsupported', 'status': 'none-found'}}
            return {'task_id': target.name, 'state': 'completed', 'product': product}
        with patch('evidence_mesh.leader._call_partner', side_effect=fake):
            result = await audit_claim(request_json(request), targets)
        self.assertEqual(calls[0], 'source-verifier')
        self.assertEqual(calls.count('source-verifier'), 1)
        self.assertIn('https://example.com/a', result['answer'])
        self.assertIn('出处追溯线索', result['answer'])
        self.assertIn('首发身份待确认', result['answer'])
        self.assertIn('支持与反证检索尚未完整完成', result['answer'])
        self.assertFalse(result['source_authenticity_verified'])
        self.assertNotEqual(result['decision'], 'supported')


if __name__ == '__main__':
    unittest.main()
