export type Candidate = {
  candidate_id: string;
  run_id?: string | null;
  type: string;
  anchor_object_id: string;
  anchor_object_type: string;
  base_conf: number;
  final_conf: number;
  severity?: number | null;
  priority_score?: number | null;
  status: string;
  created_at?: string | null;
  updated_at?: string | null;
  features_preview?: Record<string, unknown>;
  summary?: Record<string, unknown>;
  llm_preview?: {
    verify_verdict?: string | null;
    priority_hint?: string | null;
    verify_created_at?: string | null;
  };
};

export type CandidateEvidence = {
  candidate_id: string;
  evidence_event_ids?: string[] | null;
  evidence_object_ids?: string[] | null;
  timeline?: Array<Record<string, unknown>> | null;
  features?: Record<string, unknown> | null;
  subgraph?: {
    nodes: Array<Record<string, unknown>>;
    edges: Array<Record<string, unknown>>;
  } | null;
};

export type CandidateDetail = {
  candidate: Candidate;
  evidence: CandidateEvidence | null;
  latest_label?: Record<string, unknown> | null;
  latest_llm_verify?: Record<string, unknown> | null;
  latest_llm_explain?: Record<string, unknown> | null;
};

export type ListResponse = {
  items: Candidate[];
  count: number;
  run_id?: string | null;
};

export type LLMResponse = {
  id?: number;
  verdict?: string | null;
  v_conf?: number | null;
  explanation?: string | null;
  possible_false_positive?: unknown;
  next_questions?: unknown;
  raw_json?: Record<string, unknown> | null;
  evidence_used?: string[] | null;
  created_at?: string | null;
  cached?: boolean;
};

export type StatsResponse = {
  run_id: string | null;
  totals: {
    candidates: number;
    labeled: number;
    coverage: number;
  };
  by_type: Array<{ type: string; count: number }>;
  by_status: Array<{ status: string; count: number }>;
  labels: Array<{ label: string; count: number }>;
  accuracy: {
    confirm: number;
    reject: number;
    accuracy: number | null;
  };
  accuracy_by_type: Array<{
    type: string;
    confirm: number;
    reject: number;
    accuracy: number | null;
  }>;
  severity_buckets: {
    low: number;
    medium: number;
    high: number;
    unknown: number;
  };
  label_averages: Array<{
    label: string;
    avg_severity: number | null;
    avg_priority_score: number | null;
  }>;
  top_priority: Array<{
    candidate_id: string;
    type: string;
    priority_score: number | null;
    severity: number | null;
    final_conf: number | null;
    status: string;
  }>;
};

export type SubgraphResponse = {
  candidate_id: string;
  subgraph: {
    nodes: Array<Record<string, unknown>>;
    edges: Array<Record<string, unknown>>;
  };
};
