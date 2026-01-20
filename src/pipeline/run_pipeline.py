from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

import yaml

from src.app.core.db import get_engine, init_db, resolve_db_path, session_scope
from src.app.core.models import Candidate, CandidateEvidence
from src.pipeline.detectors.duplicate_payment import run as run_duplicate_payment
from src.pipeline.detectors.lengthy_approval import run as run_lengthy_approval
from src.pipeline.detectors.maverick_buying import run as run_maverick_buying
from src.pipeline.ocel.derived_event_object import create_derived_event_object
from src.pipeline.scoring.base_confidence import score_candidates
from src.pipeline.severity import compute_priority_score, compute_severity

DETERMINISTIC_NAMESPACE = uuid.UUID("6f2efcf2-2dc4-4e34-a25a-5d7f0f4df9b3")


def load_config(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def ensure_unified_events(conn: sqlite3.Connection) -> None:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='view' AND name='v_events_unified'"
    ).fetchone()
    if row:
        return
    sql_path = os.path.join(os.path.dirname(__file__), "ocel", "unify_events.sql")
    with open(sql_path, "r", encoding="utf-8") as f:
        conn.executescript(f.read())
    conn.commit()


def ensure_derived_event_object(conn: sqlite3.Connection, serving_path: str) -> None:
    create_derived_event_object(conn)
    serving_conn = sqlite3.connect(serving_path)
    try:
        create_derived_event_object(conn, output_conn=serving_conn)
    finally:
        serving_conn.close()


def deterministic_candidate_id(candidate: Dict[str, Any]) -> str:
    payload = {
        "type": candidate.get("type"),
        "anchor": candidate.get("anchor_object_id"),
        "evidence": sorted(candidate.get("evidence_event_ids") or []),
    }
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=True)
    return str(uuid.uuid5(DETERMINISTIC_NAMESPACE, raw))


def build_timeline(
    conn: sqlite3.Connection, evidence_event_ids: List[str]
) -> List[Dict[str, Any]]:
    if not evidence_event_ids:
        return []
    placeholders = ",".join("?" for _ in evidence_event_ids)
    rows = conn.execute(
        f"""
        SELECT e.event_id, e.activity, e.ts, e.resource, e.lifecycle, deo.object_id
        FROM v_events_unified e
        LEFT JOIN derived_event_object deo ON e.event_id = deo.event_id
        WHERE e.event_id IN ({placeholders})
        """,
        evidence_event_ids,
    ).fetchall()
    grouped: Dict[str, Dict[str, Any]] = {}
    for event_id, activity, ts, resource, lifecycle, object_id in rows:
        payload = grouped.setdefault(
            event_id,
            {
                "event_id": event_id,
                "activity": activity,
                "ts": ts,
                "resource": resource,
                "lifecycle": lifecycle,
                "linked_object_ids": [],
            },
        )
        if object_id and object_id not in payload["linked_object_ids"]:
            payload["linked_object_ids"].append(object_id)
    timeline = list(grouped.values())
    timeline.sort(key=lambda x: x["ts"] or "")
    return timeline


def build_subgraph(
    conn: sqlite3.Connection,
    candidate_type: str,
    anchor_object_id: str,
    evidence_event_ids: List[str],
) -> Dict[str, Any]:
    object_types = dict(conn.execute("SELECT ocel_id, ocel_type FROM object").fetchall())
    nodes: List[Dict[str, Any]] = []
    edges: List[Dict[str, Any]] = []
    object_ids = {anchor_object_id}
    root_objects = {anchor_object_id}

    if evidence_event_ids:
        placeholders = ",".join("?" for _ in evidence_event_ids)
        rows = conn.execute(
            f"""
            SELECT deo.event_id, deo.object_id, deo.qualifier
            FROM derived_event_object deo
            WHERE deo.event_id IN ({placeholders})
            """,
            evidence_event_ids,
        ).fetchall()
        for event_id, obj_id, qualifier in rows:
            if obj_id:
                object_ids.add(obj_id)
                root_objects.add(obj_id)
            edges.append(
                {
                    "source": event_id,
                    "target": obj_id,
                    "type": "E2O",
                    "qualifier": qualifier,
                }
            )

        for event_id, activity in conn.execute(
            f"SELECT event_id, activity FROM v_events_unified WHERE event_id IN ({placeholders})",
            evidence_event_ids,
        ).fetchall():
            nodes.append({"id": event_id, "type": "Event", "activity": activity})

    if candidate_type == "lengthy_approval_pr":
        rows = conn.execute(
            """
            SELECT ocel_source_id, ocel_target_id, ocel_qualifier
            FROM object_object
            WHERE ocel_source_id = ? OR ocel_target_id = ?
            """,
            (anchor_object_id, anchor_object_id),
        ).fetchall()
        for src_id, tgt_id, qualifier in rows:
            other = tgt_id if src_id == anchor_object_id else src_id
            if object_types.get(other) != "quotation":
                continue
            object_ids.add(other)
            edges.append(
                {
                    "source": src_id,
                    "target": tgt_id,
                    "type": "O2O",
                    "qualifier": qualifier,
                }
            )
    elif candidate_type == "lengthy_approval_po":
        rows = conn.execute(
            """
            SELECT ocel_source_id, ocel_target_id, ocel_qualifier
            FROM object_object
            WHERE ocel_source_id = ? OR ocel_target_id = ?
            """,
            (anchor_object_id, anchor_object_id),
        ).fetchall()
        for src_id, tgt_id, qualifier in rows:
            other = tgt_id if src_id == anchor_object_id else src_id
            if object_types.get(other) != "material":
                continue
            object_ids.add(other)
            edges.append(
                {
                    "source": src_id,
                    "target": tgt_id,
                    "type": "O2O",
                    "qualifier": qualifier,
                }
            )
    elif candidate_type == "duplicate_payment":
        obj_placeholders = ",".join("?" for _ in root_objects)
        rows = conn.execute(
            f"""
            SELECT ocel_source_id, ocel_target_id, ocel_qualifier
            FROM object_object
            WHERE ocel_source_id IN ({obj_placeholders})
               OR ocel_target_id IN ({obj_placeholders})
            """,
            list(root_objects) + list(root_objects),
        ).fetchall()
        for src_id, tgt_id, qualifier in rows:
            if src_id not in root_objects and tgt_id not in root_objects:
                continue
            object_ids.add(src_id)
            object_ids.add(tgt_id)
            edges.append(
                {
                    "source": src_id,
                    "target": tgt_id,
                    "type": "O2O",
                    "qualifier": qualifier,
                }
            )
    elif candidate_type == "maverick_buying":
        obj_placeholders = ",".join("?" for _ in root_objects)
        rows = conn.execute(
            f"""
            SELECT ocel_source_id, ocel_target_id, ocel_qualifier
            FROM object_object
            WHERE ocel_source_id IN ({obj_placeholders})
               OR ocel_target_id IN ({obj_placeholders})
            """,
            list(root_objects) + list(root_objects),
        ).fetchall()
        path_objects = {anchor_object_id}
        pr_ids = [obj for obj in root_objects if object_types.get(obj) == "purchase_requisition"]
        if pr_ids:
            path_objects.update(pr_ids)
        else:
            quotation_ids = {obj for obj in root_objects if object_types.get(obj) == "quotation"}
            for src_id, tgt_id, _ in rows:
                if src_id == anchor_object_id and object_types.get(tgt_id) == "quotation":
                    quotation_ids.add(tgt_id)
                if tgt_id == anchor_object_id and object_types.get(src_id) == "quotation":
                    quotation_ids.add(src_id)
            path_objects.update(quotation_ids)
            for src_id, tgt_id, _ in rows:
                if src_id in quotation_ids and object_types.get(tgt_id) == "purchase_requisition":
                    path_objects.add(tgt_id)
                if tgt_id in quotation_ids and object_types.get(src_id) == "purchase_requisition":
                    path_objects.add(src_id)
        for src_id, tgt_id, qualifier in rows:
            if src_id in path_objects and tgt_id in path_objects:
                object_ids.add(src_id)
                object_ids.add(tgt_id)
                edges.append(
                    {
                        "source": src_id,
                        "target": tgt_id,
                        "type": "O2O",
                        "qualifier": qualifier,
                    }
                )

    if candidate_type == "maverick_buying":
        object_ids = set(path_objects)
        edges = [
            edge
            for edge in edges
            if edge["type"] != "E2O" or edge["target"] in object_ids
        ]

    for obj_id in object_ids:
        nodes.append(
            {
                "id": obj_id,
                "type": "Object",
                "object_type": object_types.get(obj_id),
            }
        )

    return {"nodes": nodes, "edges": edges}


def upsert_candidates(
    engine,
    candidates: Iterable[Dict[str, Any]],
    conn: sqlite3.Connection,
    run_id: str,
) -> None:
    now = datetime.now(timezone.utc)
    with session_scope(engine) as session:
        for candidate in candidates:
            candidate_id = deterministic_candidate_id(candidate)
            candidate["candidate_id"] = candidate_id
            base_conf = candidate.get("base_conf", 0.0)
            final_conf = candidate.get("final_conf", base_conf)
            severity = compute_severity(candidate)
            priority_score = compute_priority_score(final_conf, severity)

            db_candidate = Candidate(
                candidate_id=candidate_id,
                run_id=run_id,
                type=candidate["type"],
                anchor_object_id=candidate["anchor_object_id"],
                anchor_object_type=candidate["anchor_object_type"],
                base_conf=base_conf,
                final_conf=final_conf,
                severity=severity,
                priority_score=priority_score,
                status=candidate.get("status", "open"),
                updated_at=now,
                created_at=candidate.get("created_at", now),
            )
            session.merge(db_candidate)

            evidence_event_ids = candidate.get("evidence_event_ids") or []
            timeline = build_timeline(conn, evidence_event_ids)
            subgraph = build_subgraph(
                conn,
                candidate["type"],
                candidate["anchor_object_id"],
                evidence_event_ids,
            )

            db_evidence = CandidateEvidence(
                candidate_id=candidate_id,
                evidence_event_ids=evidence_event_ids,
                evidence_object_ids=candidate.get("evidence_object_ids") or [],
                timeline=timeline,
                features=candidate.get("features") or {},
                subgraph=subgraph,
            )
            session.merge(db_evidence)


def print_type_counts(engine) -> None:
    from sqlalchemy import func, select

    with session_scope(engine) as session:
        total = session.execute(select(func.count(Candidate.candidate_id))).scalar_one()
        print(f"[pipeline] stored candidates: {total}")
        rows = session.execute(
            select(Candidate.type, func.count(Candidate.candidate_id)).group_by(Candidate.type)
        ).all()
        for ctype, count in rows:
            print(f"  - {ctype}: {count}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run OCEL pipeline and store serving DB.")
    parser.add_argument("--input", default="data/raw/ocel2-p2p.sqlite", help="OCEL SQLite")
    parser.add_argument("--serving-db", default=None, help="Serving DB SQLite path")
    parser.add_argument("--config", default="configs/pipeline.yaml", help="Pipeline config")
    args = parser.parse_args()

    config = load_config(args.config)
    run_id = str(uuid.uuid4())
    print(f"[pipeline] run_id: {run_id}")
    conn = sqlite3.connect(args.input)
    try:
        ensure_unified_events(conn)
        serving_path = resolve_db_path(args.serving_db)
        ensure_derived_event_object(conn, serving_path)
        prev_maverick = 0
        if os.path.exists(serving_path):
            prev_conn = sqlite3.connect(serving_path)
            try:
                prev_maverick = (
                    prev_conn.execute(
                        "SELECT COUNT(*) FROM candidates WHERE type = 'maverick_buying'"
                    ).fetchone()[0]
                )
            finally:
                prev_conn.close()
        approve_links = conn.execute(
            """
            SELECT COUNT(*)
            FROM derived_event_object deo
            JOIN object o ON o.ocel_id = deo.object_id
            JOIN v_events_unified v ON v.event_id = deo.event_id
            WHERE v.activity = 'ApprovePurchaseRequisition'
              AND o.ocel_type = 'purchase_requisition'
            """
        ).fetchone()[0]
        delegate_links = conn.execute(
            """
            SELECT COUNT(*)
            FROM derived_event_object deo
            JOIN object o ON o.ocel_id = deo.object_id
            JOIN v_events_unified v ON v.event_id = deo.event_id
            WHERE v.activity = 'DelegatePurchaseRequisitionApproval'
              AND o.ocel_type = 'purchase_requisition'
            """
        ).fetchone()[0]
        print(f"[pipeline] approve_pr_links (derived): {approve_links}")
        print(f"[pipeline] delegate_pr_links (derived): {delegate_links}")
        candidates = []

        dup = run_duplicate_payment(conn, config)
        candidates.extend(dup)

        lengthy = run_lengthy_approval(conn, config)
        candidates.extend(lengthy)
        approval_activity_counts: Dict[str, int] = {}
        for cand in lengthy:
            if cand["type"] == "lengthy_approval_pr":
                activity = cand.get("features", {}).get("approval_event_activity")
                if activity:
                    approval_activity_counts[activity] = approval_activity_counts.get(activity, 0) + 1

        maverick = run_maverick_buying(conn, config)
        candidates.extend(maverick)
        reason_counts: Dict[str, int] = {}
        for cand in maverick:
            reason = cand.get("features", {}).get("maverick_reason")
            if reason:
                reason_counts[reason] = reason_counts.get(reason, 0) + 1
        if reason_counts:
            print("[maverick_buying] reason counts:")
            for reason, count in sorted(reason_counts.items()):
                print(f"  - {reason}: {count}")
        if approval_activity_counts:
            print("[lengthy_approval_pr] approval_event_activity counts:")
            for activity, count in sorted(approval_activity_counts.items()):
                print(f"  - {activity}: {count}")

        score_candidates(candidates, config)
    finally:
        conn.close()

    engine = get_engine(args.serving_db)
    init_db(engine)
    conn = sqlite3.connect(args.input)
    try:
        upsert_candidates(engine, candidates, conn, run_id)
    finally:
        conn.close()
    print_type_counts(engine)

    serving_path = resolve_db_path(args.serving_db)
    conn = sqlite3.connect(serving_path)
    try:
        row = conn.execute("SELECT COUNT(*) FROM derived_event_object").fetchone()
        print(f"[pipeline] derived_event_object rows: {row[0]}")
        rows = conn.execute(
            """
            SELECT json_extract(ce.features, '$.maverick_reason') AS reason, COUNT(*) AS c
            FROM candidate_evidence ce
            JOIN candidates c ON c.candidate_id = ce.candidate_id
            WHERE c.type = 'maverick_buying'
            GROUP BY reason
            ORDER BY c DESC
            """
        ).fetchall()
        if rows:
            print("[pipeline] maverick_reason (query):")
            for reason, count in rows:
                print(f"  - {reason}: {count}")
        after_maverick = (
            conn.execute("SELECT COUNT(*) FROM candidates WHERE type = 'maverick_buying'")
            .fetchone()[0]
        )
        print(f"[pipeline] maverick_buying count before: {prev_maverick}")
        print(f"[pipeline] maverick_buying count after: {after_maverick}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
