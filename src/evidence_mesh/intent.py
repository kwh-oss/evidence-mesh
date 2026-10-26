"""Conservative intent and claim analysis for the generalized Leader."""

from __future__ import annotations

import re
from typing import Any

from .contracts import AuditRequest, MISSING_SOURCE_EXCERPT


SUPPORTED_TASK_TYPES = {
    "auto",
    "intent_and_claims",
    "answer_grounding_check",
    "claim_boundary_check",
    "cross_text_conflict",
    "safe_rewrite",
    "full_preflight",
}


def analyze_request(request: AuditRequest) -> dict[str, Any]:
    """Return traceable analysis without adding facts absent from the input."""

    task_type = _resolve_task_type(request)
    claims = _atomic_claims(request.claim_text)
    ambiguities = _ambiguities(request.claim_text)
    missing_information: list[str] = []
    if request.source_excerpt == MISSING_SOURCE_EXCERPT:
        missing_information.append("supporting context or evidence")

    return {
        "task_type": task_type,
        "intent": {
            "speech_act": _speech_act(request.claim_text),
            "goal": request.goal or "unspecified",
            "audience": request.audience or "unspecified",
            "ambiguities": ambiguities,
        },
        "atomic_claims": claims,
        "missing_information": missing_information,
        "clarification_required": False,
    }


def safe_utterance(claim_text: str, decision: str) -> str:
    """Provide a deterministic boundary-preserving delivery sentence."""

    if decision == "supported":
        return claim_text
    if decision == "conflicting":
        return f"现有材料对以下表述存在冲突，暂不能作出确定判断：{claim_text}"
    if decision == "no-evidence":
        return f"现有材料不足以支持以下表述：{claim_text}"
    if decision == "incomplete":
        return f"核验信息尚不完整，暂不能确认以下表述：{claim_text}"
    return f"以下表述仍需复核，尚不能确认有证据支持：{claim_text}"


def _resolve_task_type(request: AuditRequest) -> str:
    declared = request.task_type.strip().lower().replace("-", "_")
    if declared in SUPPORTED_TASK_TYPES and declared != "auto":
        return declared

    combined = " ".join(
        (request.claim_text, request.source_excerpt, request.goal)
    ).lower()
    if any(word in combined for word in ("改写", "润色", "措辞", "rewrite", "rephrase")):
        return "safe_rewrite"
    if any(
        word in combined
        for word in ("材料a", "材料 a", "材料b", "材料 b", "比较两", "冲突", "contradict")
    ):
        return "cross_text_conflict"
    if any(word in combined for word in ("完整审计", "交付前", "preflight", "全面核验")):
        return "full_preflight"
    if request.source_excerpt == MISSING_SOURCE_EXCERPT:
        return "intent_and_claims"
    if any(word in request.goal.lower() for word in ("报告", "结论", "分析", "research", "report")):
        return "claim_boundary_check"
    return "answer_grounding_check"


def _speech_act(text: str) -> str:
    normalized = text.strip().lower()
    if normalized.endswith(("?", "？")) or normalized.startswith(
        ("是否", "为什么", "如何", "what", "why", "how", "is ", "are ")
    ):
        return "question"
    if normalized.startswith(("请", "帮我", "请你", "please")):
        return "request"
    if any(word in normalized for word in ("应该", "建议", "应当", "should", "recommend")):
        return "recommendation"
    return "claim"


def _atomic_claims(text: str) -> list[dict[str, str]]:
    # Split only on strong separators. Full stops are intentionally retained
    # because clause-level sentence splitting can silently change meaning.
    spans = [part.strip() for part in re.split(r"[；;\n]+", text) if part.strip()]
    return [
        {
            "claim_id": f"claim-{index}",
            "original_span": span,
            "normalized_claim": span,
            "claim_type": _claim_type(span),
            "checkability": "requires-evidence",
        }
        for index, span in enumerate(spans, start=1)
    ]


def _claim_type(text: str) -> str:
    normalized = text.lower()
    if any(word in normalized for word in ("导致", "引起", "造成", "cause", "result in")):
        return "causal"
    if any(word in normalized for word in ("高于", "低于", "优于", "相比", "than", "compared")):
        return "comparative"
    if any(word in normalized for word in ("将会", "预计", "预测", "will", "predict")):
        return "predictive"
    if any(word in normalized for word in ("应该", "应当", "建议", "should", "recommend")):
        return "normative"
    if re.search(r"\d", normalized):
        return "quantitative"
    return "factual"


def _ambiguities(text: str) -> list[str]:
    stripped = text.strip()
    indicators: list[str] = []
    if len(stripped) < 4:
        indicators.append("expression-is-too-short")
    if re.search(r"(?:这个|那个|它|他们|其)(?:是|会|可能|导致|提高|降低)", stripped):
        indicators.append("possibly-unclear-reference")
    return indicators
