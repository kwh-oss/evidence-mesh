import unittest
from evidence_mesh.semantic_review import validate_partial_review


def model_row(claim, quote, status='contradicted'):
    return {'schema_version':'1.2', 'claims':[{
        'claim_span':claim, 'kind':'fact', 'status':status,
        'contradiction_basis':'direct-negation' if status=='contradicted' else 'none',
        'mechanisms':['certainty'], 'quotes':[{'text':quote}],
        'explanation':'比较所提供材料的要求强度。', 'suggested_wording':None}]}


class ModalityTests(unittest.TestCase):
    def test_actual_high_school_response_rejected_not_relabelled(self):
        claim='因此北京所有普通高中也必须执行同样安排。'
        quote='普通高中可以参考执行。'
        result=validate_partial_review(model_row(claim,quote),claim,quote)
        self.assertEqual(result['rejected_claims'][0]['reason_code'],'modality-boundary')
        self.assertFalse(result['coverage_complete'])
        self.assertEqual(result['claims'],[])

    def test_new_domain_weak_modalities_not_direct_negation(self):
        for quote in ('鼓励博物馆延时开放。','建议企业设置休息区。','场馆原则上预约入场。','其他场馆可参考执行。'):
            with self.subTest(quote=quote):
                claim='所有相关机构必须无例外执行。'
                result=validate_partial_review(model_row(claim,quote),claim,quote)
                self.assertEqual(result['rejected_claims'][0]['reason_code'],'modality-boundary')

    def test_strengthening_can_be_overstated_or_unsupported(self):
        claim='场馆必须延时开放。'
        quote='鼓励场馆延时开放。'
        for status in ('overstated','unsupported'):
            self.assertEqual(validate_partial_review(model_row(claim,quote,status),claim,quote)['claims'][0]['status'],status)

    def test_explicit_negative_obligation_not_rejected(self):
        claim='参与者必须缴费。'
        quote='参与者可以参加活动，无需缴费。'
        self.assertEqual(validate_partial_review(model_row(claim,quote),claim,quote)['claims'][0]['status'],'contradicted')

    def test_explicit_must_not_downgraded(self):
        claim='参与者必须登记。'
        quote='参与者必须登记。'
        self.assertEqual(validate_partial_review(model_row(claim,quote,'supported'),claim,quote)['claims'][0]['status'],'supported')
