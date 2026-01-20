import React from "react";
import { formatLocal } from "../utils/time";

export type TimelineItem = {
  event_id?: string;
  activity?: string;
  ts?: string | null;
  resource?: string | null;
  lifecycle?: string | null;
  linked_object_ids?: string[];
  placeholder?: boolean;
};

export default function Timeline({
  items,
  missingEvents,
}: {
  items: TimelineItem[];
  missingEvents?: string[];
}) {
  const placeholders: TimelineItem[] = (missingEvents || []).map((activity) => ({
    activity,
    ts: "NOT FOUND",
    placeholder: true,
  }));
  const merged: TimelineItem[] = [...items, ...placeholders];
  const sorted = merged.map((item, index) => ({
    item,
    index,
  }));
  sorted.sort((a, b) => {
    const aTs = a.item.ts && a.item.ts !== "NOT FOUND" ? a.item.ts : null;
    const bTs = b.item.ts && b.item.ts !== "NOT FOUND" ? b.item.ts : null;
    if (aTs && bTs) {
      const cmp = aTs.localeCompare(bTs);
      if (cmp !== 0) return cmp;
    }
    if (aTs && !bTs) return -1;
    if (!aTs && bTs) return 1;
    return a.index - b.index;
  });

  return (
    <div className="timeline">
      {sorted.map(({ item }, index) => (
        <div key={`${item.event_id || item.activity}-${index}`} className="timeline-item">
          <div className="split" style={{ justifyContent: "space-between" }}>
            <strong>{item.activity || "Unknown"}</strong>
            <span className="code">{item.ts || ""}</span>
          </div>
          {item.ts && item.ts !== "NOT FOUND" && (
            <div className="small">{formatLocal(item.ts)}</div>
          )}
          {item.event_id && <div className="small code">{item.event_id}</div>}
          {item.resource && <div className="small">Resource: {item.resource}</div>}
          {item.lifecycle && <div className="small">Lifecycle: {item.lifecycle}</div>}
          {item.linked_object_ids && item.linked_object_ids.length > 0 && (
            <div className="small code">Linked: {item.linked_object_ids.join(", ")}</div>
          )}
          {item.placeholder && <div className="small">NOT FOUND placeholder</div>}
        </div>
      ))}
    </div>
  );
}
