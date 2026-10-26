import json
import unittest

import httpx

from evidence_mesh.contracts import SCHEMA_VERSION
from evidence_mesh.contradiction_partner import app as contradiction_app
from evidence_mesh.grader_partner import app as grader_app
from evidence_mesh.leader import PartnerTarget, audit_claim
from evidence_mesh.source_partner import app as source_app


def request_json(claim: str, excerpt: str) -> str:
    return json.dumps(
        {
            "schema_version": SCHEMA_VERSION,
            "claim_id": "claim-leader",
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


def local_targets() -> list[PartnerTarget]:
    return [
        PartnerTarget(
            "source-verifier",
            "http://source.test/rpc",
            httpx.ASGITransport(app=source_app),
        ),
        PartnerTarget(
            "evidence-grader",
            "http://grader.test/rpc",
            httpx.ASGITransport(app=grader_app),
        ),
        PartnerTarget(
            "contradiction-scout",
            "http://contradiction.test/rpc",
            httpx.ASGITransport(app=contradiction_app),
        ),
    ]


class EvidenceLeaderTests(unittest.IsolatedAsyncioTestCase):
    async def test_external_review_does_not_replace_core_verdict(self):
        from unittest.mock import AsyncMock
        collaborator = type('Reviewer', (), {})()
        collaborator.review = AsyncMock(return_value={'task_id': 'external-task',
            'partner_name': '独立伙伴', 'status': 'grounded-suggestions',
            'issues': [{'quote': '处理降低细胞活性', 'explanation': '需要注意方向。'}]})
        passport = await audit_claim(request_json('处理提高细胞活性', '在相同条件下，处理降低细胞活性。'),
            local_targets(), external_collaborator=collaborator, collaboration_root='actual-root')
        self.assertEqual(passport['decision'], 'conflicting')
        self.assertIn('外部独立复核', passport['answer'])
        request, _ = collaborator.review.await_args.args
        self.assertEqual(request.claim_id, 'actual-root')
        self.assertIn('降低细胞活性', request.source_excerpt)

    async def test_supported_passport_contains_three_task_ids(self) -> None:
        passport = await audit_claim(
            request_json(
                "材料提高抗菌率",
                "结果显示材料提高抗菌率，并在重复实验中观察到相同趋势。",
            ),
            local_targets(),
        )
        self.assertEqual(passport["decision"], "supported")
        self.assertEqual(len(passport["task_ids"]), 3)
        self.assertEqual(len(passport["partner_products"]), 3)
        self.assertEqual(passport["risk_flags"], [])
        self.assertEqual(passport["task_type"], "answer_grounding_check")
        self.assertEqual(passport["intent"]["speech_act"], "claim")
        self.assertEqual(
            passport["atomic_claims"][0]["original_span"], "材料提高抗菌率"
        )
        self.assertEqual(passport["safe_utterance"], "材料提高抗菌率")

    async def test_causal_overreach_requires_review(self) -> None:
        passport = await audit_claim(
            request_json(
                "处理导致细胞死亡",
                "结果提示处理与细胞死亡相关，可能涉及氧化应激。",
            ),
            local_targets(),
        )
        self.assertEqual(passport["decision"], "needs-review")
        self.assertIn("claim:evidence-conditional", passport["risk_flags"])
        self.assertIn("有限或条件性支持", passport["safe_utterance"])

    async def test_confirmed_contradiction_is_not_overridden(self) -> None:
        passport = await audit_claim(
            request_json(
                "处理提高细胞活性",
                "在相同条件下，处理降低细胞活性。",
            ),
            local_targets(),
        )
        self.assertEqual(passport["decision"], "conflicting")
        self.assertIn("claim:confirmed-contradiction", passport["risk_flags"])
        self.assertIn("存在冲突", passport["safe_utterance"])

    async def test_missing_partner_configuration_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "targets must be exactly"):
            await audit_claim(
                request_json("材料提高抗菌率", "结果显示材料提高抗菌率。"),
                local_targets()[:2],
            )


if __name__ == "__main__":
    unittest.main()
