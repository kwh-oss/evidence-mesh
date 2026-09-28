"""Optional AIP Group endpoint for one deterministic evidence Partner."""

from __future__ import annotations

from collections.abc import Callable
import json
from typing import Any

from fastapi import FastAPI, Request

from acps_sdk.aip import (
    GroupPartnerMqClient,
    Product,
    TaskCommand,
    TaskCommandType,
    TextDataItem,
)
from acps_sdk.aip.aip_group_model import (
    GroupInvitationErrorData,
    RabbitMQRequest,
    RabbitMQResponse,
    RabbitMQResponseError,
)
from acps_sdk.aip.aip_peer_cert import get_request_peer_aic

from .amp_observability import AmpObservability
from .contracts import product_json, request_from_json
from .runtime_config import build_group_ssl_context, env_flag


Processor = Callable[[Any], Any]


async def process_group_command(
    *,
    client: GroupPartnerMqClient,
    command: TaskCommand,
    is_mentioned: bool,
    service_name: str,
    product_type: str,
    processor: Processor,
    amp: AmpObservability | None = None,
) -> None:
    """Run the existing deterministic processor for one mentioned Group task."""

    if not is_mentioned or command.command != TaskCommandType.Start:
        return
    if not command.taskId or not command.sessionId or not command.groupId:
        return

    try:
        await client.accept_task(command.taskId, command.sessionId)
        await client.start_working(command.taskId, command.sessionId)
        request_text = next(
            item.text
            for item in command.dataItems or []
            if isinstance(item, TextDataItem) and item.text.strip()
        )
        request = request_from_json(
            request_text, default_claim_id=command.taskId
        )
        payload = processor(request)
        output = product_json(product_type, payload)
        product = Product(
            id=f"{service_name}-{command.taskId}",
            name=product_type,
            description=f"Structured {product_type} Group product",
            dataItems=[TextDataItem(text=output)],
        )
        await client.submit_for_completion(
            command.taskId, command.sessionId, [product]
        )
        if amp is not None:
            await amp.emit_task_result(
                actor_aic=command.senderId,
                task_id=command.taskId,
                session_id=command.sessionId,
                success=True,
                reason="group-product-ready",
            )
    except (StopIteration, ValueError, json.JSONDecodeError) as error:
        await client.fail_task(
            command.taskId, command.sessionId, f"invalid-request: {error}"
        )
        if amp is not None:
            await amp.emit_task_result(
                actor_aic=command.senderId,
                task_id=command.taskId,
                session_id=command.sessionId,
                success=False,
                reason="group-invalid-request",
            )
    except Exception as error:
        await client.fail_task(
            command.taskId, command.sessionId, f"processing-error: {error}"
        )
        if amp is not None:
            await amp.emit_task_result(
                actor_aic=command.senderId,
                task_id=command.taskId,
                session_id=command.sessionId,
                success=False,
                reason="group-processing-error",
            )


def install_group_partner_endpoint(
    app: FastAPI,
    *,
    local_aic: str,
    identity_binding_enabled: bool,
    service_name: str,
    product_type: str,
    processor: Processor,
    amp: AmpObservability | None,
) -> bool:
    """Install `/group/rpc` only when strict Group credentials are configured."""

    enabled = env_flag("GROUP_ENABLED", default=False)
    app.state.group_enabled = enabled
    if not enabled:
        return False

    ssl_context = build_group_ssl_context()
    clients: dict[str, GroupPartnerMqClient] = {}

    @app.post("/group/rpc", response_model=RabbitMQResponse)
    async def handle_group_invite(
        payload: RabbitMQRequest, request: Request
    ) -> RabbitMQResponse:
        group_id = payload.params.group.groupId
        leader_aic = payload.params.group.leader.aic
        if identity_binding_enabled and get_request_peer_aic(request) != leader_aic:
            return RabbitMQResponse(
                jsonrpc="2.0",
                id=payload.id,
                error=RabbitMQResponseError(
                    code=-32022,
                    message="Leader certificate identity mismatch",
                    data=GroupInvitationErrorData(
                        errorType="IDENTITY_MISMATCH",
                        details="mTLS peer AIC must equal group.leader.aic",
                    ),
                ),
            )

        client = GroupPartnerMqClient(
            partner_aic=local_aic,
            rabbitmq_user=None,
            rabbitmq_password=None,
            ssl_context=ssl_context,
            message_emitter=amp.message if amp is not None else None,
            identity_binding_enabled=identity_binding_enabled,
        )

        async def on_command(command: TaskCommand, is_mentioned: bool) -> None:
            await process_group_command(
                client=client,
                command=command,
                is_mentioned=is_mentioned,
                service_name=service_name,
                product_type=product_type,
                processor=processor,
                amp=amp,
            )

        client.set_command_handler(on_command)
        response = await client.join_group(payload)
        if response.result is not None:
            previous = clients.pop(group_id, None)
            if previous is not None:
                await previous.close()
            clients[group_id] = client
        else:
            await client.close()
        return response

    async def close_group_clients() -> None:
        for client in list(clients.values()):
            await client.close()
        clients.clear()

    app.router.add_event_handler("shutdown", close_group_clients)
    app.state.group_clients = clients
    return True
