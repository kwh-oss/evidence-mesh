"""Versioned JSON contracts exchanged over AIP TextDataItem products."""

from dataclasses import asdict, dataclass
from enum import Enum
import json
from typing import Any

from .models import EvidenceFinding, EvidenceLevel, SourceRef


SCHEMA_VERSION = "1.0"


class SourceStatus(str, Enum):
    VERIFIED = "verified"
    INCOMPLETE = "incomplete"
    INVALID = "invalid"


class ContradictionStatus(str, Enum):
    NONE_FOUND = "none-found"
    POSSIBLE = "possible"
    CONFIRMED = "confirmed"


@dataclass(frozen=True, slots=True)
class AuditRequest:
    claim_id: str
    claim_text: str
    source: SourceRef
    source_excerpt: str

    @classmethod
    def from_dict(
        cls, value: dict[str, Any], *, default_claim_id: str | None = None
    ) -> "AuditRequest":
        source = value.get("source") or {}
        return cls(
            claim_id=(
                str(value.get("claim_id", "")).strip()
                or str(default_claim_id or "").strip()
            ),
            claim_text=str(value.get("claim_text", "")).strip(),
            source=SourceRef(
                source_id=str(source.get("source_id", "")).strip(),
                title=str(source.get("title", "")).strip(),
                locator=str(source.get("locator", "")).strip(),
            ),
            source_excerpt=str(value.get("source_excerpt", "")).strip(),
        )

    def __post_init__(self) -> None:
        if not self.claim_id:
            raise ValueError("claim_id must not be empty")
        if not self.claim_text:
            raise ValueError("claim_text must not be empty")
        if not self.source_excerpt:
            raise ValueError("source_excerpt must not be empty")


@dataclass(frozen=True, slots=True)
class SourceCheck:
    claim_id: str
    agent_id: str
    status: SourceStatus
    issues: tuple[str, ...]
    source: SourceRef


@dataclass(frozen=True, slots=True)
class ContradictionCheck:
    claim_id: str
    agent_id: str
    status: ContradictionStatus
    indicators: tuple[str, ...]


def request_from_json(
    text: str, *, default_claim_id: str | None = None
) -> AuditRequest:
    value = json.loads(text)
    if not isinstance(value, dict):
        raise ValueError("request must be a JSON object")
    if value.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"schema_version must be {SCHEMA_VERSION}")
    return AuditRequest.from_dict(value, default_claim_id=default_claim_id)


def request_json(request: AuditRequest) -> str:
    """Serialize one validated request for downstream Partners."""

    return json.dumps(
        {
            "schema_version": SCHEMA_VERSION,
            "claim_id": request.claim_id,
            "claim_text": request.claim_text,
            "source": asdict(request.source),
            "source_excerpt": request.source_excerpt,
        },
        ensure_ascii=False,
        sort_keys=True,
    )


def product_json(product_type: str, payload: Any) -> str:
    if isinstance(payload, EvidenceFinding):
        data = {
            "claim_id": payload.claim_id,
            "agent_id": payload.agent_id,
            "level": payload.level.value,
            "rationale": payload.rationale,
            "sources": [asdict(source) for source in payload.sources],
            "confidence": payload.confidence,
        }
    else:
        data = asdict(payload)
        for key, value in list(data.items()):
            if isinstance(value, Enum):
                data[key] = value.value
    return json.dumps(
        {
            "schema_version": SCHEMA_VERSION,
            "product_type": product_type,
            "payload": data,
        },
        ensure_ascii=False,
        sort_keys=True,
    )
