import unittest

from evidence_mesh.semantic_review import validate_partial_review, validate_review, render_review


def response(span, kind='opinion', status='opinion'):
    return {'schema_version': '1.2', 'claims': [{
        'claim_span': span, 'kind': kind, 'status': status,
        'contradiction_basis': 'none', 'mechanisms': [], 'suggested_wording': None,
        'quotes': [{'text': '100名参加考试的学员中80名通过，未承诺人人通过。'}],
        'explanation': '根据所提供材料说明判断范围。'}]}


class EvidenceBoundaryClassificationTests(unittest.TestCase):
    def test_statistical_boundary_cannot_be_skipped_as_opinion(self):
        span = '这一统计不代表每个参加培训的人都保证通过'
        excerpt = '100名参加考试的学员中80名通过，未承诺人人通过。'
        result = validate_partial_review(response(span), span, excerpt)
        self.assertEqual(result['status'], 'failed-or-invalid')
        self.assertEqual(result['claims'], [])
        self.assertEqual(result['rejected_claims'][0]['reason_code'], 'classification-boundary')
        self.assertIn('可核对', render_review(result))

    def test_supported_fact_boundary_is_allowed(self):
        span = '这一统计不代表每个参加培训的人都保证通过'
        result = validate_review(response(span, 'fact', 'supported'), span,
                                 '100名参加考试的学员中80名通过，未承诺人人通过。')
        self.assertEqual(result['claims'][0]['status'], 'supported')

    def test_real_value_judgment_remains_opinion(self):
        for span in ('我觉得这个培训班很值得参加', '我认为这个数据看起来很有趣'):
            result = validate_review(response(span), span,
                                     '100名参加考试的学员中80名通过，未承诺人人通过。')
            self.assertEqual(result['claims'][0]['status'], 'opinion')

    def test_valid_numeric_row_is_retained_alongside_rejected_boundary(self):
        excerpt = '100名参加考试的学员中80名通过，未承诺人人通过。'
        boundary = '这一统计不代表人人保证通过'
        numerical = '该组通过率为80%'
        value = response(boundary)
        value['claims'].extend(response(numerical, 'fact', 'supported')['claims'])
        result = validate_partial_review(value, numerical + '；' + boundary, excerpt)
        self.assertEqual(result['status'], 'partial-model-suggestion')
        self.assertEqual(len(result['claims']), 1)
        self.assertEqual(result['claims'][0]['claim_span'], numerical)
