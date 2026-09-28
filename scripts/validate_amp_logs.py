"""Validate deployed AMP heartbeat/audit heads without printing sensitive bodies."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def records(path: Path) -> list[dict]:
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines:
        raise ValueError(f"empty AMP log: {path}")
    return [json.loads(line) for line in lines]


def validate_agent(log_root: Path, name: str, aic: str) -> dict:
    audit_name = "evidence-audit-leader" if name == "leader" else name
    heartbeat_path = log_root / name / f"amp_heartbeat_{audit_name}.jsonl"
    audit_path = log_root / name / f"amp_audit_{audit_name}.jsonl"
    heartbeats = records(heartbeat_path)
    audits = records(audit_path)
    heartbeat = heartbeats[-1]
    audit = audits[-1]

    if heartbeat.get("log_type") != "heartbeat" or heartbeat.get("aic") != aic:
        raise ValueError(f"heartbeat identity mismatch for {name}")
    if len(heartbeats) < 2:
        raise ValueError(f"heartbeat is not yet continuous for {name}")
    if any(item.get("aic") != aic for item in heartbeats):
        raise ValueError(f"mixed heartbeat identities for {name}")
    if audit.get("log_type") != "audit" or audit.get("aic") != aic:
        raise ValueError(f"audit identity mismatch for {name}")
    integrity = audit.get("integrity") or {}
    if not all(integrity.get(field) for field in ("alg", "kid", "sig")):
        raise ValueError(f"signed audit integrity missing for {name}")
    return {
        "agent": name,
        "aic": aic,
        "heartbeat": "ok",
        "heartbeat_records": len(heartbeats),
        "signed_audit": "ok",
        "audit_alg": integrity["alg"],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--log-root", type=Path, required=True)
    parser.add_argument(
        "--agent",
        action="append",
        required=True,
        metavar="NAME=AIC",
        help="Repeat for each deployed agent directory",
    )
    args = parser.parse_args()
    results = []
    for value in args.agent:
        name, separator, aic = value.partition("=")
        if not separator or not name or not aic:
            raise ValueError(f"invalid --agent value: {value}")
        results.append(validate_agent(args.log_root, name, aic))
    print(json.dumps({"status": "AMP_HEAD_OK", "agents": results}, ensure_ascii=False))


if __name__ == "__main__":
    main()
