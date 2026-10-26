"""Machine-authored local regression cases, not a real-world accuracy benchmark."""
import json
import unittest

from evidence_mesh.contracts import request_from_caller_text, request_json
from evidence_mesh.leader import audit_claim
from evidence_mesh.models import EvidenceLevel
from evidence_mesh.processors import find_contradiction, grade_evidence
from test_evidence_leader import local_targets


def normalize(value):
    return request_from_caller_text(json.dumps(value, ensure_ascii=False), default_claim_id="local-domain")


class CrossDomainReadinessTests(unittest.IsolatedAsyncioTestCase):
    async def passport(self, value):
        return await audit_claim(request_json(normalize(value)), local_targets())

    async def test_intent_only_does_not_suggest_evidence_support(self):
        result = await self.passport({"task_type": "intent_and_claims", "draft": "请比较两款产品"})
        self.assertEqual(result["task_ids"], {})
        self.assertNotIn("条件性支持", result["safe_utterance"])
        self.assertIn("尚未核验", result["safe_utterance"])

    async def test_news_no_control_cannot_establish_causality(self):
        result = await self.passport({"task_type": "claim_boundary_check", "draft": "新措施导致销量提高",
                                     "context": "措施实施后销量增加，但没有对照组，无法判断因果。"})
        self.assertEqual(result["partner_products"]["evidence-grader"]["payload"]["level"], "conditional")
        self.assertNotEqual(result["decision"], "supported")

    async def test_rag_known_conflict_not_hidden_when_scout_skipped(self):
        result = await self.passport({"task_type": "answer_grounding_check", "answer": "该地区就业率提高",
                                     "context": "最新通报称该地区就业率降低。"})
        self.assertEqual(result["decision"], "conflicting")
        self.assertNotIn("contradiction-scout", result["task_ids"])

    async def test_rag_restrictions_not_unconditional_promise(self):
        result = await self.passport({"task_type": "answer_grounding_check", "answer": "所有用户均可无条件退款",
                                     "context": "购买后七天内，未使用的订单可申请退款。"})
        self.assertEqual(result["partner_products"]["evidence-grader"]["payload"]["level"], "conditional")
        self.assertNotEqual(result["decision"], "supported")

    async def test_profile_single_conversation_not_lifetime_preference(self):
        result = await self.passport({"task_type": "claim_boundary_check", "draft": "用户永远只购买低价商品",
                                     "context": "本次会话中用户询问了两款低价商品。"})
        self.assertEqual(result["partner_products"]["evidence-grader"]["payload"]["level"], "conditional")

    async def test_customer_chinese_duration_difference(self):
        result = await self.passport({"task_type": "cross_text_conflict", "draft": "退款期限为七天",
                                     "context": "材料A：退款期限为七天。材料B：退款期限为三天。"})
        # The dedicated semantic scout no longer silently falls back to rules.
        self.assertEqual(result["decision"], "needs-review")
        scout = result['partner_products']['contradiction-scout']
        self.assertFalse(scout['input_assessment']['inspection_performed'])
        self.assertFalse(scout['semantic_conflict']['coverage_complete'])

    async def test_equal_duration_arabic_and_chinese_is_not_conflict(self):
        result = await self.passport({"task_type": "cross_text_conflict", "draft": "退款期限为7天",
                                     "context": "材料A：退款期限为七天。材料B：退款期限为7天。"})
        self.assertEqual(result["partner_products"]["contradiction-scout"]["payload"]["status"], "none-found")

    def test_different_duration_subjects_not_compared(self):
        result = find_contradiction(normalize({"draft": "退款期限为七天",
                                               "context": "退款期限为七天。配送期限为三天。"}))
        self.assertEqual(result.status.value, "none-found")

    def test_week_and_days_equivalent(self):
        result = find_contradiction(normalize({"draft": "退款期限为一周", "context": "退款期限为七天。"}))
        self.assertEqual(result.status.value, "none-found")

    def test_arabic_different_fields_not_compared_as_bare_numbers(self):
        result = find_contradiction(normalize({"draft": "退款期限为7天", "context": "配送期限为3天。"}))
        self.assertEqual(result.status.value, "none-found")

    def test_24_hours_and_one_day_equivalent(self):
        result = find_contradiction(normalize({"draft": "响应时间为24小时", "context": "响应时间为1天。"}))
        self.assertEqual(result.status.value, "none-found")

    def test_scope_claim_exact_quote_still_needs_limitation(self):
        result = grade_evidence(normalize({"draft": "用户永远只购买低价商品",
                                          "context": "本次会话不能证明用户永远只购买低价商品。"}))
        self.assertNotEqual(result.level, EvidenceLevel.DIRECT)

    async def test_missing_context_does_not_get_full_support(self):
        result = await self.passport({"task_type": "full_preflight", "draft": "所有用户可以退款"})
        self.assertNotEqual(result["decision"], "supported")
        self.assertIn("supporting context or evidence", result["missing_information"])

    async def test_full_legacy_support_still_works(self):
        result = await self.passport({"draft": "服务支持退款", "context": "官方条款明确规定服务支持退款，请按规则申请。",
                                     "source": {"source_id":"local-policy", "title":"服务条款", "locator":"第2条"}})
        self.assertEqual(result["decision"], "supported")
        self.assertEqual(len(result["task_ids"]), 3)
