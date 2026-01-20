import React, { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { apiFetch } from "../api/client";
import { Candidate, ListResponse } from "../api/types";
import CandidateId from "../components/CandidateId";
import Spinner from "../components/Spinner";
import Toast from "../components/Toast";
import { formatLocal } from "../utils/time";

const TYPES = ["maverick_buying", "duplicate_payment", "lengthy_approval_pr", "lengthy_approval_po"];

function summaryText(candidate: Candidate) {
  const summary = candidate.features_preview || candidate.summary || {};
  const entries = Object.entries(summary).filter(([, value]) => value !== null && value !== undefined);
  if (!entries.length) return "-";
  return entries.map(([key, value]) => `${key}: ${value}`).join(" | ");
}

export default function Queue() {
  const [items, setItems] = useState<Candidate[]>([]);
  const [runId, setRunId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [type, setType] = useState<string>("");
  const [status, setStatus] = useState<string>("open");
  const [sort, setSort] = useState<string>("priority");
  const [search, setSearch] = useState<string>("");
  const [hasLlmOnly, setHasLlmOnly] = useState(false);
  const [highSeverityOnly, setHighSeverityOnly] = useState(false);
  const [offset, setOffset] = useState(0);
  const [limit] = useState(50);
  const [displayCount, setDisplayCount] = useState<number | null>(null);
  const [lastRefreshed, setLastRefreshed] = useState<string | null>(null);
  const [refreshToken, setRefreshToken] = useState(0);

  useEffect(() => {
    let active = true;
    const fetchList = async () => {
      setLoading(true);
      setError(null);
      try {
        const params = new URLSearchParams();
        params.set("limit", String(limit));
        params.set("offset", String(offset));
        if (type) params.set("type", type);
        if (status) params.set("status", status);
        const sortParam =
          sort === "priority"
            ? "priority"
            : sort === "severity"
              ? "severity"
              : sort === "confidence"
                ? "confidence"
                : sort === "newest"
                  ? "updated_at_desc"
                  : "final_conf_desc";
        params.set("sort", sortParam);
        const data = await apiFetch<ListResponse>(`/api/candidates?${params.toString()}`);
        if (!active) return;
        setItems(data.items || []);
        setRunId(data.run_id || (data.items && data.items[0]?.run_id) || null);
        setDisplayCount(typeof data.count === "number" ? data.count : null);
        setLastRefreshed(new Date().toLocaleString());
      } catch (err: any) {
        if (!active) return;
        setError(err.message || "Failed to load queue.");
        setToast(err.message || "Failed to load queue.");
      } finally {
        if (active) setLoading(false);
      }
    };
    fetchList();
    return () => {
      active = false;
    };
  }, [type, status, offset, limit, refreshToken, sort]);

  const filtered = useMemo(() => {
    let next = [...items];
    if (search) {
      next = next.filter((item) => item.candidate_id.includes(search));
    }
    if (hasLlmOnly) {
      next = next.filter((item) => Boolean(item.llm_preview?.verify_created_at));
    }
    if (highSeverityOnly) {
      next = next.filter((item) => (item.severity ?? -1) >= 0.7);
    }
    if (sort === "newest") {
      next.sort((a, b) => (b.created_at || "").localeCompare(a.created_at || ""));
    } else if (sort === "confidence") {
      next.sort((a, b) => (b.final_conf || 0) - (a.final_conf || 0));
    } else if (sort === "severity") {
      next.sort((a, b) => {
        const aScore = a.severity ?? -1;
        const bScore = b.severity ?? -1;
        if (bScore !== aScore) return bScore - aScore;
        if ((b.final_conf || 0) !== (a.final_conf || 0)) {
          return (b.final_conf || 0) - (a.final_conf || 0);
        }
        return (b.created_at || "").localeCompare(a.created_at || "");
      });
    } else if (sort === "priority") {
      next.sort((a, b) => {
        const aScore = a.priority_score ?? -1;
        const bScore = b.priority_score ?? -1;
        if (bScore !== aScore) return bScore - aScore;
        if ((b.final_conf || 0) !== (a.final_conf || 0)) {
          return (b.final_conf || 0) - (a.final_conf || 0);
        }
        return (b.created_at || "").localeCompare(a.created_at || "");
      });
    } else if (sort === "llm_priority") {
      const rank = (value?: string | null) => {
        if (value === "high") return 0;
        if (value === "medium") return 1;
        if (value === "low") return 2;
        return 3;
      };
      const toTime = (value?: string | null) => {
        if (!value) return 0;
        const ts = new Date(value).getTime();
        return Number.isNaN(ts) ? 0 : ts;
      };
      next.sort((a, b) => {
        const aRank = rank(a.llm_preview?.priority_hint);
        const bRank = rank(b.llm_preview?.priority_hint);
        if (aRank !== bRank) return aRank - bRank;
        const aTime = toTime(a.llm_preview?.verify_created_at);
        const bTime = toTime(b.llm_preview?.verify_created_at);
        if (aTime !== bTime) return bTime - aTime;
        if ((b.final_conf || 0) !== (a.final_conf || 0)) {
          return (b.final_conf || 0) - (a.final_conf || 0);
        }
        return a.candidate_id.localeCompare(b.candidate_id);
      });
    } else {
      next.sort((a, b) => (b.final_conf || 0) - (a.final_conf || 0));
    }
    return next;
  }, [items, search, sort, hasLlmOnly, highSeverityOnly]);

  useEffect(() => {
    setOffset(0);
  }, [type, status, sort]);

  const runLabel = runId || "N/A";
  const isTotalCount =
    displayCount !== null &&
    displayCount > items.length &&
    offset + items.length <= displayCount;
  const countLabel = isTotalCount
    ? `total: ${displayCount}`
    : `showing: ${items.length}`;

  return (
    <div className="container">
      <div className="header">
        <div className="brand">
          <div className="chip">HITL Queue</div>
          <h1>Karma Risk Triage</h1>
        </div>
        <div className="split" style={{ alignItems: "center" }}>
          <Link className="button secondary" to="/stats">
            View Stats
          </Link>
          <div className="panel" style={{ padding: 12 }}>
            <div className="panel-title" style={{ marginBottom: 8 }}>
              Latest Run
            </div>
            <div className="stack">
            <div className="split" style={{ alignItems: "center" }}>
              <span className="code">{runLabel}</span>
              <button
                className="button secondary"
                type="button"
                onClick={async () => {
                  try {
                    await navigator.clipboard.writeText(runLabel);
                    setToast("Run ID copied.");
                  } catch {
                    setToast("Copy failed.");
                  }
                }}
                disabled={runLabel === "N/A"}
              >
                Copy
              </button>
            </div>
            <div className="small">{countLabel}</div>
            <div className="small">Last refreshed: {lastRefreshed || "-"}</div>
            </div>
          </div>
        </div>
      </div>

      <div className="panel" style={{ marginBottom: 20 }}>
        <div className="controls">
          <select
            className="select"
            value={type}
            onChange={(e) => setType(e.target.value)}
          >
            <option value="">All types</option>
            {TYPES.map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </select>
          <select
            className="select"
            value={status}
            onChange={(e) => setStatus(e.target.value)}
          >
            <option value="">All status</option>
            <option value="open">open</option>
            <option value="closed">closed</option>
          </select>
          <select
            className="select"
            value={sort}
            onChange={(e) => setSort(e.target.value)}
          >
            <option value="priority">Sort: priority</option>
            <option value="severity">Sort: severity</option>
            <option value="confidence">Sort: confidence</option>
            <option value="newest">Sort: newest</option>
            <option value="llm_priority">Sort: LLM priority</option>
          </select>
          <button
            className="button secondary"
            type="button"
            onClick={() => setHasLlmOnly((prev) => !prev)}
          >
            {hasLlmOnly ? "Has LLM verify ✓" : "Has LLM verify"}
          </button>
          <button
            className="button secondary"
            type="button"
            onClick={() => setHighSeverityOnly((prev) => !prev)}
          >
            {highSeverityOnly ? "Severity ≥ 0.7 ✓" : "Severity ≥ 0.7"}
          </button>
          <input
            className="input"
            placeholder="Search candidate_id"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <button
            className="button secondary"
            type="button"
            disabled={loading}
            onClick={() => setRefreshToken((prev) => prev + 1)}
          >
            {loading ? "Refreshing..." : "Refresh"}
          </button>
        </div>
        {loading && <Spinner label="Loading queue" />}
        {error && <div className="small" style={{ color: "#b0301b" }}>{error}</div>}
        {!loading && filtered.length === 0 && <div className="small">No candidates found.</div>}
        {!loading && filtered.length > 0 && (
          <table className="table">
            <thead>
              <tr>
                <th>Candidate</th>
                <th>Type</th>
                <th>Status</th>
                <th>LLM</th>
                <th>Scores</th>
                <th>Summary</th>
                <th>Created</th>
                <th>Run</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((candidate) => (
                <tr key={candidate.candidate_id}>
                  <td>
                    <div className="stack">
              <CandidateId value={candidate.candidate_id} />
                      <Link className="button secondary" to={`/cases/${candidate.candidate_id}`}>
                        Open
                      </Link>
                    </div>
                  </td>
                  <td>{candidate.type}</td>
                  <td>
                    <span className="badge">{candidate.status}</span>
                  </td>
                  <td>
                    {candidate.llm_preview?.priority_hint ? (
                      <span className="badge">
                        LLM: {candidate.llm_preview.priority_hint}
                      </span>
                    ) : (
                      <span className="small">-</span>
                    )}
                  </td>
                  <td>
                    <div className="small">
                      base {candidate.base_conf?.toFixed(2)} | final {candidate.final_conf?.toFixed(2)}
                    </div>
                    <div className="small">
                      sev {candidate.severity?.toFixed(2) ?? "-"} | prio{" "}
                      {candidate.priority_score?.toFixed(2) ?? "-"}
                    </div>
                  </td>
                  <td>{summaryText(candidate)}</td>
                  <td>
                    <div className="small">{candidate.created_at || "-"}</div>
                    <div className="small">{formatLocal(candidate.created_at)}</div>
                  </td>
                  <td className="code">{candidate.run_id || runId || "-"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {!loading && (
          <div className="controls" style={{ marginTop: 12 }}>
            <button
              className="button secondary"
              type="button"
              disabled={offset === 0}
              onClick={() => setOffset(Math.max(0, offset - limit))}
            >
              Prev
            </button>
            <button
              className="button"
              type="button"
              disabled={items.length < limit}
              onClick={() => setOffset(offset + limit)}
            >
              Next
            </button>
          </div>
        )}
      </div>

      {toast && <Toast message={toast} onClose={() => setToast(null)} />}
    </div>
  );
}
