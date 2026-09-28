"""Run one real Group task across the three registered evidence Partners."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import ssl
import time
import uuid

from acps_sdk.aip import ACSObject, GroupLeader, TaskState, TextDataItem


def required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ValueError(f"{name} is required")
    return value


def required_file(name: str) -> Path:
    path = Path(required(name)).expanduser()
    if not path.is_file():
        raise ValueError(f"{name} does not point to a file: {path}")
    return path


def tls_context() -> tuple[ssl.SSLContext, tuple[str, str]]:
    ca_file = required_file("GROUP_CA_FILE")
    cert_file = required_file("GROUP_CLIENT_CERT_FILE")
    key_file = required_file("GROUP_CLIENT_KEY_FILE")
    context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH, cafile=str(ca_file))
    context.minimum_version = ssl.TLSVersion.TLSv1_3
    context.load_cert_chain(str(cert_file), str(key_file))
    return context, (str(cert_file), str(key_file))


async def wait_for(predicate, event: asyncio.Event, timeout: float) -> None:
    deadline = time.monotonic() + timeout
    while not predicate():
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("Group state did not converge before timeout")
        try:
            await asyncio.wait_for(event.wait(), timeout=remaining)
        finally:
            event.clear()


async def main() -> None:
    leader_aic = required("LEADER_AIC")
    public_host = required("PUBLIC_HOST")
    partners = {
        "source-verifier": (
            required("SOURCE_VERIFIER_AIC"),
            f"https://{public_host}:8441/group/rpc",
        ),
        "evidence-grader": (
            required("EVIDENCE_GRADER_AIC"),
            f"https://{public_host}:8442/group/rpc",
        ),
        "contradiction-scout": (
            required("CONTRADICTION_SCOUT_AIC"),
            f"https://{public_host}:8443/group/rpc",
        ),
    }
    context, client_cert = tls_context()
    leader = GroupLeader(
        leader_aic=leader_aic,
        rabbitmq_config={
            "host": os.getenv("GROUP_RABBITMQ_HOST", "wt.ioa.pub"),
            "port": int(os.getenv("GROUP_RABBITMQ_PORT", "5671")),
            "vhost": os.getenv("GROUP_RABBITMQ_VHOST", "acps"),
            "user": None,
            "password": None,
            "auth_service_url": os.getenv(
                "GROUP_AUTH_SERVICE_URL", "https://wt.ioa.pub:9007"
            ),
        },
        ssl_context=context,
        ssl_cert=client_cert,
        identity_binding_enabled=True,
    )
    session_id = f"evidence-mesh-{uuid.uuid4().hex[:12]}"
    task_payload = {
        "schema_version": "1.0",
        "claim_id": "group-platform-smoke",
        "claim_text": "处理组观察到信号升高",
        "source": {
            "source_id": "synthetic:group-platform-smoke",
            "title": "Synthetic Group smoke fixture",
            "locator": "fixture paragraph 1",
        },
        "source_excerpt": "结果显示处理组信号升高，但该观察不单独证明因果关系。",
    }

    try:
        session = await leader.create_group_session(session_id, initial_partners=[])
        for partner_aic, rpc_url in partners.values():
            joined = await leader.invite_partner(
                session_id=session_id,
                partner_acs=ACSObject(aic=partner_aic),
                partner_rpc_url=rpc_url,
            )
            if not joined:
                raise RuntimeError(f"Partner did not join: {partner_aic}")

        runtime = leader.get_group_runtime(session_id)
        if runtime["connected_members"] != 3:
            raise RuntimeError(f"Expected three connected Partners: {runtime}")

        task_id = await leader.start_task(
            session_id=session_id,
            task_content=json.dumps(task_payload, ensure_ascii=False),
            target_partners=[aic for aic, _ in partners.values()],
        )
        await wait_for(
            lambda: len(session.get_task_summary(task_id)["products"]) == 3,
            session.state_update_event,
            60,
        )
        await leader.complete_task(session_id, task_id)
        await wait_for(
            lambda: session.get_task_summary(task_id)["completed_count"] == 3,
            session.state_update_event,
            30,
        )

        summary = session.get_task_summary(task_id)
        product_types = {}
        for partner_aic, products in summary["products"].items():
            product_text = next(
                item.text
                for product in products
                for item in product.dataItems
                if isinstance(item, TextDataItem)
            )
            product_types[partner_aic] = json.loads(product_text)["product_type"]
        if set(product_types.values()) != {
            "source-check",
            "evidence-finding",
            "contradiction-check",
        }:
            raise RuntimeError(f"Unexpected Group products: {product_types}")

        print(
            json.dumps(
                {
                    "status": "GROUP_PLATFORM_SMOKE_OK",
                    "group_id": session.group_id,
                    "task_id": task_id,
                    "connected_members": runtime["connected_members"],
                    "completed_members": summary["completed_count"],
                    "product_types": product_types,
                    "identity_binding": "enabled",
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
    finally:
        await leader.close()


if __name__ == "__main__":
    asyncio.run(main())
