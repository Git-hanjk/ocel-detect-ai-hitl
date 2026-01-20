from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from zoneinfo import ZoneInfo
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

import jsonschema
import requests
from jinja2 import Template
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from src.app.core.models import Candidate, CandidateEvidence, LLMResult

PROMPT_PATHS = {
    "verify": "prompts/verify_rule.jinja",
    "explain": "prompts/explain_case.jinja",
}
SCHEMA_PATHS = {
    "verify": "schemas/llm_verify.schema.json",
    "explain": "schemas/llm_explain.schema.json",
}
PROMPT_VERSION = "v2.1"
VERIFY_SCHEMA_VERSION = "verify.v2.1"
EXPLAIN_SCHEMA_VERSION = "explain.v2.1"

logger = logging.getLogger(__name__)


class LLMServiceError(RuntimeError):
    def __init__(self, message: str, status_code: int, error_code: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.error_code = error_code


def load_llm_config(path: str = "configs/llm.yaml") -> Dict[str, Any]:
    import yaml

    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _load_prompt(task: str) -> str:
    path = PROMPT_PATHS[task]
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _load_schema(task: str) -> Dict[str, Any]:
    path = SCHEMA_PATHS[task]
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _rule_text(candidate_type: str) -> str:
    rules = {
        "duplicate_payment": "Same invoice object has ExecutePayment event count >= 2.",
        "lengthy_approval_pr": (
            "PR: CreatePurchaseRequisition -> approval complete lead time exceeds threshold. "
            "Approval complete = ApprovePurchaseRequisition OR DelegatePurchaseRequisitionApproval."
        ),
        "lengthy_approval_po": "PO: CreatePurchaseOrder -> ApprovePurchaseOrder lead time exceeds threshold.",
        "maverick_buying": (
            "PO created before PR approval-complete or approval-complete missing for linked PR. "
            "Approval complete = ApprovePurchaseRequisition OR DelegatePurchaseRequisitionApproval."
        ),
    }
    return rules.get(candidate_type, "Unknown rule.")


def _candidate_payload(candidate: Candidate, evidence: CandidateEvidence) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    cand = {
        "candidate_id": candidate.candidate_id,
        "type": candidate.type,
        "anchor_object_id": candidate.anchor_object_id,
        "anchor_object_type": candidate.anchor_object_type,
        "base_conf": candidate.base_conf,
        "final_conf": candidate.final_conf,
        "status": candidate.status,
    }
    ev = {
        "evidence_event_ids": evidence.evidence_event_ids,
        "evidence_object_ids": evidence.evidence_object_ids,
        "timeline": evidence.timeline,
        "features": evidence.features,
        "subgraph": evidence.subgraph,
    }
    return cand, ev


def _render_prompt(task: str, candidate: Dict[str, Any], evidence: Dict[str, Any]) -> str:
    template = Template(_load_prompt(task))
    return template.render(
        rule=_rule_text(candidate["type"]),
        candidate_json=json.dumps(candidate, ensure_ascii=False, sort_keys=True),
        evidence_json=json.dumps(evidence, ensure_ascii=False, sort_keys=True),
    )


def _extract_json(text: str) -> Dict[str, Any]:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            return json.loads(text[start : end + 1])
        raise


def _call_llm(
    prompt: str, config: Dict[str, Any], task: str
) -> tuple[Dict[str, Any], Optional[Dict[str, Any]]]:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set; set it or use LLM_PROVIDER=mock.")

    url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1/chat/completions")
    payload = {
        "model": config.get("model"),
        "temperature": config.get("temperature", 0.2),
        "max_tokens": config.get("max_tokens", 3000),
        "messages": [{"role": "user", "content": prompt}],
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    timeout = float(config.get("timeout_seconds", 30))
    retries = 2
    backoff = 0.5
    for attempt in range(retries + 1):
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
        except requests.Timeout as exc:
            if attempt < retries:
                time.sleep(backoff)
                backoff *= 2
                continue
            raise LLMServiceError("LLM request timed out.", 504, "llm_timeout") from exc
        except requests.RequestException as exc:
            if attempt < retries:
                time.sleep(backoff)
                backoff *= 2
                continue
            raise LLMServiceError("LLM request failed.", 502, "llm_request_failed") from exc

        if resp.status_code == 429 or resp.status_code >= 500:
            if attempt < retries:
                time.sleep(backoff)
                backoff *= 2
                continue
            code = "llm_rate_limited" if resp.status_code == 429 else "llm_upstream_error"
            raise LLMServiceError("LLM upstream error.", 502, code)
        if 400 <= resp.status_code < 500:
            raise LLMServiceError("LLM request rejected.", 502, "llm_bad_request")

        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        usage = data.get("usage") if isinstance(data, dict) else None
        try:
            return _extract_json(content), usage
        except json.JSONDecodeError as exc:
            raise LLMServiceError("LLM response parse failed.", 502, "llm_bad_response") from exc

    raise LLMServiceError("LLM request failed.", 502, "llm_request_failed")


def _validate_output(task: str, output: Dict[str, Any]) -> None:
    schema = _load_schema(task)
    jsonschema.validate(instance=output, schema=schema)


def _llm_result_to_dict(row: LLMResult) -> Dict[str, Any]:
    return {
        "id": row.id,
        "candidate_id": row.candidate_id,
        "model": row.model,
        "prompt_hash": row.prompt_hash,
        "input_hash": row.input_hash,
        "verdict": row.verdict,
        "v_conf": row.v_conf,
        "explanation": row.explanation,
        "possible_false_positive": row.possible_false_positive,
        "next_questions": row.next_questions,
        "raw_json": row.raw_json,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def get_latest_llm_result(db: Session, candidate_id: str, task: str) -> Optional[Dict[str, Any]]:
    prompt_hash = _hash_text(PROMPT_VERSION + _load_prompt(task))
    row = db.execute(
        select(LLMResult)
        .where(
            LLMResult.candidate_id == candidate_id,
            LLMResult.prompt_hash == prompt_hash,
        )
        .order_by(desc(LLMResult.created_at))
        .limit(1)
    ).scalar_one_or_none()
    return _llm_result_to_dict(row) if row else None


def prompt_hash_for(task: str) -> str:
    return _hash_text(PROMPT_VERSION + _load_prompt(task))


def _evidence_hash(candidate_id: str, evidence: CandidateEvidence) -> str:
    event_ids = sorted(evidence.evidence_event_ids or [])
    object_ids = sorted(evidence.evidence_object_ids or [])
    features = evidence.features or {}
    timeline = [
        {
            "event_id": item.get("event_id"),
            "ts": item.get("ts"),
            "activity": item.get("activity"),
        }
        for item in (evidence.timeline or [])
        if isinstance(item, dict)
    ]
    payload = {
        "candidate_id": candidate_id,
        "event_ids": event_ids,
        "object_ids": object_ids,
        "features": features,
        "timeline": timeline,
    }
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=True)
    return _hash_text(raw)


def _input_hash(
    task: str, evidence_hash: str, config: Dict[str, Any], provider: str
) -> str:
    payload = {
        "task": task,
        "prompt_version": PROMPT_VERSION,
        "evidence_hash": evidence_hash,
        "model": config.get("model"),
        "temperature": config.get("temperature", 0.2),
        "max_tokens": config.get("max_tokens", 3000),
        "provider": provider,
    }
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=True)
    return _hash_text(raw)


def _coerce_output(task: str, output: Dict[str, Any]) -> Dict[str, Any]:
    if task == "verify":
        if "confidence" in output:
            payload = dict(output)
        else:
            payload = {
                "schema_version": VERIFY_SCHEMA_VERSION,
                "verdict": output.get("verdict", "uncertain"),
                "confidence": output.get("v_conf", 0.5),
                "reasons": [output.get("explanation", "No explanation provided.")],
                "evidence_used": output.get("evidence_used", []),
                "cautions": output.get("possible_false_positive", []),
            }
        payload.setdefault("schema_version", VERIFY_SCHEMA_VERSION)
        reasons = payload.get("reasons")
        if not isinstance(reasons, list):
            payload["reasons"] = [str(reasons)] if reasons else []
        evidence_used = payload.get("evidence_used")
        if not isinstance(evidence_used, list):
            payload["evidence_used"] = []
        cautions = payload.get("cautions")
        if not isinstance(cautions, list):
            payload["cautions"] = [str(cautions)] if cautions else []
        next_questions = payload.get("next_questions")
        if not isinstance(next_questions, list):
            payload["next_questions"] = [str(next_questions)] if next_questions else []
        priority_hint = payload.get("priority_hint")
        if priority_hint is not None and priority_hint not in ("high", "medium", "low"):
            payload["priority_hint"] = None
        return payload

    if "summary" in output:
        payload = dict(output)
    else:
        bullets = [
            output.get("why_anomalous"),
            output.get("evidence_summary"),
        ]
        payload = {
            "schema_version": EXPLAIN_SCHEMA_VERSION,
            "summary": output.get("one_liner", "No summary provided."),
            "bullets": [item for item in bullets if item],
            "evidence_used": output.get("evidence_used", []),
            "short_summary": output.get("one_liner", "No summary provided."),
            "caveats": output.get("possible_normal_reasons", []),
        }
    payload.setdefault("schema_version", EXPLAIN_SCHEMA_VERSION)
    bullets = payload.get("bullets")
    if not isinstance(bullets, list):
        payload["bullets"] = [str(bullets)] if bullets else []
    evidence_used = payload.get("evidence_used")
    if not isinstance(evidence_used, list):
        payload["evidence_used"] = []
    if not isinstance(payload.get("short_summary"), str):
        payload["short_summary"] = payload.get("summary", "No summary provided.")
    caveats = payload.get("caveats")
    if not isinstance(caveats, list):
        payload["caveats"] = [str(caveats)] if caveats else []
    return payload


def _enforce_evidence_used(
    task: str,
    output: Dict[str, Any],
    allowed_event_ids: list[str],
) -> Dict[str, Any]:
    event_set = set(allowed_event_ids)
    evidence_used = output.get("evidence_used")
    if not isinstance(evidence_used, list):
        evidence_used = []
    out_of_scope = [item for item in evidence_used if item not in event_set]
    if not evidence_used or out_of_scope:
        if task == "verify":
            output["verdict"] = "inconclusive"
        key = "cautions" if task == "verify" else "caveats"
        notes = output.get(key) or []
        if not isinstance(notes, list):
            notes = [str(notes)]
        notes.append("evidence_used_missing_or_out_of_scope")
        output[key] = notes
        output["evidence_used"] = []
    return output


def _timeline_event_ids(evidence: CandidateEvidence) -> list[str]:
    event_ids = []
    for item in evidence.timeline or []:
        if not isinstance(item, dict):
            continue
        event_id = item.get("event_id")
        if event_id and event_id not in event_ids:
            event_ids.append(event_id)
    return event_ids


def _mock_evidence_used(evidence: CandidateEvidence) -> list[str]:
    event_ids = list(evidence.evidence_event_ids or [])
    if event_ids:
        return event_ids[:3]
    timeline_ids = _timeline_event_ids(evidence)
    return timeline_ids[:3]


def _mock_reason(features: Dict[str, Any]) -> Optional[str]:
    for key in ("maverick_reason", "duplicate_reason", "lengthy_reason"):
        if features.get(key):
            return str(features[key])
    for key, value in features.items():
        if key.endswith("_reason") and value:
            return str(value)
    return None


def _mock_priority_hint(candidate: Candidate) -> str:
    score = candidate.base_conf or candidate.final_conf or 0.0
    if score >= 0.9:
        return "high"
    if score >= 0.7:
        return "medium"
    return "low"


def _mock_activity_map(evidence: CandidateEvidence) -> Dict[str, str]:
    mapping: Dict[str, str] = {}
    for item in evidence.timeline or []:
        if not isinstance(item, dict):
            continue
        event_id = item.get("event_id")
        activity = item.get("activity")
        if event_id and activity:
            mapping[str(event_id)] = str(activity)
    return mapping


def _mock_allowed_activities(candidate: Candidate, evidence: CandidateEvidence) -> set[str]:
    reason = _mock_reason(evidence.features or {})
    if candidate.type == "maverick_buying" and reason == "missing_pr_create":
        return {"CreateRequestforQuotation", "CreatePurchaseOrder"}
    if candidate.type == "duplicate_payment":
        return {
            "CreateInvoiceReceipt",
            "ExecutePayment",
            "PerformTwoWayMatch",
            "PerformThreeWayMatch",
        }
    if candidate.type in ("lengthy_approval_pr", "lengthy_approval_po"):
        return {
            "CreatePurchaseRequisition",
            "CreatePurchaseOrder",
            "ApprovePurchaseRequisition",
            "DelegatePurchaseRequisitionApproval",
            "ApprovePurchaseOrder",
        }
    return set()


def _mock_verify_output(candidate: Candidate, evidence: CandidateEvidence) -> Dict[str, Any]:
    evidence_used = _mock_evidence_used(evidence)
    verdict = "confirm" if evidence_used else "inconclusive"
    confidence = 0.7 if len(evidence_used) == 1 else 0.8 if len(evidence_used) >= 2 else 0.4
    features = evidence.features or {}
    reason = _mock_reason(features)
    reasons = [f"Detector type is {candidate.type}."]
    if reason:
        reasons.append(f"Reason provided: {reason}.")
    if evidence_used:
        reasons.append(f"Evidence events used: {', '.join(evidence_used)}.")
    else:
        reasons.append("No evidence events available in evidence_event_ids or timeline.")
    reasons = reasons[:3]
    cautions = []
    if not evidence_used:
        cautions.append("evidence_used_missing_or_out_of_scope")
    next_questions = [
        "Is there additional evidence in the event log that clarifies this case?"
    ]
    return {
        "schema_version": VERIFY_SCHEMA_VERSION,
        "verdict": verdict,
        "confidence": confidence,
        "reasons": reasons,
        "evidence_used": evidence_used,
        "cautions": cautions,
        "priority_hint": _mock_priority_hint(candidate),
        "next_questions": next_questions,
    }


def _mock_explain_output(candidate: Candidate, evidence: CandidateEvidence) -> Dict[str, Any]:
    evidence_used = _mock_evidence_used(evidence)
    features = evidence.features or {}
    reason = _mock_reason(features)
    summary_reason = f" Reason: {reason}." if reason else ""
    summary = f"{candidate.type} case based on provided evidence.{summary_reason}"
    short_summary = summary if len(summary) <= 140 else summary[:137] + "..."
    if candidate.type in ("lengthy_approval_pr", "lengthy_approval_po"):
        lead = features.get("lead_time_hours")
        threshold = features.get("threshold_hours")
        if isinstance(lead, (int, float)) and isinstance(threshold, (int, float)) and threshold:
            over_by = lead - threshold
            ratio = lead / threshold
            summary = (
                f"Approval lead time {lead:.1f}h exceeds threshold {threshold:.1f}h "
                f"by {over_by:+.1f}h ({ratio:.2f}x)."
            )
            short_summary = summary
    if candidate.type == "duplicate_payment":
        count = features.get("payment_count")
        if isinstance(count, (int, float)):
            short_summary = f"Invoice paid {int(count)} times for a single invoice receipt."
            summary = short_summary
    if candidate.type == "maverick_buying" and reason == "missing_pr_create":
        short_summary = "RFQ observed but PR create not observed; PR→Quotation→PO path observed."
    bullets = []
    activity_map = _mock_activity_map(evidence)
    allowed = _mock_allowed_activities(candidate, evidence)
    seen = set()

    for event_id in evidence_used:
        activity = activity_map.get(event_id)
        if activity and (not allowed or activity in allowed) and activity not in seen:
            bullets.append(f"Observed event: {activity}.")
            seen.add(activity)
        if len(bullets) >= 5:
            break

    if len(bullets) < 5:
        for item in evidence.timeline or []:
            if not isinstance(item, dict):
                continue
            activity = item.get("activity")
            if not activity:
                continue
            if allowed and activity not in allowed:
                continue
            if activity in seen:
                continue
            bullets.append(f"Observed event: {activity}.")
            seen.add(activity)
            if len(bullets) >= 5:
                break

    if candidate.type in ("lengthy_approval_pr", "lengthy_approval_po") and len(bullets) < 5:
        lead = features.get("lead_time_hours")
        threshold = features.get("threshold_hours")
        if isinstance(lead, (int, float)) and isinstance(threshold, (int, float)) and threshold:
            ratio = lead / threshold
            bullets.append(
                f"Lead time {lead:.1f}h vs threshold {threshold:.1f}h ({ratio:.2f}x)."
            )

    if not bullets and evidence_used:
        bullets = [f"Evidence event referenced: {event_id}." for event_id in evidence_used]
    if not bullets:
        bullets = ["No timeline events available to summarize."]
    caveats = []
    if not evidence_used:
        caveats.append("evidence_used_missing_or_out_of_scope")
    return {
        "schema_version": EXPLAIN_SCHEMA_VERSION,
        "summary": summary,
        "short_summary": short_summary,
        "bullets": bullets,
        "evidence_used": evidence_used,
        "caveats": caveats,
    }


def _default_next_question(candidate: Candidate) -> str:
    if candidate.type in ("lengthy_approval_pr", "lengthy_approval_po"):
        return "Are there intermediate rework/changes on the same PR/PO that explain the delay?"
    if candidate.type == "duplicate_payment":
        return "Do payment events share the same invoice reference/amount in the evidence?"
    return "Is CreatePurchaseRequisition missing across all linked objects, or only on the PR object?"


def _daily_limit_allowed(db: Session, provider: str) -> bool:
    if provider == "mock":
        return True
    limit = int(os.environ.get("LLM_DAILY_LIMIT", "20"))
    tz_name = os.environ.get("LLM_DAILY_WINDOW_TZ", "Asia/Seoul")
    tz = ZoneInfo(tz_name)
    now = datetime.now(tz)
    start = datetime(now.year, now.month, now.day, tzinfo=tz).astimezone(timezone.utc)
    count = (
        db.execute(
            select(func.count())
            .select_from(LLMResult)
            .where(LLMResult.created_at >= start, LLMResult.provider == provider)
        )
        .scalar_one()
    )
    return count < limit


def run_llm(
    db: Session,
    candidate_id: str,
    task: str,
    config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    if task not in ("verify", "explain"):
        raise ValueError("task must be 'verify' or 'explain'")

    candidate = db.get(Candidate, candidate_id)
    evidence = db.get(CandidateEvidence, candidate_id)
    if not candidate or not evidence:
        raise ValueError("candidate or evidence not found")

    cand_payload, ev_payload = _candidate_payload(candidate, evidence)
    prompt = _render_prompt(task, cand_payload, ev_payload)
    prompt_hash = _hash_text(PROMPT_VERSION + _load_prompt(task))
    if config is None:
        config = load_llm_config()
    model = config.get("model")
    provider = os.environ.get("LLM_PROVIDER", "openai")
    evidence_hash = _evidence_hash(candidate_id, evidence)
    input_hash = _input_hash(task, evidence_hash, config, provider)

    logger.info(
        "llm_request candidate=%s run_id=%s task=%s provider=%s model=%s prompt_version=%s",
        candidate_id,
        candidate.run_id,
        task,
        provider,
        model,
        PROMPT_VERSION,
    )

    cached = db.execute(
        select(LLMResult).where(
            LLMResult.candidate_id == candidate_id,
            LLMResult.prompt_hash == prompt_hash,
            LLMResult.input_hash == input_hash,
            LLMResult.model == model,
        )
    ).scalar_one_or_none()
    if cached:
        return _llm_result_to_dict(cached)

    if provider == "mock":
        output = (
            _mock_verify_output(candidate, evidence)
            if task == "verify"
            else _mock_explain_output(candidate, evidence)
        )
        usage = None
    else:
        if not _daily_limit_allowed(db, provider):
            raise LLMServiceError(
                "LLM daily limit reached.", 429, "llm_daily_limit_reached"
            )
        output, usage = _call_llm(prompt, config, task)
    output = _coerce_output(task, output)
    allowed_event_ids = list(evidence.evidence_event_ids or []) or _timeline_event_ids(evidence)
    output = _enforce_evidence_used(task, output, allowed_event_ids)
    if task == "verify" and not output.get("next_questions"):
        output["next_questions"] = [_default_next_question(candidate)]
    try:
        _validate_output(task, output)
    except jsonschema.ValidationError:
        retry_prompt = prompt + "\n\nReturn JSON only."
        if provider == "mock":
            output = (
                _mock_verify_output(candidate, evidence)
                if task == "verify"
                else _mock_explain_output(candidate, evidence)
            )
        else:
            output, usage = _call_llm(retry_prompt, config, task)
        output = _coerce_output(task, output)
        allowed_event_ids = list(evidence.evidence_event_ids or []) or _timeline_event_ids(evidence)
        output = _enforce_evidence_used(task, output, allowed_event_ids)
        if task == "verify" and not output.get("next_questions"):
            output["next_questions"] = [_default_next_question(candidate)]
        try:
            _validate_output(task, output)
        except jsonschema.ValidationError as exc:
            logger.error(
                "llm_schema_invalid candidate=%s task=%s provider=%s model=%s",
                candidate_id,
                task,
                provider,
                model,
            )
            raise LLMServiceError("LLM response schema invalid.", 422, "llm_schema_invalid") from exc

    row = LLMResult(
        candidate_id=candidate_id,
        model=model,
        provider=provider,
        schema_version=output.get("schema_version"),
        prompt_hash=prompt_hash,
        input_hash=input_hash,
        verdict=output.get("verdict") if task == "verify" else None,
        v_conf=output.get("confidence") if task == "verify" else None,
        explanation=(
            " | ".join(output.get("reasons") or [])
            if task == "verify"
            else output.get("summary")
        ),
        possible_false_positive=output.get("cautions") if task == "verify" else None,
        next_questions=output.get("next_questions") if task == "verify" else None,
        raw_json=output,
        prompt_tokens=usage.get("prompt_tokens") if isinstance(usage, dict) else None,
        completion_tokens=usage.get("completion_tokens") if isinstance(usage, dict) else None,
        total_tokens=usage.get("total_tokens") if isinstance(usage, dict) else None,
        created_at=datetime.now(timezone.utc),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _llm_result_to_dict(row)
