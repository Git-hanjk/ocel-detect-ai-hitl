from __future__ import annotations

import argparse

from sqlalchemy import select

from src.app.core.db import get_engine, init_db, session_scope
from src.app.core.models import Candidate, CandidateEvidence
from src.pipeline.severity import compute_priority_score, compute_severity


def backfill(run_id: str | None, db_path: str | None) -> int:
    engine = get_engine(db_path)
    init_db(engine)
    updated = 0
    with session_scope(engine) as session:
        query = (
            select(Candidate, CandidateEvidence)
            .join(CandidateEvidence, CandidateEvidence.candidate_id == Candidate.candidate_id)
            .where(Candidate.severity.is_(None))
        )
        if run_id:
            query = query.where(Candidate.run_id == run_id)
        for candidate, evidence in session.execute(query).all():
            features = evidence.features or {}
            payload = {"type": candidate.type, "features": features}
            severity = compute_severity(payload)
            priority_score = compute_priority_score(candidate.final_conf, severity)
            if severity is None and priority_score is None:
                continue
            candidate.severity = severity
            candidate.priority_score = priority_score
            updated += 1
    return updated


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill severity/priority_score for candidates.")
    parser.add_argument("--run-id", default=None, help="Limit backfill to a single run_id.")
    parser.add_argument("--db", default=None, help="Serving DB sqlite path.")
    args = parser.parse_args()
    updated = backfill(args.run_id, args.db)
    print(f"[backfill] updated candidates: {updated}")


if __name__ == "__main__":
    main()
