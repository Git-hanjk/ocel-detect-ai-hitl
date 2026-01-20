from __future__ import annotations

from datetime import datetime
import uuid
from typing import Any, Dict, Iterable, List, Optional

Candidate = Dict[str, Any]

approval_complete_activities = [
    "ApprovePurchaseRequisition",
    "DelegatePurchaseRequisitionApproval",
]


def new_candidate_id() -> str:
    return str(uuid.uuid4())


def parse_ts(ts: str) -> datetime:
    if ts.endswith("Z"):
        ts = ts[:-1] + "+00:00"
    return datetime.fromisoformat(ts)


def hours_between(start: datetime, end: datetime) -> float:
    return (end - start).total_seconds() / 3600.0


def percentile(values: Iterable[float], p: float) -> Optional[float]:
    vals = sorted(values)
    if not vals:
        return None
    if p <= 0:
        return vals[0]
    if p >= 1:
        return vals[-1]
    n = len(vals)
    pos = p * (n - 1)
    lower = int(pos)
    upper = min(lower + 1, n - 1)
    if lower == upper:
        return vals[lower]
    frac = pos - lower
    return vals[lower] * (1 - frac) + vals[upper] * frac


def pick_approval_complete(
    events: Dict[str, Tuple[str, str]]
) -> Optional[Tuple[str, str, str]]:
    choices = []
    for activity, payload in events.items():
        if activity in approval_complete_activities and payload:
            event_id, ts = payload
            choices.append((event_id, ts, activity))
    if not choices:
        return None
    return min(choices, key=lambda item: parse_ts(item[1]))


def print_summary(detector_name: str, candidates: List[Candidate], feature_keys: List[str]) -> None:
    print(f"[{detector_name}] candidates: {len(candidates)}")
    for cand in candidates[:5]:
        feats = ", ".join(f"{k}={cand['features'].get(k)}" for k in feature_keys)
        anchor = f"{cand['anchor_object_id']} ({cand['anchor_object_type']})"
        print(f"  - {cand['candidate_id']} | {cand['type']} | {anchor} | {feats}")
