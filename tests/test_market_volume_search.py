import unittest
from unittest.mock import AsyncMock
from evidence_mesh.public_evidence import public_search_plan,PublicEvidenceCollector


class MarketVolumeSearchTests(unittest.IsolatedAsyncioTestCase):
    def test_independent_query_keeps_product_and_scope_without_assuming_viral_number(self):
        for query,number,product in [
            ('实体硅胶娃娃行业是否达到全球年销量数十万具的规模？','数十万具','实体硅胶娃娃'),
            ('某品牌手机全球年销量达到300万台？','300万台','某品牌手机'),
            ('2025年某类汽车出货量超过20万辆吗？','20万辆','某类汽车')]:
            plan=public_search_plan(query)
            self.assertEqual(plan['queries'][0],query)
            self.assertIn(product,plan['queries'][1])
            self.assertNotIn(number,plan['queries'][1])
            self.assertIn('统计口径',plan['queries'][1])
            self.assertIn('statistics',plan['profile']['domains'])
        self.assertIn('2025年',plan['queries'][1])

    async def test_video_quotation_cannot_replace_neutral_statistical_retrieval(self):
        search=AsyncMock(return_value=[])
        query='实体硅胶娃娃行业全球年销量达到十万具吗？'
        result=await PublicEvidenceCollector(search).collect(query,focused_query='这个行业已经年销数十万具，发展了30年')
        self.assertEqual(search.await_args_list[0].args[0],query)
        second=search.await_args_list[1].args[0]
        self.assertIn('实体硅胶娃娃',second)
        self.assertNotIn('十万具',second)
        self.assertNotIn('这个行业',second)
        self.assertFalse(result['claim_verified'])

    def test_not_every_number_is_treated_as_sales_volume(self):
        plan=public_search_plan('某型号手机2025年发布了吗？')
        self.assertFalse(plan['profile']['market_volume'])
