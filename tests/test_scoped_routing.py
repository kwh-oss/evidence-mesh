"""Local-only routing regressions; these do not generate platform calls."""
import json
import unittest
from unittest.mock import AsyncMock, patch

from evidence_mesh.leader import PartnerTarget, audit_claim


class ScopedRoutingTests(unittest.IsolatedAsyncioTestCase):
    def targets(self):
        return [PartnerTarget(name, "http://unused.test/rpc") for name in (
            "source-verifier", "evidence-grader", "contradiction-scout"
        )]

    def request(self, mode):
        return json.dumps({"schema_version": "1.0", "claim_id": "local",
                           "claim_text": "服务支持退款", "source_excerpt": "服务支持退款",
                           "task_type": mode})

    async def test_intent_does_not_call_partners_or_claim_verification(self):
        with patch("evidence_mesh.leader._call_partner", new_callable=AsyncMock) as call:
            result = await audit_claim(self.request("intent_and_claims"), self.targets())
        call.assert_not_awaited()
        self.assertEqual(result["decision"], "needs-review")
        self.assertEqual(result["task_ids"], {})
        self.assertEqual(result["routing"]["scope"], "analysis-only")

    async def test_explicit_routes_only_call_required_partners(self):
        modes = {
            "answer_grounding_check": {"source-verifier", "evidence-grader"},
            "claim_boundary_check": {"evidence-grader", "contradiction-scout"},
            "cross_text_conflict": {"source-verifier", "contradiction-scout"},
        }
        async def fake(target, *_):
            return {"task_id": target.name, "state": "completed", "product": {
                "payload": {"status": "verified" if target.name == "source-verifier" else "none-found", "level": "direct"}}}
        for mode, expected in modes.items():
            with self.subTest(mode=mode), patch("evidence_mesh.leader._call_partner", side_effect=fake) as call:
                result = await audit_claim(self.request(mode), self.targets())
                self.assertEqual({args.args[0].name for args in call.await_args_list}, expected)
                self.assertEqual(result["decision"], "needs-review")
                self.assertEqual(set(result["task_ids"]), expected)

    async def test_required_failure_is_incomplete(self):
        with patch("evidence_mesh.leader._call_partner", side_effect=RuntimeError("offline")):
            result = await audit_claim(self.request("answer_grounding_check"), self.targets())
        self.assertEqual(result["decision"], "incomplete")

    async def test_partial_conflict_not_hidden(self):
        async def fake(target, *_):
            return {"task_id": target.name, "state": "completed", "product": {
                "payload": {"status": "confirmed", "level": "direct"}}}
        with patch("evidence_mesh.leader._call_partner", side_effect=fake):
            result = await audit_claim(self.request("claim_boundary_check"), self.targets())
        self.assertEqual(result["decision"], "conflicting")

    async def test_duplicate_partner_configuration_rejected(self):
        targets = self.targets()
        with self.assertRaises(ValueError):
            await audit_claim(self.request("intent_and_claims"), targets + [targets[0]])

    async def test_malformed_required_status_cannot_be_supported(self):
        async def fake(target, *_):
            payload = {"status": "verified", "level": "direct"}
            if target.name == "contradiction-scout":
                payload = {}
            return {"task_id": target.name, "state": "completed", "product": {"payload": payload}}
        with patch("evidence_mesh.leader._call_partner", side_effect=fake):
            result = await audit_claim(self.request("full_preflight"), self.targets())
        self.assertEqual(result["decision"], "incomplete")
        self.assertIn("contradiction-scout:invalid-product-status", result["risk_flags"])
