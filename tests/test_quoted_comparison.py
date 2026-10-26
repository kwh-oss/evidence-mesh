import json
import unittest
from evidence_mesh.caller_document import quoted_comparison
from evidence_mesh.contracts import request_from_caller_text, MISSING_SOURCE_EXCERPT


class QuotedComparisonTests(unittest.TestCase):
    def test_real_dingdang_task_has_both_texts_without_planning_summary(self):
        text = '帮我检查这两句是否矛盾：“所有人免费入场”和“仅学生免费入场”。 DAG 指定的上游产物摘要：叮当已完成协作规划并开始按 DAG 派发。'
        for value in (text, json.dumps({'text': text}, ensure_ascii=False)):
            r = request_from_caller_text(value, default_claim_id='test')
            self.assertEqual((r.claim_text, r.source_excerpt), ('所有人免费入场', '仅学生免费入场'))
            self.assertEqual(r.task_type, 'cross_text_conflict')
            self.assertNotIn('DAG', r.goal)
            self.assertEqual(r.source.source_id, 'caller:quoted-comparison')
            self.assertIn('未认证', r.source.title)

    def test_general_texts_and_context_are_preserved_verbatim(self):
        for left, right in [('价格降低，但销量提高', '销售额不变'), ('不允许转让', '可以无偿转让'), ('所有门店开放', '全部门店营业')]:
            text = f'不同日期发布，请比较“{left}”与“{right}”是否冲突。'
            r = request_from_caller_text(text, default_claim_id='test')
            self.assertEqual((r.claim_text, r.source_excerpt), (left, right))
            self.assertEqual(r.goal, text)
            self.assertIn(f'[{text.index(right)}:{text.index(right)+len(right)}]', r.source.locator)

    def test_quoted_entities_and_unmatched_or_multiple_quotes_are_not_material(self):
        for text in ['查找“甲”和“乙”的资料。', '“甲说法”是否矛盾？', '比较“甲句”“乙句”“丙句”是否冲突。', '比较“甲句”和“乙句”是否冲突？还有“', '不要比较“甲句”和“乙句”是否矛盾。']:
            self.assertIsNone(quoted_comparison(text))
            self.assertEqual(request_from_caller_text(text, default_claim_id='test').source_excerpt, MISSING_SOURCE_EXCERPT)

    def test_explicit_material_and_caller_scope_win(self):
        text = '比较“甲句”和“乙句”是否一致？'
        r = request_from_caller_text(json.dumps({'text': text, 'source_excerpt': '实际提供的独立原文', 'task_type': 'intent_and_claims'}), default_claim_id='test')
        self.assertEqual(r.source_excerpt, '实际提供的独立原文')
        self.assertEqual(r.task_type, 'intent_and_claims')
        r = request_from_caller_text(json.dumps({'text': text, 'task_type': 'intent_and_claims', 'source': {'source_id': 'caller-explicit'}}), default_claim_id='test')
        self.assertEqual(r.source.source_id, 'caller-explicit')
        self.assertEqual(r.task_type, 'intent_and_claims')


if __name__ == '__main__':
    unittest.main()
