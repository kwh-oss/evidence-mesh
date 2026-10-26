from evidence_mesh.product_presentation import read_product
import asyncio
import json
import unittest
from pathlib import Path
import tempfile

from acps_sdk.aip import TaskCommand, TaskCommandType, TextDataItem

from evidence_mesh.contracts import SCHEMA_VERSION
from evidence_mesh.group_partner import process_group_command
from evidence_mesh.processors import verify_source
from evidence_mesh.retrieval_archive import AIP_TASK_ID, AIP_TASK_TRANSPORT, RetrievalArchive


def valid_request() -> str:
    return json.dumps(
        {
            "schema_version": SCHEMA_VERSION,
            "claim_id": "claim-group",
            "claim_text": "处理导致细胞死亡",
            "source": {
                "source_id": "doi:group-example",
                "title": "Example controlled study",
                "locator": "Results, paragraph 2",
            },
            "source_excerpt": "结果提示处理与细胞死亡相关。",
        },
        ensure_ascii=False,
    )


class FakeGroupClient:
    def __init__(self) -> None:
        self.events = []
        self.products = []

    async def accept_task(self, task_id, session_id):
        self.events.append(("accept", task_id, session_id))

    async def start_working(self, task_id, session_id):
        self.events.append(("working", task_id, session_id))

    async def submit_for_completion(self, task_id, session_id, products):
        self.events.append(("ready", task_id, session_id))
        self.products.extend(products)

    async def fail_task(self, task_id, session_id, error):
        self.events.append(("failed", task_id, session_id, error))


def command(text: str) -> TaskCommand:
    return TaskCommand(
        id="message-1",
        sentAt="2026-09-28T00:00:00Z",
        senderRole="leader",
        senderId="1.2.156.test.leader",
        mentions=["1.2.156.test.partner"],
        dataItems=[TextDataItem(text=text)],
        groupId="evidence-mesh-smoke",
        sessionId="session-1",
        command=TaskCommandType.Start,
        taskId="task-1",
    )


class GroupPartnerTests(unittest.IsolatedAsyncioTestCase):
    async def test_builder_errors_never_echo_sensitive_exception_text(self):
        marker = 'sensitive-test-marker /private/token.txt'
        for error_type, category in [(ValueError, 'invalid-request'),
                                     (RuntimeError, 'processing-error')]:
            with self.subTest(error_type=error_type):
                client = FakeGroupClient()
                async def builder(request):
                    raise error_type(marker)
                await process_group_command(client=client,
                    command=command(valid_request()), is_mentioned=True,
                    service_name='source-verifier', product_type='source-check',
                    processor=verify_source, product_builder=builder)
                self.assertEqual(client.events[-1][0], 'failed')
                self.assertIn(category, client.events[-1][3])
                self.assertNotIn(marker, client.events[-1][3])
                self.assertFalse(client.products)
                self.assertIsNone(AIP_TASK_ID.get())
                self.assertIsNone(AIP_TASK_TRANSPORT.get())

    async def test_concurrent_group_archives_keep_distinct_task_bindings(self):
        """Overlapping retrievals must not borrow another command's identity."""
        arrived = asyncio.Event()
        count = 0
        with tempfile.TemporaryDirectory() as folder:
            async def builder(request):
                nonlocal count
                count += 1
                if count == 2:
                    arrived.set()
                await asyncio.wait_for(arrived.wait(), timeout=2)
                await asyncio.sleep(0)
                archive = RetrievalArchive(Path(folder).resolve(), AIP_TASK_ID.get())
                record = archive.finish({'payload': {'claim_id': request.claim_id}})
                return json.dumps({'answer': 'Offline archive fixture', 'archive': record})

            clients = [FakeGroupClient(), FakeGroupClient()]
            commands = []
            for index in range(2):
                payload = json.loads(valid_request())
                payload['claim_id'] = f'claim-{index}'
                item = command(json.dumps(payload))
                item.taskId = f'task-{index}'
                commands.append(item)
            await asyncio.gather(*[
                process_group_command(client=client, command=item,
                    is_mentioned=True, service_name='source-verifier',
                    product_type='source-check', processor=verify_source,
                    product_builder=builder)
                for client, item in zip(clients, commands)
            ])
            manifests = [json.loads(p.read_text())
                         for p in Path(folder).glob('*/manifest.json')]
            self.assertEqual(len(manifests), 2)
            self.assertEqual({(m['partner_task_id'], m['claim_id']) for m in manifests},
                             {('task-0', 'claim-0'), ('task-1', 'claim-1')})
            self.assertTrue(all(m['task_transport'] == 'aip-group' for m in manifests))
            self.assertTrue(all(client.events[-1][0] == 'ready' for client in clients))
        self.assertIsNone(AIP_TASK_ID.get())
        self.assertIsNone(AIP_TASK_TRANSPORT.get())

    async def test_group_archive_id_is_command_id_not_claim_id(self):
        client = FakeGroupClient()
        with tempfile.TemporaryDirectory() as folder:
            async def builder(request):
                archive = RetrievalArchive(Path(folder).resolve(), AIP_TASK_ID.get())
                record = archive.finish({'payload': {'claim_id': request.claim_id}})
                return json.dumps({'answer': 'offline', 'archive': record})
            await process_group_command(client=client, command=command(valid_request()),
                is_mentioned=True, service_name='source-verifier', product_type='source-check',
                processor=verify_source, product_builder=builder)
            manifest = json.loads(next(Path(folder).glob('*/manifest.json')).read_text())
            self.assertEqual(manifest['partner_task_id'], 'task-1')
            self.assertEqual(manifest['claim_id'], 'claim-group')
            self.assertEqual(manifest['task_transport'], 'aip-group')
            self.assertFalse(manifest['semantic_acceptance'])
        self.assertEqual(client.events[-1][0], 'ready')
        self.assertIsNone(AIP_TASK_ID.get())
        self.assertIsNone(AIP_TASK_TRANSPORT.get())

    async def test_group_task_context_cleared_on_builder_error(self):
        client = FakeGroupClient()
        async def builder(request):
            self.assertEqual(AIP_TASK_ID.get(), 'task-1')
            self.assertEqual(AIP_TASK_TRANSPORT.get(), 'aip-group')
            raise RuntimeError('offline simulated failure')
        await process_group_command(client=client, command=command(valid_request()),
            is_mentioned=True, service_name='source-verifier', product_type='source-check',
            processor=verify_source, product_builder=builder)
        self.assertEqual(client.events[-1][0], 'failed')
        self.assertIsNone(AIP_TASK_ID.get())
        self.assertIsNone(AIP_TASK_TRANSPORT.get())

    async def test_compact_group_input_reports_material_gap(self) -> None:
        client = FakeGroupClient()
        await process_group_command(
            client=client, command=command('{"answer":"服务支持退款"}'),
            is_mentioned=True, service_name="source-verifier", product_type="source-check",
            processor=verify_source,
        )
        self.assertEqual(client.events[-1][0], "ready")
        product = read_product(client.products)
        self.assertEqual(product["payload"]["claim_id"], "task-1")
        self.assertEqual(product["payload"]["status"], "incomplete")
        self.assertFalse(product["input_assessment"]["evidence_provided"])

    async def test_group_start_runs_existing_processor(self) -> None:
        client = FakeGroupClient()
        await process_group_command(
            client=client,
            command=command(valid_request()),
            is_mentioned=True,
            service_name="source-verifier",
            product_type="source-check",
            processor=verify_source,
        )

        self.assertEqual(
            [event[0] for event in client.events], ["accept", "working", "ready"]
        )
        product = read_product(client.products)
        self.assertEqual(product["product_type"], "source-check")
        self.assertEqual(product["payload"]["claim_id"], "claim-group")

    async def test_invalid_group_payload_fails_closed(self) -> None:
        client = FakeGroupClient()
        await process_group_command(
            client=client,
            command=command('{"claim":'),
            is_mentioned=True,
            service_name="source-verifier",
            product_type="source-check",
            processor=verify_source,
        )

        self.assertEqual(client.events[-1][0], "failed")
        self.assertIn("invalid-request", client.events[-1][3])

    async def test_unmentioned_group_task_is_ignored(self) -> None:
        client = FakeGroupClient()
        await process_group_command(
            client=client,
            command=command(valid_request()),
            is_mentioned=False,
            service_name="source-verifier",
            product_type="source-check",
            processor=verify_source,
        )

        self.assertEqual(client.events, [])


if __name__ == "__main__":
    unittest.main()
