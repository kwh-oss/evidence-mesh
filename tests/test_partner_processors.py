import json
import unittest

from evidence_mesh.contracts import (
    ContradictionStatus,
    SCHEMA_VERSION,
    SourceStatus,
    request_from_json,
)
from evidence_mesh.models import EvidenceLevel
from evidence_mesh.processors import find_contradiction, grade_evidence, verify_source


def request_json(claim: str, excerpt: str) -> str:
    return json.dumps(
        {
            "schema_version": SCHEMA_VERSION,
            "claim_id": "claim-1",
            "claim_text": claim,
            "source": {
                "source_id": "doi:example",
                "title": "Example controlled study",
                "locator": "Results, paragraph 2",
            },
            "source_excerpt": excerpt,
        },
        ensure_ascii=False,
    )


class PartnerProcessorTests(unittest.TestCase):
    def test_source_verifier_accepts_traceable_excerpt(self) -> None:
        request = request_from_json(
            request_json("材料提高抗菌率", "结果显示该材料在测试条件下提高抗菌率。")
        )
        self.assertEqual(verify_source(request).status, SourceStatus.VERIFIED)

    def test_grader_detects_explicit_support(self) -> None:
        request = request_from_json(
            request_json("材料提高抗菌率", "结果显示材料提高抗菌率，重复实验趋势一致。")
        )
        self.assertEqual(grade_evidence(request).level, EvidenceLevel.DIRECT)

    def test_grader_downgrades_causal_overreach(self) -> None:
        request = request_from_json(
            request_json("处理导致细胞死亡", "处理与细胞死亡相关，可能涉及氧化应激。")
        )
        self.assertEqual(grade_evidence(request).level, EvidenceLevel.CONDITIONAL)

    def test_grader_downgrades_unsupported_significance(self) -> None:
        request = request_from_json(
            request_json(
                "处理显著提高了存活率",
                "处理组平均值较高，但未进行显著性检验。",
            )
        )
        finding = grade_evidence(request)
        self.assertEqual(finding.level, EvidenceLevel.CONDITIONAL)
        self.assertIn("significance", finding.rationale)

    def test_grader_downgrades_universal_claim_from_pilot(self) -> None:
        request = request_from_json(
            request_json(
                "该方案一定能够降低所有用户的成本",
                "小规模试点中观察到部分用户成本下降。",
            )
        )
        finding = grade_evidence(request)
        self.assertEqual(finding.level, EvidenceLevel.CONDITIONAL)
        self.assertIn("limited", finding.rationale)

    def test_contradiction_scout_detects_direction_reversal(self) -> None:
        request = request_from_json(
            request_json("处理提高细胞活性", "在相同条件下，处理降低细胞活性。")
        )
        self.assertEqual(
            find_contradiction(request).status, ContradictionStatus.CONFIRMED
        )
        self.assertEqual(grade_evidence(request).level, EvidenceLevel.CONFLICTING)

    def test_contradiction_scout_detects_conflict_between_two_materials(self) -> None:
        request = request_from_json(
            request_json(
                "比较两份材料是否一致",
                "材料A称销量提高；材料B称销量降低。",
            )
        )
        result = find_contradiction(request)
        self.assertEqual(result.status, ContradictionStatus.POSSIBLE)
        self.assertIn("internal:提高<->降低", result.indicators)

    def test_contradiction_scout_flags_certainty_boundary(self) -> None:
        request = request_from_json(
            request_json(
                "该产品一定能够降低成本",
                "小规模试点提示产品可能降低部分成本。",
            )
        )
        result = find_contradiction(request)
        self.assertEqual(result.status, ContradictionStatus.POSSIBLE)
        self.assertIn("certainty-boundary-conflict", result.indicators)

    def test_contract_rejects_wrong_schema_version(self) -> None:
        payload = json.loads(request_json("claim", "long enough source excerpt"))
        payload["schema_version"] = "9.9"
        with self.assertRaisesRegex(ValueError, "schema_version"):
            request_from_json(json.dumps(payload))


if __name__ == "__main__":
    unittest.main()
