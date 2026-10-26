"""Regression for the actual failure shape, with synthetic cross-topic material."""
import json
import unittest
from unittest.mock import AsyncMock
from evidence_mesh.source_delivery import source_delivery


def page(text, **kw):
    return dict(source_id='fixture', title='规则说明', url='https://example.com/rules',
        text=text, fetched_at='2026-10-19T17:22:01+00:00', **kw)


class AnswerContextTests(unittest.TestCase):
    def test_numbered_items_without_punctuation_follow_explicit_introduction(self):
        for items in ('（一）定制产品\n（二）易腐产品', '1. 定制产品\n2. 易腐产品'):
            text = ('不适用本店退货承诺的商品包括：\n' + items
                    + '\n其他商品经购买时确认后可以不适用。\n其他栏目\n联系我们')
            value = source_delivery({'sources': [page(text)]}, '哪些商品不适用退货承诺？')
            quotes = value['sources'][0]['excerpts']
            self.assertTrue(any('定制产品' in q['text'] and '易腐产品' in q['text']
                                and '购买时确认' in q['text'] for q in quotes))
            for q in quotes:
                self.assertEqual(text[q['start']:q['end']], q['text'])
            self.assertNotIn('联系我们', value['answer'])

    def test_standalone_numbered_titles_are_still_not_body(self):
        value = source_delivery({'sources': [page('1. 退款问题\n2. 邮费问题\n联系我们')]}, '退款规则')
        self.assertFalse(value['material_available'])

    def test_question_is_locator_and_answer_list_and_confirmation_stay_together(self):
        text = ('首页\n退款规则\n所有商品都能退货吗？\n'
                '不是。下列商品不适用本店自愿退货承诺：\n'
                '（一）定制产品；\n（二）易腐产品。\n'
                '其他特殊商品须经顾客购买时确认，方可不适用该承诺。\n'
                '退货邮费谁承担？\n默认由顾客承担，另有约定除外。')
        value = source_delivery({'sources': [page(text)]}, '网上买的商品都能退货吗？')
        quotes = value['sources'][0]['excerpts']
        self.assertTrue(value['material_available'])
        self.assertFalse(value['semantic_answer_produced'])
        self.assertTrue(any('定制产品' in q['text'] and '购买时确认' in q['text'] for q in quotes))
        self.assertFalse(any(q['text'].strip().endswith('吗？') for q in quotes))
        self.assertTrue(any(q['heading_locator'] == '所有商品都能退货吗？' for q in quotes))
        for q in quotes:
            self.assertEqual(text[q['start']:q['end']], q['text'])

    def test_headings_and_search_hits_alone_are_not_delivered_evidence(self):
        value = source_delivery({'sources': [page('首页\n所有商品都能退货吗？\n相关新闻\n打印页面')],
            'leads': [{'content': '搜索摘要声称所有商品可退'}]}, '所有商品都能退货吗？')
        self.assertFalse(value['material_available'])
        self.assertFalse(value['sources'][0]['excerpts'])
        self.assertIn('需要补读正文', value['answer'])
        self.assertNotIn('搜索摘要声称', value['answer'])
        self.assertNotIn('> 所有商品都能', value['answer'])

    def test_general_rule_beats_narrative_and_keeps_exceptions(self):
        text = ('案例：顾客网上购买的商品收货后不想要，申请退货，双方对商品退货发生争议。\n'
                '法定例外：并非所有网上商品都适用退货规则。\n'
                '可以不适用的商品包括：\n'
                '定制商品；易腐商品；已交付的特定数字内容。\n'
                '经顾客在购买时确认后，可以不适用的商品：\n'
                '启用后价值贬损较大的商品。\n'
                '其他栏目\n联系我们')
        value = source_delivery({'sources': [page(text)]}, '网上买的商品都能退货吗？')
        joined = '\n'.join(q['text'] for q in value['sources'][0]['excerpts'])
        self.assertIn('定制商品', joined)
        self.assertIn('购买时确认', joined)
        self.assertNotIn('联系我们', joined)

    def test_generic_operating_rule_and_scientific_scope_context(self):
        cases = [
            ('科技馆哪天开放？\n周二至周日开放。\n节假日按另行公告执行。\n门票怎么买？\n请预约。',
             '科技馆哪天开放？', ['周二至周日开放', '另行公告']),
            ('这项研究证明普遍有效吗？\n本研究仅纳入24个体外样本，观察到相关性。\n'
             '结果不能直接推广至人体，也没有建立因果关系。\n论文作者是谁？\n见书目信息。',
             '这项研究证明普遍有效吗？', ['24个体外样本', '不能直接推广', '没有建立因果关系'])]
        for text, question, required in cases:
            quotes = source_delivery({'sources': [page(text)]}, question)['sources'][0]['excerpts']
            joined = '\n'.join(q['text'] for q in quotes)
            for term in required:
                self.assertIn(term, joined)
            for q in quotes:
                self.assertEqual(q['text'], text[q['start']:q['end']])

    def test_source_dates_are_human_readable_metadata_remains_exact(self):
        value = source_delivery({'sources': [page('规则要求提前预约，临时调整另行公告。')]}, '需要预约吗？')
        self.assertIn('2026-10-20（北京时间）', value['answer'])
        self.assertNotIn('17:22:01', value['answer'])
        self.assertEqual(value['sources'][0]['fetched_at'], '2026-10-19T17:22:01+00:00')

    def test_context_limit_never_leaves_list_introduction_without_its_items(self):
        text = ('退货规则为网上购物商品提供保障，仍有适用条件。\n'
                '适用情形：网上购买的商品，一般适用退货规则。\n'
                '不适用情形：部分商品不在退货范围。\n'
                '例外情形：并非所有商品都能退货。\n'
                '可以不适用的商品包括：\n定制产品和易腐产品。\n'
                '经购买时确认后，可以不适用的商品包括：\n启用后价值大幅降低的产品。\n'
                '其他事项\n请保存购物凭证。')
        quotes = source_delivery({'sources': [page(text)]}, '网上购物商品都能退货吗？')['sources'][0]['excerpts']
        self.assertFalse(any(q['text'].rstrip().endswith(('：', ':')) for q in quotes))
        self.assertTrue(any('定制产品' in q['text'] and '购买时确认' in q['text']
                            and '价值大幅降低' in q['text'] for q in quotes))

    def test_long_context_flags_cut_and_does_not_stitch_quotes(self):
        text = '适用条件：\n' + '必须满足登记条件且仅供本次使用，' * 150 + '\n退货条件是什么？\n另行确认。'
        value = source_delivery({'sources': [page(text)]}, '适用条件')
        for q in value['sources'][0]['excerpts']:
            self.assertEqual(q['text'], text[q['start']:q['end']])
        self.assertTrue(any(q['truncated'] for q in value['sources'][0]['excerpts']))
        self.assertIn('条件或例外可能未完整交付', value['answer'])


class AnswerContextIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_newly_read_material_is_not_reported_as_missing_to_downstream(self):
        from evidence_mesh.source_partner import source_product
        from evidence_mesh.contracts import request_from_caller_text
        collector = AsyncMock()
        collector.collect.return_value = {'status': 'retrieved', 'sources': [page(
            '哪些人免费入场？\n仅登记会员免费，其他观众需购票。')]}
        value = json.loads(await source_product(request_from_caller_text('活动所有人免费吗？',
            default_claim_id='fixture'), collector))
        self.assertFalse(value['input_assessment']['evidence_provided'])
        self.assertTrue(value['output_assessment']['material_available'])
        self.assertEqual(value['collaboration']['material_origin'], 'retrieved-public-unverified')
        self.assertEqual(value['collaboration']['next_action'], 'semantic-answer-integration')
        self.assertTrue(value['collaboration']['standalone_callable'])
        self.assertFalse(value['collaboration']['requires_our_leader'])
        self.assertFalse(value['output_assessment']['source_authenticity_verified'])
        self.assertIn('仅登记会员免费', value['answer'])

    async def test_title_only_material_requires_body_not_semantic_guess(self):
        from evidence_mesh.source_partner import source_product
        from evidence_mesh.contracts import request_from_caller_text
        collector = AsyncMock()
        collector.collect.return_value = {'status': 'retrieved', 'sources': [page('所有人都免费吗？')]}
        value = json.loads(await source_product(request_from_caller_text('所有人免费吗？',
            default_claim_id='fixture'), collector))
        self.assertFalse(value['output_assessment']['material_available'])
        self.assertEqual(value['collaboration']['next_action'], 'acquire-substantive-material')
        self.assertNotIn('> 所有人都免费吗', value['answer'])
