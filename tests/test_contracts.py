import json
import unittest

from evidence_mesh.contracts import (
    MISSING_SOURCE_EXCERPT,
    request_from_caller_text,
    request_from_json,
    request_json,
)


class ContractUsabilityTests(unittest.TestCase):
    def test_aip_task_id_can_supply_missing_claim_id(self) -> None:
        request = request_from_json(
            json.dumps(
                {
                    "schema_version": "1.0",
                    "claim_text": "处理导致细胞死亡",
                    "source_excerpt": "处理组死亡比例升高，但机制尚不明确。",
                },
                ensure_ascii=False,
            ),
            default_claim_id="task-generated-id",
        )

        self.assertEqual(request.claim_id, "task-generated-id")
        self.assertEqual(request.source.source_id, "")
        canonical = json.loads(request_json(request))
        self.assertEqual(canonical["claim_id"], "task-generated-id")
        self.assertEqual(canonical["source"]["title"], "")

    def test_missing_claim_id_still_fails_without_aip_task_context(self) -> None:
        with self.assertRaisesRegex(ValueError, "claim_id"):
            request_from_json(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "claim_text": "处理导致细胞死亡",
                        "source_excerpt": "处理组死亡比例升高。",
                    },
                    ensure_ascii=False,
                )
            )

    def test_plain_text_caller_gets_fail_closed_request(self) -> None:
        request = request_from_caller_text(
            "处理导致细胞死亡", default_claim_id="task-plain-text"
        )

        self.assertEqual(request.claim_id, "task-plain-text")
        self.assertEqual(request.claim_text, "处理导致细胞死亡")
        self.assertEqual(request.source_excerpt, MISSING_SOURCE_EXCERPT)

    def test_compact_json_aliases_are_normalized(self) -> None:
        request = request_from_caller_text(
            json.dumps(
                {
                    "claim": "处理导致细胞死亡",
                    "evidence": "处理组死亡比例升高，但机制尚不明确。",
                },
                ensure_ascii=False,
            ),
            default_claim_id="task-compact-json",
        )

        self.assertEqual(request.claim_text, "处理导致细胞死亡")
        self.assertEqual(
            request.source_excerpt, "处理组死亡比例升高，但机制尚不明确。"
        )

    def test_chinese_labeled_sentence_is_split_for_upstream_agents(self) -> None:
        request = request_from_caller_text(
            "请核验：结论“处理导致细胞死亡”；证据摘录“处理组死亡比例升高，但机制尚不明确”。",
            default_claim_id="task-labeled-text",
        )

        self.assertEqual(request.claim_text, "处理导致细胞死亡")
        self.assertEqual(
            request.source_excerpt, "处理组死亡比例升高，但机制尚不明确"
        )

    def test_chinese_period_separates_explicit_evidence_label(self) -> None:
        request = request_from_caller_text(
            "结论：该产品使所有用户效率显著提高。依据：10名试用者中6人自述体验改善，未进行显著性检验。",
            default_claim_id="task-period-separated",
        )
        self.assertEqual(request.claim_text, "该产品使所有用户效率显著提高")
        self.assertEqual(request.source_excerpt, "10名试用者中6人自述体验改善，未进行显著性检验")

    def test_common_upstream_field_names_are_normalized(self) -> None:
        request = request_from_caller_text(
            json.dumps(
                {
                    "payload": {
                        "conclusion": "干预改善学习表现",
                        "context": "观察到相关性，但未进行随机分组。",
                    }
                },
                ensure_ascii=False,
            ),
            default_claim_id="task-upstream-envelope",
        )

        self.assertEqual(request.claim_text, "干预改善学习表现")
        self.assertEqual(request.source_excerpt, "观察到相关性，但未进行随机分组。")

    def test_english_labeled_sentence_is_split(self) -> None:
        request = request_from_caller_text(
            "Claim: the intervention caused the improvement; "
            "Evidence: the groups were observational and not randomized.",
            default_claim_id="task-english-text",
        )

        self.assertEqual(request.claim_text, "the intervention caused the improvement")
        self.assertEqual(
            request.source_excerpt,
            "the groups were observational and not randomized",
        )

    def test_general_agent_output_fields_and_delivery_context_are_preserved(self) -> None:
        request = request_from_caller_text(
            json.dumps(
                {
                    "answer": "该产品一定能够降低成本",
                    "materials": [
                        "试点部门的平均成本下降。",
                        "尚未排除季节变化和业务量差异。",
                    ],
                    "goal": "交付客户报告",
                    "audience": "采购负责人",
                    "constraints": ["不得新增事实", "保留不确定性"],
                },
                ensure_ascii=False,
            ),
            default_claim_id="task-general-output",
        )

        self.assertEqual(request.claim_text, "该产品一定能够降低成本")
        self.assertIn("试点部门", request.source_excerpt)
        self.assertIn("季节变化", request.source_excerpt)
        self.assertEqual(request.goal, "交付客户报告")
        self.assertEqual(request.audience, "采购负责人")
        self.assertEqual(request.constraints, ("不得新增事实", "保留不确定性"))

        canonical = json.loads(request_json(request))
        self.assertEqual(canonical["goal"], "交付客户报告")
        self.assertEqual(canonical["constraints"], ["不得新增事实", "保留不确定性"])


if __name__ == "__main__":
    unittest.main()
