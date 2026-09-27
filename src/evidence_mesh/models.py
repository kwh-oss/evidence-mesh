"""Typed, model-independent products exchanged by evidence Partners."""

from dataclasses import dataclass
from enum import Enum


class EvidenceLevel(str, Enum):
    DIRECT = "direct"
    INDIRECT = "indirect"
    CONDITIONAL = "conditional"
    UNSUPPORTED = "unsupported"
    CONFLICTING = "conflicting"


@dataclass(frozen=True, slots=True)
class SourceRef:
    source_id: str
    title: str
    locator: str

    def __post_init__(self) -> None:
        if not self.source_id.strip():
            raise ValueError("source_id must not be empty")
        if not self.title.strip():
            raise ValueError("title must not be empty")
        if not self.locator.strip():
            raise ValueError("locator must not be empty")


@dataclass(frozen=True, slots=True)
class EvidenceFinding:
    claim_id: str
    agent_id: str
    level: EvidenceLevel
    rationale: str
    sources: tuple[SourceRef, ...] = ()
    confidence: float = 0.5

    def __post_init__(self) -> None:
        if not self.claim_id.strip():
            raise ValueError("claim_id must not be empty")
        if not self.agent_id.strip():
            raise ValueError("agent_id must not be empty")
        if not self.rationale.strip():
            raise ValueError("rationale must not be empty")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")
