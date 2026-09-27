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

    def test_contradiction_scout_detects_direction_reversal(self) -> None:
        request = request_from_json(
            request_json("处理提高细胞活性", "在相同条件下，处理降低细胞活性。")
        )
        self.assertEqual(
            find_contradiction(request).status, ContradictionStatus.CONFIRMED
        )

    def test_contract_rejects_wrong_schema_version(self) -> None:
        payload = json.loads(request_json("claim", "long enough source excerpt"))
        payload["schema_version"] = "9.9"
        with self.assertRaisesRegex(ValueError, "schema_version"):
            request_from_json(json.dumps(payload))


if __name__ == "__main__":
    unittest.main()
