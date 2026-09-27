"""Minimal local AIP Leader client using acps-sdk 2.2.0."""

import asyncio
import json
import uuid

from acps_sdk.aip import TextDataItem
from acps_sdk.aip.aip_rpc_client import AipRpcClient


PARTNER_URL = "http://127.0.0.1:8011/rpc"
LEADER_ID = "competition-local-leader"


async def run_demo(user_input: str = "梧桐平台本地协议联调") -> dict:
    session_id = f"session-{uuid.uuid4()}"
    task_id = f"task-{uuid.uuid4()}"
    client = AipRpcClient(
        PARTNER_URL,
        LEADER_ID,
        identity_binding_enabled=False,
    )

    try:
        started = await client.start_task(session_id, user_input, task_id=task_id)
        completed = await client.complete_task(task_id, session_id)
    finally:
        await client.close()

    product_texts = [
        item.text
        for product in completed.products or []
        for item in product.dataItems
        if isinstance(item, TextDataItem)
    ]
    return {
        "taskId": completed.taskId,
        "startState": started.status.state.value,
        "finalState": completed.status.state.value,
        "products": product_texts,
    }


if __name__ == "__main__":
    print(json.dumps(asyncio.run(run_demo()), ensure_ascii=False, indent=2))
