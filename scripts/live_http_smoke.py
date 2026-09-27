"""Run the four-agent HTTP topology and record a local smoke-test result.

This proves process startup, health checks, real loopback HTTP transport, and the
Leader-to-three-Partner AIP flow. It does not prove Registry, Discovery, mTLS,
AMP, or public-network acceptance.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any

import httpx


ROOT = Path(__file__).resolve().parents[1]
RUN_DIR = ROOT / "evidence" / "runs" / "2026-09-26-local-http-topology"

SERVICES = (
    ("source-verifier", "evidence_mesh.source_partner:app", 8021),
    ("evidence-grader", "evidence_mesh.grader_partner:app", 8022),
    ("contradiction-scout", "evidence_mesh.contradiction_partner:app", 8023),
    ("leader", "evidence_mesh.leader_app:app", 8010),
)

SAMPLE_REQUEST = {
    "schema_version": "1.0",
    "claim_id": "local-http-smoke-001",
    "claim_text": "材料提高抗菌率",
    "source": {
        "source_id": "doi:local-smoke-example",
        "title": "Local HTTP smoke-test source",
        "locator": "Results, paragraph 2",
    },
    "source_excerpt": "结果显示材料提高抗菌率，并在重复实验中趋势一致。",
}


def wait_for_health(process: subprocess.Popen[str], url: str, timeout: float = 20.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    last_error = "not attempted"
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"service exited early with code {process.returncode}")
        try:
            response = httpx.get(url, timeout=1.0)
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, ValueError) as error:
            last_error = str(error)
            time.sleep(0.2)
    raise TimeoutError(f"health check timed out for {url}: {last_error}")


def main() -> int:
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(ROOT / "src")
    environment["AIP_IDENTITY_BINDING_ENABLED"] = "false"

    processes: list[tuple[str, subprocess.Popen[str], Any]] = []
    health: dict[str, Any] = {}
    creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0

    try:
        for name, application, port in SERVICES:
            log_handle = (RUN_DIR / f"{name}.log").open("w", encoding="utf-8")
            command = [
                sys.executable,
                "-m",
                "uvicorn",
                application,
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
            ]
            process = subprocess.Popen(
                command,
                cwd=ROOT,
                env=environment,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                text=True,
                creationflags=creationflags,
            )
            processes.append((name, process, log_handle))

        for name, process, _ in processes:
            port = next(item[2] for item in SERVICES if item[0] == name)
            health[name] = wait_for_health(process, f"http://127.0.0.1:{port}/health")

        response = httpx.post(
            "http://127.0.0.1:8010/audit", json=SAMPLE_REQUEST, timeout=20.0
        )
        response.raise_for_status()
        passport = response.json()
        expected_products = {
            "source-check",
            "evidence-finding",
            "contradiction-check",
        }
        observed_products = {
            item.get("product_type")
            for item in passport.get("partner_products", {}).values()
        }
        if observed_products != expected_products:
            raise AssertionError(
                f"unexpected Partner products: {sorted(observed_products)}"
            )

        report = {
            "status": "passed",
            "scope": "local-loopback-http-only",
            "proves": [
                "four independent processes started",
                "four health endpoints responded over HTTP",
                "Leader called three Partner /rpc endpoints",
                "three typed Partner products were returned",
            ],
            "does_not_prove": [
                "Registry approval or AIC issuance",
                "Discovery lookup",
                "mTLS identity binding",
                "AMP telemetry",
                "public-network reachability",
                "competition-platform acceptance",
            ],
            "health": health,
            "request": SAMPLE_REQUEST,
            "response": passport,
        }
        output_path = RUN_DIR / "validation.json"
        output_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(f"PASS: {output_path}")
        print(f"decision={passport.get('decision')}")
        print(f"products={sorted(observed_products)}")
        return 0
    finally:
        for _, process, _ in reversed(processes):
            if process.poll() is None:
                process.terminate()
        for _, process, log_handle in reversed(processes):
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
            log_handle.close()


if __name__ == "__main__":
    raise SystemExit(main())
