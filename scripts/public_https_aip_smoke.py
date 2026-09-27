"""Validate the public HTTPS AIP-RPC state machine against all three Partners.

This is a deployment smoke test with identity binding disabled. It proves public
TLS transport and the SDK task lifecycle, not Registry approval or AIP mTLS.
"""

from __future__ import annotations

import asyncio
from datetime import date
import json
import os
from pathlib import Path
import uuid

import httpx
from acps_sdk.aip import TaskState, TextDataItem
from acps_sdk.aip.aip_rpc_client import AipRpcClient


ROOT = Path(__file__).resolve().parents[1]
RUN_ID = os.environ.get(
    "EVIDENCE_RUN_ID", f"{date.today().isoformat()}-public-https-aip"
).strip()
RUN_DIR = ROOT / "evidence" / "runs" / RUN_ID
PUBLIC_HOST = os.environ.get("PUBLIC_HOST", "").strip()
if not PUBLIC_HOST:
    raise SystemExit("set PUBLIC_HOST to the deployed HTTPS hostname")
BASE_URL = f"https://{PUBLIC_HOST}"

PARTNERS = {
    "source-verifier": "source-check",
    "evidence-grader": "evidence-finding",
    "contradiction-scout": "contradiction-check",
}

SAMPLE_REQUEST = {
    "schema_version": "1.0",
    "claim_id": "public-https-aip-smoke-001",
    "claim_text": "示例处理导致细胞死亡",
    "source": {
        "source_id": "demo:public-https-aip-smoke",
        "title": "无敏感数据的公网 AIP-RPC 测试",
        "locator": "synthetic smoke test",
    },
    "source_excerpt": "结果提示处理与细胞死亡相关，可能涉及氧化应激。",
}


async def call_partner(
    name: str, expected_product_type: str
) -> dict:
    endpoint = f"{BASE_URL}/{name}/rpc"
    transport = httpx.AsyncHTTPTransport(retries=2, verify=True)
    client = AipRpcClient(
        endpoint,
        "preview-leader",
        transport=transport,
        identity_binding_enabled=False,
    )
    session_id = f"session-{uuid.uuid4()}"
    task_id = f"task-{uuid.uuid4()}"
    try:
        started = await client.start_task(
            session_id,
            json.dumps(SAMPLE_REQUEST, ensure_ascii=False),
            task_id=task_id,
        )
        if started.status.state is not TaskState.AwaitingCompletion:
            raise AssertionError(f"{name} start state: {started.status.state}")
        completed = await client.complete_task(task_id, session_id)
        if completed.status.state is not TaskState.Completed:
            raise AssertionError(f"{name} complete state: {completed.status.state}")
        product_text = next(
            item.text
            for product in completed.products or []
            for item in product.dataItems
            if isinstance(item, TextDataItem)
        )
        product = json.loads(product_text)
        if product.get("product_type") != expected_product_type:
            raise AssertionError(
                f"{name} product type: {product.get('product_type')}"
            )
        return {
            "endpoint": endpoint,
            "session_id": session_id,
            "task_id": task_id,
            "start_state": started.status.state.value,
            "complete_state": completed.status.state.value,
            "product": product,
        }
    finally:
        await client.close()


async def main() -> int:
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    results = await asyncio.gather(
        *(
            call_partner(name, product_type)
            for name, product_type in PARTNERS.items()
        )
    )

    report = {
        "status": "passed",
        "scope": "public-https-aip-rpc-preview",
        "base_url": BASE_URL,
        "identity_binding_enabled": False,
        "proves": [
            "public HTTPS reaches three independent Partner RPC endpoints",
            "SDK start and complete task lifecycle succeeds for every Partner",
            "each Partner returns its declared typed product",
        ],
        "does_not_prove": [
            "Registry approval or AIC issuance",
            "Discovery lookup",
            "mTLS peer identity binding",
            "AMP telemetry",
            "competition-platform acceptance",
        ],
        "request": SAMPLE_REQUEST,
        "partners": dict(zip(PARTNERS, results, strict=True)),
    }
    output = RUN_DIR / "validation.json"
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"PASS: {output}")
    for name, result in report["partners"].items():
        print(
            f"{name}: {result['start_state']} -> {result['complete_state']} "
            f"({result['product']['product_type']})"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
