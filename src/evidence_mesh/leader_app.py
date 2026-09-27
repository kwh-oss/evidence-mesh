"""User-facing HTTP entry point for the Evidence Mesh MVP."""

import json
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .contracts import request_from_json
from .leader import PartnerTarget, audit_claim
from .runtime_config import build_client_ssl_context, leader_identity, required_env


app = FastAPI(title="Evidence Mesh Leader", version="0.1.0")
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
