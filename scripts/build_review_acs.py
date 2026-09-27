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

ENDPOINTS = {
    "evidence-audit-leader.draft.json": (8440, "/rpc"),
    "source-verifier.draft.json": (8441, "/rpc"),
    "evidence-grader.draft.json": (8442, "/rpc"),
    "contradiction-scout.draft.json": (8443, "/rpc"),
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
    agent_version = os.environ.get("ACS_VERSION", "0.1.0").strip() or "0.1.0"

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for filename, (endpoint_port, endpoint_path) in ENDPOINTS.items():
        raw = json.loads((SOURCE_DIR / filename).read_text(encoding="utf-8"))
        # The static admission rule rejects an empty provider. Use the team
        # display name without disclosing a school or personal identity.
        raw["provider"] = {
            "countryCode": "CN",
            "organization": provider_display_name,
        }
        raw["version"] = agent_version
        assigned_aic = os.environ.get(AIC_ENV_NAMES[filename], "").strip()
        if assigned_aic:
            raw["aic"] = assigned_aic
        raw["certificate"]["altNames"]["dns"] = [public_host]
        raw["endPoints"][0]["url"] = (
            f"https://{public_host}:{endpoint_port}{endpoint_path}"
        )
        raw.setdefault("entityMeta", {})["environment"] = "registry-review-candidate"
        if assigned_aic:
            raw["entityMeta"]["validationBoundary"] = (
                "Registry AIC, EAB and platform-issued certificates acquired; "
                "public mTLS boundary verified; Discovery and AMP validation remain pending."
            )
        else:
            raw["entityMeta"]["validationBoundary"] = (
                "Public mTLS endpoint boundary verified using the approved 0.1.0 "
                "deployment identity; this version's Registry AIC, EAB and "
                "platform-issued certificates remain pending until approval."
            )

        if agent_version == "0.1.0":
            output_name = filename.replace(".draft.json", ".review.json")
        else:
            version_suffix = agent_version.replace(".", "-")
            output_name = filename.replace(
                ".draft.json", f".v{version_suffix}.review.json"
            )
        output = OUTPUT_DIR / output_name
        output.write_text(
            json.dumps(raw, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        AgentCapabilitySpec.from_file(output)
        print(f"built and SDK-validated: {output.name}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
