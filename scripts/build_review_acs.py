"""Build private ACS candidates for Registry review from public templates.

The generated files contain the real deployment host and are written only to
the Git-ignored registry/acs-private directory.  The Registry admission rule
requires a non-empty provider object, so review candidates use the non-sensitive
team/provider display name supplied through the environment. Registry may
replace it with the account's verified provider snapshot during approval.
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
    "evidence-audit-leader.draft.json": "/rpc",
    "source-verifier.draft.json": "/source-verifier/rpc",
    "evidence-grader.draft.json": "/evidence-grader/rpc",
    "contradiction-scout.draft.json": "/contradiction-scout/rpc",
}

AIC_ENV_NAMES = {
    "evidence-audit-leader.draft.json": "LEADER_AIC",
    "source-verifier.draft.json": "SOURCE_VERIFIER_AIC",
    "evidence-grader.draft.json": "EVIDENCE_GRADER_AIC",
    "contradiction-scout.draft.json": "CONTRADICTION_SCOUT_AIC",
}


def required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise SystemExit(f"set {name} before building private ACS candidates")
    return value


def main() -> int:
    public_host = required_env("PUBLIC_HOST")
    provider_display_name = required_env("PROVIDER_OR_TEAM_NAME")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for filename, endpoint_path in ENDPOINT_PATHS.items():
        raw = json.loads((SOURCE_DIR / filename).read_text(encoding="utf-8"))
        # The static admission rule rejects an empty provider. Use the team
        # display name without disclosing a school or personal identity.
        raw["provider"] = {
            "countryCode": "CN",
            "organization": provider_display_name,
        }
        assigned_aic = os.environ.get(AIC_ENV_NAMES[filename], "").strip()
        if assigned_aic:
            raw["aic"] = assigned_aic
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
