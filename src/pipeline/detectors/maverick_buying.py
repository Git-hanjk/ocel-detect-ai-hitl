from __future__ import annotations

from typing import Dict, List, Optional, Set, Tuple

from .common import (
    Candidate,
    approval_complete_activities,
    new_candidate_id,
    parse_ts,
    print_summary,
)


def _add_edge(adj: Dict[str, Set[str]], a: str, b: str) -> None:
    if a == b:
        return
    adj.setdefault(a, set()).add(b)
    adj.setdefault(b, set()).add(a)


def run(conn, config) -> List[Candidate]:
    object_types = dict(conn.execute("SELECT ocel_id, ocel_type FROM object").fetchall())

    adj: Dict[str, Set[str]] = {}
    po_to_q: Dict[str, Set[str]] = {}
    q_to_pr: Dict[str, Set[str]] = {}
    po_to_pr_direct: Dict[str, Set[str]] = {}
    for src_id, tgt_id in conn.execute(
        "SELECT ocel_source_id, ocel_target_id FROM object_object"
    ).fetchall():
        _add_edge(adj, src_id, tgt_id)
        src_type = object_types.get(src_id)
        tgt_type = object_types.get(tgt_id)
        if src_type == "purchase_order" and tgt_type == "quotation":
            po_to_q.setdefault(src_id, set()).add(tgt_id)
        if tgt_type == "purchase_order" and src_type == "quotation":
            po_to_q.setdefault(tgt_id, set()).add(src_id)
        if src_type == "quotation" and tgt_type == "purchase_requisition":
            q_to_pr.setdefault(src_id, set()).add(tgt_id)
        if tgt_type == "quotation" and src_type == "purchase_requisition":
            q_to_pr.setdefault(tgt_id, set()).add(src_id)
        if src_type == "purchase_order" and tgt_type == "purchase_requisition":
            po_to_pr_direct.setdefault(src_id, set()).add(tgt_id)
        if tgt_type == "purchase_order" and src_type == "purchase_requisition":
            po_to_pr_direct.setdefault(tgt_id, set()).add(src_id)

    rows = conn.execute(
        """
        SELECT deo.event_id, deo.object_id
        FROM derived_event_object deo
        JOIN object o ON o.ocel_id = deo.object_id
        WHERE o.ocel_type IN ('purchase_order', 'purchase_requisition', 'quotation')
        """
    ).fetchall()
    by_event: Dict[str, List[str]] = {}
    for event_id, obj_id in rows:
        by_event.setdefault(event_id, []).append(obj_id)
    for obj_ids in by_event.values():
        for i in range(len(obj_ids)):
            for j in range(i + 1, len(obj_ids)):
                _add_edge(adj, obj_ids[i], obj_ids[j])
                a = obj_ids[i]
                b = obj_ids[j]
                if object_types.get(a) == "purchase_order" and object_types.get(b) == "purchase_requisition":
                    po_to_pr_direct.setdefault(a, set()).add(b)
                if object_types.get(b) == "purchase_order" and object_types.get(a) == "purchase_requisition":
                    po_to_pr_direct.setdefault(b, set()).add(a)

    pr_approve: Dict[str, Tuple[str, str]] = {}
    rows = conn.execute(
        """
        SELECT deo.object_id, e.event_id, e.ts
        FROM derived_event_object deo
        JOIN v_events_unified e ON e.event_id = deo.event_id
        JOIN object o ON o.ocel_id = deo.object_id
        WHERE o.ocel_type = 'purchase_requisition'
          AND e.activity IN ('ApprovePurchaseRequisition','DelegatePurchaseRequisitionApproval')
        """
    ).fetchall()
    for pr_id, event_id, ts in rows:
        current = pr_approve.get(pr_id)
        if current is None or parse_ts(ts) < parse_ts(current[1]):
            pr_approve[pr_id] = (event_id, ts)

    pr_create: Dict[str, Tuple[str, str]] = {}
    rows = conn.execute(
        """
        SELECT deo.object_id, e.event_id, e.ts
        FROM derived_event_object deo
        JOIN v_events_unified e ON e.event_id = deo.event_id
        JOIN object o ON o.ocel_id = deo.object_id
        WHERE o.ocel_type = 'purchase_requisition'
          AND e.activity = 'CreatePurchaseRequisition'
        """
    ).fetchall()
    for pr_id, event_id, ts in rows:
        current = pr_create.get(pr_id)
        if current is None or parse_ts(ts) < parse_ts(current[1]):
            pr_create[pr_id] = (event_id, ts)

    pr_rfq: Dict[str, Tuple[str, str]] = {}
    rows = conn.execute(
        """
        SELECT deo.object_id, e.event_id, e.ts
        FROM derived_event_object deo
        JOIN v_events_unified e ON e.event_id = deo.event_id
        JOIN object o ON o.ocel_id = deo.object_id
        WHERE o.ocel_type = 'purchase_requisition'
          AND e.activity = 'CreateRequestforQuotation'
        """
    ).fetchall()
    for pr_id, event_id, ts in rows:
        current = pr_rfq.get(pr_id)
        if current is None or parse_ts(ts) < parse_ts(current[1]):
            pr_rfq[pr_id] = (event_id, ts)

    po_create: Dict[str, Tuple[str, str]] = {}
    rows = conn.execute(
        """
        SELECT deo.object_id, e.event_id, e.ts
        FROM derived_event_object deo
        JOIN v_events_unified e ON e.event_id = deo.event_id
        JOIN object o ON o.ocel_id = deo.object_id
        WHERE o.ocel_type = 'purchase_order'
          AND e.activity = 'CreatePurchaseOrder'
        """
    ).fetchall()
    for po_id, event_id, ts in rows:
        current = po_create.get(po_id)
        if current is None or parse_ts(ts) < parse_ts(current[1]):
            po_create[po_id] = (event_id, ts)

    candidates: List[Candidate] = []
    for po_id, po_create_evt in po_create.items():
        pr_ids = set(po_to_pr_direct.get(po_id, set()))
        quotation_ids = po_to_q.get(po_id, set())
        for q_id in quotation_ids:
            pr_ids.update(q_to_pr.get(q_id, set()))

        pr_ids = sorted(pr_ids)
        has_pr = bool(pr_ids)
        pr_id_used: Optional[str] = None
        pr_approve_evt: Optional[Tuple[str, str]] = None
        if has_pr:
            pr_id_used = pr_ids[0]
            for pr_id in pr_ids:
                if pr_id in pr_approve:
                    if pr_approve_evt is None or parse_ts(pr_approve[pr_id][1]) < parse_ts(
                        pr_approve_evt[1]
                    ):
                        pr_id_used = pr_id
                        pr_approve_evt = pr_approve[pr_id]

        po_create_dt = parse_ts(po_create_evt[1])
        pr_create_ts = None
        pr_create_event_id = None
        rfq_ts = None
        rfq_event_id = None
        if pr_ids:
            best_pr_create = None
            best_rfq = None
            for pr_id in pr_ids:
                if pr_id in pr_create:
                    event_id, ts = pr_create[pr_id]
                    if best_pr_create is None or parse_ts(ts) < parse_ts(best_pr_create[1]):
                        best_pr_create = (event_id, ts)
                if pr_id in pr_rfq:
                    event_id, ts = pr_rfq[pr_id]
                    if best_rfq is None or parse_ts(ts) < parse_ts(best_rfq[1]):
                        best_rfq = (event_id, ts)
            if best_pr_create is not None:
                pr_create_event_id, pr_create_ts = best_pr_create
            if best_rfq is not None:
                rfq_event_id, rfq_ts = best_rfq

        pr_approve_ts = pr_approve_evt[1] if pr_approve_evt is not None else None
        maverick_reason = None
        approval_gap_hours = None
        if not has_pr:
            maverick_reason = "no_pr_found"
        elif pr_create_event_id is None and rfq_event_id is not None:
            maverick_reason = "missing_pr_create"
        elif pr_approve_evt is None:
            maverick_reason = "missing_pr_approval"

        if maverick_reason is None:
            continue

        evidence_event_ids = [po_create_evt[0]]
        if has_pr and pr_create_event_id is not None:
            evidence_event_ids.append(pr_create_event_id)
        if maverick_reason == "missing_pr_create" and rfq_event_id is not None:
            evidence_event_ids.append(rfq_event_id)
        if pr_approve_evt is not None:
            evidence_event_ids.append(pr_approve_evt[0])
        evidence_object_ids = [po_id]
        if pr_id_used is not None:
            evidence_object_ids.append(pr_id_used)

        missing_events: List[str] = []
        if has_pr and pr_create_event_id is None:
            missing_events.append("CreatePurchaseRequisition")
        if has_pr and pr_approve_evt is None:
            missing_events.extend(approval_complete_activities)

        candidate: Candidate = {
            "candidate_id": new_candidate_id(),
            "type": "maverick_buying",
            "anchor_object_id": po_id,
            "anchor_object_type": "purchase_order",
            "evidence_event_ids": evidence_event_ids,
            "evidence_object_ids": evidence_object_ids,
            "features": {
                "po_create_ts": po_create_evt[1],
                "pr_create_ts": pr_create_ts,
                "pr_approve_ts": pr_approve_ts,
                "rfq_ts": rfq_ts,
                "has_pr": has_pr,
                "approval_gap_hours": approval_gap_hours,
                "maverick_reason": maverick_reason,
            },
        }
        if missing_events:
            candidate["features"]["missing_events"] = missing_events
        candidates.append(candidate)

    print_summary("maverick_buying", candidates, ["has_pr", "approval_gap_hours"])
    return candidates
