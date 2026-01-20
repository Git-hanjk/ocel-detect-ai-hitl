# SPEC — OCEL(P2P) → KG → Anomaly → HITL (with LLM verify/explain)

## 0. 목표
- 입력: OCEL2 이벤트 로그 (SQLite: `data/raw/ocel2-p2p.sqlite`)
- 출력:
  1) KG(노드/엣지 + 속성) 생성 및 evidence 서브그래프 조회 가능
  2) 이상 후보 탐지(규칙/통계 기반) + base_confidence 산출
  3) LLM을 이용한 후보 검증(더블체크) + 설명 생성
  4) HITL 큐(사람 리뷰) + 라벨 저장
  5) 시각화(UI): 후보 리스트/필터 + 증거 타임라인 + evidence 서브그래프 + LLM 설명 + 라벨링

## 1. 원칙(중요)
1) **LLM은 사실을 생성하지 않는다.**
   - LLM 입력으로 제공된 evidence(이벤트/오브젝트/속성) 밖의 사실은 “모름” 처리.
2) **후보 생성은 결정론적으로 재현 가능해야 한다.**
   - 탐지기는 SQL/파이썬 로직으로 deterministic.
3) **후보에는 반드시 evidence를 포함한다.**
   - candidate가 왜 이상인지 UI/LLM/HITL이 그대로 쓸 수 있게 `evidence_event_ids`, `evidence_object_ids`, `timeline` 또는 `subgraph` 제공.
4) **confidence는 2단 합성**
   - base_conf (결정론) + llm_verification (보조) → final_conf
   - LLM이 base_conf를 “뒤집지 않게” α 가중치 사용(기본 α=0.7)

## 2. 입력 데이터(OCEL2 SQLite)
- 핵심 테이블(예상):
  - `event(ocel_id, ocel_type, ...)`
  - `object(ocel_id, ocel_type, ...)`
  - `event_object(ocel_event_id, ocel_object_id, ocel_qualifier, ...)`
  - `object_object(ocel_source_id, ocel_target_id, ocel_qualifier, ...)`
  - 이벤트 타입별 테이블:
    - `event_CreatePurchaseRequisition`, `event_ApprovePurchaseRequisition`,
      `event_CreateRequestForQuotation`, `event_MaintainQuotation`,
      `event_CreatePurchaseOrder`, `event_ApprovePurchaseOrder`,
      `event_RecordGoodsReceipt`, `event_RecordInvoiceReceipt`,
      `event_ReleaseBlockedInvoice`, `event_ExecutePayment`, ...
    - 공통 컬럼: `ocel_id`, `ocel_time`, `resource`, `lifecycle` (+ 기타 속성)

## 3. 표준화/정규화(Schema Alignment)
### 3.1 활동/오브젝트 타입 정규화
- 활동(activity): 기본은 `event.ocel_type` 또는 이벤트 테이블명으로 라벨링.
- 오브젝트 타입(object_type): `object.ocel_type` 그대로 사용.
- qualifier 정규화: `event_object.ocel_qualifier`, `object_object.ocel_qualifier`를 그대로 보관하되,
  `configs/schema.yaml`로 표준 키로 매핑할 수 있어야 함.

### 3.2 통합 이벤트 뷰(필수)
- 모든 이벤트 타입별 테이블을 UNION하여 다음 스키마의 뷰/테이블로 만든다.
- 이름: `v_events_unified`

`v_events_unified` columns:
- `event_id` (ocel_id)
- `activity` (표준화된 이벤트 타입 문자열)
- `ts` (ocel_time, ISO8601)
- `resource` (nullable)
- `lifecycle` (nullable)
- `raw` (JSON nullable: 이벤트별 추가 속성)

## 4. KG 스키마(그래프 표현)
### 4.1 노드 타입
- `Event`
  - id, activity, ts, resource, lifecycle, raw
- `Object`
  - id, object_type, raw(속성)

### 4.2 엣지 타입
- `E2O` (Event -> Object)
  - from `event_object`
  - props: qualifier
- `O2O` (Object -> Object)
  - from `object_object`
  - props: qualifier
- `NEXT` (Event -> Event)
  - 파생(derived)
  - 정의: 특정 view(오브젝트 기준)에서 같은 object_id에 연결된 이벤트를 ts로 정렬 후 인접한 이벤트끼리 연결
  - props: view = `object_id` (또는 `object_type` 옵션), object_id, object_type

### 4.3 Evidence Subgraph 규약
- UI/LLM에 보여줄 그래프는 “전체 KG”가 아니라 후보별 **최소 서브그래프**.
- 최소 서브그래프 구성:
  - anchor object (필수)
  - evidence events (필수)
  - evidence events에 연결된 objects (필수)
  - 필요시 O2O로 1-hop 확장(옵션)

## 5. 이상탐지(Detectors) — 후보 정의 및 evidence 생성
각 detector는 다음을 출력:
- Candidate 레코드(섹션 6 참고)
- evidence 이벤트/오브젝트 ID 목록
- derived features

### 5.1 Duplicate Payments (중복 결제)
- anchor: InvoiceReceipt object (object_type=invoice receipt 또는 스키마 매핑된 Invoice)
- 규칙:
  - 동일 invoice object에 연결된 `ExecutePayment` 이벤트 수가 2 이상이면 후보
- features 예:
  - `payment_count`
  - `payment_ts_list`
  - `unique_resources`
  - (가능하면) amount/currency

### 5.2 Lengthy Approval (승인 지연)
- PR: CreatePurchaseRequisition → ApprovePurchaseRequisition
- PO: CreatePurchaseOrder → ApprovePurchaseOrder
- anchor: 해당 PR/PO object
- 규칙:
  - lead_time_hours = approve_ts - create_ts
  - 기본 임계치: 분위수 기반 (예: p95)
- features:
  - `lead_time_hours`, `threshold_hours`, `percentile_rank`

### 5.3 Maverick Buying (절차 우회)
- anchor: PurchaseOrder object
- 규칙(기본형):
  - PO 생성 시각 < 연결된 PR 승인 시각(또는 PR 승인 없음)
  - 연결된 PR은 O2O 또는 E2O를 통해 추적(구현에서 정의)
- features:
  - `po_create_ts`
  - `pr_approve_ts` (nullable)
  - `has_pr` (bool)
  - `approval_gap_hours` (nullable)

## 6. Candidate / Evidence / Label 데이터 모델(서빙 DB)
### 6.1 candidates
- `candidate_id` (UUID)
- `type` (enum: duplicate_payment | lengthy_approval_pr | lengthy_approval_po | maverick_buying)
- `anchor_object_id`
- `anchor_object_type`
- `base_conf` (0~1)
- `final_conf` (0~1, default = base_conf until LLM runs)
- `status` (enum: open | reviewed | archived)
- `created_at`, `updated_at`

### 6.2 candidate_evidence
- `candidate_id` (FK)
- `evidence_event_ids` (JSON array of string)
- `evidence_object_ids` (JSON array of string)
- `timeline` (JSON array; optional but recommended)
  - each: {event_id, activity, ts, resource, lifecycle, linked_object_ids[]}
- `features` (JSON object)
- `subgraph` (JSON object; optional cache)
  - {nodes: [...], edges: [...]}

### 6.3 llm_results
- `candidate_id` (FK)
- `model` (string)
- `prompt_hash` (string)
- `input_hash` (string)  # candidate+evidence hash
- `verdict` (enum: confirm | uncertain | reject)
- `v_conf` (0~1)
- `explanation` (text)
- `possible_false_positive` (JSON array)
- `next_questions` (JSON array)
- `raw_json` (JSON)
- `created_at`

### 6.4 labels (HITL)
- `label_id` (UUID)
- `candidate_id` (FK)
- `label` (enum: confirm | reject | needs_more)
- `reason_code` (string; controlled vocabulary)
- `note` (text; optional)
- `reviewer` (string; optional)
- `created_at`

## 7. Confidence 스코어링
### 7.1 base_conf
- 구성 요소(0~1 정규화):
  - S: severity (위반 강도)
  - R: rarity (희귀도/분포 기반)
  - I: impact (금액/지연/연쇄 영향)
  - Q: data_quality (evidence 완전성/결측)
- 공식:
  - `base_conf = clamp(wS*S + wR*R + wI*I + wQ*Q, 0, 1)`
- 기본 가중치(초기값, config로 조절):
  - wS=0.45, wR=0.20, wI=0.25, wQ=0.10

### 7.2 LLM verification 합성
- `final_conf = α*base_conf + (1-α)*v_conf` (기본 α=0.7)
- LLM verdict 기반 보정(옵션):
  - verdict=reject이면 final_conf 상한 0.49로 캡
  - verdict=confirm이면 final_conf 하한 0.51로 플로어
  - uncertain은 그대로

## 8. LLM 사용 범위와 출력 스키마(필수)
### 8.1 LLM 작업 2종
1) Verify: “룰을 evidence가 만족하는지” 확인
2) Explain: “사람이 빠르게 판단하도록” 설명 생성(근거 기반)

### 8.2 LLM 입력(Verify/Explain 공통)
- Rule definition(짧은 텍스트)
- Candidate summary(type, anchor, features)
- Evidence timeline + subgraph(nodes/edges) (필수)
- 금지: evidence 밖 추론으로 신규 사실 생성

### 8.3 LLM 출력(JSON; 엄격)
Verify output schema:
- `verdict`: "confirm" | "uncertain" | "reject"
- `v_conf`: number (0~1)
- `explanation`: string (짧게)
- `evidence_used`: string[] (event_ids)
- `possible_false_positive`: string[] (있으면)
- `next_questions`: string[] (있으면)

Explain output schema:
- `one_liner`: string
- `why_anomalous`: string
- `evidence_summary`: string  # 핵심 이벤트/시간/연결 요약
- `what_to_check_next`: string[]
- `possible_normal_reasons`: string[]

### 8.4 캐싱 규칙
- 동일 candidate+evidence(입력 해시) + 동일 프롬프트 해시 + 동일 모델이면 재호출 금지(캐시 반환)

## 9. API 스펙(최소)
### 9.1 Candidates
- `GET /api/candidates?status=open&type=...&min_conf=...&sort=final_conf_desc&limit=...`
- `GET /api/candidates/{candidate_id}`
  - candidate + evidence + (llm_results latest) + labels

### 9.2 Graph/Evidence
- `GET /api/candidates/{candidate_id}/subgraph`
  - evidence subgraph nodes/edges 반환(캐시 있으면 캐시)

### 9.3 LLM
- `POST /api/candidates/{candidate_id}/llm/verify`
- `POST /api/candidates/{candidate_id}/llm/explain`

### 9.4 Labels(HITL)
- `POST /api/candidates/{candidate_id}/labels`
  - body: {label, reason_code, note, reviewer}
- `GET /api/candidates/{candidate_id}/labels`

## 10. UI 요구사항(필수 화면)
### 10.1 Queue(후보 리스트)
- 컬럼: type, anchor, final_conf, base_conf, impact(가능), created_at, status
- 필터: type/status/conf range
- 정렬: final_conf desc 기본
- 버킷: High(>0.85), Mid(0.6~0.85), Low(<0.6)

### 10.2 Case Detail(후보 상세)
좌: timeline
- 이벤트 순서, 간격(lead time) 강조
중앙: evidence graph
- subgraph만 표시(Cytoscape.js)
우: LLM 카드 + HITL 패널
- Verify 결과(verdict/v_conf)
- Explain(한줄+근거+정상가능성+다음확인)
- 버튼: Confirm / Reject / Needs more
- reason_code 선택 + note 입력

## 11. 파이프라인 실행
- `python -m pipeline.run_pipeline --input data/raw/ocel2-p2p.sqlite --out data/derived`
- 단계:
  1) v_events_unified 생성
  2) detectors 실행 → candidates + evidence 저장
  3) base_conf 계산 및 저장
  4) (옵션) 초기 LLM verify/explain 배치 실행(또는 UI에서 on-demand)

## 12. 테스트(최소)
- detector 단위:
  - duplicate_payment: payment_count>=2 후보 존재 테스트
  - lengthy_approval: lead_time 계산/threshold 적용 테스트
  - maverick: pr 승인 누락/지연 케이스 탐지 테스트
- LLM schema:
  - 출력 JSON 스키마 검증(필수)
- API:
  - candidates list/detail 응답 스키마 테스트

---
END
