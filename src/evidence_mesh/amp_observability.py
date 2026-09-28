"""Small, environment-gated AMP heartbeat and audit integration."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import re
import time
from pathlib import Path

from fastapi import FastAPI

from acps_sdk.amp import (
    AccessBody,
    AccessEmitter,
    AccessParticipant,
    AccessRequest,
    AccessResponse,
    AuditAction,
    AuditActor,
    AuditBody,
    AuditEmitter,
    AuditResult,
    AuditTarget,
    CertificateAuditSigner,
    HeartbeatEmitter,
    MessageEmitter,
)


LOGGER = logging.getLogger(__name__)


def _enabled() -> bool:
    return os.getenv("AMP_ENABLED", "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _safe_name(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_.-]+", "-", value).strip("-") or "agent"


def _certificate_signer() -> CertificateAuditSigner | None:
    cert_path = Path(os.getenv("AMP_AUDIT_CERT_FILE", "/run/acps/server-cert.pem"))
    key_path = Path(os.getenv("AMP_AUDIT_KEY_FILE", "/run/acps/server-key.pem"))
    if not cert_path.is_file() or not key_path.is_file():
        LOGGER.warning("AMP audit signer unavailable: certificate or key is missing")
        return None
    try:
        return CertificateAuditSigner(
            private_key_pem=key_path.read_text(encoding="utf-8"),
            cert_pem=cert_path.read_text(encoding="utf-8"),
        )
    except Exception:
        LOGGER.warning("AMP audit signer could not be initialized", exc_info=True)
        return None


class AmpObservability:
    """Own the AMP emitters used by Direct RPC and Group transports."""

    def __init__(self, *, aic: str, agent_name: str) -> None:
        log_dir = Path(os.environ["AMP_LOG_DIR"])
        safe_name = _safe_name(agent_name)
        self.aic = aic
        self.agent_name = agent_name
        self.interval_seconds = float(
            os.getenv("AMP_HEARTBEAT_INTERVAL_SECONDS", "15")
        )
        if self.interval_seconds <= 0:
            raise ValueError("AMP_HEARTBEAT_INTERVAL_SECONDS must be positive")
        self.heartbeat = HeartbeatEmitter(
            log_dir / f"amp_heartbeat_{safe_name}.jsonl", aic=aic
        )
        self.audit = AuditEmitter(
            log_dir / f"amp_audit_{safe_name}.jsonl",
            aic=aic,
            signer=_certificate_signer(),
        )
        self.access = AccessEmitter(
            log_dir / f"amp_access_{safe_name}.jsonl", aic=aic
        )
        self.message = MessageEmitter(
            log_dir / f"amp_message_{safe_name}.jsonl", aic=aic
        )
        self._heartbeat_task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        # Emit synchronously with application startup so a healthy process always
        # leaves an immediately verifiable liveness record.
        await self.heartbeat.emit()
        self._heartbeat_task = asyncio.create_task(
            self._heartbeat_loop(), name=f"amp-heartbeat-{self.agent_name}"
        )

    async def _heartbeat_loop(self) -> None:
        while True:
            await asyncio.sleep(self.interval_seconds)
            await self.heartbeat.emit()

    async def stop(self) -> None:
        if self._heartbeat_task is None:
            return
        self._heartbeat_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._heartbeat_task
        self._heartbeat_task = None

    async def emit_task_result(
        self,
        *,
        actor_aic: str | None,
        task_id: str,
        session_id: str | None,
        success: bool,
        reason: str,
    ) -> None:
        await self.audit.emit(
            AuditBody(
                actor=AuditActor(id=actor_aic or "unknown", type="agent"),
                action=AuditAction(
                    name="receive_task_start", type="aip_protocol", method="Start"
                ),
                target=AuditTarget(type="task", id=task_id),
                result=AuditResult(
                    status="success" if success else "failure",
                    reason=reason,
                ),
            ),
            trace_id=session_id,
            correlation_id=task_id,
        )

    async def emit_access(
        self,
        *,
        caller_aic: str | None,
        caller_service: str,
        callee_aic: str | None,
        callee_service: str,
        task_id: str,
        session_id: str | None,
        url: str,
        duration_ms: float,
        status_code: int,
    ) -> None:
        """Emit one AIP access edge using taskId as the required correlationId."""

        await self.access.emit(
            AccessBody(
                durationMs=duration_ms,
                request=AccessRequest(method="Start", url=url, route="/rpc"),
                response=AccessResponse(statusCode=status_code),
                caller=AccessParticipant(
                    aic=caller_aic, serviceName=caller_service
                ),
                callee=AccessParticipant(
                    aic=callee_aic, serviceName=callee_service
                ),
            ),
            trace_id=session_id,
            correlation_id=task_id,
        )


def monotonic_ms() -> float:
    """Expose one clock helper so protocol handlers use a consistent unit."""

    return time.monotonic() * 1000


def install_amp_observability(
    app: FastAPI, *, aic: str, agent_name: str
) -> AmpObservability | None:
    """Attach AMP lifecycle hooks when explicitly enabled by deployment."""

    if not _enabled():
        return None
    if not aic.strip():
        raise ValueError("AMP requires a non-empty registered AIC")
    if not os.getenv("AMP_LOG_DIR", "").strip():
        raise ValueError("AMP_LOG_DIR is required when AMP_ENABLED=true")

    observability = AmpObservability(aic=aic, agent_name=agent_name)
    app.state.amp_observability = observability
    # FastAPI releases differ on whether this proxy is exposed on the app;
    # APIRouter owns the stable Starlette event-handler interface.
    app.router.add_event_handler("startup", observability.start)
    app.router.add_event_handler("shutdown", observability.stop)
    return observability

