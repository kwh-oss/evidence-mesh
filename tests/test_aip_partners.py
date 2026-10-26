import json
import unittest
import uuid

import httpx

from acps_sdk.aip import TaskState, TextDataItem
from acps_sdk.aip.aip_rpc_client import AipRpcClient

from evidence_mesh.product_presentation import read_product
from evidence_mesh.contracts import SCHEMA_VERSION
from evidence_mesh.aip_partner import build_partner_app
from evidence_mesh.processors import verify_source
from evidence_mesh.retrieval_archive import AIP_TASK_ID, AIP_TASK_TRANSPORT
from evidence_mesh.contradiction_partner import app as contradiction_app
from evidence_mesh.grader_partner import app as grader_app
from evidence_mesh.source_partner import app as source_app
from acps_sdk.aip.aip_peer_cert import AipPeerCertificateMiddleware


def valid_request() -> str:
    return json.dumps(
        {
            "schema_version": SCHEMA_VERSION,
            "claim_id": "claim-aip",
            "claim_text": "处理导致细胞死亡",
            "source": {
                "source_id": "doi:example",
                "title": "Example controlled study",
                "locator": "Results, paragraph 2",
            },
            "source_excerpt": "结果提示处理与细胞死亡相关，可能涉及氧化应激。",
        },
        ensure_ascii=False,
    )


class AipPartnerTests(unittest.IsolatedAsyncioTestCase):
    async def test_rpc_builder_failures_do_not_expose_exception_content(self):
        marker = 'sensitive-test-marker /private/token.txt'
        for error_type, category in [(ValueError, 'invalid-request'),
                                     (RuntimeError, 'processing-error')]:
            with self.subTest(error_type=error_type):
                async def builder(request):
                    raise error_type(marker)
                app = build_partner_app(service_name='source-verifier',
                    product_type='source-check', processor=verify_source,
                    product_builder=builder)
                client = AipRpcClient('http://partner.test/rpc', 'test-leader',
                    transport=httpx.ASGITransport(app=app), identity_binding_enabled=False)
                try:
                    result = await client.start_task(f'session-{uuid.uuid4()}',
                        valid_request(), task_id=f'task-{uuid.uuid4()}')
                    self.assertEqual(result.status.state, TaskState.Failed)
                    reply = result.model_dump_json()
                    self.assertIn(category, reply)
                    self.assertNotIn(marker, reply)
                    self.assertFalse(result.products)
                    self.assertIsNone(AIP_TASK_ID.get())
                    self.assertIsNone(AIP_TASK_TRANSPORT.get())
                finally:
                    await client.close()

    def test_partner_apps_install_peer_certificate_middleware(self) -> None:
        for app in (source_app, grader_app, contradiction_app):
            self.assertTrue(
                any(
                    middleware.cls is AipPeerCertificateMiddleware
                    for middleware in app.user_middleware
                )
            )

    async def call_partner(self, app, expected_product_type: str) -> dict:
        transport = httpx.ASGITransport(app=app)
        client = AipRpcClient(
            "http://partner.test/rpc",
            "test-leader",
            transport=transport,
            identity_binding_enabled=False,
        )
        session_id = f"session-{uuid.uuid4()}"
        task_id = f"task-{uuid.uuid4()}"
        try:
            started = await client.start_task(
                session_id, valid_request(), task_id=task_id
            )
            self.assertEqual(started.status.state, TaskState.AwaitingCompletion)
            completed = await client.complete_task(task_id, session_id)
            self.assertEqual(completed.status.state, TaskState.Completed)
            product = read_product(completed.products)
            self.assertEqual(completed.products[0].dataItems[0].text, product['answer'])
            self.assertFalse(completed.products[0].dataItems[0].text.startswith('{'))
            self.assertEqual(product["schema_version"], SCHEMA_VERSION)
            self.assertEqual(product["product_type"], expected_product_type)
            self.assertEqual(product["payload"]["claim_id"], "claim-aip")
            return product
        finally:
            await client.close()

    async def test_source_partner_over_aip(self) -> None:
        product = await self.call_partner(source_app, "source-check")
        self.assertEqual(product["payload"]["status"], "verified")

    async def test_grader_partner_over_aip(self) -> None:
        product = await self.call_partner(grader_app, "evidence-finding")
        self.assertEqual(product["payload"]["level"], "conditional")

    async def test_contradiction_partner_over_aip(self) -> None:
        product = await self.call_partner(
            contradiction_app, "contradiction-check"
        )
        self.assertEqual(product["payload"]["status"], "none-found")

    async def test_invalid_json_returns_failed_state(self) -> None:
        transport = httpx.ASGITransport(app=grader_app)
        client = AipRpcClient(
            "http://partner.test/rpc",
            "test-leader",
            transport=transport,
            identity_binding_enabled=False,
        )
        try:
            result = await client.start_task(
                f"session-{uuid.uuid4()}",
                '{"claim":',
                task_id=f"task-{uuid.uuid4()}",
            )
            self.assertEqual(result.status.state, TaskState.Failed)
            self.assertIn("invalid-request", result.status.dataItems[0].text)
        finally:
            await client.close()


if __name__ == "__main__":
    unittest.main()
