# HITL UI MVP

## Run (backend + frontend)

Run order:
1. Start backend (uvicorn).
2. Start frontend (Vite).
3. Optional: `LLM_PROVIDER=mock` for LLM calls.

Backend (FastAPI, default 8001):

```bash
uvicorn src.app.main:app --host 0.0.0.0 --port 8001
```

Frontend (Vite, default 5173):

```bash
cd frontend
npm i
npm run dev
```

Environment:
- `frontend/.env.example` has `VITE_API_BASE_URL` defaulting to `http://127.0.0.1:8001`.
- CORS: backend allows `http://127.0.0.1:5173` and `http://localhost:5173` by default.
- Optional: `LLM_PROVIDER=mock` for local LLM calls.

## Validation commands

```bash
cd frontend
npm run typecheck && npm run build
```

## Minimal check flow
1. Open `http://127.0.0.1:5173` and confirm Queue shows latest `run_id`.
2. Filter type `maverick_buying`, click `Open` on a candidate.
3. In Case Detail, confirm Timeline + Graph render, then `Fit to screen`.
4. Click `Run Verify` or `Run Explain` and expand evidence IDs.
5. Click `Confirm/Reject/Unsure` and verify label refreshes.

## Stats page
1. Open `http://127.0.0.1:5173/stats`.
2. Confirm latest run_id and aggregate cards render within ~1s.

## LLM smoke check

Use mock mode for safe local validation:

```bash
LLM_PROVIDER=mock python scripts/smoke_llm.py
```

Optional API base override:

```bash
API_BASE_URL=http://127.0.0.1:8001 LLM_PROVIDER=mock python scripts/smoke_llm.py
LLM_PROVIDER=mock python scripts/smoke_llm.py --base-url http://127.0.0.1:8001
```

LLM safety policy:
- `evidence_used` is enforced to be a subset of `evidence_event_ids`.
- If missing/out-of-scope, verify verdict is downgraded to `inconclusive` and a caution is added.

On-demand LLM usage:
- The UI shows GET `/llm/latest` by default.
- Verify/Explain are generated only when the buttons are clicked.

Real mode settings:
- `LLM_PROVIDER=real`
- `OPENAI_API_KEY=...`
- `LLM_DAILY_LIMIT=20` (default) and `LLM_DAILY_WINDOW_TZ=Asia/Seoul`

Limit error example:

```json
{
  "error_code": "llm_daily_limit_reached",
  "message": "LLM daily limit reached."
}
```

Sample Verify (mock):

```json
{
  "schema_version": "verify.v2",
  "verdict": "confirm",
  "confidence": 0.8,
  "reasons": ["Detector type is maverick_buying."],
  "evidence_used": ["event:1"],
  "cautions": [],
  "priority_hint": "medium"
}
```

Sample Explain (mock):

```json
{
  "schema_version": "explain.v2",
  "summary": "maverick_buying case based on provided evidence. Reason: missing_pr_create.",
  "short_summary": "maverick_buying based on evidence; missing_pr_create.",
  "bullets": ["Observed event: CreateRequestforQuotation."],
  "evidence_used": ["event:1"],
  "caveats": []
}
```

## Routes covered
- `GET /api/candidates`
- `GET /api/candidates/{candidate_id}`
- `GET /api/candidates/{candidate_id}/subgraph`
- `GET /api/candidates/{candidate_id}/llm/latest`
- `POST /api/candidates/{candidate_id}/llm/verify`
- `POST /api/candidates/{candidate_id}/llm/explain`
- `POST /api/candidates/{candidate_id}/labels`

## Sample API capture

Queue list (latest run_id is returned automatically):

```bash
curl "http://127.0.0.1:8001/api/candidates?limit=1&type=maverick_buying"
```

Sample response:

```json
{
  "items": [
    {
      "candidate_id": "abfeb1b1-19d1-5c94-8100-fd2da552d135",
      "run_id": "5bcc670f-0f82-4381-a810-5fdea94d648e",
      "type": "maverick_buying",
      "anchor_object_id": "purchase_order:565",
      "anchor_object_type": "purchase_order",
      "base_conf": 0.65,
      "final_conf": 0.65,
      "status": "open",
      "created_at": "2025-01-01T00:00:00",
      "updated_at": "2025-01-01T00:00:00",
      "features_preview": {
        "maverick_reason": "missing_pr_create",
        "rfq_ts": "2021-05-05T08:30:00Z"
      },
      "summary": {
        "maverick_reason": "missing_pr_create",
        "rfq_ts": "2021-05-05T08:30:00Z"
      }
    }
  ],
  "count": 1,
  "run_id": "5bcc670f-0f82-4381-a810-5fdea94d648e"
}
```

LLM latest:

```bash
curl "http://127.0.0.1:8001/api/candidates/abfeb1b1-19d1-5c94-8100-fd2da552d135/llm/latest"
```

Sample response:

```json
{
  "candidate_id": "abfeb1b1-19d1-5c94-8100-fd2da552d135",
  "latest_verify": {
    "id": 1,
    "verdict": "uncertain",
    "v_conf": 0.5,
    "explanation": "Mock response.",
    "raw_json": {
      "verdict": "uncertain",
      "v_conf": 0.5,
      "explanation": "Mock response.",
      "evidence_used": ["event:50"]
    },
    "created_at": "2025-01-01T00:00:00"
  },
  "latest_explain": null
}
```
