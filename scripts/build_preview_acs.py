"""Build non-submittable ACS snapshots matching the public HTTPS preview."""

from __future__ import annotations

import json
import os
from pathlib import Path

from acps_sdk.acs import AgentCapabilitySpec


ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT / "registry" / "acs-drafts"
OUTPUT_DIR = ROOT / "registry" / "acs-preview"
PUBLIC_HOST = os.environ.get("PUBLIC_HOST", "preview-host.invalid").strip()

ENDPOINTS = {
    "evidence-audit-leader.draft.json": (
        f"https://{PUBLIC_HOST}",
        "HTTP_JSON",
    ),
    "source-verifier.draft.json": (
        f"https://{PUBLIC_HOST}/source-verifier/rpc",
        "JSONRPC",
    ),
    "evidence-grader.draft.json": (
        f"https://{PUBLIC_HOST}/evidence-grader/rpc",
        "JSONRPC",
    ),
    "contradiction-scout.draft.json": (
        f"https://{PUBLIC_HOST}/contradiction-scout/rpc",
        "JSONRPC",
    ),
}


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for filename, (url, transport) in ENDPOINTS.items():
        source = SOURCE_DIR / filename
        raw = json.loads(source.read_text(encoding="utf-8"))
        raw["securitySchemes"] = {}
        raw.pop("certificate", None)
        raw["active"] = False
        raw["endPoints"] = [{"url": url, "transport": transport}]
        raw.setdefault("entityMeta", {})["environment"] = (
            "preview-https-no-identity-binding"
        )
        raw["entityMeta"]["submissionReady"] = False
        raw["entityMeta"]["validationBoundary"] = (
            "Public HTTPS preview only; Registry AIC, mTLS identity binding, "
            "Discovery and AMP remain unverified."
        )
        output = OUTPUT_DIR / filename.replace(".draft.json", ".preview.json")
        output.write_text(
            json.dumps(raw, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        AgentCapabilitySpec.from_file(output)
        print(f"built and SDK-validated: {output.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
