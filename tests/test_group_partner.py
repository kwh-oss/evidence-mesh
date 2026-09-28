import json
import unittest

from acps_sdk.aip import TaskCommand, TaskCommandType, TextDataItem

from evidence_mesh.contracts import SCHEMA_VERSION
from evidence_mesh.group_partner import process_group_command
from evidence_mesh.processors import verify_source


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
        product_text = client.products[0].dataItems[0].text
        product = json.loads(product_text)
        self.assertEqual(product["product_type"], "source-check")
        self.assertEqual(product["payload"]["claim_id"], "claim-group")

    async def test_invalid_group_payload_fails_closed(self) -> None:
        client = FakeGroupClient()
        await process_group_command(
            client=client,
            command=command("not-json"),
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
