"""Search planning fixtures; domain preference is not evidence of correctness."""
import hashlib
import unittest
from collections import deque
from unittest.mock import AsyncMock
from evidence_mesh.public_evidence import public_search_plan, next_public_lead, PublicEvidenceCollector
from evidence_mesh.tavily_search import routed_query


class ScienceRetrievalTests(unittest.IsolatedAsyncioTestCase):
    def test_science_question_keeps_neutral_search_and_adds_independent_evidence_search(self):
        for query in ['醋洗肉有没有科学依据？','磁疗产品的功效是否可靠？','这种清洁方法是否有科学原理？']:
            plan=public_search_plan(query)
            self.assertEqual(plan['queries'][0],query)
            self.assertEqual(len(plan['queries']),2)
            self.assertIn('science',plan['profile']['domains'])
            wire,domains=routed_query(plan['queries'][1])
            self.assertIn('适用条件',wire)
            self.assertNotIn('site:',wire)
            self.assertIn('edu.cn',domains)
            self.assertIn('gov.cn',domains)
            self.assertIn('cdc.gov',domains)

    def test_scientific_reading_prefers_guidance_over_repeated_social_posts(self):
        queue=deque([{'url':'https://www.facebook.com/groups/123/posts/456','title':'生活技巧'},
            {'url':'https://www.cdc.gov/food-safety/about/index.html','title':'食物清洗研究指南'}])
        self.assertIn('cdc.gov',next_public_lead(queue,set(),['指南'],['science'])['url'])

    async def test_failed_social_pages_do_not_consume_every_science_reading_slot(self):
        leads=[{'url':'https://a.example.com/'+str(i),'title':'转载短片'} for i in range(3)]
        leads.append({'url':'https://b.example.com/guide','title':'科学指南'})
        seen=[]
        def fetch(url):
            seen.append(url)
            if url.endswith('guide'):
                text='这是读取能力的离线夹具，不是科学结论。'
                return {'url':url,'title':'科学指南','text':text,'text_sha256':hashlib.sha256(text.encode()).hexdigest()}
            raise ValueError('page-too-large')
        result=await PublicEvidenceCollector(AsyncMock(return_value=leads),fetch).collect('这种方法的科学依据是什么？')
        self.assertEqual(len(result['sources']),1)
        self.assertLessEqual(result['page_attempt_count'],5)
        self.assertFalse(result['claim_verified'])
