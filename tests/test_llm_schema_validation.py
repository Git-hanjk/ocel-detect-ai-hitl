import json
import os
import tempfile
from datetime import datetime, timezone

import jsonschema
import pytest


def _load_schema(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _init_db(db_path: str):
    os.environ["SERVING_DB_PATH"] = db_path
    from src.app.core.db import get_engine, init_db, session_scope
    from src.app.core.models import Candidate, CandidateEvidence

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
            features={"maverick_reason": "missing_pr_create"},
            subgraph={
                "nodes": [{"id": "event:1", "type": "Event", "activity": "CreatePurchaseOrder"}],
                "edges": [],
            },
        )
        session.merge(evidence)
    return engine


def test_verify_schema_validation():
    schema = _load_schema("schemas/llm_verify.schema.json")
    sample = {
        "schema_version": "verify.v2",
        "verdict": "uncertain",
        "confidence": 0.5,
        "reasons": ["Evidence missing approval event."],
        "evidence_used": ["event:1"],
        "cautions": [],
        "priority_hint": "medium",
        "next_questions": ["Is there additional evidence in the event log?"],
    }
    jsonschema.validate(instance=sample, schema=schema)


def test_explain_schema_validation():
    schema = _load_schema("schemas/llm_explain.schema.json")
    sample = {
        "schema_version": "explain.v2",
        "summary": "Approval missing for linked PR.",
        "bullets": ["No approval event exists in evidence."],
        "evidence_used": ["event:1"],
        "short_summary": "Approval missing for linked PR.",
        "caveats": ["Emergency procurement."],
    }
    jsonschema.validate(instance=sample, schema=schema)


def test_llm_schema_invalid_returns_422(monkeypatch):
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "serving.sqlite")
        engine = _init_db(db_path)
        from src.app.services import llm_service
        from src.app.core.db import session_scope
        from src.app.services.llm_service import LLMServiceError

        def _bad_call(*_args, **_kwargs):
            return ({
                "schema_version": "verify.v2",
                "verdict": "confirm",
                "confidence": "high",
                "reasons": ["bad confidence type"],
                "evidence_used": ["event:1"],
            }, None)

        monkeypatch.setattr(llm_service, "_call_llm", _bad_call)
        with session_scope(engine) as session:
            with pytest.raises(LLMServiceError) as excinfo:
                llm_service.run_llm(session, "test-candidate-1", "verify")
            assert excinfo.value.status_code == 422
            assert excinfo.value.error_code == "llm_schema_invalid"


def test_llm_evidence_out_of_scope_downgrades(monkeypatch):
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "serving.sqlite")
        engine = _init_db(db_path)
        from src.app.services import llm_service
        from src.app.core.db import session_scope

        def _bad_evidence(*_args, **_kwargs):
            return ({
                "schema_version": "verify.v2",
                "verdict": "confirm",
                "confidence": 0.9,
                "reasons": ["Uses evidence outside scope."],
                "evidence_used": ["event:999"],
                "cautions": [],
            }, None)

        monkeypatch.setattr(llm_service, "_call_llm", _bad_evidence)
        with session_scope(engine) as session:
            payload = llm_service.run_llm(session, "test-candidate-1", "verify")
        assert payload["verdict"] == "inconclusive"
        assert payload["raw_json"]["evidence_used"] == []


def test_mock_explain_missing_pr_create_bullets():
    with tempfile.TemporaryDirectory() as tmpdir:
        os.environ["LLM_PROVIDER"] = "mock"
        db_path = os.path.join(tmpdir, "serving.sqlite")
        from src.app.core.db import get_engine, init_db, session_scope
        from src.app.core.models import Candidate, CandidateEvidence
        from src.app.services import llm_service

        engine = get_engine(db_path)
        init_db(engine)
        with session_scope(engine) as session:
            candidate = Candidate(
                candidate_id="test-candidate-2",
                type="maverick_buying",
                anchor_object_id="purchase_order:1",
                anchor_object_type="purchase_order",
                base_conf=0.8,
                final_conf=0.8,
                status="open",
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
            session.merge(candidate)
            evidence = CandidateEvidence(
                candidate_id="test-candidate-2",
                evidence_event_ids=["event:rfq", "event:po"],
                evidence_object_ids=["purchase_requisition:1", "purchase_order:1"],
                timeline=[
                    {
                        "event_id": "event:rfq",
                        "activity": "CreateRequestforQuotation",
                        "ts": "2022-01-01T00:00:00Z",
                    },
                    {
                        "event_id": "event:po",
                        "activity": "CreatePurchaseOrder",
                        "ts": "2022-01-02T00:00:00Z",
                    },
                ],
                features={"maverick_reason": "missing_pr_create"},
                subgraph={"nodes": [], "edges": []},
            )
            session.merge(evidence)

        with session_scope(engine) as session:
            payload = llm_service.run_llm(session, "test-candidate-2", "explain")
        bullets = (payload.get("raw_json") or {}).get("bullets") or []
        joined = " ".join(bullets)
        assert "CreateRequestforQuotation" in joined
        assert "CreatePurchaseOrder" in joined
