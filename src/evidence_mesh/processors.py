"""Deterministic baseline processors used before model-assisted reasoning is added."""

import re

from .contracts import (
    AuditRequest,
    ContradictionCheck,
    ContradictionStatus,
    SourceCheck,
    SourceStatus,
)
from .models import EvidenceFinding, EvidenceLevel


def verify_source(request: AuditRequest) -> SourceCheck:
    issues: list[str] = []
    if len(request.source_excerpt) < 12:
        issues.append("source excerpt is too short for reliable inspection")
    if request.source.locator.lower() in {"unknown", "n/a", "none"}:
        issues.append("source locator is not specific")

    return SourceCheck(
        claim_id=request.claim_id,
        agent_id="source-verifier",
        status=SourceStatus.VERIFIED if not issues else SourceStatus.INCOMPLETE,
        issues=tuple(issues),
        source=request.source,
    )


def grade_evidence(request: AuditRequest) -> EvidenceFinding:
    claim = _normalize(request.claim_text)
    excerpt = _normalize(request.source_excerpt)
    rationale: str
    confidence: float

    if _has_causal_overreach(request.claim_text, request.source_excerpt):
        level = EvidenceLevel.CONDITIONAL
        rationale = "The claim is causal or definitive, while the excerpt is associative or hedged."
        confidence = 0.88
    elif claim and claim in excerpt:
        level = EvidenceLevel.DIRECT
        rationale = "The normalized claim appears explicitly in the supplied excerpt."
        confidence = 0.95
    else:
        overlap = _bigram_overlap(claim, excerpt)
        if overlap >= 0.65:
            level = EvidenceLevel.INDIRECT
            rationale = f"The excerpt is related but does not state the full claim (overlap={overlap:.2f})."
            confidence = 0.78
        else:
            level = EvidenceLevel.UNSUPPORTED
            rationale = f"The supplied excerpt does not adequately cover the claim (overlap={overlap:.2f})."
            confidence = 0.82

    return EvidenceFinding(
        claim_id=request.claim_id,
        agent_id="evidence-grader",
        level=level,
        rationale=rationale,
        sources=(request.source,),
        confidence=confidence,
    )


def find_contradiction(request: AuditRequest) -> ContradictionCheck:
    pairs = (
        ("提高", "降低"),
        ("增加", "减少"),
        ("存在", "不存在"),
        ("促进", "抑制"),
        ("有效", "无效"),
        ("increase", "decrease"),
        ("present", "absent"),
        ("effective", "ineffective"),
        ("supports", "does not support"),
    )
    claim = request.claim_text.lower()
    excerpt = request.source_excerpt.lower()
    indicators = [f"{left}->{right}" for left, right in pairs if left in claim and right in excerpt]

    if indicators:
        status = ContradictionStatus.CONFIRMED
    elif any(marker in excerpt for marker in ("然而", "相反", "but", "however", "contrary")):
        status = ContradictionStatus.POSSIBLE
        indicators.append("contrast-marker")
    else:
        status = ContradictionStatus.NONE_FOUND

    return ContradictionCheck(
        claim_id=request.claim_id,
        agent_id="contradiction-scout",
        status=status,
        indicators=tuple(indicators),
    )


def _normalize(text: str) -> str:
    return "".join(re.findall(r"[a-z0-9\u4e00-\u9fff]+", text.lower()))


def _bigrams(text: str) -> set[str]:
    return {text[index : index + 2] for index in range(max(0, len(text) - 1))}


def _bigram_overlap(claim: str, excerpt: str) -> float:
    claim_bigrams = _bigrams(claim)
    if not claim_bigrams:
        return 0.0
    return len(claim_bigrams & _bigrams(excerpt)) / len(claim_bigrams)


def _has_causal_overreach(claim: str, excerpt: str) -> bool:
    causal = ("导致", "证明", "引起", "决定", "cause", "causes", "prove", "proves")
    hedged = ("相关", "关联", "可能", "提示", "may", "might", "associated", "correlated")
    claim_lower = claim.lower()
    excerpt_lower = excerpt.lower()
    return any(word in claim_lower for word in causal) and any(
        word in excerpt_lower for word in hedged
    )
