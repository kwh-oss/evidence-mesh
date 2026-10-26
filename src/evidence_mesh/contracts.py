"""Versioned JSON contracts exchanged over AIP TextDataItem products."""

from dataclasses import asdict, dataclass
from enum import Enum
import json
import re
from typing import Any

from .models import EvidenceFinding, EvidenceLevel, SourceRef
from .caller_document import document_sections, quoted_comparison


SCHEMA_VERSION = "1.0"
MISSING_SOURCE_EXCERPT = "未提供证据摘录；请补充原文或数据位置。"


_LABELED_TEXT_PATTERNS = (
    re.compile(
        r"(?:结论|主张|断言)\s*(?:[：:]\s*)?[“\"']?"
        r"(?P<claim>.+?)[”\"']?\s*[；;,，。\n]\s*"
        r"(?:证据摘录|证据|依据|原文|结果)\s*(?:[：:]\s*)?[“\"']?"
        r"(?P<evidence>.+?)[”\"']?\s*$",
        re.DOTALL,
    ),
    re.compile(
        r"(?:claim|conclusion|statement|assertion)\s*:\s*[\"']?"
        r"(?P<claim>.+?)[\"']?\s*[;\n]\s*"
        r"(?:evidence|excerpt|source|context)\s*:\s*[\"']?"
        r"(?P<evidence>.+?)[\"']?\s*$",
        re.IGNORECASE | re.DOTALL,
    ),
)


def _labeled_text_payload(text: str) -> dict[str, str] | None:
    candidate = text.strip()
    candidate = re.sub(r"^请(?:帮我)?核验\s*[：:]?\s*", "", candidate)
    for pattern in _LABELED_TEXT_PATTERNS:
        match = pattern.search(candidate)
        if match:
            return {
                "claim_text": match.group("claim").strip(" \t\r\n‘’“”\"'。."),
                "source_excerpt": match.group("evidence").strip(
                    " \t\r\n‘’“”\"'。."
                ),
            }
    return None


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
    task_type: str = "auto"
    goal: str = ""
    audience: str = ""
    constraints: tuple[str, ...] = ()

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
            task_type=str(value.get("task_type", "auto")).strip() or "auto",
            goal=str(value.get("goal", "")).strip(),
            audience=str(value.get("audience", "")).strip(),
            constraints=_string_tuple(value.get("constraints")),
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


def request_from_caller_text(
    text: str, *, default_claim_id: str | None = None
) -> AuditRequest:
    """Normalize caller-friendly text into the strict internal contract.

    Missing evidence is represented explicitly so the fail-closed pipeline can
    return a useful needs-review result instead of rejecting the AIP task.
    """

    raw_text = text.strip()
    if not raw_text:
        raise ValueError("request text must not be empty")

    try:
        value = json.loads(raw_text)
    except json.JSONDecodeError:
        value = document_sections(raw_text) or _labeled_text_payload(raw_text) or quoted_comparison(raw_text) or {"claim_text": raw_text}

    if not isinstance(value, dict):
        raise ValueError("request must be plain text or a JSON object")

    normalized = dict(value)
    if not any(
        key in normalized
        for key in (
            "claim_text",
            "claim",
            "conclusion",
            "statement",
            "assertion",
            "finding",
            "query",
            "text",
            "draft",
            "answer",
            "response",
            "output",
            "final_answer",
        )
    ):
        for envelope_key in ("payload", "input", "data", "request"):
            envelope = normalized.get(envelope_key)
            if isinstance(envelope, dict):
                normalized = {**normalized, **envelope}
                break
    normalized.setdefault("schema_version", SCHEMA_VERSION)
    if normalized.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"schema_version must be {SCHEMA_VERSION}")

    if not str(normalized.get("claim_text", "")).strip():
        for alias in (
            "claim",
            "conclusion",
            "statement",
            "assertion",
            "finding",
            "query",
            "text",
            "request",
            "draft",
            "answer",
            "response",
            "output",
            "final_answer",
        ):
            alias_text = _coerce_text(normalized.get(alias))
            if alias_text:
                normalized["claim_text"] = alias_text
                break

    if not str(normalized.get("source_excerpt", "")).strip():
        for alias in (
            "evidence_excerpt",
            "excerpt",
            "evidence",
            "supporting_text",
            "source_text",
            "citation_excerpt",
            "context",
            "result_text",
            "materials",
            "documents",
            "passages",
        ):
            alias_text = _coerce_text(normalized.get(alias))
            if alias_text:
                normalized["source_excerpt"] = alias_text
                break
        else:
            normalized["source_excerpt"] = MISSING_SOURCE_EXCERPT

    # Dingdang can wrap a flattened labelled task inside a JSON text field.
    # Never replace separately provided caller evidence with embedded material.
    if normalized.get('source_excerpt') == MISSING_SOURCE_EXCERPT:
        embedded_text = str(normalized.get('claim_text', ''))
        sections = document_sections(embedded_text) or _labeled_text_payload(embedded_text) or quoted_comparison(embedded_text)
        if sections:
            if 'source' in sections:
                sections['source'] = {**sections['source'], **(normalized.get('source') or {})}
            for field in ('task_type', 'goal'):
                if normalized.get(field):
                    sections.pop(field, None)
            normalized.update(sections)
    return AuditRequest.from_dict(normalized, default_claim_id=default_claim_id)


def request_json(request: AuditRequest) -> str:
    """Serialize one validated request for downstream Partners."""

    return json.dumps(
        {
            "schema_version": SCHEMA_VERSION,
            "claim_id": request.claim_id,
            "claim_text": request.claim_text,
            "source": asdict(request.source),
            "source_excerpt": request.source_excerpt,
            "task_type": request.task_type,
            "goal": request.goal,
            "audience": request.audience,
            "constraints": list(request.constraints),
        },
        ensure_ascii=False,
        sort_keys=True,
    )


def _coerce_text(value: Any) -> str:
    """Preserve caller material without inventing content."""

    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (list, tuple)):
        parts = [_coerce_text(item) for item in value]
        return "\n\n".join(part for part in parts if part)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return ""


def _string_tuple(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value.strip(),) if value.strip() else ()
    if isinstance(value, (list, tuple)):
        return tuple(text for item in value if (text := _coerce_text(item)))
    return ()


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
