import React from "react";

export default function Spinner({ label = "Loading" }: { label?: string }) {
  return (
    <div className="stack" style={{ alignItems: "center", padding: "20px" }}>
      <div
        style={{
          width: 34,
          height: 34,
          borderRadius: "50%",
          border: "3px solid #e8dccb",
          borderTop: "3px solid #c4552f",
          animation: "spin 1s linear infinite",
        }}
      />
      <span className="small">{label}...</span>
    </div>
  );
}
