import os
import tempfile
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from src.app.core.db import get_engine, init_db, session_scope
from src.app.core.models import Candidate, CandidateEvidence, LLMResult
from src.app.services.llm_service import run_llm


def test_llm_cache_hits():
    os.environ["LLM_PROVIDER"] = "mock"
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "serving.sqlite")
        engine = get_engine(db_path)
        init_db(engine)

        with session_scope(engine) as session:
            candidate = Candidate(
                candidate_id="cache-candidate-1",
                type="maverick_buying",
                anchor_object_id="purchase_order:1",
                anchor_object_type="purchase_order",
                base_conf=0.7,
                final_conf=0.7,
                status="open",
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
            session.merge(candidate)
            evidence = CandidateEvidence(
                candidate_id="cache-candidate-1",
                evidence_event_ids=["event:1"],
                evidence_object_ids=["purchase_order:1"],
                timeline=[],
                features={"maverick_reason": "no_pr_found"},
                subgraph={"nodes": [], "edges": []},
            )
            session.merge(evidence)

        with Session(engine) as session:
            first = run_llm(session, "cache-candidate-1", "verify")
            second = run_llm(session, "cache-candidate-1", "verify")
            assert first["id"] == second["id"]
            count = session.query(LLMResult).count()
            assert count == 1
