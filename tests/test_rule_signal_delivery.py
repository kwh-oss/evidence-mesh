import copy
import unittest

from evidence_mesh.contracts import request_from_caller_text, request_json as serialize
from evidence_mesh.human_result import human_summary
from evidence_mesh.leader import audit_claim, _decide
from evidence_mesh.processors import find_contradiction
from evidence_mesh.rule_signals import effective_contradiction_status, rule_signal_explanation
from test_evidence_leader import local_targets, request_json

MATERIAL = '某培训班公布，2025年参加其培训且参加考试的100名学员中，80名通过考试。材料没有提供未参加培训者的数据，也未承诺每名学员都能通过。'
CLAIM = '参加这个培训班就保证能通过考试，所有学员的通过率都是100%。'


def legacy_numeric_product():
    return {'input_assessment': {'evidence_provided': True, 'inspection_performed': True,
                                'inspection_scope': 'supplied-text-rules'},
            'payload': {'status': 'confirmed', 'indicators': ['numeric-mismatch']}}


class SignalBoundaryTests(unittest.IsolatedAsyncioTestCase):
    def test_legacy_product_is_downgraded_without_mutation(self):
        product = legacy_numeric_product()
        original = copy.deepcopy(product)
        self.assertEqual(effective_contradiction_status(product), 'possible')
        products = {'source-verifier': {'payload': {'status': 'verified'}},
                    'evidence-grader': {'payload': {'level': 'unsupported'}},
                    'contradiction-scout': product}
        risks = []
        self.assertEqual(_decide(products, risks), 'needs-review')
        self.assertNotIn('claim:confirmed-contradiction', risks)
        self.assertEqual(product, original)
        summary = human_summary({'decision': 'needs-review', 'partner_products': products})
        self.assertIn('尚未对齐', summary)
        self.assertNotIn('规则匹配到冲突线索', summary)

    def test_unrelated_number_differences_are_not_confirmed(self):
        request = request_from_caller_text(
            '原始材料：甲班有80名学员参加活动。\n待核验帖子：乙班有20名学员参加活动。',
            default_claim_id='different-groups')
        self.assertEqual(find_contradiction(request).status.value, 'possible')

    def test_equivalent_units_are_not_confirmed_by_bare_numbers(self):
        request = request_from_caller_text(
            '原始材料：该包装的净重为1000克。\n待核验帖子：该包装的净重为1千克。',
            default_claim_id='units')
        self.assertEqual(find_contradiction(request).status.value, 'possible')

    def test_no_performed_check_means_no_signal_explanation(self):
        product = legacy_numeric_product()
        product['input_assessment']['inspection_performed'] = False
        self.assertEqual(rule_signal_explanation(product), '')

    def test_mixed_strong_signal_not_silently_downgraded(self):
        product = legacy_numeric_product()
        product['payload']['indicators'].append('提高->降低')
        self.assertEqual(effective_contradiction_status(product), 'confirmed')

    def test_material_aliases_work_in_both_orders(self):
        for text in ('材料原文：' + MATERIAL + '\n待核验说法：' + CLAIM,
                     '待核验说法：' + CLAIM + '\n材料原文：' + MATERIAL):
            request = request_from_caller_text(text, default_claim_id='alias')
            self.assertEqual(request.claim_text, CLAIM)
            self.assertEqual(request.source_excerpt, MATERIAL)

    async def test_actual_case_has_readable_signal_and_no_fake_semantic_success(self):
        request = request_from_caller_text('材料原文：' + MATERIAL + '\n待核验说法：' + CLAIM,
                                         default_claim_id='training-case')
        result = await audit_claim(serialize(request), local_targets())
        self.assertEqual(result['decision'], 'needs-review')
        self.assertEqual(result['semantic_review']['status'], 'disabled')
        self.assertEqual(len(result['task_ids']), 3)
        # Model-disabled scout has not inspected the text. Do not manufacture
        # a numeric explanation from a partner that returned no findings.
        scout = result['partner_products']['contradiction-scout']
        self.assertFalse(scout['input_assessment']['inspection_performed'])
        self.assertNotIn('数字检查发现待核对线索', result['answer'])
        self.assertFalse(scout['semantic_conflict']['coverage_complete'])
        self.assertNotIn('claim:confirmed-contradiction', result['risk_flags'])
        # Legacy safe_utterance is a separate compatibility field; both must
        # preserve the unresolved status, without requiring identical wording.
        self.assertIn('仍需复核', result['safe_utterance'])
        self.assertIn('无法可靠判断', result['answer'])

    async def test_partner_failure_does_not_adopt_other_signals_as_completed_answer(self):
        targets = local_targets()
        import httpx
        from dataclasses import replace
        targets[0] = replace(targets[0], transport=httpx.MockTransport(
            lambda request: httpx.Response(503)))
        result = await audit_claim(request_json(CLAIM, MATERIAL), targets)
        self.assertEqual(result['decision'], 'incomplete')
        self.assertEqual(result['text_comparison']['status'], 'not-inspected')
        self.assertNotIn('数字检查发现', result['answer'])

    async def test_old_deployed_scout_is_interpreted_safely_and_raw_preserved(self):
        from unittest.mock import patch
        products = {
            'source-verifier': {'payload': {'status': 'incomplete'}},
            'evidence-grader': {'payload': {'level': 'unsupported'}},
            'contradiction-scout': legacy_numeric_product(),
        }
        async def recorded(target, *args):
            return {'state': 'completed', 'task_id': 'recorded-' + target.name,
                    'product': copy.deepcopy(products[target.name])}
        with patch('evidence_mesh.leader._call_partner', side_effect=recorded):
            result = await audit_claim(request_json(CLAIM, MATERIAL), local_targets())
        self.assertEqual(result['decision'], 'needs-review')
        self.assertEqual(result['partner_products']['contradiction-scout']['payload']['status'], 'confirmed')
        self.assertEqual(result['rule_signal_assessment']['reported_status'], 'confirmed')
        self.assertEqual(result['rule_signal_assessment']['effective_status'], 'possible')
        self.assertIn('尚未对齐', result['answer'])

    async def test_absent_numbers_do_not_fabricate_signal(self):
        result = await audit_claim(request_json('此方案可改善体验', '材料记录了试用者的体验描述。'), local_targets())
        self.assertNotIn('数字检查发现', result['answer'])
