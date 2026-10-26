"""Mock-only provider/limit/security checks; not real search acceptance."""
import asyncio
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import httpx
from evidence_mesh.tavily_search import TavilySearch, SearchQuotaUnavailable, SearchProviderUnavailable
from evidence_mesh.public_evidence import configured_collector, PublicEvidenceCollector


class TavilyTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.key = Path(self.temp.name) / 'tavily.key'
        self.key.write_text('tvly-offline-test-key')
        self.key.chmod(0o600)
        self.ledger = Path(self.temp.name) / 'search-quota.sqlite3'

    def client(self, handler, limit=2, capture=None):
        return TavilySearch(self.key, self.ledger, limit, transport=httpx.MockTransport(handler), capture=capture)

    def response(self, request, **overrides):
        return httpx.Response(200, json=dict(query=json.loads(request.content)['query'],
            results=[{'url': 'https://www.12306.cn/notice', 'title': '公告',
                      'content': '搜索摘要不能当作原文'}], usage={'credits': 1},
            request_id='offline-request-1', **overrides))

    async def test_basic_contract_metadata_and_snippet_not_evidence(self):
        def handler(r):
            p = json.loads(r.content)
            self.assertEqual(str(r.url), 'https://api.tavily.com/search')
            self.assertEqual(r.method, 'POST')
            self.assertEqual(p['search_depth'], 'basic')
            for k in ('auto_parameters', 'include_answer', 'include_images'):
                self.assertIs(p[k], False)
            self.assertIs(p['include_raw_content'], True)
            self.assertNotIn('api_key', p)
            self.assertEqual(r.headers['Authorization'], 'Bearer tvly-offline-test-key')
            return self.response(r)
        captures = []
        rows = await self.client(handler, capture=lambda q, raw: captures.append(raw))('2025春运')
        self.assertEqual(len(captures), 1)
        self.assertNotIn('content', rows[0])
        self.assertEqual(rows.search_metadata['usage_credits'], 1)
        self.assertFalse(rows.search_metadata['response_is_evidence'])

    async def test_domain_suffix_uses_provider_filter_and_checks_actual_query_echo(self):
        captures = []
        def handler(request):
            p = json.loads(request.content)
            self.assertEqual(p['query'], '民法典 第五百七十七条 原文')
            self.assertEqual(p['include_domains'], ['npc.gov.cn', 'gov.cn', 'court.gov.cn'])
            return self.response(request)
        result = await self.client(handler, capture=lambda q,r: captures.append(q))(
            '民法典 第五百七十七条 原文 (site:npc.gov.cn OR site:gov.cn OR site:court.gov.cn)')
        self.assertEqual(captures, ['民法典 第五百七十七条 原文'])
        self.assertEqual(result.search_metadata['include_domains'][0], 'npc.gov.cn')

    async def test_full_page_is_separate_from_result_snippet(self):
        body='这是一份离线虚构的机构介绍正文，包含机构性质与地址信息，用于验证完整页面字段，绝非真实网页。'
        def handler(request):
            return httpx.Response(200,json={'query':json.loads(request.content)['query'],
                'results':[{'url':'https://public.example/about','title':'机构介绍','content':'不能引用的摘要','raw_content':body}],
                'usage':{'credits':1}})
        result=await self.client(handler)('某机构介绍')
        self.assertEqual(result.page_documents[0]['text'],body)
        self.assertNotIn('content',result[0])
        self.assertEqual(result.page_documents[0]['extraction_method'],'tavily-full-page-visible-text')

    async def test_error_no_retry_and_attempt_persists(self):
        calls = []
        def handler(r):
            calls.append(r)
            return httpx.Response(429, text='private diagnostic must not be echoed')
        client = self.client(handler, limit=1)
        with self.assertRaises(SearchProviderUnavailable):
            await client('公告')
        restarted = self.client(handler, limit=1)
        with self.assertRaises(SearchQuotaUnavailable):
            await restarted('公告')
        self.assertEqual(len(calls), 1)
        with closing(sqlite3.connect(self.ledger)) as db:
            self.assertEqual(db.execute('SELECT attempts,ceiling FROM quota').fetchone(), (1, 1))

    async def test_no_redirect_and_no_other_host_request(self):
        calls = []
        def handler(r):
            calls.append(str(r.url))
            return httpx.Response(302, headers={'Location': 'https://other.example/steal'})
        with self.assertRaises(SearchProviderUnavailable):
            await self.client(handler)('公告')
        self.assertEqual(calls, ['https://api.tavily.com/search'])

    async def test_malformed_mismatch_credit_and_secret_responses_rejected(self):
        for index, data in enumerate((
            {'query': 'wrong', 'results': [], 'usage': {'credits': 1}},
            {'query': '公告', 'results': [], 'usage': {'credits': 2}},
            {'query': '公告', 'results': [], 'usage': {}},
            {'query': '公告', 'results': [], 'usage': {'credits': 1}, 'answer': 'tvly-offline-test-key'},
        )):
            ledger = Path(self.temp.name) / str(index) / 'search-quota.sqlite3'
            ledger.parent.mkdir()
            captures = []
            search = TavilySearch(self.key, ledger, 1, transport=httpx.MockTransport(
                lambda r: httpx.Response(200, json=data)), capture=lambda q, raw: captures.append(raw))
            with self.assertRaises(ValueError):
                await search('公告')
            if index == 3:
                self.assertFalse(captures)

    async def test_mixed_real_case_urls_keep_https_official_lead(self):
        urls = ['https://www.cls.cn/detail/1885756',
                'http://finance.people.com.cn/n1/2024/1211/c1004-40380090.html',
                'https://www.12306.cn/mormhweb/zxdt/202412/t20241211_43192.html',
                'https://finance.sina.com.cn/tech/roll/2024-12-31/doc-inecipuc2161730.shtml',
                'https://www.gz.gov.cn/zwfw/zxfw/jtfw/content/post_10053263.html']
        def handler(request):
            return httpx.Response(200, json={'query': json.loads(request.content)['query'],
                'usage': {'credits': 1}, 'results': [{'url': url, 'title': 'offline'} for url in urls]})
        rows = await self.client(handler)('公告')
        self.assertEqual([row['url'] for row in rows], [url for url in urls if url.startswith('https://')])
        self.assertEqual(rows.search_metadata['discarded_result_count'], 1)
        self.assertNotIn('finance.people.com.cn', json.dumps(rows.search_metadata))

    async def test_all_private_http_and_credential_urls_are_discarded_not_fetched(self):
        urls = ['https://127.0.0.1/a', 'http://example.com/a',
                'https://user:secret@example.com/a', 'https://service.local/a']
        def handler(request):
            return httpx.Response(200, json={'query': '公告', 'usage': {'credits': 1},
                'results': [{'url': url} for url in urls]})
        rows = await self.client(handler)('公告')
        self.assertEqual(list(rows), [])
        self.assertEqual(rows.search_metadata['discarded_result_count'], 4)
        self.assertNotIn('secret', json.dumps(rows.search_metadata))

    async def test_two_concurrent_queries_reserve_atomically(self):
        calls = []
        def handler(r):
            calls.append(r)
            return self.response(r)
        search = self.client(handler, limit=1)
        results = await asyncio.gather(search('公告'), search('公告回应'), return_exceptions=True)
        self.assertEqual(len(calls), 1)
        self.assertEqual(sum(isinstance(r, SearchQuotaUnavailable) for r in results), 1)

    async def test_collector_retains_usage_without_snippets(self):
        search = self.client(self.response)
        def page(url):
            return {'url': url, 'text': '实际正文', 'text_sha256': 'test-digest'}
        result = await PublicEvidenceCollector(search, page).collect('公告')
        self.assertEqual(len(result['search_diagnostics']), 2)
        self.assertFalse(result['claim_verified'])
        self.assertEqual(result['sources'][0]['text'], '实际正文')

    async def test_operator_configuration_only_and_no_model_ledger(self):
        with patch.dict(os.environ, {'PUBLIC_RETRIEVAL_ENABLED': 'true',
                'PUBLIC_SEARCH_PROVIDER': 'tavily', 'TAVILY_KEY_FILE': str(self.key),
                'TAVILY_SEARCH_BUDGET_FILE': str(self.ledger), 'TAVILY_SEARCH_MAX_CALLS': '2'}, clear=True):
            self.assertIsInstance(configured_collector().search, TavilySearch)
            with patch.dict(os.environ, {'DEEPSEEK_BUDGET_FILE': str(self.ledger)}):
                with self.assertRaises(ValueError):
                    configured_collector()
            with patch.dict(os.environ, {'TAVILY_SEARCH_MAX_CALLS': '21'}):
                with self.assertRaises(ValueError):
                    configured_collector()

    async def test_key_symlink_or_invalid_refused(self):
        self.key.write_text('not-a-key')
        with self.assertRaises(ValueError):
            self.client(self.response)
        with self.assertRaises(ValueError):
            TavilySearch(self.key, Path(self.temp.name) / 'quota.sqlite3', 1)
