import unittest
from evidence_mesh.text_comparison import compare_text

POLICY = '因质量问题退货，商家承担运费；其他原因退货，消费者承担运费。'


class CostRuleTests(unittest.TestCase):
    def test_explicit_complement_branch_and_role_alias(self):
        result = compare_text('无质量问题的退货，需要买家承担运费。', POLICY)
        self.assertEqual(result['status'], 'conditional-correspondence')
        self.assertIn('其他原因', result['answer'])
        self.assertIn('如果实际付款主体不同', result['answer'])
        self.assertEqual(result['evidence_spans'], ['因质量问题退货，商家承担运费', '其他原因退货，消费者承担运费'])

    def test_payer_change_and_missing_condition(self):
        self.assertEqual(compare_text('无质量问题的退货，需要商家承担运费。', POLICY)['status'], 'cost-payer-difference')
        result = compare_text('退货运费由买家承担，质量问题退货运费由商家承担。', POLICY)
        self.assertEqual(result['status'], 'scope-clarification')
        self.assertEqual(result['suggested_wording'], POLICY)

    def test_other_domain_without_shipping_lookup(self):
        result = compare_text('非人为原因的维修，需要商家承担费用。', '因人为原因维修，消费者承担费用；其他原因维修，商家承担费用。')
        self.assertEqual(result['status'], 'conditional-correspondence')

    def test_incomplete_or_multiple_rules_abstain(self):
        self.assertEqual(compare_text('无质量问题的退货，需要买家承担运费。', '其他原因退货，消费者承担运费。')['status'], 'undetermined')
        self.assertEqual(compare_text('无质量问题的退货，需要买家承担运费。', POLICY + '因运输损坏退货，平台承担运费。')['status'], 'undetermined')
        self.assertEqual(compare_text('无质量问题的退货，需要买家承担运费。', POLICY + '会员退货，平台承担运费。')['status'], 'undetermined')
        self.assertEqual(compare_text('无质量问题的退货，需要买家承担运费。', POLICY + '会员享受免运费。')['status'], 'undetermined')

    def test_unknown_topic_is_not_a_negative_policy(self):
        result = compare_text('使用优惠券购买的商品，退货后优惠券会退回。', POLICY)
        self.assertEqual(result['status'], 'no-explicit-reference')
        self.assertIn('“优惠券”', result['answer'])
        self.assertIn('无法依据这段原文确认', result['answer'])
        self.assertIn('没有找到', result['answer'])
        self.assertIsNone(result.get('suggested_wording'))
        self.assertEqual(compare_text('租车后押金会退回。', '车辆须按时归还。')['status'], 'no-explicit-reference')

    def test_reference_negation_never_becomes_suggestion(self):
        result = compare_text('退款在寄出后3天内到账。', '并非退款在验收后3天内处理。')
        self.assertEqual(result['status'], 'undetermined')
        self.assertIsNone(result['suggested_wording'])
