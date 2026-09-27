import unittest

from evidence_mesh import (
    ClaimDecision,
    EvidenceFinding,
    EvidenceLevel,
    SourceRef,
    summarize_findings,
)


class EvidenceMeshTests(unittest.TestCase):
    def setUp(self) -> None:
        self.source = SourceRef("doi:example", "Example study", "Results, paragraph 2")

    def finding(self, claim_id: str, level: EvidenceLevel) -> EvidenceFinding:
        return EvidenceFinding(
            claim_id=claim_id,
            agent_id="partner-test",
            level=level,
            rationale="A bounded test rationale.",
            sources=(self.source,),
            confidence=0.8,
        )

    def test_direct_only_is_supported(self) -> None:
        summary = summarize_findings(
            ["c1"], [self.finding("c1", EvidenceLevel.DIRECT)]
        )
        self.assertEqual(summary.decisions["c1"], ClaimDecision.SUPPORTED)
        self.assertEqual(summary.evidence_coverage, 1.0)

    def test_direct_and_unsupported_is_conflicting(self) -> None:
        summary = summarize_findings(
            ["c1"],
            [
                self.finding("c1", EvidenceLevel.DIRECT),
                self.finding("c1", EvidenceLevel.UNSUPPORTED),
            ],
        )
        self.assertEqual(summary.decisions["c1"], ClaimDecision.CONFLICTING)
        self.assertIn("c1:conflict", summary.risk_flags)

    def test_missing_finding_is_not_silently_accepted(self) -> None:
        summary = summarize_findings(
            ["c1", "c2"], [self.finding("c1", EvidenceLevel.INDIRECT)]
        )
        self.assertEqual(summary.decisions["c1"], ClaimDecision.NEEDS_REVIEW)
        self.assertEqual(summary.decisions["c2"], ClaimDecision.NO_EVIDENCE)
        self.assertEqual(summary.evidence_coverage, 0.5)

    def test_unknown_claim_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "unknown claims"):
            summarize_findings(
                ["c1"], [self.finding("not-requested", EvidenceLevel.DIRECT)]
            )

    def test_invalid_confidence_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "between 0 and 1"):
            EvidenceFinding(
                claim_id="c1",
                agent_id="partner-test",
                level=EvidenceLevel.DIRECT,
                rationale="Invalid confidence test.",
                confidence=1.1,
            )


if __name__ == "__main__":
    unittest.main()
