import React, { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { apiFetch } from "../api/client";
import { CandidateDetail, LLMResponse, SubgraphResponse } from "../api/types";
import Spinner from "../components/Spinner";
import Timeline from "../components/Timeline";
import Graph, { HighlightConfig } from "../components/Graph";
import LLMCard from "../components/LLMCard";
import LabelCard from "../components/LabelCard";
import Toast from "../components/Toast";
import { formatLocal } from "../utils/time";
import CandidateId from "../components/CandidateId";

export default function CaseDetail() {
  const { candidateId } = useParams();
  const [detail, setDetail] = useState<CandidateDetail | null>(null);
  const [subgraph, setSubgraph] = useState<SubgraphResponse | null>(null);
  const [llmLatest, setLlmLatest] = useState<{ verify?: LLMResponse | null; explain?: LLMResponse | null } | null>(null);
  const [loading, setLoading] = useState(true);
  const [graphLoading, setGraphLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [verifyLoading, setVerifyLoading] = useState(false);
  const [explainLoading, setExplainLoading] = useState(false);
  const [labelLoading, setLabelLoading] = useState(false);
  const [labelError, setLabelError] = useState<string | null>(null);
  const [llmError, setLlmError] = useState<string | null>(null);
  const [highlightEnabled, setHighlightEnabled] = useState(false);

  useEffect(() => {
    setDetail(null);
    setSubgraph(null);
    setLlmLatest(null);
    setLoading(true);
    setGraphLoading(true);
    setError(null);
    setToast(null);
    setLlmError(null);
    setLabelError(null);
    setVerifyLoading(false);
    setExplainLoading(false);
    setLabelLoading(false);
  }, [candidateId]);

  useEffect(() => {
    if (!candidateId) return;
    let active = true;
    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        const data = await apiFetch<CandidateDetail>(`/api/candidates/${candidateId}`);
        if (!active) return;
        setDetail(data);
      } catch (err: any) {
        if (!active) return;
        setError(err.message || "Failed to load case.");
        setToast(err.message || "Failed to load case.");
      } finally {
        if (active) setLoading(false);
      }
    };
    load();
    return () => {
      active = false;
    };
  }, [candidateId]);

  useEffect(() => {
    if (!candidateId) return;
    let active = true;
    const load = async () => {
      setGraphLoading(true);
      try {
        const data = await apiFetch<SubgraphResponse>(`/api/candidates/${candidateId}/subgraph`);
        if (!active) return;
        setSubgraph(data);
      } catch (err: any) {
        if (!active) return;
        setToast(err.message || "Failed to load subgraph.");
      } finally {
        if (active) setGraphLoading(false);
      }
    };
    load();
    return () => {
      active = false;
    };
  }, [candidateId]);

  useEffect(() => {
    if (!candidateId) return;
    let active = true;
    const load = async () => {
      try {
        const data = await apiFetch<{ latest_verify?: LLMResponse | null; latest_explain?: LLMResponse | null }>(
          `/api/candidates/${candidateId}/llm/latest`
        );
        if (!active) return;
        setLlmLatest({ verify: data.latest_verify, explain: data.latest_explain });
      } catch (err: any) {
        if (!active) return;
        setLlmError(err.message || "Failed to load LLM data.");
      }
    };
    load();
    return () => {
      active = false;
    };
  }, [candidateId]);

  const features = detail?.evidence?.features || {};
  const timelineItems = (detail?.evidence?.timeline as any[]) || [];
  const missingEvents = (features as any)?.missing_events as string[] | undefined;

  const scoreFlags = useMemo(() => {
    const S = (features as any)?.S;
    const R = (features as any)?.R;
    const I = (features as any)?.I;
    const Q = (features as any)?.Q;
    return { S, R, I, Q };
  }, [features]);

  const handleVerify = async () => {
    if (!candidateId) return;
    setVerifyLoading(true);
    setLlmError(null);
    try {
      const data = await apiFetch<LLMResponse>(`/api/candidates/${candidateId}/llm/verify`, {
        method: "POST",
      });
      setLlmLatest((prev) => ({ ...prev, verify: data }));
    } catch (err: any) {
      setLlmError(err.message || "Verify failed.");
    } finally {
      setVerifyLoading(false);
    }
  };

  const handleExplain = async () => {
    if (!candidateId) return;
    setExplainLoading(true);
    setLlmError(null);
    try {
      const data = await apiFetch<LLMResponse>(`/api/candidates/${candidateId}/llm/explain`, {
        method: "POST",
      });
      setLlmLatest((prev) => ({ ...prev, explain: data }));
    } catch (err: any) {
      setLlmError(err.message || "Explain failed.");
    } finally {
      setExplainLoading(false);
    }
  };

  const handleLabel = async (label: string, note: string) => {
    if (!candidateId) return;
    setLabelLoading(true);
    setLabelError(null);
    try {
      await apiFetch(`/api/candidates/${candidateId}/labels`, {
        method: "POST",
        body: JSON.stringify({ label, note }),
      });
      const data = await apiFetch<CandidateDetail>(`/api/candidates/${candidateId}`);
      setDetail(data);
    } catch (err: any) {
      setLabelError(err.message || "Failed to save label.");
    } finally {
      setLabelLoading(false);
    }
  };

  const candidate = detail?.candidate;
  const caseUrl = window.location.href;
  const isMissingPrCreate =
    candidate?.type === "maverick_buying" &&
    (features as any)?.maverick_reason === "missing_pr_create";

  useEffect(() => {
    setHighlightEnabled(Boolean(isMissingPrCreate));
  }, [isMissingPrCreate]);

  const highlightConfig = useMemo<HighlightConfig | undefined>(() => {
    if (!isMissingPrCreate || !subgraph?.subgraph) return undefined;
    const nodes = subgraph.subgraph.nodes || [];
    const edges = subgraph.subgraph.edges || [];
    const prNode = nodes.find(
      (node) =>
        node.object_type === "purchase_requisition" ||
        (node.id && String(node.id).startsWith("purchase_requisition:"))
    );
    const poNode = nodes.find(
      (node) =>
        node.object_type === "purchase_order" ||
        (candidate?.anchor_object_id && node.id === candidate.anchor_object_id) ||
        (node.id && String(node.id).startsWith("purchase_order:"))
    );
    const quotationNode = nodes.find((node) => node.object_type === "quotation");
    const rfqEvent = nodes.find(
      (node) => node.type === "Event" && node.activity === "CreateRequestforQuotation"
    );
    const poCreateEvent = nodes.find(
      (node) => node.type === "Event" && node.activity === "CreatePurchaseOrder"
    );

    const nodeIds = new Set<string>();
    const edgeIds = new Set<string>();
    [prNode, poNode, quotationNode, rfqEvent, poCreateEvent].forEach((node) => {
      if (node?.id) {
        nodeIds.add(String(node.id));
      }
    });

    const addEdge = (sourceId?: string, targetId?: string, edgeType?: string) => {
      if (!sourceId || !targetId) return;
      edges.forEach((edge, index) => {
        if (edgeType && edge.type !== edgeType) return;
        const edgeId = `e-${index}-${edge.source}-${edge.target}`;
        if (
          (edge.source === sourceId && edge.target === targetId) ||
          (edge.source === targetId && edge.target === sourceId)
        ) {
          edgeIds.add(edgeId);
        }
      });
    };

    addEdge(rfqEvent?.id as string, prNode?.id as string, "E2O");
    addEdge(prNode?.id as string, quotationNode?.id as string, "O2O");
    addEdge(quotationNode?.id as string, poNode?.id as string, "O2O");
    addEdge(poCreateEvent?.id as string, poNode?.id as string, "E2O");

    return {
      enabled: highlightEnabled,
      nodeIds,
      edgeIds,
    };
  }, [candidate?.anchor_object_id, highlightEnabled, isMissingPrCreate, subgraph]);

  if (loading) {
    return (
      <div className="container">
        <Spinner label="Loading case" />
      </div>
    );
  }

  if (error || !detail || !candidate) {
    return (
      <div className="container">
        <div className="panel">{error || "Case not found."}</div>
      </div>
    );
  }

  return (
    <div className="container">
      <div className="header">
        <div className="brand">
          <div className="chip">Case Detail</div>
          <h1>{candidate.type}</h1>
        </div>
        <div className="split" style={{ alignItems: "center" }}>
          <button
            className="button secondary"
            type="button"
            onClick={async () => {
              try {
                await navigator.clipboard.writeText(caseUrl);
                setToast("Case URL copied.");
              } catch {
                setToast("Copy failed.");
              }
            }}
          >
            Copy URL
          </button>
          <CandidateId
            value={candidate.candidate_id}
            onCopy={() => setToast("Candidate ID copied.")}
            onCopyError={() => setToast("Copy failed.")}
          />
          <Link className="button secondary" to="/stats">
            View Stats
          </Link>
          <Link className="button secondary" to="/">
            Back to Queue
          </Link>
        </div>
      </div>

      <div className="grid grid-2" style={{ marginBottom: 20 }}>
        <div className="panel">
          <div className="panel-title">Summary</div>
          <div className="stack">
            <div><strong>Candidate:</strong> <span className="code">{candidate.candidate_id}</span></div>
            <div><strong>Anchor:</strong> {candidate.anchor_object_id}</div>
            <div><strong>Status:</strong> {candidate.status}</div>
            <div><strong>Scores:</strong> base {candidate.base_conf?.toFixed(2)} | final {candidate.final_conf?.toFixed(2)}</div>
            <div className="small">Created: {candidate.created_at} ({formatLocal(candidate.created_at)})</div>
            <div className="small">Updated: {candidate.updated_at} ({formatLocal(candidate.updated_at)})</div>
            <div><strong>Reason:</strong> {(features as any)?.maverick_reason || "-"}</div>
            <div className="small">Missing events: {missingEvents?.join(", ") || "-"}</div>
            <div className="small">
              S/R/I/Q: {scoreFlags.S?.toFixed?.(2) ?? "-"} / {scoreFlags.R?.toFixed?.(2) ?? "-"} / {scoreFlags.I?.toFixed?.(2) ?? "-"} / {scoreFlags.Q?.toFixed?.(2) ?? "-"}
            </div>
          </div>
        </div>
        <div className="panel">
          <div className="panel-title">Evidence Overview</div>
          <div className="stack">
            <div className="small">Event IDs</div>
            <div className="code">{(detail.evidence?.evidence_event_ids || []).join(", ") || "-"}</div>
            <div className="small">Object IDs</div>
            <div className="code">{(detail.evidence?.evidence_object_ids || []).join(", ") || "-"}</div>
            <div className="small">Features</div>
            <pre className="code" style={{ whiteSpace: "pre-wrap" }}>
              {JSON.stringify(features, null, 2)}
            </pre>
          </div>
        </div>
      </div>

      <div className="grid grid-2" style={{ marginBottom: 20 }}>
        <div className="panel">
          <div className="panel-title">Timeline</div>
          <Timeline items={timelineItems} missingEvents={missingEvents} />
        </div>
        <div className="panel">
          <div className="panel-title">Graph</div>
          {isMissingPrCreate && (
            <button
              className="button secondary"
              type="button"
              onClick={() => setHighlightEnabled((prev) => !prev)}
              style={{ marginBottom: 12 }}
            >
              {highlightEnabled ? "Disable" : "Enable"} Highlight Path
            </button>
          )}
          {graphLoading ? (
            <Spinner label="Loading graph" />
          ) : (
            <Graph graph={subgraph?.subgraph} highlight={highlightConfig} />
          )}
        </div>
      </div>

      <div className="grid grid-3" style={{ marginBottom: 20 }}>
        <LLMCard
          title="LLM Verify"
          latest={llmLatest?.verify}
          loading={verifyLoading}
          error={llmError}
          onAction={handleVerify}
          actionLabel="Run Verify"
          onToast={(message) => setToast(message)}
        />
        <LLMCard
          title="LLM Explain"
          latest={llmLatest?.explain}
          loading={explainLoading}
          error={llmError}
          onAction={handleExplain}
          actionLabel="Run Explain"
          onToast={(message) => setToast(message)}
        />
        <LabelCard
          latestLabel={detail.latest_label}
          onSubmit={handleLabel}
          loading={labelLoading}
          error={labelError}
        />
      </div>

      {toast && <Toast message={toast} onClose={() => setToast(null)} />}
    </div>
  );
}
