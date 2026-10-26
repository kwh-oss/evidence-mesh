import unittest
from evidence_mesh.text_comparison import compare_text


class TextComparisonTests(unittest.TestCase):
    def test_refund_trigger_and_action_differences(self):
        result = compare_text('退款在消费者寄出商品后3个工作日内到账。', '退款在仓库收到退货并验收通过后3个工作日内处理。')
        self.assertEqual(result['status'], 'wording-difference')
        self.assertEqual([d['field'] for d in result['differences']], ['起算条件', '承诺的动作'])
        self.assertIn('验收通过', result['answer'])
        self.assertNotIn('task-', result['answer'])

    def test_other_topics_and_durations(self):
        result = compare_text('维修在申请后5天内完成。', '维修在收到设备后2个工作日内完成。')
        self.assertEqual(len(result['differences']), 3)
        self.assertEqual(result['suggested_wording'], '维修在收到设备后2个工作日内完成。')

    def test_ambiguous_rules_abstain(self):
        result = compare_text('退款在寄出后3天内到账。', '退款在验收后3天内处理；退款在特殊审批后1天内到账。')
        self.assertEqual(result['status'], 'undetermined')

    def test_synonyms_are_not_asserted_as_conflict(self):
        result = compare_text('维修在收到机器后3天内完成。', '维修在收到设备后3天内完成。')
        self.assertEqual(result['status'], 'wording-difference')
        self.assertNotIn('冲突', result['answer'])

    def test_missing_and_unmentioned_material(self):
        self.assertEqual(compare_text('任何问题', '')['status'], 'not-inspected')
        self.assertEqual(compare_text('优惠券会退回', '运费由商家承担。')['status'], 'no-explicit-reference')

    def test_number_variants_and_negated_context(self):
        self.assertEqual(compare_text('退款在验收后三工作日内到账。', '退款在验收后3个工作日内到账。')['differences'], [])
        self.assertEqual(compare_text('并非退款在寄出后3天内到账。', '退款在验收后3天内处理。')['status'], 'undetermined')

    def test_verbatim_only(self):
        self.assertEqual(compare_text('运费由商家承担。', '质量问题运费由商家承担。')['status'], 'undetermined')
        self.assertEqual(compare_text('运费由商家承担。', '运费由商家承担。')['status'], 'textually-supported')

    def test_preserves_conditions_in_simple_paraphrase(self):
        result = compare_text('普通商品未使用且包装完整可以退货。', '普通商品未使用且包装完整可退货。')
        self.assertEqual(result['status'], 'textually-supported')
        self.assertEqual(compare_text('普通商品可以退货。', '普通商品未使用且包装完整可退货。')['status'], 'undetermined')

    def test_explicit_exception_across_categories(self):
        for claim, evidence in [('所有商品都能在7天内无理由退货。','定制商品不支持无理由退货。'), ('所有用户都可以领取补贴。','未实名用户不允许领取补贴。')]:
            self.assertEqual(compare_text(claim, evidence)['status'], 'explicit-exception')
        self.assertEqual(compare_text('所有商品都能无理由退货。', '定制商品不支持无理由退货，除非商家同意。')['status'], 'undetermined')
