"""Offline discovery behavior; none of these fixtures establishes real facts."""
from collections import deque
import hashlib
import unittest
from unittest.mock import AsyncMock

from evidence_mesh.page_document import VisibleHTML
from evidence_mesh.public_evidence import PublicEvidenceCollector, public_search_plan, next_public_lead
from evidence_mesh.retrieval_profiles import research_reference


class ResearchDiscoveryTests(unittest.TestCase):
    def test_everyday_research_questions_get_two_complementary_searches(self):
        for query in ('研究说AI检测器能百分百识别AI文章，是真的吗？',
                      '一项研究发现午睡与成绩相关，靠谱吗？',
                      '实验结果能证明这款电池更安全吗？',
                      'A study says this detector is perfect. Is it?'):
            with self.subTest(query=query):
                plan=public_search_plan(query)
                self.assertEqual(plan['queries'][0],query)
                self.assertEqual(len(plan['queries']),2)
                self.assertIn('academic',plan['profile']['domains'])
                self.assertIn('独立评测',plan['queries'][1])
                self.assertNotIn('site:',plan['queries'][1])
                self.assertFalse(plan['profile']['exhaustive'])

    def test_research_as_everyday_verb_does_not_trigger_academic_route(self):
        for query in ('帮我研究一下周末去哪玩','研究一下这个商品怎么退货'):
            self.assertNotIn('academic',public_search_plan(query)['profile']['domains'])

    def test_second_paper_beats_new_vendor_host_but_explicit_link_still_first(self):
        paper={'url':'https://aclanthology.org/2023.emnlp-main.1/','title':'Independent evaluation'}
        vendor={'url':'https://vendor.example/blog/perfect','title':'Perfect AI detector'}
        queue=deque([vendor,paper])
        self.assertEqual(next_public_lead(queue,{'aclanthology.org'},['evaluation'],['academic']),paper)
        queue=deque([dict(vendor,discovery='caller-link'),paper])
        self.assertEqual(next_public_lead(queue,set(),[],['academic'])['discovery'],'caller-link')

    def test_lookalike_repository_host_has_no_preference(self):
        fake={'url':'https://arxiv.org.evil.example/abs/2401.12345','title':'Study'}
        real={'url':'https://arxiv.org/abs/2401.12345','title':'Study'}
        self.assertEqual(next_public_lead(deque([fake,real]),set(),[],['academic']),real)

    def test_citation_links_without_original_source_label_are_traceable(self):
        parser=VisibleHTML()
        parser.feed('<article><p>Read <a href="https://doi.org/10.1234/fixture">[1]</a> '
                    'and <a href="https://aclanthology.org/2023.emnlp-main.1/">evaluation</a>.</p></article>')
        hints=parser.source_link_hints()
        self.assertEqual(len(hints),2)
        self.assertTrue(all(row['verified'] is False for row in hints))

    def test_citation_hints_reject_homepages_credentials_and_lookalikes(self):
        for url in ('https://doi.org/','https://doi.org.evil.example/10.1234/fixture',
                    'https://user@doi.org/10.1234/fixture','https://aclanthology.org/about/',
                    'http://doi.org/10.1234/fixture'):
            self.assertFalse(research_reference(url),url)


class ResearchCollectionTests(unittest.IsolatedAsyncioTestCase):
    async def test_vendor_reference_is_read_within_existing_bound_and_not_certified(self):
        read=[]
        def fetch(url):
            read.append(url)
            text='Offline fixture only: '+url
            page={'url':url,'title':'fixture','text':text,'text_sha256':hashlib.sha256(text.encode()).hexdigest()}
            if 'vendor' in url:
                page['source_link_hints']=[{'url':'https://doi.org/10.1234/reference','label':'[1]'}]
            return page
        search=AsyncMock(side_effect=[
            [{'url':'https://vendor.example/blog','title':'Detector claim'}],
            [{'url':'https://evaluation.example/study','title':'独立评测'}]])
        result=await PublicEvidenceCollector(search,fetch).collect('研究说检测器百分百准确吗？')
        self.assertIn('https://doi.org/10.1234/reference',read)
        self.assertLessEqual(result['page_attempt_count'],5)
        self.assertLessEqual(len(result['sources']),3)
        self.assertEqual(search.await_count,2)
        self.assertFalse(result['claim_verified'])
        self.assertFalse(result['source_selection']['independence_established'])
        self.assertTrue(all(not row['original_source_verified'] for row in result['source_relations']))

    async def test_paper_read_failure_retains_readable_vendor_with_limitations(self):
        def fetch(url):
            if 'arxiv' in url:raise TimeoutError()
            text='Vendor fixture: '+url
            return {'url':url,'title':'fixture','text':text,'text_sha256':hashlib.sha256(text.encode()).hexdigest()}
        search=AsyncMock(return_value=[{'url':'https://arxiv.org/abs/2401.12345'},
                                      {'url':'https://vendor.example/blog'}])
        result=await PublicEvidenceCollector(search,fetch).collect('研究说检测器准确吗？')
        self.assertEqual(result['sources'][0]['url'],'https://vendor.example/blog')
        self.assertTrue(any(row.get('stage')=='page' for row in result['failures']))
        self.assertFalse(result['claim_verified'])
