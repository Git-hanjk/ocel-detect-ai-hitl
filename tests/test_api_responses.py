import importlib
import os
import sys
import tempfile
from datetime import datetime, timezone

from fastapi.testclient import TestClient


def _load_app(db_path: str):
    os.environ["SERVING_DB_PATH"] = db_path
    for mod in ["src.app.api.routes", "src.app.main"]:
        if mod in sys.modules:
            del sys.modules[mod]
    from src.app.main import app
    from src.app.core.db import get_engine, init_db, session_scope
    from src.app.core.models import Candidate, CandidateEvidence, LLMResult

    engine = get_engine(db_path)
    init_db(engine)
    with session_scope(engine) as session:
        candidate = Candidate(
            candidate_id="test-candidate-1",
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
                prompt_hash="prompt-hash",
                input_hash="input-hash",
                verdict="confirm",
                v_conf=0.8,
                explanation="Mock verify.",
                raw_json={"priority_hint": "high"},
                created_at=datetime.now(timezone.utc),
            )
        )
    return app


def test_api_responses_have_subgraph():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "serving.sqlite")
        app = _load_app(db_path)
        client = TestClient(app)

        resp = client.get("/api/candidates?limit=5")
        assert resp.status_code == 200
        payload = resp.json()
        assert "items" in payload
        assert payload["items"][0]["features_preview"]["maverick_reason"] == "no_pr_found"
        llm_preview = payload["items"][0].get("llm_preview") or {}
        created = llm_preview.get("verify_created_at") or ""
        assert "T" in created

        detail = client.get("/api/candidates/test-candidate-1")
        assert detail.status_code == 200
        detail_payload = detail.json()
        assert detail_payload["evidence"]["subgraph"]["nodes"]

        subgraph = client.get("/api/candidates/test-candidate-1/subgraph")
        assert subgraph.status_code == 200
        subgraph_payload = subgraph.json()
        assert "subgraph" in subgraph_payload
