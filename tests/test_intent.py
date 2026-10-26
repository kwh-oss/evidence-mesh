import unittest

from evidence_mesh.contracts import AuditRequest, MISSING_SOURCE_EXCERPT
from evidence_mesh.intent import analyze_request, safe_utterance
from evidence_mesh.models import SourceRef


def request(
    claim: str,
    excerpt: str = MISSING_SOURCE_EXCERPT,
    *,
    task_type: str = "auto",
    goal: str = "",
    audience: str = "",
) -> AuditRequest:
    return AuditRequest(
        claim_id="claim-intent",
        claim_text=claim,
        source=SourceRef(source_id="", title="", locator=""),
        source_excerpt=excerpt,
        task_type=task_type,
        goal=goal,
        audience=audience,
    )


class IntentAnalysisTests(unittest.TestCase):
    def test_plain_question_routes_to_intent_analysis_without_forced_clarification(self) -> None:
        result = analyze_request(request("为什么本季度成本上升？"))

        self.assertEqual(result["task_type"], "intent_and_claims")
        self.assertEqual(result["intent"]["speech_act"], "question")
        self.assertFalse(result["clarification_required"])
        self.assertEqual(result["atomic_claims"][0]["original_span"], "为什么本季度成本上升？")

    def test_rag_answer_with_context_routes_to_grounding_check(self) -> None:
        result = analyze_request(
            request(
                "该政策已经在全国实施",
                "材料只说明该政策正在三个城市试点。",
            )
        )

        self.assertEqual(result["task_type"], "answer_grounding_check")
        self.assertEqual(result["atomic_claims"][0]["claim_type"], "factual")

    def test_report_goal_routes_to_claim_boundary_check(self) -> None:
        result = analyze_request(
            request(
                "处理导致细胞死亡",
                "处理与细胞死亡相关。",
                goal="写入研究报告结论",
                audience="同行评审者",
            )
        )

        self.assertEqual(result["task_type"], "claim_boundary_check")
        self.assertEqual(result["atomic_claims"][0]["claim_type"], "causal")
        self.assertEqual(result["intent"]["audience"], "同行评审者")

    def test_two_materials_route_to_conflict_check(self) -> None:
        result = analyze_request(
            request(
                "比较两份材料是否冲突",
                "材料A称销量提高；材料B称销量降低。",
            )
        )

        self.assertEqual(result["task_type"], "cross_text_conflict")

    def test_rewrite_goal_routes_to_safe_rewrite(self) -> None:
        result = analyze_request(
            request(
                "我们的方案必然成功",
                "当前只有小规模试点结果。",
                goal="改写为客户汇报措辞",
            )
        )

        self.assertEqual(result["task_type"], "safe_rewrite")

    def test_strong_separator_preserves_traceable_atomic_claim_spans(self) -> None:
        result = analyze_request(
            request("销量提高；利润下降", "季度经营材料。")
        )

        self.assertEqual(
            [item["original_span"] for item in result["atomic_claims"]],
            ["销量提高", "利润下降"],
        )

    def test_safe_utterance_never_promotes_an_unverified_claim(self) -> None:
        claim = "该产品一定能够降低成本"
        self.assertEqual(safe_utterance(claim, "supported"), claim)
        self.assertIn("不足以支持", safe_utterance(claim, "no-evidence"))
        self.assertIn("暂不能确认", safe_utterance(claim, "incomplete"))
        self.assertIn("存在冲突", safe_utterance(claim, "conflicting"))


if __name__ == "__main__":
    unittest.main()
