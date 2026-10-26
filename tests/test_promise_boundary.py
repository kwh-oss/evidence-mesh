import copy
import unittest

from evidence_mesh.semantic_review import validate_review, validate_partial_review, render_review, semantic_decision

MATERIAL = '某培训班公布，2025年参加其培训且参加考试的100名学员中，80名通过考试。材料没有提供未参加培训者的数据，也未承诺每名学员都能通过。'
CLAIM = '参加这个培训班就保证能通过考试，所有学员的通过率都是100%。'


def actual_shape():
    # The classification and quote choices match the first public model test.
    return {'schema_version': '1.2', 'claims': [
        {'claim_span': '参加这个培训班就保证能通过考试', 'kind': 'prediction',
         'status': 'contradicted', 'contradiction_basis': 'direct-negation',
         'mechanisms': ['certainty', 'added-claim'], 'suggested_wording': None,
         'quotes': [{'text': '材料没有提供未参加培训者的数据，也未承诺每名学员都能通过。'}],
         'explanation': '这一保证缺少依据，且与材料所述未承诺相反。'},
        {'claim_span': '所有学员的通过率都是100%。', 'kind': 'fact',
         'status': 'contradicted', 'contradiction_basis': 'mutually-exclusive-value',
         'mechanisms': ['number'], 'suggested_wording': None,
         'quotes': [{'text': '2025年参加其培训且参加考试的100名学员中，80名通过考试。'}],
         'explanation': '该组100人中80人通过，80%与100%不一致。'}]}


class PromiseBoundaryTests(unittest.TestCase):
    def test_live_response_replay_retains_numeric_row_rejects_promise_inference(self):
        value = actual_shape()
        original = copy.deepcopy(value)
        result = validate_partial_review(value, CLAIM, MATERIAL)
        self.assertEqual(result['status'], 'partial-model-suggestion')
        self.assertFalse(result['coverage_complete'])
        self.assertEqual(len(result['claims']), 1)
        self.assertEqual(result['claims'][0]['claim_span'], '所有学员的通过率都是100%。')
        self.assertEqual(result['rejected_claims'][0]['reason_code'], 'promise-boundary')
        self.assertEqual(semantic_decision(result), 'incomplete')
        self.assertIn('材料未作承诺不能单独证明预测结果相反', render_review(result))
        self.assertNotIn('这一保证缺少依据，且', render_review(result))
        self.assertEqual(value, original)

    def test_lack_of_commitment_can_still_support_insufficient_evidence_label(self):
        value = actual_shape()
        value['claims'][0].update(status='unsupported', contradiction_basis='none',
                                 explanation='材料未作承诺，不能据此保证每个人通过。')
        result = validate_review(value, CLAIM, MATERIAL)
        self.assertTrue(result['coverage_complete'])
        self.assertEqual(len(result['claims']), 2)

    def test_explicit_claim_that_institution_made_promise_can_be_denied(self):
        row = actual_shape()['claims'][0]
        row.update(kind='fact', claim_span='培训班承诺每名学员都能通过')
        result = validate_review({'schema_version': '1.2', 'claims': [row]},
                                 row['claim_span'], MATERIAL)
        self.assertEqual(result['claims'][0]['status'], 'contradicted')

    def test_no_promise_wording_variants(self):
        for excerpt in ('机构没有承诺用户一定成功。', '平台不作任何保证。', '公司并未作出保证。'):
            row = actual_shape()['claims'][0]
            row['quotes'] = [{'text': excerpt}]
            with self.subTest(excerpt=excerpt), self.assertRaisesRegex(ValueError, 'absence of a promise'):
                validate_review({'schema_version': '1.2', 'claims': [row]}, row['claim_span'], excerpt)
