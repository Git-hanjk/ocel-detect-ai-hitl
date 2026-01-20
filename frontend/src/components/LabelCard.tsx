import React, { useState } from "react";

export default function LabelCard({
  latestLabel,
  onSubmit,
  loading,
  error,
}: {
  latestLabel?: Record<string, unknown> | null;
  onSubmit: (label: string, note: string) => void;
  loading?: boolean;
  error?: string | null;
}) {
  const [note, setNote] = useState("");

  return (
    <div className="panel">
      <div className="panel-title">HITL Label</div>
      {error && <div className="small" style={{ color: "#b0301b" }}>{error}</div>}
      <div className="stack">
        <div className="split">
          <button
            className="button"
            type="button"
            disabled={loading}
            onClick={() => onSubmit("confirm", note)}
          >
            Confirm
          </button>
          <button
            className="button secondary"
            type="button"
            disabled={loading}
            onClick={() => onSubmit("reject", note)}
          >
            Reject
          </button>
          <button
            className="button secondary"
            type="button"
            disabled={loading}
            onClick={() => onSubmit("unsure", note)}
          >
            Unsure
          </button>
        </div>
        <textarea
          className="input"
          placeholder="Add a short note"
          value={note}
          rows={3}
          onChange={(event) => setNote(event.target.value)}
        />
        {latestLabel && (
          <div className="small">
            Latest: {String(latestLabel.label || "")}
            {latestLabel.created_at ? ` • ${latestLabel.created_at}` : ""}
          </div>
        )}
      </div>
    </div>
  );
}
