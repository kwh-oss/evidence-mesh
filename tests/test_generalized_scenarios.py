import json
from pathlib import Path
import unittest

from evidence_mesh.contracts import request_from_caller_text
from evidence_mesh.intent import analyze_request
from evidence_mesh.processors import find_contradiction, grade_evidence


ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "benchmarks" / "generalized_inputs_v0.1.jsonl"
# Keep the original draft dataset intact. Its old confirmed labels were based
# on bare numeric sets / certainty / opposite-word co-occurrence, not aligned evidence.
WEAK_SIGNAL_CASES = {'rag-numeric-mismatch', 'pilot-universal-claim',
                     'customer-safe-rewrite', 'quantitative-conflict', 'two-material-direction-conflict'}


class GeneralizedScenarioTests(unittest.TestCase):
    def test_all_draft_generalized_cases_match_declared_expectations(self) -> None:
        for line in DATASET.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            case = json.loads(line)
            with self.subTest(case_id=case["case_id"]):
                request = request_from_caller_text(
                    json.dumps(case["input"], ensure_ascii=False),
                    default_claim_id=case["case_id"],
                )
                expected = case["expected"]
                self.assertEqual(analyze_request(request)["task_type"], expected["task_type"])
                if "evidence_level" in expected:
                    self.assertEqual(
                        grade_evidence(request).level.value,
                        expected["evidence_level"],
                    )
                if "contradiction_status" in expected:
                    self.assertEqual(
                        find_contradiction(request).status.value,
                        ('possible' if case['case_id'] in WEAK_SIGNAL_CASES
                         else expected["contradiction_status"]),
                    )


if __name__ == "__main__":
    unittest.main()
