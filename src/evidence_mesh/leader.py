"""AIP Leader orchestration for the three evidence Partners."""

import asyncio
from dataclasses import dataclass
import json
import ssl
import uuid
from typing import Any

import httpx

from acps_sdk.aip import TaskState, TextDataItem
from acps_sdk.aip.aip_rpc_client import AipRpcClient


@dataclass(frozen=True, slots=True)
class PartnerTarget:
    name: str
    url: str
    transport: httpx.AsyncBaseTransport | None = None
    leader_aic: str = "evidence-audit-leader"
    expected_partner_aic: str | None = None
    identity_binding_enabled: bool = False
    ssl_context: ssl.SSLContext | None = None


async def audit_claim(request_json: str, targets: list[PartnerTarget]) -> dict[str, Any]:
    """Delegate one claim in parallel and return a fail-closed Evidence Passport."""
    expected = {"source-verifier", "evidence-grader", "contradiction-scout"}
    names = {target.name for target in targets}
    if names != expected:
        raise ValueError(f"targets must be exactly {sorted(expected)}; got {sorted(names)}")

    results = await asyncio.gather(
        *(_call_partner(target, request_json) for target in targets),
        return_exceptions=True,
    )

    products: dict[str, dict[str, Any]] = {}
    task_ids: dict[str, str] = {}
    risks: list[str] = []

    for target, result in zip(targets, results, strict=True):
        if isinstance(result, Exception):
            risks.append(f"{target.name}:call-failed:{type(result).__name__}")
            continue
        task_ids[target.name] = result["task_id"]
        if result["state"] != TaskState.Completed.value:
            risks.append(f"{target.name}:state-{result['state']}")
            continue
        products[target.name] = result["product"]

    decision = _decide(products, risks)
    claim_id = _request_claim_id(request_json)
    return {
        "schema_version": "1.0",
        "product_type": "evidence-passport",
        "claim_id": claim_id,
        "decision": decision,
        "risk_flags": sorted(risks),
        "task_ids": task_ids,
        "partner_products": products,
    }


async def _call_partner(target: PartnerTarget, request_json: str) -> dict[str, Any]:
    session_id = f"session-{uuid.uuid4()}"
    task_id = f"task-{uuid.uuid4()}"
    client = AipRpcClient(
        target.url,
        target.leader_aic,
        transport=target.transport,
        ssl_context=target.ssl_context,
        expected_partner_aic=target.expected_partner_aic,
        identity_binding_enabled=target.identity_binding_enabled,
    )
    try:
        started = await client.start_task(session_id, request_json, task_id=task_id)
        if started.status.state == TaskState.Failed:
            return {
                "task_id": task_id,
                "state": TaskState.Failed.value,
                "product": {},
            }
        if started.status.state != TaskState.AwaitingCompletion:
            return {
                "task_id": task_id,
                "state": started.status.state.value,
                "product": {},
            }
        completed = await client.complete_task(task_id, session_id)
        product_text = next(
            item.text
            for product in completed.products or []
            for item in product.dataItems
            if isinstance(item, TextDataItem)
        )
        return {
            "task_id": task_id,
            "state": completed.status.state.value,
            "product": json.loads(product_text),
        }
    finally:
        await client.close()


def _decide(products: dict[str, dict[str, Any]], risks: list[str]) -> str:
    if risks or len(products) != 3:
        return "incomplete"

    source_status = products["source-verifier"]["payload"]["status"]
    evidence_level = products["evidence-grader"]["payload"]["level"]
    contradiction = products["contradiction-scout"]["payload"]["status"]

    if contradiction == "confirmed":
        risks.append("claim:confirmed-contradiction")
        return "conflicting"
    if contradiction == "possible":
        risks.append("claim:possible-contradiction")
        return "needs-review"
    if source_status != "verified":
        risks.append("claim:source-not-verified")
        return "needs-review"
    if evidence_level == "direct":
        return "supported"
    if evidence_level == "unsupported":
        risks.append("claim:unsupported")
        return "no-evidence"

    risks.append(f"claim:evidence-{evidence_level}")
    return "needs-review"


def _request_claim_id(request_json: str) -> str:
    try:
        value = json.loads(request_json)
        return str(value.get("claim_id", "")) if isinstance(value, dict) else ""
    except json.JSONDecodeError:
        return ""
