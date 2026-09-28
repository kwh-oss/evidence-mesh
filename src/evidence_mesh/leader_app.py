"""User-facing HTTP entry point for the Evidence Mesh MVP."""

import json
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from acps_sdk.aip import Product, TaskResult, TaskState, TextDataItem
from acps_sdk.aip.aip_peer_cert import AipPeerCertificateMiddleware
from acps_sdk.aip.aip_rpc_server import (
    CommandHandlers,
    DefaultHandlers,
    TaskManager,
    add_aip_rpc_router,
)

from .amp_observability import install_amp_observability
from .contracts import request_from_json
from .leader import PartnerTarget, audit_claim
from .runtime_config import build_client_ssl_context, leader_identity, required_env


app = FastAPI(title="Evidence Mesh Leader", version="0.1.0")
app.add_middleware(AipPeerCertificateMiddleware)
STATIC_DIR = Path(__file__).with_name("static")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def configured_targets() -> list[PartnerTarget]:
    leader_aic, identity_binding_enabled = leader_identity()
    ssl_context = build_client_ssl_context() if identity_binding_enabled else None

    def target(name: str, url_env: str, default_url: str, aic_env: str) -> PartnerTarget:
        return PartnerTarget(
            name=name,
            url=os.getenv(url_env, default_url),
            leader_aic=leader_aic,
            expected_partner_aic=(
                required_env(aic_env) if identity_binding_enabled else None
            ),
            identity_binding_enabled=identity_binding_enabled,
            ssl_context=ssl_context,
        )

    return [
        target(
            "source-verifier",
            "SOURCE_VERIFIER_URL",
            "http://127.0.0.1:8021/rpc",
            "SOURCE_VERIFIER_AIC",
        ),
        target(
            "evidence-grader",
            "EVIDENCE_GRADER_URL",
            "http://127.0.0.1:8022/rpc",
            "EVIDENCE_GRADER_AIC",
        ),
        target(
            "contradiction-scout",
            "CONTRADICTION_SCOUT_URL",
            "http://127.0.0.1:8023/rpc",
            "CONTRADICTION_SCOUT_AIC",
        ),
    ]


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "evidence-audit-leader"}


@app.get("/", include_in_schema=False)
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.post("/audit")
async def audit(payload: dict) -> dict:
    request_text = json.dumps(payload, ensure_ascii=False)
    try:
        request_from_json(request_text)
    except (ValueError, json.JSONDecodeError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    return await audit_claim(request_text, configured_targets())


async def aip_on_start(command, task: TaskResult | None) -> TaskResult:
    """Expose the Leader through the same AIP JSON-RPC lifecycle as Partners."""

    current = await DefaultHandlers.start(command, task)
    if task is not None:
        return current

    local_aic, _ = leader_identity()
    current.senderId = local_aic
    try:
        request_text = next(
            item.text
            for item in command.dataItems or []
            if isinstance(item, TextDataItem) and item.text.strip()
        )
        request_from_json(request_text)
        passport = await audit_claim(request_text, configured_targets())
    except (StopIteration, ValueError, json.JSONDecodeError) as error:
        if _amp is not None:
            await _amp.emit_task_result(
                actor_aic=getattr(command, "senderId", None),
                task_id=current.taskId,
                session_id=getattr(command, "sessionId", None),
                success=False,
                reason="invalid-request",
            )
        return TaskManager.update_task_status(
            current.taskId,
            TaskState.Failed,
            [TextDataItem(text=f"invalid-request: {error}")],
        )
    except Exception:
        if _amp is not None:
            await _amp.emit_task_result(
                actor_aic=getattr(command, "senderId", None),
                task_id=current.taskId,
                session_id=getattr(command, "sessionId", None),
                success=False,
                reason="orchestration-error",
            )
        raise

    TaskManager.set_products(
        current.taskId,
        [
            Product(
                id=f"evidence-audit-leader-{current.taskId}",
                name="evidence-passport",
                description="Aggregated Evidence Passport from the Leader",
                dataItems=[
                    TextDataItem(
                        text=json.dumps(passport, ensure_ascii=False, sort_keys=True)
                    )
                ],
            )
        ],
    )
    if _amp is not None:
        await _amp.emit_task_result(
            actor_aic=getattr(command, "senderId", None),
            task_id=current.taskId,
            session_id=getattr(command, "sessionId", None),
            success=True,
            reason="evidence-passport-ready",
        )
    return TaskManager.update_task_status(
        current.taskId,
        TaskState.AwaitingCompletion,
        [TextDataItem(text="Evidence Passport ready for caller confirmation.")],
    )


_leader_aic, _leader_identity_binding_enabled = leader_identity()
_amp = install_amp_observability(
    app, aic=_leader_aic, agent_name="evidence-audit-leader"
)
_aip_handlers = CommandHandlers(
    on_start=aip_on_start,
    on_get=DefaultHandlers.get,
    on_cancel=DefaultHandlers.cancel,
    on_complete=DefaultHandlers.complete,
    on_continue=DefaultHandlers.continue_,
)
add_aip_rpc_router(
    app,
    "/rpc",
    _aip_handlers,
    local_aic=_leader_aic,
    identity_binding_enabled=_leader_identity_binding_enabled,
)
