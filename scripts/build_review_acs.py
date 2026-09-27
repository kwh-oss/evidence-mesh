"""Build private ACS candidates for Registry review from public templates.

The generated files contain real provider and deployment information and are
written only to the Git-ignored registry/acs-private directory.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from acps_sdk.acs import AgentCapabilitySpec


ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT / "registry" / "acs-drafts"
OUTPUT_DIR = ROOT / "registry" / "acs-private"

ENDPOINT_PATHS = {
    "evidence-audit-leader.draft.json": "/audit",
    "source-verifier.draft.json": "/source-verifier/rpc",
    "evidence-grader.draft.json": "/evidence-grader/rpc",
    "contradiction-scout.draft.json": "/contradiction-scout/rpc",
}


def required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise SystemExit(f"set {name} before building private ACS candidates")
    return value


def main() -> int:
    public_host = required_env("PUBLIC_HOST")
    provider_organization = required_env("PROVIDER_ORGANIZATION")
    provider_department = required_env("PROVIDER_DEPARTMENT")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for filename, endpoint_path in ENDPOINT_PATHS.items():
        raw = json.loads((SOURCE_DIR / filename).read_text(encoding="utf-8"))
        raw["provider"]["organization"] = provider_organization
        raw["provider"]["department"] = provider_department
        raw["certificate"]["altNames"]["dns"] = [public_host]
        raw["endPoints"][0]["url"] = f"https://{public_host}{endpoint_path}"
        raw.setdefault("entityMeta", {})["environment"] = "registry-review-candidate"
        raw["entityMeta"]["validationBoundary"] = (
            "Public HTTPS and application protocol validated before review; "
            "Registry AIC, EAB, platform-issued mTLS certificates, Discovery "
            "and AMP remain post-approval work."
        )

        output = OUTPUT_DIR / filename.replace(".draft.json", ".review.json")
        output.write_text(
            json.dumps(raw, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        AgentCapabilitySpec.from_file(output)
        print(f"built and SDK-validated: {output.name}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
