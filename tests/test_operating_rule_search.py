import unittest
from collections import deque
from evidence_mesh.public_evidence import public_search_plan, next_public_lead


class OperatingRuleSearchTests(unittest.TestCase):
    def test_generic_opening_questions_seek_current_rules_not_only_old_news(self):
        for question in ('故宫每个周一都闭馆吗？', '科技馆开放时间是什么？', '图书馆的营业时间有调整吗？'):
            plan = public_search_plan(question)
            self.assertEqual(plan['queries'][0], question)
            self.assertIn('现行', plan['queries'][1])
            self.assertIn('开放时间', plan['focus_terms'])
        other = public_search_plan('某品牌的广告事件后续调查')
        self.assertNotIn('开放时间', other['focus_terms'])

    def test_operating_page_can_outrank_host_diversity_but_seed_stays_first(self):
        historical = {'url': 'https://museum.example/news/2014', 'title': '2014年起实行周一闭馆'}
        current = {'url': 'https://museum.example/visit', 'title': '参观须知与开放时间'}
        other_host = {'url': 'https://blog.example/news', 'title': '周一为什么闭馆'}
        focus = public_search_plan('博物馆周一闭馆吗')['focus_terms']
        queue = deque([historical, other_host, current])
        self.assertEqual(next_public_lead(queue, {'museum.example'}, focus)['url'], current['url'])
        seed = dict(historical, discovery='caller-link')
        self.assertEqual(next_public_lead(deque([seed, current]), set(), focus)['url'], seed['url'])
