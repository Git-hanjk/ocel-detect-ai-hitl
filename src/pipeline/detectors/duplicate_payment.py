from __future__ import annotations

from typing import Dict, List, Tuple

from .common import Candidate, new_candidate_id, parse_ts, print_summary


def run(conn, config) -> List[Candidate]:
    rows = conn.execute(
        """
        SELECT
            deo.object_id AS invoice_id,
            o.ocel_type AS object_type,
            e.event_id,
            e.ts
        FROM derived_event_object deo
        JOIN v_events_unified e ON e.event_id = deo.event_id
        JOIN object o ON o.ocel_id = deo.object_id
        WHERE e.activity = 'ExecutePayment'
          AND lower(o.ocel_type) = 'invoice receipt'
        """
    ).fetchall()

    grouped: Dict[str, Dict[str, List[Tuple[str, str]]]] = {}
    object_types: Dict[str, str] = {}
    for invoice_id, object_type, event_id, ts in rows:
        grouped.setdefault(invoice_id, {"events": []})["events"].append((event_id, ts))
        object_types[invoice_id] = object_type

    candidates: List[Candidate] = []
    for invoice_id, payload in grouped.items():
        events = payload["events"]
        if len(events) < 2:
            continue
        events_sorted = sorted(events, key=lambda x: parse_ts(x[1]))
        payment_event_ids = [e_id for e_id, _ in events_sorted]
        payment_ts_list = [ts for _, ts in events_sorted]
        candidate: Candidate = {
            "candidate_id": new_candidate_id(),
            "type": "duplicate_payment",
            "anchor_object_id": invoice_id,
            "anchor_object_type": object_types.get(invoice_id, "invoice receipt"),
            "evidence_event_ids": payment_event_ids,
            "evidence_object_ids": [invoice_id],
            "features": {
                "payment_count": len(events_sorted),
                "payment_ts_list": payment_ts_list,
                "payment_event_ids": payment_event_ids,
            },
        }
        candidates.append(candidate)

    print_summary("duplicate_payment", candidates, ["payment_count"])
    return candidates
