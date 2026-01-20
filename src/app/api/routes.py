from __future__ import annotations

from datetime import datetime, timezone
import uuid
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import and_, desc, func, select
from sqlalchemy.orm import Session, aliased

from src.app.core.db import get_engine, init_db
from src.app.core.models import Candidate, CandidateEvidence, Label, LLMResult
from fastapi.responses import JSONResponse

from src.app.services.llm_service import (
    LLMServiceError,
    get_latest_llm_result,
    prompt_hash_for,
    run_llm,
)

engine = get_engine()
init_db(engine)

router = APIRouter(prefix="/api")


def get_db():
    session = Session(engine)
    try:
        yield session
    finally:
        session.close()


def _iso(dt: Optional[datetime]) -> Optional[str]:
    if dt is None:
        return None
    if isinstance(dt, str):
        if "T" in dt:
            return dt
        if " " in dt and "+" not in dt and "Z" not in dt:
            return dt.replace(" ", "T") + "+00:00"
        return dt
    return dt.isoformat()


def candidate_to_dict(candidate: Candidate) -> Dict[str, Any]:
    return {
        "candidate_id": candidate.candidate_id,
        "run_id": candidate.run_id,
        "type": candidate.type,
        "anchor_object_id": candidate.anchor_object_id,
        "anchor_object_type": candidate.anchor_object_type,
        "base_conf": candidate.base_conf,
        "final_conf": candidate.final_conf,
        "status": candidate.status,
        "created_at": _iso(candidate.created_at),
        "updated_at": _iso(candidate.updated_at),
    }


def evidence_to_dict(evidence: CandidateEvidence) -> Dict[str, Any]:
    return {
        "candidate_id": evidence.candidate_id,
        "evidence_event_ids": evidence.evidence_event_ids,
        "evidence_object_ids": evidence.evidence_object_ids,
        "timeline": evidence.timeline,
        "features": evidence.features,
        "subgraph": evidence.subgraph,
    }


def label_to_dict(label: Label) -> Dict[str, Any]:
    return {
        "label_id": label.label_id,
        "candidate_id": label.candidate_id,
        "label": label.label,
        "reason_code": label.reason_code,
        "note": label.note,
        "reviewer": label.reviewer,
        "created_at": _iso(label.created_at),
    }


class LabelIn(BaseModel):
    label: str
    reason_code: Optional[str] = None
    note: Optional[str] = None
    reviewer: Optional[str] = None


def preview_from_features(candidate_type: str, features: Dict[str, Any]) -> Dict[str, Any]:
    if candidate_type == "duplicate_payment":
        return {"payment_count": features.get("payment_count")}
    if candidate_type in ("lengthy_approval_pr", "lengthy_approval_po"):
        return {"lead_time_hours": features.get("lead_time_hours")}
    if candidate_type == "maverick_buying":
        preview = {"maverick_reason": features.get("maverick_reason")}
        if features.get("pr_create_ts") is not None:
            preview["pr_create_ts"] = features.get("pr_create_ts")
        else:
            preview["po_create_ts"] = features.get("po_create_ts")
        if features.get("approval_gap_hours") is not None:
            preview["approval_gap_hours"] = features.get("approval_gap_hours")
        return preview
    return {}


@router.get("/candidates")
def list_candidates(
    status: Optional[str] = "open",
    type: Optional[str] = None,
    min_conf: Optional[float] = None,
    sort: str = "final_conf_desc",
    limit: int = 100,
    offset: int = 0,
    run_id: Optional[str] = None,
    db: Session = Depends(get_db),
):
    if run_id is None:
        run_id = (
            db.execute(
                select(Candidate.run_id)
                .where(Candidate.run_id.is_not(None))
                .order_by(desc(Candidate.updated_at))
                .limit(1)
            )
            .scalars()
            .first()
        )
    verify_prompt_hash = prompt_hash_for("verify")
    latest_verify_subq = (
        select(
            LLMResult.candidate_id,
            func.max(LLMResult.created_at).label("latest_at"),
        )
        .where(LLMResult.prompt_hash == verify_prompt_hash)
        .group_by(LLMResult.candidate_id)
        .subquery()
    )
    verify_alias = aliased(LLMResult)

    query = (
        select(Candidate, CandidateEvidence, verify_alias)
        .join(
            CandidateEvidence,
            CandidateEvidence.candidate_id == Candidate.candidate_id,
            isouter=True,
        )
        .join(
            latest_verify_subq,
            latest_verify_subq.c.candidate_id == Candidate.candidate_id,
            isouter=True,
        )
        .join(
            verify_alias,
            and_(
                verify_alias.candidate_id == Candidate.candidate_id,
                verify_alias.created_at == latest_verify_subq.c.latest_at,
            ),
            isouter=True,
        )
    )
    if status:
        query = query.where(Candidate.status == status)
    if type:
        query = query.where(Candidate.type == type)
    if min_conf is not None:
        query = query.where(Candidate.final_conf >= min_conf)
    if run_id:
        query = query.where(Candidate.run_id == run_id)
    if sort == "final_conf_asc":
        query = query.order_by(Candidate.final_conf.asc())
    else:
        query = query.order_by(desc(Candidate.final_conf))
    query = query.limit(limit).offset(offset)
    rows = db.execute(query).all()
    items = []
    for candidate, evidence, verify_row in rows:
        payload = candidate_to_dict(candidate)
        features = evidence.features if evidence and evidence.features else {}
        preview = preview_from_features(candidate.type, features)
        payload["features_preview"] = preview
        payload["summary"] = preview
        if verify_row:
            raw = verify_row.raw_json if isinstance(verify_row.raw_json, dict) else {}
            payload["llm_preview"] = {
                "verify_verdict": verify_row.verdict,
                "priority_hint": raw.get("priority_hint"),
                "verify_created_at": _iso(verify_row.created_at),
            }
        items.append(payload)
    return {"items": items, "count": len(items), "run_id": run_id}


@router.get("/candidates/{candidate_id}")
def get_candidate(candidate_id: str, db: Session = Depends(get_db)):
    candidate = db.get(Candidate, candidate_id)
    if not candidate:
        raise HTTPException(status_code=404, detail="candidate not found")
    evidence = db.get(CandidateEvidence, candidate_id)
    label_row = db.execute(
        select(Label)
        .where(Label.candidate_id == candidate_id)
        .order_by(desc(Label.created_at))
        .limit(1)
    ).scalar_one_or_none()
    return {
        "candidate": candidate_to_dict(candidate),
        "evidence": evidence_to_dict(evidence) if evidence else None,
        "latest_label": label_to_dict(label_row) if label_row else None,
        "latest_llm_verify": get_latest_llm_result(db, candidate_id, "verify"),
        "latest_llm_explain": get_latest_llm_result(db, candidate_id, "explain"),
    }


@router.post("/candidates/{candidate_id}/labels")
def create_label(candidate_id: str, payload: LabelIn, db: Session = Depends(get_db)):
    candidate = db.get(Candidate, candidate_id)
    if not candidate:
        raise HTTPException(status_code=404, detail="candidate not found")
    label = Label(
        label_id=str(uuid.uuid4()),
        candidate_id=candidate_id,
        label=payload.label,
        reason_code=payload.reason_code,
        note=payload.note,
        reviewer=payload.reviewer,
        created_at=datetime.now(timezone.utc),
    )
    db.add(label)
    db.commit()
    db.refresh(label)
    return label_to_dict(label)


@router.get("/candidates/{candidate_id}/subgraph")
def get_subgraph(candidate_id: str, db: Session = Depends(get_db)):
    evidence = db.get(CandidateEvidence, candidate_id)
    if not evidence:
        raise HTTPException(status_code=404, detail="candidate not found")
    return {"candidate_id": candidate_id, "subgraph": evidence.subgraph}


@router.post("/candidates/{candidate_id}/llm/verify")
def llm_verify(candidate_id: str, db: Session = Depends(get_db)):
    try:
        return run_llm(db, candidate_id, "verify")
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except LLMServiceError as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error_code": exc.error_code, "message": str(exc)},
        )


@router.post("/candidates/{candidate_id}/llm/explain")
def llm_explain(candidate_id: str, db: Session = Depends(get_db)):
    try:
        return run_llm(db, candidate_id, "explain")
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except LLMServiceError as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error_code": exc.error_code, "message": str(exc)},
        )


@router.get("/candidates/{candidate_id}/llm/latest")
def llm_latest(candidate_id: str, db: Session = Depends(get_db)):
    return {
        "candidate_id": candidate_id,
        "latest_verify": get_latest_llm_result(db, candidate_id, "verify"),
        "latest_explain": get_latest_llm_result(db, candidate_id, "explain"),
    }


@router.get("/stats")
def get_stats(run_id: Optional[str] = None, db: Session = Depends(get_db)):
    if run_id is None:
        run_id = (
            db.execute(
                select(Candidate.run_id)
                .where(Candidate.run_id.is_not(None))
                .order_by(desc(Candidate.updated_at))
                .limit(1)
            )
            .scalars()
            .first()
        )

    if run_id is None:
        return {
            "run_id": None,
            "totals": {"candidates": 0, "labeled": 0, "coverage": 0.0},
            "by_type": [],
            "by_status": [],
            "labels": [],
            "accuracy": {"confirm": 0, "reject": 0, "accuracy": None},
            "accuracy_by_type": [],
        }

    candidate_filter = Candidate.run_id == run_id
    total_candidates = (
        db.execute(select(func.count()).select_from(Candidate).where(candidate_filter))
        .scalar_one()
    )
    by_type_rows = (
        db.execute(
            select(Candidate.type, func.count())
            .where(candidate_filter)
            .group_by(Candidate.type)
        ).all()
    )
    by_status_rows = (
        db.execute(
            select(Candidate.status, func.count())
            .where(candidate_filter)
            .group_by(Candidate.status)
        ).all()
    )

    latest_label_subq = (
        select(Label.candidate_id, func.max(Label.created_at).label("latest_at"))
        .join(Candidate, Candidate.candidate_id == Label.candidate_id)
        .where(candidate_filter)
        .group_by(Label.candidate_id)
        .subquery()
    )
    label_rows = (
        db.execute(
            select(Label.label, func.count())
            .join(
                latest_label_subq,
                and_(
                    Label.candidate_id == latest_label_subq.c.candidate_id,
                    Label.created_at == latest_label_subq.c.latest_at,
                ),
            )
            .group_by(Label.label)
        ).all()
    )
    label_counts = {label: count for label, count in label_rows}
    confirm_count = label_counts.get("confirm", 0)
    reject_count = label_counts.get("reject", 0)
    labeled_total = sum(label_counts.values())
    coverage = (labeled_total / total_candidates) if total_candidates else 0.0
    denom = confirm_count + reject_count
    accuracy = (confirm_count / denom) if denom else None

    by_type_label_rows = (
        db.execute(
            select(Candidate.type, Label.label, func.count())
            .join(
                latest_label_subq,
                Candidate.candidate_id == latest_label_subq.c.candidate_id,
            )
            .join(
                Label,
                and_(
                    Label.candidate_id == latest_label_subq.c.candidate_id,
                    Label.created_at == latest_label_subq.c.latest_at,
                ),
            )
            .where(candidate_filter)
            .group_by(Candidate.type, Label.label)
        ).all()
    )
    by_type_labels: dict[str, dict[str, int]] = {}
    for ctype, label, count in by_type_label_rows:
        by_type_labels.setdefault(ctype, {})[label] = count

    accuracy_by_type = []
    for ctype, counts in sorted(by_type_labels.items()):
        c_confirm = counts.get("confirm", 0)
        c_reject = counts.get("reject", 0)
        c_denom = c_confirm + c_reject
        c_accuracy = (c_confirm / c_denom) if c_denom else None
        accuracy_by_type.append(
            {
                "type": ctype,
                "confirm": c_confirm,
                "reject": c_reject,
                "accuracy": c_accuracy,
            }
        )

    return {
        "run_id": run_id,
        "totals": {"candidates": total_candidates, "labeled": labeled_total, "coverage": coverage},
        "by_type": [{"type": t, "count": c} for t, c in by_type_rows],
        "by_status": [{"status": s, "count": c} for s, c in by_status_rows],
        "labels": [{"label": l, "count": c} for l, c in label_rows],
        "accuracy": {"confirm": confirm_count, "reject": reject_count, "accuracy": accuracy},
        "accuracy_by_type": accuracy_by_type,
    }
