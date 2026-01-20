from __future__ import annotations

from typing import Any, Dict, Optional


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    if value < low:
        return low
    if value > high:
        return high
    return value


def compute_severity(candidate: Dict[str, Any]) -> Optional[float]:
    ctype = candidate.get("type")
    features = candidate.get("features") or {}

    if ctype == "duplicate_payment":
        count = features.get("payment_count")
        if not isinstance(count, (int, float)):
            return None
        return _clamp((float(count) - 1.0) / 4.0)

    if ctype in ("lengthy_approval_pr", "lengthy_approval_po"):
        lead = features.get("lead_time_hours")
        threshold = features.get("threshold_hours")
        if not isinstance(lead, (int, float)) or not isinstance(threshold, (int, float)):
            return None
        if threshold <= 0:
            return None
        excess_ratio = max(0.0, (float(lead) - float(threshold)) / float(threshold))
        return _clamp(excess_ratio / 3.0)

    if ctype == "maverick_buying":
        reason = features.get("maverick_reason")
        base = {
            "missing_pr_create": 0.7,
            "missing_pr_approval": 0.6,
            "po_before_pr_approval": 0.9,
            "no_pr_found": 0.8,
        }.get(reason, 0.6)
        gap = features.get("approval_gap_hours")
        if reason == "po_before_pr_approval" and isinstance(gap, (int, float)):
            base = min(1.0, base + min(0.1, float(gap) / 72.0 * 0.1))
        missing_events = features.get("missing_events") or []
        if missing_events:
            base = max(0.0, base - 0.1)
        return _clamp(base)

    return None


def compute_priority_score(final_conf: Optional[float], severity: Optional[float]) -> Optional[float]:
    if severity is None:
        return None
    if final_conf is None:
        return None
    if not isinstance(final_conf, (int, float)):
        return None
    return float(severity) * float(final_conf)
