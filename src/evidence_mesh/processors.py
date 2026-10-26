"""Deterministic baseline processors used before model-assisted reasoning is added."""

import re

from .contracts import (
    AuditRequest,
    MISSING_SOURCE_EXCERPT,
    ContradictionCheck,
    ContradictionStatus,
    SourceCheck,
    SourceStatus,
)
from .models import EvidenceFinding, EvidenceLevel
from .rule_signals import is_weak_indicator


_DURATION_PATTERN = re.compile(
    r"(?P<field>退款期限|配送期限|退货期限|保修期限|响应时间)"
    r"\s*(?:为|是|[:：])\s*(?P<number>\d+|[零一二两三四五六七八九十]+)"
    r"\s*(?P<unit>小时|天|周)(?=[。；;，,\s]|$)"
)


def verify_source(request: AuditRequest) -> SourceCheck:
    issues: list[str] = []
    if not request.source.source_id.strip():
        issues.append("source identifier is missing")
    if not request.source.title.strip():
        issues.append("source title is missing")
    if not request.source.locator.strip():
        issues.append("source locator is missing")
    if request.source_excerpt == MISSING_SOURCE_EXCERPT:
        issues.append("source excerpt is missing")
    elif len(request.source_excerpt) < 12:
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

    if _has_directional_conflict(request.claim_text, request.source_excerpt):
        level = EvidenceLevel.CONFLICTING
        rationale = "The supplied material states the opposite direction or polarity of the claim."
        confidence = 0.94
    elif _has_causal_overreach(request.claim_text, request.source_excerpt):
        level = EvidenceLevel.CONDITIONAL
        rationale = "The claim is causal or definitive, while the excerpt is associative or hedged."
        confidence = 0.88
    elif _has_significance_overreach(request.claim_text, request.source_excerpt):
        level = EvidenceLevel.CONDITIONAL
        rationale = "The claim asserts significance, but the supplied material says statistical testing is absent or inconclusive."
        confidence = 0.92
    elif _has_scope_overreach(request.claim_text, request.source_excerpt):
        level = EvidenceLevel.CONDITIONAL
        rationale = "The claim is universal or definitive, while the supplied material is limited, preliminary, or local."
        confidence = 0.86
    elif claim and claim in excerpt:
        level = EvidenceLevel.DIRECT
        rationale = "The normalized claim appears explicitly in the supplied excerpt."
        confidence = 0.95
    else:
        overlap = _bigram_overlap(claim, excerpt)
        if overlap >= 0.65 or _has_matching_numeric_anchor(
            request.claim_text, request.source_excerpt, overlap
        ):
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
    indicators.extend(_duration_mismatches(claim, excerpt))
    indicators.extend(
        f"internal:{left}<->{right}"
        for left, right in pairs
        if left in excerpt and right in excerpt
    )

    certain = ("一定", "必然", "完全", "已经证明", "always", "certainly", "proven")
    limited = (
        "可能",
        "初步",
        "试点",
        "尚未",
        "有限",
        "may",
        "might",
        "preliminary",
        "pilot",
        "not yet",
    )
    if any(word in claim for word in certain) and any(word in excerpt for word in limited):
        indicators.append("certainty-boundary-conflict")

    # Labelled durations have already been compared by field and converted
    # to hours; do not compare them again as unrelated bare numbers.
    labelled_both = _DURATION_PATTERN.search(claim) and _DURATION_PATTERN.search(excerpt)
    numeric_claim = _DURATION_PATTERN.sub("", claim) if labelled_both else claim
    numeric_excerpt = _DURATION_PATTERN.sub("", excerpt) if labelled_both else excerpt
    claim_numbers = set(re.findall(r"\d+(?:\.\d+)?%?", numeric_claim))
    excerpt_numbers = set(re.findall(r"\d+(?:\.\d+)?%?", numeric_excerpt))
    if claim_numbers and excerpt_numbers and claim_numbers.isdisjoint(excerpt_numbers):
        indicators.append("numeric-mismatch")

    if indicators and all(is_weak_indicator(i) for i in indicators):
        status = ContradictionStatus.POSSIBLE
    elif indicators:
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
    hedged = (
        "相关", "关联", "可能", "提示", "没有对照", "无对照", "无法判断因果",
        "不能判断因果", "may", "might", "associated", "correlated",
        "no control group", "cannot establish causality", "observational",
    )
    claim_lower = claim.lower()
    excerpt_lower = excerpt.lower()
    return any(word in claim_lower for word in causal) and any(
        word in excerpt_lower for word in hedged
    )


def _has_directional_conflict(claim: str, excerpt: str) -> bool:
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
    claim_lower = claim.lower()
    excerpt_lower = excerpt.lower()
    return any(left in claim_lower and right in excerpt_lower for left, right in pairs)


def _has_matching_numeric_anchor(claim: str, excerpt: str, overlap: float) -> bool:
    """Treat matching quantities plus shared wording as indirect, not direct, support."""

    claim_numbers = set(re.findall(r"\d+(?:\.\d+)?%?", claim))
    excerpt_numbers = set(re.findall(r"\d+(?:\.\d+)?%?", excerpt))
    return bool(claim_numbers) and claim_numbers <= excerpt_numbers and overlap >= 0.25


def _has_significance_overreach(claim: str, excerpt: str) -> bool:
    significance = ("显著", "statistically significant", "significant")
    unavailable = (
        "未进行显著性检验",
        "没有显著性检验",
        "差异不显著",
        "未报告p值",
        "not statistically significant",
        "no significance test",
        "p value was not reported",
    )
    claim_lower = claim.lower()
    excerpt_lower = excerpt.lower()
    return any(word in claim_lower for word in significance) and any(
        word in excerpt_lower for word in unavailable
    )


def _has_scope_overreach(claim: str, excerpt: str) -> bool:
    universal = (
        "永远", "无条件", "绝对", "必定",
        "一定",
        "必然",
        "所有",
        "完全",
        "普遍",
        "always",
        "all users",
        "universally",
        "certainly",
    )
    limited = (
        "本次会话", "本次交互", "仅限", "未使用", "仅适用", "不能证明",
        "不足以证明", "this conversation", "only eligible", "unused orders",
        "小规模",
        "初步",
        "试点",
        "单个",
        "有限",
        "可能",
        "small sample",
        "preliminary",
        "pilot",
        "limited",
        "may",
    )
    claim_lower = claim.lower()
    excerpt_lower = excerpt.lower()
    return any(word in claim_lower for word in universal) and any(
        word in excerpt_lower for word in limited
    )


def _duration_mismatches(claim: str, excerpt: str) -> list[str]:
    """Compare explicit same-field duration assertions, not arbitrary numbers.

    Bounded rule: labelled deadlines/durations, integer Arabic or Chinese
    values below 100, and hours/days/weeks. Dates, ranges and unrelated
    subjects are not inferred. This is not general semantic contradiction.
    """
    def quantities(text: str) -> dict[str, set[int]]:
        values: dict[str, set[int]] = {}
        for match in _DURATION_PATTERN.finditer(text):
            number = _small_integer(match["number"])
            if number is None:
                continue
            hours = number * {"小时": 1, "天": 24, "周": 168}[match["unit"]]
            values.setdefault(match["field"], set()).add(hours)
        return values

    left, right = quantities(claim), quantities(excerpt)
    return [f"duration-mismatch:{field}" for field in sorted(left.keys() | right.keys())
            if len(left.get(field, set()) | right.get(field, set())) > 1]


def _small_integer(text: str) -> int | None:
    if text.isdigit():
        value = int(text)
        return value if value < 100 else None
    digits = {word: value for value, word in enumerate("零一二三四五六七八九")}
    digits["两"] = 2
    if text in digits:
        return digits[text]
    if text.count("十") == 1:
        tens, ones = text.split("十")
        if (not tens or tens in digits) and (not ones or ones in digits):
            return (digits[tens] if tens else 1) * 10 + (digits[ones] if ones else 0)
    return None
