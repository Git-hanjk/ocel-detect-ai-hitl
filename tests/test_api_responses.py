import os
import tempfile
from datetime import datetime, timezone


def _load_db(db_path: str):
    os.environ["SERVING_DB_PATH"] = db_path
    from src.app.core.db import get_engine, init_db, session_scope
    from src.app.core.models import Candidate, CandidateEvidence, LLMResult
    from src.app.services.llm_service import prompt_hash_for

    engine = get_engine(db_path)
    init_db(engine)
    with session_scope(engine) as session:
        candidate = Candidate(
            candidate_id="test-candidate-1",
            run_id="run-1",
            type="maverick_buying",
            anchor_object_id="purchase_order:1",
            anchor_object_type="purchase_order",
            base_conf=0.7,
            final_conf=0.7,
            severity=0.6,
            priority_score=0.42,
            status="open",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        session.merge(candidate)
        evidence = CandidateEvidence(
            candidate_id="test-candidate-1",
            evidence_event_ids=["event:1"],
            evidence_object_ids=["purchase_order:1"],
            timeline=[
                {
                    "event_id": "event:1",
                    "activity": "CreatePurchaseOrder",
                    "ts": "2022-01-01T00:00:00Z",
                    "resource": "user",
                    "lifecycle": "complete",
                    "linked_object_ids": ["purchase_order:1"],
                }
            ],
            features={"maverick_reason": "no_pr_found", "approval_gap_hours": None},
            subgraph={
                "nodes": [{"id": "event:1", "type": "Event", "activity": "CreatePurchaseOrder"}],
                "edges": [],
            },
        )
        session.merge(evidence)
        session.merge(
            LLMResult(
                candidate_id="test-candidate-1",
                model="mock",
                provider="mock",
                schema_version="verify.v2",
                prompt_hash=prompt_hash_for("verify"),
                input_hash="input-hash",
                verdict="confirm",
                v_conf=0.8,
                explanation="Mock verify.",
                raw_json={"priority_hint": "high"},
                created_at=datetime.now(timezone.utc),
            )
        )
    return engine


def test_api_responses_have_subgraph():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "serving.sqlite")
        engine = _load_db(db_path)
        from sqlalchemy.orm import Session
        from src.app.api.routes import get_candidate, get_subgraph, list_candidates

        with Session(engine) as session:
            payload = list_candidates(limit=5, db=session)
            assert "items" in payload
            assert payload["items"][0]["features_preview"]["maverick_reason"] == "no_pr_found"
            assert payload["items"][0]["severity"] == 0.6
            assert payload["items"][0]["priority_score"] == 0.42
            llm_preview = payload["items"][0].get("llm_preview") or {}
            created = llm_preview.get("verify_created_at") or ""
            assert "T" in created

            detail_payload = get_candidate("test-candidate-1", db=session)
            assert detail_payload["candidate"]["severity"] is not None
            assert detail_payload["candidate"]["priority_score"] is not None
            assert detail_payload["evidence"]["subgraph"]["nodes"] is not None

            subgraph_payload = get_subgraph("test-candidate-1", db=session)
            assert "subgraph" in subgraph_payload
