"""Deterministic aggregation rules; no LLM is allowed to rewrite these states."""

from dataclasses import dataclass
from enum import Enum

from .models import EvidenceFinding, EvidenceLevel


class ClaimDecision(str, Enum):
    SUPPORTED = "supported"
    NEEDS_REVIEW = "needs-review"
    CONFLICTING = "conflicting"
    NO_EVIDENCE = "no-evidence"


@dataclass(frozen=True, slots=True)
class AuditSummary:
    decisions: dict[str, ClaimDecision]
    finding_counts: dict[str, int]
    evidence_coverage: float
    risk_flags: tuple[str, ...]


def summarize_findings(
    claim_ids: list[str], findings: list[EvidenceFinding]
) -> AuditSummary:
    """Aggregate Partner products without silently resolving missing or conflicting evidence."""
    unique_claim_ids = list(dict.fromkeys(claim_id.strip() for claim_id in claim_ids))
    if not unique_claim_ids or any(not claim_id for claim_id in unique_claim_ids):
        raise ValueError("claim_ids must contain at least one non-empty id")

    known_ids = set(unique_claim_ids)
    unknown_ids = sorted({finding.claim_id for finding in findings} - known_ids)
    if unknown_ids:
        raise ValueError(f"findings reference unknown claims: {unknown_ids}")

    grouped = {claim_id: [] for claim_id in unique_claim_ids}
    for finding in findings:
        grouped[finding.claim_id].append(finding)

    decisions: dict[str, ClaimDecision] = {}
    counts: dict[str, int] = {}
    flags: list[str] = []

    for claim_id, claim_findings in grouped.items():
        counts[claim_id] = len(claim_findings)
        levels = {finding.level for finding in claim_findings}

        if not levels:
            decisions[claim_id] = ClaimDecision.NO_EVIDENCE
            flags.append(f"{claim_id}:no-finding")
        elif EvidenceLevel.CONFLICTING in levels or (
            EvidenceLevel.DIRECT in levels and EvidenceLevel.UNSUPPORTED in levels
        ):
            decisions[claim_id] = ClaimDecision.CONFLICTING
            flags.append(f"{claim_id}:conflict")
        elif levels == {EvidenceLevel.DIRECT}:
            decisions[claim_id] = ClaimDecision.SUPPORTED
        else:
            decisions[claim_id] = ClaimDecision.NEEDS_REVIEW
            flags.append(f"{claim_id}:insufficient-or-conditional")

    covered = sum(1 for claim_id in unique_claim_ids if grouped[claim_id])
    return AuditSummary(
        decisions=decisions,
        finding_counts=counts,
        evidence_coverage=covered / len(unique_claim_ids),
        risk_flags=tuple(flags),
    )
