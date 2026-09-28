import json
import unittest

from evidence_mesh.contracts import request_from_json, request_json


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


if __name__ == "__main__":
    unittest.main()
