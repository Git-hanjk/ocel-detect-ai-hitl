from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from .common import (
    Candidate,
    approval_complete_activities,
    hours_between,
    new_candidate_id,
    parse_ts,
    percentile,
    pick_approval_complete,
    print_summary,
)


def _pick_earliest(current: Optional[Tuple[str, str]], event_id: str, ts: str) -> Tuple[str, str]:
    if current is None:
        return event_id, ts
    if parse_ts(ts) < parse_ts(current[1]):
        return event_id, ts
    return current


def run(conn, config) -> List[Candidate]:
    rows = conn.execute(
        """
        SELECT
            o.ocel_id,
            o.ocel_type,
            e.activity,
            e.event_id,
            e.ts
        FROM object o
        JOIN derived_event_object deo ON deo.object_id = o.ocel_id
        JOIN v_events_unified e ON e.event_id = deo.event_id
        WHERE o.ocel_type IN ('purchase_requisition', 'purchase_order')
          AND e.activity IN (
            'CreatePurchaseRequisition',
            'ApprovePurchaseRequisition',
            'DelegatePurchaseRequisitionApproval',
            'CreatePurchaseOrder',
            'ApprovePurchaseOrder'
          )
        """
    ).fetchall()

    delegate_rows = conn.execute(
        """
        SELECT
            deo.object_id,
            e.event_id,
            e.ts
        FROM derived_event_object deo
        JOIN v_events_unified e ON e.event_id = deo.event_id
        JOIN object o ON o.ocel_id = deo.object_id
        WHERE o.ocel_type = 'purchase_requisition'
          AND e.activity = 'DelegatePurchaseRequisitionApproval'
        """
    ).fetchall()
    delegate_events: Dict[str, List[Tuple[str, str]]] = {}
    for obj_id, event_id, ts in delegate_rows:
        delegate_events.setdefault(obj_id, []).append((event_id, ts))

    per_object: Dict[str, Dict[str, Optional[Tuple[str, str]]]] = {}
    object_types: Dict[str, str] = {}
    for obj_id, obj_type, activity, event_id, ts in rows:
        object_types[obj_id] = obj_type
        state = per_object.setdefault(
            obj_id,
            {"create": None, "approve": None, "delegate": None},
        )
        if activity in ("CreatePurchaseRequisition", "CreatePurchaseOrder"):
            state["create"] = _pick_earliest(state["create"], event_id, ts)
        elif activity in ("ApprovePurchaseRequisition", "ApprovePurchaseOrder"):
            state["approve"] = _pick_earliest(state["approve"], event_id, ts)
        elif activity == "DelegatePurchaseRequisitionApproval":
            state["delegate"] = _pick_earliest(state["delegate"], event_id, ts)

    lead_times_by_type: Dict[str, List[float]] = {"purchase_requisition": [], "purchase_order": []}
    for obj_id, state in per_object.items():
        create = state["create"]
        approve = state["approve"]
        delegate = state["delegate"]
        approval = None
        if object_types[obj_id] == "purchase_requisition":
            approval = pick_approval_complete(
                {
                    "ApprovePurchaseRequisition": approve,
                    "DelegatePurchaseRequisitionApproval": delegate,
                }
            )
        elif approve:
            approval = (approve[0], approve[1], "ApprovePurchaseOrder")
        if not create or not approval:
            continue
        lead_time = hours_between(parse_ts(create[1]), parse_ts(approval[1]))
        lead_times_by_type[object_types[obj_id]].append(lead_time)

    p = config.get("thresholds", {}).get("lengthy_approval", {}).get("p", 0.95)
    thresholds = {
        obj_type: percentile(values, p) for obj_type, values in lead_times_by_type.items()
    }

    candidates: List[Candidate] = []
    for obj_id, state in per_object.items():
        obj_type = object_types.get(obj_id)
        create = state["create"]
        approve = state["approve"]
        delegate = state["delegate"]
        approval = None
        if obj_type == "purchase_requisition":
            approval = pick_approval_complete(
                {
                    "ApprovePurchaseRequisition": approve,
                    "DelegatePurchaseRequisitionApproval": delegate,
                }
            )
        elif approve:
            approval = (approve[0], approve[1], "ApprovePurchaseOrder")
        if not create or not approval:
            continue
        threshold = thresholds.get(obj_type)
        if threshold is None:
            continue
        lead_time_hours = hours_between(parse_ts(create[1]), parse_ts(approval[1]))
        if lead_time_hours <= threshold:
            continue
        evidence_event_ids = [create[0], approval[0]]
        if obj_type == "purchase_requisition":
            delegates = []
            for event_id, ts in delegate_events.get(obj_id, []):
                if parse_ts(create[1]) <= parse_ts(ts) <= parse_ts(approval[1]):
                    delegates.append((event_id, ts))
            if delegates:
                delegates_sorted = sorted(delegates, key=lambda item: parse_ts(item[1]))
                evidence_event_ids.extend([event_id for event_id, _ in delegates_sorted])

        candidate: Candidate = {
            "candidate_id": new_candidate_id(),
            "type": "lengthy_approval_pr" if obj_type == "purchase_requisition" else "lengthy_approval_po",
            "anchor_object_id": obj_id,
            "anchor_object_type": obj_type,
            "evidence_event_ids": evidence_event_ids,
            "evidence_object_ids": [obj_id],
            "features": {
                "lead_time_hours": lead_time_hours,
                "threshold_hours": threshold,
                "create_event_id": create[0],
                "approval_event_id": approval[0],
                "approval_event_activity": approval[2],
            },
        }
        candidates.append(candidate)

    print_summary("lengthy_approval", candidates, ["lead_time_hours", "threshold_hours"])
    return candidates
