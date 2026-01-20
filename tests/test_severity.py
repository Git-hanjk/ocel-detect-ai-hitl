import pytest

from src.pipeline.severity import compute_priority_score, compute_severity


def test_duplicate_payment_severity():
    candidate = {"type": "duplicate_payment", "features": {"payment_count": 2}}
    severity = compute_severity(candidate)
    assert severity == 0.25


def test_lengthy_approval_severity():
    candidate = {
        "type": "lengthy_approval_pr",
        "features": {"lead_time_hours": 400, "threshold_hours": 100},
    }
    severity = compute_severity(candidate)
    assert severity == 1.0


def test_maverick_severity_missing_events():
    candidate = {
        "type": "maverick_buying",
        "features": {"maverick_reason": "missing_pr_create", "missing_events": ["CreatePR"]},
    }
    severity = compute_severity(candidate)
    assert severity == 0.6


def test_priority_score_calculation():
    severity = 0.7
    priority = compute_priority_score(0.8, severity)
    assert priority == pytest.approx(0.56)
