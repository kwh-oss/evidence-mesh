"""Offline scheduling regressions; ranking hints never establish truth."""
import unittest
import hashlib
from unittest.mock import AsyncMock
from collections import deque
from evidence_mesh.public_evidence import public_search_plan, next_public_lead, PublicEvidenceCollector


class EventSearchPlanTests(unittest.TestCase):
    def test_assertions_questions_and_negations_share_followup_retrieval(self):
        for subject, label in [('姜萍', '数学天才'), ('甲医生', '神医'), ('某机构', '权威')]:
            with self.subTest(subject=subject):
                reference = public_search_plan(subject + '是' + label + '吗')['queries'][1]
                for suffix in ('', '。', '？', '吗', '吗？'):
                    for copula in ('是', '不是', '是不是'):
                        query = subject + copula + label + suffix
                        plan = public_search_plan(query)
                        self.assertEqual(plan['queries'][0], query)
                        self.assertEqual(plan['queries'][1], reference)
                        self.assertIn('调查', plan['focus_terms'])

    def test_evaluative_questions_search_event_subject_without_assuming_verdict(self):
        for query, subject in [('姜萍是数学天才吗', '姜萍'),
                               ('甲医生是不是神医？', '甲医生'),
                               ('某机构是权威吗', '某机构')]:
            with self.subTest(query=query):
                plan = public_search_plan(query)
                self.assertEqual(len(plan['queries']), 2)
                self.assertEqual(plan['queries'][0], query)
                self.assertTrue(plan['queries'][1].startswith(subject + ' 事件'))
                self.assertIn('情况说明', plan['queries'][1])
                self.assertNotIn('作弊', plan['queries'][1])
                self.assertIn('not-fact-verification', plan['scope'])

    def test_event_followup_and_holiday_paths_still_bounded(self):
        for query in ('某次赛事争议后续', '某会议放假吗', '水的化学式是什么'):
            self.assertEqual(len(public_search_plan(query)['queries']), 2)
        self.assertIn('调休', public_search_plan('某会议放假吗')['queries'][1])

    def test_statement_text_gets_slot_before_video_and_commentary(self):
        queue = deque([
            {'url':'https://a.example/video/one', 'title':'事件调查结果 情况说明 视频'},
            {'url':'https://b.example/post/one', 'title':'天才爆红后续故事'},
            {'url':'https://c.example/news/one', 'title':'赛事组委会情况说明全文'}])
        lead = next_public_lead(queue, set(), public_search_plan('某人是天才吗')['focus_terms'])
        self.assertEqual(lead['url'], 'https://c.example/news/one')
        # Retain other candidates; no title establishes publisher authenticity.
        self.assertEqual(len(queue), 2)

    def test_explicit_caller_and_source_links_keep_precedence(self):
        for kind in ('caller-link', 'source-link'):
            queue = deque([{'url':'https://a.example/video/one', 'title':'', 'discovery':kind},
                           {'url':'https://b.example/news', 'title':'情况说明'}])
            self.assertEqual(next_public_lead(queue, set(), ['情况说明'])['discovery'], kind)


class AssertionRetrievalTests(unittest.IsolatedAsyncioTestCase):
    async def test_unpunctuated_evaluation_reads_followup_in_existing_budget(self):
        # Distinct fake bodies prove selection, not a model's factual reasoning.
        read = []
        def fetch(url):
            read.append(url)
            text = '离线模拟正文：' + url
            return dict(url=url, title='', text=text,
                        text_sha256=hashlib.sha256(text.encode()).hexdigest())
        neutral = [dict(url=f'https://early.example/{i}', title='某人天才爆红') for i in range(5)]
        followup = [dict(url='https://event.example/statement', title='赛事组委会调查结果 情况说明')]
        search = AsyncMock(side_effect=[neutral, followup])
        result = await PublicEvidenceCollector(search, fetch).collect('某人是数学天才')
        self.assertEqual(read[0], followup[0]['url'])
        self.assertEqual(search.await_count, 2)
        self.assertEqual(len(read), 3)
        self.assertFalse(result['claim_verified'])
        self.assertFalse(result['source_selection']['independence_established'])
