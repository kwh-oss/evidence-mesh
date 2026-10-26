import unittest
from evidence_mesh.text_comparison import compare_text
from evidence_mesh.contracts import request_from_caller_text


class SpreadCheckTests(unittest.TestCase):
    def test_certainty_and_scope(self):
        for original, post in [('这种措施可能降低风险', '这种措施一定降低风险'),
                               ('部分设备支持此功能', '所有设备支持此功能')]:
            result = compare_text(post, original)
            self.assertEqual(result['status'], 'spread-boundary-difference')
            self.assertEqual(result['evidence_spans'], [original])
            self.assertIn(original, result['answer'])
            self.assertIn('传播失真线索', result['answer'])
            self.assertNotIn('不证明消息真假', result['answer'])

    def test_unchanged_is_not_distortion(self):
        self.assertEqual(compare_text('部分设备支持此功能', '部分设备支持此功能')['status'], 'textually-supported')

    def test_unrelated_negated_and_multiple_edits_abstain(self):
        for original, post in [('部分设备支持此功能', '所有药物都有疗效'),
                               ('这种措施不一定降低风险', '这种措施可能降低风险'),
                               ('这种措施可能降低风险', '这种措施一定消除风险')]:
            self.assertEqual(compare_text(post, original)['status'], 'undetermined')

    def test_no_material(self):
        self.assertEqual(compare_text('所有设备都安全', '')['status'], 'not-inspected')

    def test_new_labels(self):
        for label in ('政策材料', '原始材料', '对照材料'):
            request = request_from_caller_text(f'{label}：部分设备支持此功能。\n待核验帖子：所有设备支持此功能。', default_claim_id='spread-label-test')
            self.assertEqual(request.source_excerpt, '部分设备支持此功能。')
            self.assertEqual(request.claim_text, '所有设备支持此功能。')
