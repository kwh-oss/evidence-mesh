"""Resume existing external children while preserving the root AIP identity."""
import asyncio
import json
from pathlib import Path
from acps_sdk.aip import Product, TaskResult, TaskState, TextDataItem
from acps_sdk.aip.aip_rpc_server import DefaultHandlers, TaskManager
from .external_consultation import pending_external_children, refresh_pending_consultation
from .product_presentation import read_product, readable_product_item
from .result_presentation import present_passport
from .leader_delivery import with_external_supplements

_locks = {}


def restore_pending_snapshots(local_aic, path='/run/evidence-pending-roots.json'):
    """Restore operator-captured old web roots across this service deployment."""
    file=Path(path)
    if not file.exists():
        return 0
    if file.stat().st_size>4_000_000:
        raise ValueError('pending snapshot exceeds bound')
    rows=json.loads(file.read_text())
    if not isinstance(rows,list) or len(rows)>150:
        raise ValueError('bounded pending snapshots required')
    restored=0
    for value in rows:
        task=TaskResult.model_validate(value)
        passport=read_product(task.products)
        if (task.senderId!=local_aic or not task.sessionId or not task.commandHistory
                or not isinstance(passport,dict) or not pending_external_children(passport)):
            raise ValueError('snapshot must be an authenticated pending Leader product')
        if TaskManager.get_task(task.taskId) is None:
            TaskManager._tasks[task.taskId]=task
            restored+=1
    return restored


async def get_with_external_recovery(command, task, collaborator):
    if task.status.state in (TaskState.Canceled,TaskState.Failed,TaskState.Rejected):
        return await DefaultHandlers.get(command,task)
    passport=read_product(task.products)
    if not isinstance(passport,dict) or not pending_external_children(passport):
        return await DefaultHandlers.get(command,task)
    lock=_locks.setdefault(task.taskId,asyncio.Lock())
    if lock.locked():
        return await DefaultHandlers.get(command,task)
    async with lock:
        try:
            refreshed=await refresh_pending_consultation(passport,collaborator)
        except Exception:
            # A failed status query never authorizes replaying Start.
            return await DefaultHandlers.get(command,task)
        if not refreshed.get('resumed_external_children'):
            return await DefaultHandlers.get(command,task)
        refreshed=with_external_supplements(present_passport(refreshed))
        TaskManager.set_products(task.taskId,[Product(id=f'evidence-audit-leader-{task.taskId}',
            name='evidence-passport',dataItems=[readable_product_item(refreshed)])])
        # Old completed roots may refresh their product without reopening their
        # terminal state. Newly pending roots remain Working until children end.
        if task.status.state not in (TaskState.Completed,TaskState.Failed):
            state=TaskState.Working if pending_external_children(refreshed) else TaskState.AwaitingCompletion
            TaskManager.update_task_status(task.taskId,state,[TextDataItem(text=refreshed.get('answer',''))])
        return await DefaultHandlers.get(command,TaskManager.get_task(task.taskId))
