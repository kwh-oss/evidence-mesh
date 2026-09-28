"""Run a synthetic end-to-end AIP request through the mTLS Leader endpoint."""

from __future__ import annotations

import asyncio
import json
import os
import uuid

from acps_sdk.aip import TaskState, TextDataItem
from acps_sdk.aip.aip_rpc_client import AipRpcClient

from evidence_mesh.runtime_config import build_client_ssl_context, required_env


async def main() -> None:
    leader_aic = required_env("LEADER_AIC")
    endpoint = os.getenv(
        "LEADER_MTLS_SMOKE_URL", "https://api.linsixuan.cn:8440/rpc"
    )
    minimal_input = os.getenv("MINIMAL_INPUT", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }
    payload = {
        "schema_version": "1.0",
        "claim_text": "处理组观察到信号升高",
        "source_excerpt": "结果显示处理组信号升高，但该观察不单独证明因果关系。",
    }
    if not minimal_input:
        payload.update(
            {
                "claim_id": "mtls-smoke",
                "source": {
                    "source_id": "synthetic:mtls-smoke",
                    "title": "Synthetic mTLS smoke fixture",
                    "locator": "fixture paragraph 1",
                },
            }
        )
    session_id = f"session-{uuid.uuid4()}"
    task_id = f"task-{uuid.uuid4()}"
    client = AipRpcClient(
        endpoint,
        leader_aic,
        ssl_context=build_client_ssl_context(),
        expected_partner_aic=leader_aic,
        identity_binding_enabled=True,
    )
    try:
        started = await client.start_task(
            session_id,
            json.dumps(payload, ensure_ascii=False),
            task_id=task_id,
        )
        if started.status.state != TaskState.AwaitingCompletion:
            raise RuntimeError(f"unexpected start state: {started.status.state}")
        completed = await client.complete_task(task_id, session_id)
        if completed.status.state != TaskState.Completed:
            raise RuntimeError(f"unexpected completion state: {completed.status.state}")
        product_text = next(
            item.text
            for product in completed.products or []
            for item in product.dataItems
            if isinstance(item, TextDataItem)
        )
        product = json.loads(product_text)
        if product.get("product_type") != "evidence-passport":
            raise RuntimeError("Leader did not return an Evidence Passport")
        task_ids = product.get("task_ids")
        partner_products = product.get("partner_products")
        if not isinstance(task_ids, dict) or len(task_ids) != 3:
            raise RuntimeError("Evidence Passport does not contain three Partner tasks")
        if not isinstance(partner_products, dict) or len(partner_products) != 3:
            raise RuntimeError("Evidence Passport does not contain three Partner products")
        if minimal_input:
            if product.get("claim_id") != task_id:
                raise RuntimeError("minimal input did not inherit the AIP task ID")
            source_product = partner_products.get("source-verifier", {})
            source_payload = source_product.get("payload", {})
            issues = source_payload.get("issues", [])
            if source_payload.get("status") != "incomplete":
                raise RuntimeError("missing source metadata was not marked incomplete")
            if not any("source" in str(issue).lower() for issue in issues):
                raise RuntimeError("missing source metadata was not recorded as an issue")
        print(
            json.dumps(
                {
                    "status": "AIP_MTLS_SMOKE_OK",
                    "leader_state": completed.status.state.value,
                    "product_type": product.get("product_type"),
                    "decision": product.get("decision"),
                    "partner_task_count": len(task_ids),
                    "partner_product_count": len(partner_products),
                    "input_mode": "minimal" if minimal_input else "complete",
                    "claim_id": product.get("claim_id"),
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
