"""Offline boundary tests; fixtures are not live academic or legal evidence."""
import hashlib
import json
from collections import deque
from io import BytesIO
import unittest
from unittest.mock import AsyncMock

from evidence_mesh.public_evidence import public_search_plan, next_public_lead, PublicEvidenceCollector
from evidence_mesh.scholarly_metadata import parse_records, crossref_lookup
from evidence_mesh.retrieval_profiles import domain_priority, select_reading_window, is_access_interstitial
from evidence_mesh.source_partner import source_product
from evidence_mesh.contracts import request_from_caller_text


def fixture():
    return {'status': 'ok', 'message': {'items': [{
        'DOI': '10.1234/Fixture', 'title': ['<i>Research</i> title'],
        'author': [{'given': 'A', 'family': 'Reader'}], 'container-title': ['Test Journal'],
        'published': {'date-parts': [[2024, 3]]}, 'type': 'journal-article',
        'abstract': '<jats:p>Deposited abstract only.</jats:p>'}]}}


def page(url):
    text = '离线测试正文，不是真实法律材料。' * 5 + url
    return {'url': url, 'text': text, 'title': 'fixture',
            'text_sha256': hashlib.sha256(text.encode()).hexdigest()}


class Profiles(unittest.TestCase):
    def test_domain_routes_keep_original_query_and_two_web_searches(self):
        for query, kind in [('找阅读与成绩的论文', 'academic'), ('民法典退款条款', 'legal'),
                            ('补贴政策原文', 'policy'), ('人口普查统计口径', 'statistics'),
                            ('产品说明书保修条件', 'product')]:
            plan = public_search_plan(query)
            self.assertEqual(plan['queries'][0], query)
            self.assertEqual(len(plan['queries']), 2)
            self.assertIn(kind, plan['profile']['domains'])
            self.assertFalse(plan['profile']['exhaustive'])

    def test_mixed_domains_and_foreign_jurisdiction_not_silently_chinese(self):
        plan = public_search_plan('美国隐私法律文献论文')
        self.assertIn('academic', plan['profile']['domains'])
        self.assertIn('legal', plan['profile']['domains'])
        self.assertNotIn('site:gov.cn', plan['queries'][1])
        self.assertEqual(plan['profile']['jurisdiction'], 'not-confirmed')

    def test_official_domain_boundary_and_caller_precedence(self):
        self.assertEqual(domain_priority('https://npc.gov.cn.evil.example/a', ['legal']), 0)
        queue = deque([{'url': 'https://news.example/a'}, {'url': 'https://www.npc.gov.cn/a'}])
        self.assertEqual(next_public_lead(queue, set(), [], ['legal'])['url'], 'https://www.npc.gov.cn/a')
        queue.appendleft({'url': 'https://news.example/b', 'discovery': 'caller-link'})
        self.assertEqual(next_public_lead(queue, set(), [], ['legal'])['discovery'], 'caller-link')

    def test_late_article_window_is_exact_and_ambiguous_headers_not_guessed(self):
        text = '法律前文。' * 1500 + '\n第五百七十七条 这是离线虚构条文。\n第五百七十八条 后续条款。'
        selected, hint = select_reading_window(text, '查找第五百七十七条', 5000)
        self.assertIn('这是离线虚构条文', selected)
        self.assertEqual(selected, text[hint['start']:hint['end']])
        self.assertEqual(hint['method'], 'explicit-article-window')
        duplicate = text + '\n第五百七十七条 又一次出现。'
        selected, hint = select_reading_window(duplicate, '查找第五百七十七条', 5000)
        self.assertEqual(hint['method'], 'document-prefix')
        self.assertEqual(selected, duplicate[:5000])

    def test_access_denied_pages_are_not_research_sources(self):
        self.assertTrue(is_access_interstitial('NCBI - WWW Error Blocked Diagnostic', 'Access Denied' * 60))
        self.assertTrue(is_access_interstitial('', 'Verify you are human'))
        self.assertFalse(is_access_interstitial('论文正文', 'We discuss access denied errors in this research.'))

    def test_law_title_and_article_reformulated_without_instruction_noise(self):
        plan = public_search_plan('帮我找《中华人民共和国民法典》第五百七十七条并记录发布日期。')
        self.assertTrue(plan['queries'][1].startswith('中华人民共和国民法典 第五百七十七条 原文'))
        self.assertNotIn('帮我找', plan['queries'][1])


class Records(unittest.TestCase):
    def test_record_provenance_dates_and_markup_are_not_full_text(self):
        row = parse_records(fixture())[0]
        self.assertEqual(row['title'], 'Research title')
        self.assertEqual(row['abstract'], 'Deposited abstract only.')
        self.assertEqual(row['publication_dates'], {'published': [2024, 3]})
        self.assertFalse(row['full_text_read'])
        self.assertFalse(row['peer_review_verified'])
        self.assertFalse(row['relevance_verified'])

    def test_invalid_doi_and_duplicates_skipped_records_bounded(self):
        data = fixture()
        rows = data['message']['items']
        rows.extend([dict(rows[0]), dict(rows[0], DOI='https://127.0.0.1/secret')])
        self.assertEqual(len(parse_records(data)), 1)
        data['message']['items'] = [dict(rows[0], DOI='10.1234/' + str(i)) for i in range(12)]
        self.assertEqual(len(parse_records(data)), 5)

    def test_exact_doi_mismatch_and_invalid_schema_fail_closed(self):
        with self.assertRaises(ValueError):
            parse_records({'status': 'ok', 'message': fixture()['message']['items'][0]}, exact_doi='10.1234/Other')
        for value in ({}, {'status': 'ok', 'message': []}):
            with self.assertRaises(ValueError):
                parse_records(value)

    def test_fixed_host_pinned_json_capture_and_single_request(self):
        raw = json.dumps(fixture()).encode()
        seen, captured = [], []
        class Response:
            status = 200
            def getheader(self, key, default=None):
                return {'Content-Type': 'application/json'}.get(key, default)
            read1 = BytesIO(raw).read
        class Connection:
            sock = None
            def __init__(self, host, ip): seen.append((host, ip))
            def request(self, method, path, headers): seen.append(path)
            def getresponse(self): return Response()
            def close(self): pass
        resolver = lambda *a, **k: [(2, 1, 6, '', ('8.8.8.8', 443))]
        result = crossref_lookup('论文 HTTPS://evil.example', resolver=resolver,
            connection_factory=Connection, capture=lambda q, r: captured.append(r))
        self.assertEqual(seen[0], ('api.crossref.org', '8.8.8.8'))
        self.assertTrue(seen[1].startswith('/works?'))
        self.assertEqual(result['request_count'], 1)
        self.assertEqual(captured, [raw])

    def test_quoted_title_uses_title_field_and_journal_filter(self):
        from urllib.parse import parse_qs, urlsplit
        seen = []
        raw = json.dumps(fixture()).encode()
        class Response:
            status = 200
            def getheader(self, key, default=None):
                return {'Content-Type': 'application/json'}.get(key, default)
            read1 = BytesIO(raw).read
        class Connection:
            sock = None
            def __init__(self, *args): pass
            def request(self, method, path, headers): seen.append(parse_qs(urlsplit(path).query))
            def getresponse(self): return Response()
            def close(self): pass
        crossref_lookup('帮我找《Deep learning》的论文', connection_factory=Connection,
            resolver=lambda *a, **k: [(2, 1, 6, '', ('8.8.8.8', 443))])
        self.assertEqual(seen[0]['query.title'], ['Deep learning'])
        self.assertEqual(seen[0]['filter'], ['type:journal-article'])

    def test_private_dns_rejected_before_connection(self):
        resolver = lambda *a, **k: [(2, 1, 6, '', ('127.0.0.1', 443))]
        with self.assertRaises(ValueError):
            crossref_lookup('论文', resolver=resolver, connection_factory=lambda *a: self.fail())


class Integration(unittest.IsolatedAsyncioTestCase):
    async def test_specialized_failed_pages_have_five_attempts_and_never_more_than_three_sources(self):
        read = []
        def fetch(url):
            read.append(url)
            if len(read) < 3: raise TimeoutError()
            return page(url)
        result = await PublicEvidenceCollector(AsyncMock(return_value=[{'url': 'https://example.com/' + str(i)}
            for i in range(8)]), fetch).collect('法律条款')
        self.assertEqual(result['page_attempt_count'], 5)
        self.assertEqual(len(result['sources']), 3)

    async def test_academic_metadata_not_inserted_into_read_sources(self):
        metadata = {'status': 'retrieved', 'records': parse_records(fixture())}
        result = await PublicEvidenceCollector(AsyncMock(return_value=[]),
            fetch=lambda u: (_ for _ in ()).throw(TimeoutError()), scholarly=lambda q: metadata).collect('阅读论文')
        self.assertEqual(result['status'], 'metadata-only')
        self.assertEqual(result['sources'], [])
        self.assertEqual(result['page_attempt_count'], 1)
        self.assertFalse(result['claim_verified'])

    async def test_metadata_failure_does_not_lose_web_pages(self):
        def failed(q): raise TimeoutError()
        result = await PublicEvidenceCollector(AsyncMock(return_value=[{'url': 'https://journal.example/a'}]),
            page, failed).collect('阅读论文')
        self.assertEqual(result['status'], 'retrieved')
        self.assertEqual(result['scholarly_metadata']['status'], 'incomplete')
        self.assertFalse(result['search_complete'])
        self.assertEqual(len(result['sources']), 1)

    async def test_legal_reading_prefers_official_but_does_not_assert_valid_law(self):
        result = await PublicEvidenceCollector(AsyncMock(return_value=[{'url': 'https://news.example/a'},
            {'url': 'https://www.npc.gov.cn/a'}]), page).collect('民法典条款')
        self.assertEqual(result['sources'][0]['url'], 'https://www.npc.gov.cn/a')
        legal = result['sources'][0]['legal_context']
        self.assertEqual(legal['effective_status'], 'not-verified')
        self.assertFalse(legal['version_verified'])
        self.assertLessEqual(result['page_attempt_count'], 5)
        self.assertLessEqual(len(result['sources']), 3)

    async def test_nonacademic_never_calls_catalogue(self):
        def unexpected(q): self.fail('unneeded metadata request')
        await PublicEvidenceCollector(AsyncMock(return_value=[]), page, unexpected).collect('今天放假吗')

    async def test_partner_answer_reports_actual_read_scope(self):
        collector = AsyncMock()
        collector.collect.return_value = {'status': 'metadata-only', 'sources': [],
            'scholarly_metadata': {'records': parse_records(fixture())}, 'search_complete': False}
        request = request_from_caller_text('帮我检索阅读论文', default_claim_id='offline-academic')
        result = json.loads(await source_product(request, collector))
        self.assertIn('1条学术书目线索', result['answer'])
        self.assertIn('实际读取0个网页', result['answer'])
        self.assertIn('部分检索未完成', result['answer'])
