import unittest

from evidence_mesh.caller_document import document_sections, numbered_claims
from evidence_mesh.contracts import request_from_caller_text, request_json
from evidence_mesh.leader import audit_claim
from test_evidence_leader import local_targets

POLICY = '普通商品签收后7天内，未使用且包装完整可申请退货；定制商品不支持无理由退货。因质量问题退货，商家承担运费；其他原因退货，消费者承担运费。退款在仓库收到退货并验收通过后3个工作日内处理。'
CLAIMS = ['普通商品签收后7天内，未使用且包装完整可以申请退货。', '所有商品都能在7天内无理由退货。', '无质量问题的退货，需要买家承担运费。', '退货运费由买家承担，质量问题退货运费由商家承担。', '退款在消费者寄出商品后3个工作日内到账。', '使用优惠券购买的商品，退货后优惠券会退回。']
TEXT = '只根据政策检查，不要把叮当的回答当成核验结果。\n政策原文：' + POLICY + '\n待核验客服回答：\n' + '\n'.join(f'{i}. {c}' for i,c in enumerate(CLAIMS, 1)) + '\nDAG 指定的上游产物摘要：\n叮当已完成协作规划并开始按 DAG 派发。'


class DocumentTests(unittest.IsolatedAsyncioTestCase):
    def test_flattened_real_caller_shape_and_json_envelope(self):
        flat = TEXT.replace('\n', ' ')
        for value in (flat, __import__('json').dumps({'text': flat}, ensure_ascii=False)):
            request = request_from_caller_text(value, default_claim_id='flat')
            self.assertEqual(request.source_excerpt, POLICY)
            self.assertEqual(numbered_claims(request.claim_text), CLAIMS)
            self.assertNotIn('DAG', request.claim_text)

    def test_numbers_in_prose_are_not_batch(self):
        self.assertEqual(numbered_claims('版本为0.1，金额3.5元，期限7天'), [])
        with self.assertRaises(ValueError):
            numbered_claims('1. 甲 3. 乙')

    def test_separates_evidence_claims_and_runtime_metadata(self):
        request = request_from_caller_text(TEXT, default_claim_id='regression')
        self.assertEqual(request.source_excerpt, POLICY)
        self.assertEqual(numbered_claims(request.claim_text), CLAIMS)
        self.assertNotIn('叮当', request.claim_text)
        self.assertFalse(request.source.source_id)

    def test_reversed_order_and_empty_sections(self):
        self.assertEqual(document_sections('回答：测试\n依据：原文')['claim_text'], '测试')
        with self.assertRaises(ValueError):
            document_sections('回答：\n依据：原文')
        with self.assertRaises(ValueError):
            numbered_claims('1.\n2. 内容')
        with self.assertRaises(ValueError):
            numbered_claims('\n'.join(f'{i}. 内容' for i in range(21)))

    async def test_six_rows_are_inspected_with_real_excerpt(self):
        request = request_from_caller_text(TEXT, default_claim_id='regression')
        result = await audit_claim(request_json(request), local_targets())
        self.assertEqual(len(result['claim_results']), 6)
        self.assertEqual([r['checked_claim'] for r in result['claim_results']], CLAIMS)
        for row in result['claim_results']:
            self.assertEqual(len(row['task_ids']), 3)
            self.assertTrue(row['partner_products']['evidence-grader']['input_assessment']['inspection_performed'])
            # No model is configured in this offline fixture. Receiving material
            # is not a semantic inspection, and the scout must say so explicitly.
            scout = row['partner_products']['contradiction-scout']
            self.assertTrue(scout['input_assessment']['evidence_provided'])
            self.assertFalse(scout['input_assessment']['inspection_performed'])
            self.assertFalse(scout['semantic_conflict']['coverage_complete'])
        self.assertIn('待核验回答', result['human_summary'])
        self.assertNotIn('DAG', result['human_summary'])

    async def test_missing_evidence_never_claims_conditional_support(self):
        request = request_from_caller_text('处理导致细胞死亡', default_claim_id='missing')
        result = await audit_claim(request_json(request), local_targets())
        self.assertEqual(result['decision'], 'no-evidence')
        self.assertNotIn('条件性支持', result['safe_utterance'])
        self.assertIn('未执行检查', result['human_summary'])
