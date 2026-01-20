from __future__ import annotations

from typing import Any, Dict, Iterable, Tuple


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    if value < low:
        return low
    if value > high:
        return high
    return value


def _evidence_quality(candidate: Dict[str, Any]) -> float:
    event_ids = candidate.get("evidence_event_ids") or []
    object_ids = candidate.get("evidence_object_ids") or []
    if event_ids and object_ids:
        return 1.0
    if event_ids or object_ids:
        return 0.6
    return 0.2


def _score_components(candidate: Dict[str, Any]) -> Tuple[float, float, float, float]:
    ctype = candidate.get("type")
    features = candidate.get("features", {})

    S = 0.5
    R = 0.5
    I = 0.5
    Q = _evidence_quality(candidate)

    if ctype == "duplicate_payment":
        count = float(features.get("payment_count") or 1)
        S = _clamp(0.4 + 0.2 * (count - 1))
        R = _clamp(0.3 + 0.1 * count)
        I = _clamp(0.4 + 0.15 * (count - 1))
    elif ctype in ("lengthy_approval_pr", "lengthy_approval_po"):
        lead = features.get("lead_time_hours")
        threshold = features.get("threshold_hours")
        ratio = 1.0
        if isinstance(lead, (int, float)) and isinstance(threshold, (int, float)) and threshold > 0:
            ratio = lead / threshold
        S = _clamp(ratio / 2.0)
        R = _clamp(0.5 + 0.3 * (ratio - 1))
        I = _clamp(0.3 + 0.2 * ratio)
    elif ctype == "maverick_buying":
        reason = features.get("maverick_reason")
        base = {
            "no_pr_found": 0.8,
            "missing_pr_approval": 0.7,
            "missing_pr_create": 0.65,
            "po_before_pr_approval": 0.6,
        }.get(reason, 0.5)
        S = base
        R = _clamp(base - 0.1)
        I = _clamp(base - 0.2)
        gap = features.get("approval_gap_hours")
        if reason == "po_before_pr_approval" and isinstance(gap, (int, float)):
            S = _clamp(base + min(0.3, gap / 72.0 * 0.3))
            I = _clamp(I + min(0.2, gap / 72.0 * 0.2))
        if reason == "missing_pr_create":
            I = _clamp(I + 0.05)
        if features.get("pr_create_ts") is None and features.get("rfq_ts") is None:
            Q = _clamp(Q - 0.3)

    return S, R, I, Q


def score_candidate(candidate: Dict[str, Any], config: Dict[str, Any]) -> float:
    weights = config.get("weights", {})
    wS = float(weights.get("wS", 0.45))
    wR = float(weights.get("wR", 0.20))
    wI = float(weights.get("wI", 0.25))
    wQ = float(weights.get("wQ", 0.10))

    S, R, I, Q = _score_components(candidate)
    base_conf = _clamp(wS * S + wR * R + wI * I + wQ * Q)

    features = candidate.setdefault("features", {})
    features["S"] = S
    features["R"] = R
    features["I"] = I
    features["Q"] = Q
    candidate["base_conf"] = base_conf
    return base_conf


def score_candidates(candidates: Iterable[Dict[str, Any]], config: Dict[str, Any]) -> None:
    for candidate in candidates:
        score_candidate(candidate, config)
