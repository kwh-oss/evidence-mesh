"""Validate pre-registration ACS drafts against the installed official SDK."""

from pathlib import Path

from acps_sdk.acs import AgentCapabilitySpec


ROOT = Path(__file__).resolve().parents[1]
DRAFT_DIR = ROOT / "registry" / "acs-drafts"
EXPECTED_FILES = {
    "evidence-audit-leader.draft.json",
    "source-verifier.draft.json",
    "evidence-grader.draft.json",
    "contradiction-scout.draft.json",
}


def validate_drafts() -> list[str]:
    files = sorted(DRAFT_DIR.glob("*.draft.json"))
    found = {path.name for path in files}
    if found != EXPECTED_FILES:
        missing = sorted(EXPECTED_FILES - found)
        extra = sorted(found - EXPECTED_FILES)
        raise AssertionError(f"draft set mismatch: missing={missing}, extra={extra}")

    skill_ids: set[str] = set()
    validated: list[str] = []
    for path in files:
        spec = AgentCapabilitySpec.from_file(path)
        assert spec.protocol_version == "02.02"
        assert spec.version == "0.1.0"
        assert spec.active is False
        assert spec.aic.startswith("REGISTRY_ASSIGNED_")
        assert spec.capabilities.streaming is False
        assert spec.capabilities.notification is False
        assert spec.capabilities.message_queue == []
        assert len(spec.end_points) == 1
        assert "replace-before-submission.invalid" in spec.end_points[0].url
        assert len(spec.skills) == 1
        skill_id = spec.skills[0].id
        assert skill_id not in skill_ids
        skill_ids.add(skill_id)
        validated.append(path.name)
    return validated


if __name__ == "__main__":
    for filename in validate_drafts():
        print(f"validated: {filename}")
