import React, { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { apiFetch } from "../api/client";
import { StatsResponse } from "../api/types";
import Spinner from "../components/Spinner";
import Toast from "../components/Toast";

export default function Stats() {
  const [stats, setStats] = useState<StatsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [toast, setToast] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        const data = await apiFetch<StatsResponse>("/api/stats");
        if (!active) return;
        setStats(data);
      } catch (err: any) {
        if (!active) return;
        setError(err.message || "Failed to load stats.");
        setToast(err.message || "Failed to load stats.");
      } finally {
        if (active) setLoading(false);
      }
    };
    load();
    return () => {
      active = false;
    };
  }, []);

  const accuracyOverall = useMemo(() => {
    if (!stats) return "-";
    if (stats.accuracy.accuracy === null) return "-";
    return `${(stats.accuracy.accuracy * 100).toFixed(1)}%`;
  }, [stats]);

  if (loading) {
    return (
      <div className="container">
        <Spinner label="Loading stats" />
      </div>
    );
  }

  if (error || !stats) {
    return (
      <div className="container">
        <div className="panel">{error || "Stats not available."}</div>
      </div>
    );
  }

  const runIdLabel = stats.run_id || "N/A";
  const coverage = stats.totals.candidates
    ? `${(stats.totals.coverage * 100).toFixed(1)}%`
    : "-";

  return (
    <div className="container">
      <div className="header">
        <div className="brand">
          <div className="chip">Stats</div>
          <h1>Operational Metrics</h1>
        </div>
        <div className="split" style={{ alignItems: "center" }}>
          <div className="panel" style={{ padding: 12 }}>
            <div className="small">Latest run_id</div>
            <div className="code">{runIdLabel}</div>
          </div>
          <Link className="button secondary" to="/">
            Back to Queue
          </Link>
        </div>
      </div>

      <div className="grid grid-3" style={{ marginBottom: 20 }}>
        <div className="panel">
          <div className="panel-title">Totals</div>
          <div className="stack">
            <div><strong>Candidates:</strong> {stats.totals.candidates}</div>
            <div><strong>Labeled:</strong> {stats.totals.labeled}</div>
            <div><strong>Coverage:</strong> {coverage}</div>
          </div>
        </div>
        <div className="panel">
          <div className="panel-title">Accuracy Proxy</div>
          <div className="stack">
            <div><strong>Confirm:</strong> {stats.accuracy.confirm}</div>
            <div><strong>Reject:</strong> {stats.accuracy.reject}</div>
            <div><strong>Accuracy:</strong> {accuracyOverall}</div>
          </div>
        </div>
        <div className="panel">
          <div className="panel-title">Labels</div>
          <div className="stack">
            {stats.labels.map((row) => (
              <div key={row.label}>
                <strong>{row.label}</strong>: {row.count}
              </div>
            ))}
            {stats.labels.length === 0 && <div className="small">No labels yet.</div>}
          </div>
        </div>
      </div>

      <div className="grid grid-2" style={{ marginBottom: 20 }}>
        <div className="panel">
          <div className="panel-title">Candidates by Type</div>
          <table className="table">
            <thead>
              <tr>
                <th>Type</th>
                <th>Count</th>
              </tr>
            </thead>
            <tbody>
              {stats.by_type.map((row) => (
                <tr key={row.type}>
                  <td>{row.type}</td>
                  <td>{row.count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="panel">
          <div className="panel-title">Candidates by Status</div>
          <table className="table">
            <thead>
              <tr>
                <th>Status</th>
                <th>Count</th>
              </tr>
            </thead>
            <tbody>
              {stats.by_status.map((row) => (
                <tr key={row.status}>
                  <td>{row.status}</td>
                  <td>{row.count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="panel">
        <div className="panel-title">Accuracy by Type</div>
        <table className="table">
          <thead>
            <tr>
              <th>Type</th>
              <th>Confirm</th>
              <th>Reject</th>
              <th>Accuracy</th>
            </tr>
          </thead>
          <tbody>
            {stats.accuracy_by_type.map((row) => (
              <tr key={row.type}>
                <td>{row.type}</td>
                <td>{row.confirm}</td>
                <td>{row.reject}</td>
                <td>{row.accuracy === null ? "-" : `${(row.accuracy * 100).toFixed(1)}%`}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {toast && <Toast message={toast} onClose={() => setToast(null)} />}
    </div>
  );
}
