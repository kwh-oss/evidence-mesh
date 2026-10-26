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
from .partner_input import partner_product, partner_request
from .group_partner import install_group_partner_endpoint
from .runtime_config import partner_identity
from .retrieval_archive import AIP_TASK_ID, AIP_TASK_TRANSPORT
from .product_presentation import readable_product_item


Processor = Callable[[Any], Any]


def build_partner_app(
    *, service_name: str, product_type: str, processor: Processor,
    product_builder=None,
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
            from .collaboration_input import command_text
            request_text = command_text(command)
            request = partner_request(
                request_text, default_claim_id=current.taskId
            )
            archive_task_token = AIP_TASK_ID.set(current.taskId)
            archive_transport_token = AIP_TASK_TRANSPORT.set('aip-rpc')
            try:
                output = (await product_builder(request) if product_builder is not None
                          else partner_product(product_type, processor, request))
            finally:
                AIP_TASK_TRANSPORT.reset(archive_transport_token)
                AIP_TASK_ID.reset(archive_task_token)
        except (StopIteration, ValueError, json.JSONDecodeError):
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
                [TextDataItem(text="invalid-request: request validation failed; internal details withheld")],
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
            return TaskManager.update_task_status(
                current.taskId,
                TaskState.Failed,
                [TextDataItem(text="processing-error: task could not be completed; internal details withheld")],
            )

        TaskManager.set_products(
            current.taskId,
            [
                Product(
                    id=f"{service_name}-{current.taskId}",
                    name=product_type,
                    description="结论与依据；机器可读结果保留在数据项元数据中",
                    dataItems=[readable_product_item(output)],
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
            [TextDataItem(text=json.loads(output)['answer'])],
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
    group_enabled = install_group_partner_endpoint(
        app,
        local_aic=local_aic,
        identity_binding_enabled=identity_binding_enabled,
        service_name=service_name,
        product_type=product_type,
        processor=processor,
        amp=amp,
        product_builder=product_builder,
    )

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {
            "status": "ok",
            "service": service_name,
            "identity_binding": "enabled" if identity_binding_enabled else "disabled",
            "group": "enabled" if group_enabled else "disabled",
        }

    return app
