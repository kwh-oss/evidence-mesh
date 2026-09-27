"""Classify ACS files as draft-save ready or submission ready.

Draft-save readiness checks the official SDK contract. Submission readiness is
stricter: it rejects every value that this repository deliberately uses as a
placeholder until Registry identity and a public deployment exist.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path

from acps_sdk.acs import AgentCapabilitySpec


ROOT = Path(__file__).resolve().parents[1]
DRAFT_DIR = ROOT / "registry" / "acs-drafts"


@dataclass(frozen=True)
class PreflightResult:
    path: Path
    submission_blockers: tuple[str, ...]
    post_approval_pending: tuple[str, ...]

    @property
    def draft_save_ready(self) -> bool:
        return True

    @property
    def submission_ready(self) -> bool:
        return not self.submission_blockers


def inspect_acs(path: Path) -> PreflightResult:
    spec = AgentCapabilitySpec.from_file(path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    blockers: list[str] = []
    pending: list[str] = []

    if spec.aic.startswith("REGISTRY_ASSIGNED_"):
        pending.append("AIC will be assigned after Registry approval")
    if spec.active is False:
        blockers.append("active=false marks this as a non-live draft")
    if "REPLACE_WITH_" in spec.provider.organization:
        blockers.append("provider organization is still a placeholder")
    for endpoint in spec.end_points:
        if ".invalid" in endpoint.url or "replace-before-submission" in endpoint.url:
            blockers.append("public endpoint is deliberately non-routable")
            break
    dns_names = raw.get("certificate", {}).get("altNames", {}).get("dns", [])
    if dns_names and any(
        ".invalid" in name or "replace-before-submission" in name
        for name in dns_names
    ):
        blockers.append("certificate DNS SAN is still a placeholder")
    if spec.entity_meta and spec.entity_meta.get("environment") == "draft":
        blockers.append("entityMeta.environment is still draft")

    return PreflightResult(
        path=path,
        submission_blockers=tuple(blockers),
        post_approval_pending=tuple(pending),
    )


def inspect_all() -> list[PreflightResult]:
    return [inspect_acs(path) for path in sorted(DRAFT_DIR.glob("*.draft.json"))]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--require-submission-ready",
        action="store_true",
        help="fail unless every ACS is safe to submit for review",
    )
    args = parser.parse_args()

    results = inspect_all()
    if not results:
        raise SystemExit(f"no ACS drafts found in {DRAFT_DIR}")

    for result in results:
        print(f"{result.path.name}: DRAFT_SAVE_READY")
        if result.submission_ready:
            print("  submission: READY")
        else:
            print("  submission: BLOCKED")
            for blocker in result.submission_blockers:
                print(f"  - {blocker}")
        for pending in result.post_approval_pending:
            print(f"  post-approval: {pending}")

    if args.require_submission_ready and any(not item.submission_ready for item in results):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
