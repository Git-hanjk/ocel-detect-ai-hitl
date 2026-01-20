import React, { useMemo, useState } from "react";
import { LLMResponse } from "../api/types";

function extractEvidence(latest?: LLMResponse | null): string[] {
  const raw = latest?.raw_json || {};
  const candidates = [
    latest?.evidence_used,
    raw["evidence_used"],
    raw["evidence"],
    raw["evidence_ids"],
  ];
  for (const entry of candidates) {
    if (Array.isArray(entry)) {
      return entry.map((value) => String(value));
    }
  }
  return [];
}

export default function LLMCard({
  latest,
  title,
  loading,
  error,
  onAction,
  actionLabel,
  onToast,
}: {
  latest?: LLMResponse | null;
  title: string;
  loading?: boolean;
  error?: string | null;
  onAction: () => void;
  actionLabel: string;
  onToast?: (message: string) => void;
}) {
  const [showEvidence, setShowEvidence] = useState(false);
  const evidenceIds = useMemo(() => extractEvidence(latest), [latest]);

  return (
    <div className="panel">
      <div className="panel-title">{title}</div>
      {error && <div className="small" style={{ color: "#b0301b" }}>{error}</div>}
      <div className="stack">
        <button type="button" className="button" onClick={onAction} disabled={loading}>
          {loading ? "Running..." : actionLabel}
        </button>
        {latest ? (
          <div className="stack">
            {latest?.verdict && <div><strong>Verdict:</strong> {latest.verdict}</div>}
            {latest?.v_conf !== undefined && latest?.v_conf !== null && (
              <div><strong>Confidence:</strong> {latest.v_conf}</div>
            )}
            {latest?.explanation && <div><strong>Summary:</strong> {latest.explanation}</div>}
            {latest?.raw_json && (
              <>
                {latest.raw_json["summary"] && (
                  <div><strong>Summary:</strong> {String(latest.raw_json["summary"])}</div>
                )}
                {latest.raw_json["short_summary"] && (
                  <div><strong>Short summary:</strong> {String(latest.raw_json["short_summary"])}</div>
                )}
                {Array.isArray(latest.raw_json["next_questions"]) && (
                  <div>
                    <strong>Next questions:</strong>
                    <ul>
                      {(latest.raw_json["next_questions"] as unknown[]).map((item, index) => (
                        <li key={`question-${index}`}>{String(item)}</li>
                      ))}
                    </ul>
                  </div>
                )}
                {Array.isArray(latest.raw_json["bullets"]) && (
                  <div>
                    <strong>Bullets:</strong>
                    <ul>
                      {(latest.raw_json["bullets"] as unknown[]).map((item, index) => (
                        <li key={`bullet-${index}`}>{String(item)}</li>
                      ))}
                    </ul>
                  </div>
                )}
                {latest.raw_json["one_liner"] && (
                  <div><strong>One-liner:</strong> {String(latest.raw_json["one_liner"])}</div>
                )}
                {latest.raw_json["why_anomalous"] && (
                  <div><strong>Why anomalous:</strong> {String(latest.raw_json["why_anomalous"])}</div>
                )}
                {latest.raw_json["evidence_summary"] && (
                  <div><strong>Evidence:</strong> {String(latest.raw_json["evidence_summary"])}</div>
                )}
              </>
            )}
            {latest?.raw_json && (
              <div className="small">Cached: {latest?.cached ? "yes" : "unknown"}</div>
            )}
            {typeof latest?.raw_json?.["priority_hint"] === "string" && (
              <div><strong>Priority:</strong> {String(latest.raw_json["priority_hint"])}</div>
            )}
            {latest?.raw_json && (
              <details>
                <summary className="small">Raw JSON</summary>
                <pre className="code" style={{ whiteSpace: "pre-wrap" }}>
                  {JSON.stringify(latest.raw_json, null, 2)}
                </pre>
              </details>
            )}
            {evidenceIds.length > 0 && (
              <div className="stack">
                <button
                  type="button"
                  className="button secondary"
                  onClick={() => setShowEvidence((prev) => !prev)}
                >
                  {showEvidence ? "Hide" : "Show"} evidence IDs ({evidenceIds.length})
                </button>
                {showEvidence && (
                  <div className="stack">
                    {evidenceIds.map((id) => (
                      <div key={id} className="split" style={{ alignItems: "center" }}>
                        <span className="code">{id}</span>
                        <button
                          type="button"
                          className="button secondary"
                          onClick={async () => {
                            try {
                              await navigator.clipboard.writeText(id);
                              onToast?.("Evidence ID copied.");
                            } catch {
                              onToast?.("Copy failed.");
                            }
                          }}
                        >
                          Copy
                        </button>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        ) : (
          <div className="small">No result yet.</div>
        )}
      </div>
    </div>
  );
}
