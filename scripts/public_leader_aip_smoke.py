"""Validate the public Leader AIP JSON-RPC endpoint end to end.

The synthetic request contains no sensitive data. Identity binding remains
disabled until Registry approval and platform certificate issuance.
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import uuid

import httpx
from acps_sdk.aip import TaskState, TextDataItem
from acps_sdk.aip.aip_rpc_client import AipRpcClient


ROOT = Path(__file__).resolve().parents[1]
PUBLIC_HOST = os.environ.get("PUBLIC_HOST", "").strip()
if not PUBLIC_HOST:
    raise SystemExit("set PUBLIC_HOST to the deployed HTTPS hostname")

REQUEST = {
    "schema_version": "1.0",
    "claim_id": "public-leader-aip-smoke-001",
    "claim_text": "示例处理导致细胞死亡",
    "source": {
        "source_id": "demo:public-leader-aip-smoke",
        "title": "无敏感数据的总控 AIP 测试",
        "locator": "synthetic smoke test",
    },
    "source_excerpt": "结果提示处理与细胞死亡相关，可能涉及氧化应激。",
}


async def main() -> int:
    endpoint = f"https://{PUBLIC_HOST}/rpc"
    client = AipRpcClient(
        endpoint,
        "preview-upstream-leader",
        transport=httpx.AsyncHTTPTransport(retries=2, verify=True),
        identity_binding_enabled=False,
    )
    session_id = f"session-{uuid.uuid4()}"
    task_id = f"task-{uuid.uuid4()}"
    try:
        started = await client.start_task(
            session_id,
            json.dumps(REQUEST, ensure_ascii=False),
            task_id=task_id,
        )
        if started.status.state is not TaskState.AwaitingCompletion:
            raise AssertionError(f"Leader start state: {started.status.state}")
        completed = await client.complete_task(task_id, session_id)
        if completed.status.state is not TaskState.Completed:
            raise AssertionError(f"Leader complete state: {completed.status.state}")
        product_text = next(
            item.text
            for product in completed.products or []
            for item in product.dataItems
            if isinstance(item, TextDataItem)
        )
        product = json.loads(product_text)
        if product.get("product_type") != "evidence-passport":
            raise AssertionError(f"Leader product type: {product.get('product_type')}")
        if set(product.get("partner_products", {})) != {
            "source-verifier",
            "evidence-grader",
            "contradiction-scout",
        }:
            raise AssertionError("Leader did not aggregate all three Partner products")
    finally:
        await client.close()

    report = {
        "status": "passed",
        "scope": "public-leader-aip-jsonrpc-preview",
        "endpoint": endpoint,
        "identity_binding_enabled": False,
        "session_id": session_id,
        "task_id": task_id,
        "start_state": started.status.state.value,
        "complete_state": completed.status.state.value,
        "product": product,
        "does_not_prove": [
            "Registry approval or AIC issuance",
            "mTLS peer identity binding",
            "Discovery lookup",
            "competition-platform acceptance",
        ],
    }
    run_dir = ROOT / "evidence" / "private" / "runs" / "2026-09-27-leader-jsonrpc"
    run_dir.mkdir(parents=True, exist_ok=True)
    output = run_dir / "validation.json"
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"PASS: {output}")
    print(
        f"leader: {report['start_state']} -> {report['complete_state']} "
        f"({product['product_type']}, {product['decision']})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
