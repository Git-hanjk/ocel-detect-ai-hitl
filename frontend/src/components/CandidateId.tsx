import React, { useState } from "react";

function truncateId(value: string) {
  if (value.length <= 14) return value;
  return `${value.slice(0, 6)}...${value.slice(-6)}`;
}

export default function CandidateId({
  value,
  onCopy,
  onCopyError,
}: {
  value: string;
  onCopy?: () => void;
  onCopyError?: () => void;
}) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      onCopy?.();
      setTimeout(() => setCopied(false), 1500);
    } catch {
      setCopied(false);
      onCopyError?.();
    }
  };

  return (
    <div className="split" style={{ alignItems: "center", gap: 8 }}>
      <span className="code">{truncateId(value)}</span>
      <button type="button" className="button secondary" onClick={handleCopy}>
        {copied ? "Copied" : "Copy"}
      </button>
    </div>
  );
}
