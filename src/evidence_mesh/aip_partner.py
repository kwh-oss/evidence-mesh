"""Reusable FastAPI/AIP wrapper for deterministic evidence processors."""

from collections.abc import Callable
import json
from typing import Any

from fastapi import FastAPI

from acps_sdk.aip import Product, TaskResult, TaskState, TextDataItem
from acps_sdk.aip.aip_rpc_server import (
    CommandHandlers,
    DefaultHandlers,
    TaskManager,
    add_aip_rpc_router,
)
from acps_sdk.aip.aip_peer_cert import AipPeerCertificateMiddleware

from .amp_observability import install_amp_observability, monotonic_ms
from .contracts import product_json, request_from_json
from .runtime_config import partner_identity


Processor = Callable[[Any], Any]


def build_partner_app(
    *, service_name: str, product_type: str, processor: Processor
) -> FastAPI:
    app = FastAPI(title=service_name, version="0.1.0")
    local_aic, identity_binding_enabled = partner_identity(service_name)
    amp = install_amp_observability(
        app, aic=local_aic, agent_name=service_name
    )
    # The SDK reads the authenticated caller AIC from request.state. In a real
    # mTLS deployment AipPeerCertH11Protocol records the TLS peer certificate,
    # and this middleware copies that identity into request.state for the RPC
    # route. It is harmless in local HTTP mode, where binding is disabled.
    app.add_middleware(AipPeerCertificateMiddleware)

    async def on_start(command, task: TaskResult | None) -> TaskResult:
        started_at = monotonic_ms()
        current = await DefaultHandlers.start(command, task)
        if task is not None:
            return current
        current.senderId = local_aic

        try:
            request_text = next(
                item.text
                for item in command.dataItems or []
                if isinstance(item, TextDataItem) and item.text.strip()
            )
            request = request_from_json(request_text)
            payload = processor(request)
            output = product_json(product_type, payload)
        except (StopIteration, ValueError, json.JSONDecodeError) as error:
            if amp is not None:
                await amp.emit_access(
                    caller_aic=getattr(command, "senderId", None),
                    caller_service="aip-caller",
                    callee_aic=local_aic,
                    callee_service=service_name,
                    task_id=current.taskId,
                    session_id=getattr(command, "sessionId", None),
                    url="/rpc",
                    duration_ms=monotonic_ms() - started_at,
                    status_code=422,
                )
                await amp.emit_task_result(
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
            if amp is not None:
                await amp.emit_access(
                    caller_aic=getattr(command, "senderId", None),
                    caller_service="aip-caller",
                    callee_aic=local_aic,
                    callee_service=service_name,
                    task_id=current.taskId,
                    session_id=getattr(command, "sessionId", None),
                    url="/rpc",
                    duration_ms=monotonic_ms() - started_at,
                    status_code=500,
                )
                await amp.emit_task_result(
                    actor_aic=getattr(command, "senderId", None),
                    task_id=current.taskId,
                    session_id=getattr(command, "sessionId", None),
                    success=False,
                    reason="processing-error",
                )
            raise

        TaskManager.set_products(
            current.taskId,
            [
                Product(
                    id=f"{service_name}-{current.taskId}",
                    name=product_type,
                    description=f"Structured {product_type} product",
                    dataItems=[TextDataItem(text=output)],
                )
            ],
        )
        if amp is not None:
            await amp.emit_access(
                caller_aic=getattr(command, "senderId", None),
                caller_service="evidence-audit-leader",
                callee_aic=local_aic,
                callee_service=service_name,
                task_id=current.taskId,
                session_id=getattr(command, "sessionId", None),
                url="/rpc",
                duration_ms=monotonic_ms() - started_at,
                status_code=200,
            )
            await amp.emit_task_result(
                actor_aic=getattr(command, "senderId", None),
                task_id=current.taskId,
                session_id=getattr(command, "sessionId", None),
                success=True,
                reason="structured-product-ready",
            )
        return TaskManager.update_task_status(
            current.taskId,
            TaskState.AwaitingCompletion,
            [TextDataItem(text="Structured product ready for Leader confirmation.")],
        )

    handlers = CommandHandlers(
        on_start=on_start,
        on_get=DefaultHandlers.get,
        on_cancel=DefaultHandlers.cancel,
        on_complete=DefaultHandlers.complete,
        on_continue=DefaultHandlers.continue_,
    )
    add_aip_rpc_router(
        app,
        "/rpc",
        handlers,
        local_aic=local_aic,
        identity_binding_enabled=identity_binding_enabled,
    )

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {
            "status": "ok",
            "service": service_name,
            "identity_binding": "enabled" if identity_binding_enabled else "disabled",
        }

    return app
