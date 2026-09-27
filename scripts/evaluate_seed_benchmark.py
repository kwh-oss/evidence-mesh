"""Evaluate deterministic Partners against the draft synthetic seed set."""

from collections import Counter, defaultdict
import json
from pathlib import Path

from evidence_mesh.contracts import AuditRequest
from evidence_mesh.processors import find_contradiction, grade_evidence, verify_source


ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "benchmarks" / "evidence_seed_v0.1.jsonl"


def main() -> None:
    rows = [
        json.loads(line)
        for line in DATASET.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    dimensions = {
        "source": ("expected_source_status", lambda request: verify_source(request).status.value),
        "evidence": ("expected_evidence_level", lambda request: grade_evidence(request).level.value),
        "contradiction": (
            "expected_contradiction_status",
            lambda request: find_contradiction(request).status.value,
        ),
    }

    result = {
        "dataset": DATASET.name,
        "review_status": "draft-machine-authored",
        "sample_count": len(rows),
        "dimensions": {},
        "errors": [],
    }

    for dimension, (expected_key, predict) in dimensions.items():
        correct = 0
        confusion: dict[str, Counter[str]] = defaultdict(Counter)
        for row in rows:
            request = AuditRequest.from_dict(row)
            expected = row[expected_key]
            predicted = predict(request)
            confusion[expected][predicted] += 1
            if predicted == expected:
                correct += 1
            else:
                result["errors"].append(
                    {
                        "id": row["id"],
                        "dimension": dimension,
                        "expected": expected,
                        "predicted": predicted,
                    }
                )
        result["dimensions"][dimension] = {
            "correct": correct,
            "total": len(rows),
            "accuracy": round(correct / len(rows), 4),
            "confusion": {
                expected: dict(sorted(predictions.items()))
                for expected, predictions in sorted(confusion.items())
            },
        }

    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
