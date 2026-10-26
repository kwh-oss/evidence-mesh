import hashlib
import unittest
from unittest.mock import AsyncMock,patch
from evidence_mesh.provider_documents import full_page_document
from evidence_mesh.public_evidence import PublicEvidenceCollector,SearchBatch
from evidence_mesh.source_delivery import source_delivery
from evidence_mesh.retrieval_recovery import non_evidence_page

TEXT='甲城博物院位于甲城东路，是甲省的事业单位。乙城博物馆是另一个机构。以上是虚构的离线测试正文。'

def document():
    return full_page_document('https://public.example/about','离线机构介绍',TEXT,
        hashlib.sha256(b'provider-json').hexdigest(),'2026-10-25T10:00:00+00:00','甲城博物院')


class ProviderDocumentTests(unittest.IsolatedAsyncioTestCase):
    def test_absent_full_page_field_never_becomes_snippet_evidence(self):
        self.assertIsNone(full_page_document('https://public.example/a','标题',None,'hash','date','问题'))
        self.assertIsNone(full_page_document('https://public.example/a','Access denied','x'*60,'hash','date','问题'))
        with self.assertRaises(ValueError):
            full_page_document('https://127.0.0.1/a','标题',TEXT,'hash','date','问题')

    async def test_separate_full_page_preserves_quotes_and_provider_provenance(self):
        doc=document()
        search=AsyncMock(return_value=SearchBatch([{'url':doc['url'],'content':'不可作为证据的摘要'}],page_documents=[doc]))
        def forbidden_fetch(url):raise AssertionError('Full content already supplied')
        with patch('evidence_mesh.public_evidence.public_addresses',return_value=['8.8.8.8']):
            result=await PublicEvidenceCollector(search,forbidden_fetch).collect('甲城博物院在哪里？')
        self.assertEqual(len(result['sources']),1)
        self.assertEqual(result['sources'][0]['text'],TEXT)
        self.assertNotIn('不可作为证据的摘要',str(result))
        self.assertIsNone(result['sources'][0]['fetched_at'])
        self.assertEqual(result['sources'][0]['body_format'],'provider-json-full-page')
        delivery=source_delivery(result,'甲城博物院在哪里？')['answer']
        self.assertIn('正文提取服务返回时间',delivery)
        self.assertNotIn('抓取时间：',delivery)

    async def test_provider_content_cannot_bypass_private_dns_checks(self):
        doc=document();search=AsyncMock(return_value=SearchBatch([{'url':doc['url']}],page_documents=[doc]))
        with patch('evidence_mesh.public_evidence.public_addresses',side_effect=ValueError('private DNS')):
            result=await PublicEvidenceCollector(search).collect('甲城博物院在哪里？')
        self.assertEqual(result['sources'],[])
        self.assertFalse(result['claim_verified'])

    def test_footer_filter_keeps_a_real_short_fact(self):
        footer='苏ICP备0504952号-7 网站标识码：3201000056 苏公网安备：32010502010231号'
        self.assertEqual(non_evidence_page({'url':'https://public.example','text':footer}),'registration-footer-without-article')
        self.assertIsNone(non_evidence_page({'url':'https://public.example','text':'甲城博物馆属于甲城市政府，位于东路。'+footer}))
