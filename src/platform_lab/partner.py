"""Minimal local AIP Partner service using acps-sdk 2.2.0."""

from fastapi import FastAPI

from acps_sdk.aip import Product, TaskResult, TaskState, TextDataItem
from acps_sdk.aip.aip_rpc_server import (
    CommandHandlers,
    DefaultHandlers,
    TaskManager,
    add_aip_rpc_router,
)


PARTNER_AIC = "competition-local-partner"

app = FastAPI(title="Competition Local Partner", version="0.1.0")


async def on_start(command, task: TaskResult | None) -> TaskResult:
    """Accept one text request and return a deterministic local product."""
    current = await DefaultHandlers.start(command, task)
    if task is not None:
        return current

    user_text = ""
    for item in command.dataItems or []:
        if isinstance(item, TextDataItem):
            user_text = item.text.strip()
            if user_text:
                break

    response_text = f"Partner received: {user_text or '[empty input]'}"
    TaskManager.set_products(
        current.taskId,
        [
            Product(
                id=f"product-{current.taskId}",
                name="Local protocol proof",
                description="Deterministic output used to verify the AIP Direct RPC loop.",
                dataItems=[TextDataItem(text=response_text)],
            )
        ],
    )
    return TaskManager.update_task_status(
        current.taskId,
        TaskState.AwaitingCompletion,
        [TextDataItem(text="Work finished; waiting for Leader confirmation.")],
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
    local_aic=PARTNER_AIC,
    identity_binding_enabled=False,
)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "aic": PARTNER_AIC}
