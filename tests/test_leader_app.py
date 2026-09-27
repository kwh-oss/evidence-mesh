import json
import unittest
from unittest.mock import AsyncMock, patch
import uuid

import httpx
from acps_sdk.aip import TaskState, TextDataItem
from acps_sdk.aip.aip_rpc_client import AipRpcClient

from evidence_mesh.leader_app import app


class LeaderAppTests(unittest.IsolatedAsyncioTestCase):
    async def test_homepage_and_static_assets_are_served(self) -> None:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://leader.test"
        ) as client:
            homepage = await client.get("/")
            stylesheet = await client.get("/static/styles.css")
            script = await client.get("/static/app.js")
        self.assertEqual(homepage.status_code, 200)
        self.assertIn("证链联研", homepage.text)
        self.assertIn("Evidence Passport", homepage.text)
        self.assertEqual(stylesheet.status_code, 200)
        self.assertIn("--green", stylesheet.text)
        self.assertEqual(script.status_code, 200)
        self.assertIn('fetch("/audit"', script.text)

    async def test_invalid_schema_returns_422(self) -> None:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://leader.test"
        ) as client:
            response = await client.post("/audit", json={"schema_version": "9.9"})
        self.assertEqual(response.status_code, 422)

    @patch("evidence_mesh.leader_app.audit_claim", new_callable=AsyncMock)
    async def test_valid_request_reaches_orchestrator(self, mocked_audit) -> None:
        mocked_audit.return_value = {
            "schema_version": "1.0",
            "product_type": "evidence-passport",
            "claim_id": "claim-http",
            "decision": "supported",
        }
        payload = {
            "schema_version": "1.0",
            "claim_id": "claim-http",
            "claim_text": "材料提高抗菌率",
            "source": {
                "source_id": "doi:example",
                "title": "Example study",
                "locator": "Results, paragraph 2",
            },
            "source_excerpt": "结果显示材料提高抗菌率，并在重复实验中趋势一致。",
        }
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://leader.test"
        ) as client:
            response = await client.post("/audit", json=payload)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["decision"], "supported")
        mocked_audit.assert_awaited_once()

    @patch("evidence_mesh.leader_app.audit_claim", new_callable=AsyncMock)
    async def test_leader_exposes_real_aip_jsonrpc(self, mocked_audit) -> None:
        mocked_audit.return_value = {
            "schema_version": "1.0",
            "product_type": "evidence-passport",
            "claim_id": "claim-aip-leader",
            "decision": "needs-review",
        }
        payload = {
            "schema_version": "1.0",
            "claim_id": "claim-aip-leader",
            "claim_text": "处理导致细胞死亡",
            "source": {
                "source_id": "demo:leader-aip",
                "title": "Synthetic AIP test",
                "locator": "test fixture",
            },
            "source_excerpt": "结果提示处理与细胞死亡相关。",
        }
        client = AipRpcClient(
            "http://leader.test/rpc",
            "test-upstream-leader",
            transport=httpx.ASGITransport(app=app),
            identity_binding_enabled=False,
        )
        session_id = f"session-{uuid.uuid4()}"
        task_id = f"task-{uuid.uuid4()}"
        try:
            started = await client.start_task(
                session_id,
                json.dumps(payload, ensure_ascii=False),
                task_id=task_id,
            )
            self.assertEqual(started.status.state, TaskState.AwaitingCompletion)
            completed = await client.complete_task(task_id, session_id)
            self.assertEqual(completed.status.state, TaskState.Completed)
            product_text = next(
                item.text
                for product in completed.products or []
                for item in product.dataItems
                if isinstance(item, TextDataItem)
            )
            product = json.loads(product_text)
            self.assertEqual(product["product_type"], "evidence-passport")
            self.assertEqual(product["claim_id"], "claim-aip-leader")
        finally:
            await client.close()


if __name__ == "__main__":
    unittest.main()
