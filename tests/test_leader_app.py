import unittest
from unittest.mock import AsyncMock, patch

import httpx

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


if __name__ == "__main__":
    unittest.main()
