#!/usr/bin/env python3
import argparse
import json
import os
import sys
import urllib.request
from urllib.error import HTTPError, URLError

DEFAULT_BASE_URL = os.environ.get("API_BASE_URL", "http://127.0.0.1:8001")


def request(base_url, path, method="GET", payload=None, timeout=10):
    url = f"{base_url}{path}"
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            return resp.status, json.loads(body) if body else {}
    except HTTPError as exc:
        body = exc.read().decode("utf-8")
        try:
            payload = json.loads(body) if body else {}
        except json.JSONDecodeError:
            payload = {"message": body}
        return exc.code, payload
    except URLError as exc:
        print(f"Network error: {exc}")
        sys.exit(2)


def main():
    parser = argparse.ArgumentParser(description="Smoke test LLM endpoints.")
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help="API base URL (default: API_BASE_URL env or http://127.0.0.1:8001)",
    )
    args = parser.parse_args()
    base_url = args.base_url

    status, payload = request(base_url, "/api/candidates?limit=1")
    if status != 200:
        print(f"Failed to list candidates: {status} {payload}")
        return 1
    items = payload.get("items") or []
    if not items:
        print("No candidates found.")
        return 1
    candidate_id = items[0]["candidate_id"]
    print(f"Using candidate_id={candidate_id}")

    status, latest = request(base_url, f"/api/candidates/{candidate_id}/llm/latest")
    if status != 200:
        print(f"Failed to get latest: {status} {latest}")
        return 1
    print("Latest retrieved.")

    status, verify1 = request(
        base_url, f"/api/candidates/{candidate_id}/llm/verify", method="POST", payload={}
    )
    if status != 200:
        print(f"Verify failed: {status} {verify1}")
        return 1
    status, verify2 = request(
        base_url, f"/api/candidates/{candidate_id}/llm/verify", method="POST", payload={}
    )
    if status != 200:
        print(f"Verify retry failed: {status} {verify2}")
        return 1
    verify_cache_hit = verify1.get("id") == verify2.get("id")
    print(f"Verify cache_hit={verify_cache_hit}")
    if not verify_cache_hit:
        print(f"Verify responses differ: {verify1} vs {verify2}")
        return 1
    verify_evidence = (verify1.get("raw_json") or {}).get("evidence_used") or []
    if not verify_evidence:
        verdict = verify1.get("verdict")
        print("Verify warning: evidence_used empty.")
        if verdict != "inconclusive":
            print(f"Verify failed: verdict={verdict} without evidence.")
            return 1
    else:
        print(f"Verify evidence_used count={len(verify_evidence)}")
        if not all(isinstance(item, str) and item.startswith("event:") for item in verify_evidence):
            print("Verify warning: evidence_used contains non event:* IDs.")
    verify_evidence = (verify1.get("raw_json") or {}).get("evidence_used") or []
    if not verify_evidence:
        verdict = verify1.get("verdict")
        print("Verify warning: evidence_used empty.")
        if verdict != "inconclusive":
            print(f"Verify failed: verdict={verdict} without evidence.")
            return 1
    else:
        print(f"Verify evidence_used count={len(verify_evidence)}")

    status, explain1 = request(
        base_url, f"/api/candidates/{candidate_id}/llm/explain", method="POST", payload={}
    )
    if status != 200:
        print(f"Explain failed: {status} {explain1}")
        return 1
    status, explain2 = request(
        base_url, f"/api/candidates/{candidate_id}/llm/explain", method="POST", payload={}
    )
    if status != 200:
        print(f"Explain retry failed: {status} {explain2}")
        return 1
    explain_cache_hit = explain1.get("id") == explain2.get("id")
    print(f"Explain cache_hit={explain_cache_hit}")
    if not explain_cache_hit:
        print(f"Explain responses differ: {explain1} vs {explain2}")
        return 1
    explain_evidence = (explain1.get("raw_json") or {}).get("evidence_used") or []
    if not explain_evidence:
        print("Explain warning: evidence_used empty.")
    else:
        print(f"Explain evidence_used count={len(explain_evidence)}")
        if not all(isinstance(item, str) and item.startswith("event:") for item in explain_evidence):
            print("Explain warning: evidence_used contains non event:* IDs.")

    short_summary = (explain1.get("raw_json") or {}).get("short_summary", "")
    summary_text = (explain1.get("raw_json") or {}).get("summary", "")
    if "lengthy_approval" in summary_text and short_summary:
        if "h" not in short_summary and "exceeds" not in short_summary:
            print("Explain warning: short_summary lacks numeric lead_time/threshold markers.")
    explain_evidence = (explain1.get("raw_json") or {}).get("evidence_used") or []
    if not explain_evidence:
        print("Explain warning: evidence_used empty.")
    else:
        print(f"Explain evidence_used count={len(explain_evidence)}")

    print("Smoke test passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
