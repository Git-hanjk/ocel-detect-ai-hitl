import React, { useEffect, useMemo, useRef, useState } from "react";
import cytoscape, { Core } from "cytoscape";

export type GraphData = {
  nodes: Array<Record<string, unknown>>;
  edges: Array<Record<string, unknown>>;
};

export type HighlightConfig = {
  enabled: boolean;
  nodeIds: Set<string>;
  edgeIds: Set<string>;
};

const OBJECT_COLORS: Record<string, string> = {
  purchase_order: "#d97745",
  purchase_requisition: "#c45252",
  quotation: "#7f8bd4",
  material: "#5aa469",
  "invoice receipt": "#c09a3d",
  "goods receipt": "#4d9aa6",
};

const DEFAULT_OBJECT_COLOR = "#b35b2b";
const EVENT_COLOR = "#1b7f79";
const EVENT_BORDER = "#0f4f4b";

function buildElements(graph?: GraphData | null, highlight?: HighlightConfig) {
  if (!graph) return [];
  const hasHighlight =
    highlight?.enabled && (highlight.nodeIds.size > 0 || highlight.edgeIds.size > 0);
  const nodes = (graph.nodes || [])
    .filter((node) => node && node.id)
    .map((node) => ({
      data: {
        id: String(node.id),
        type: node.type ?? "unknown",
        activity: node.activity ?? null,
        object_type: node.object_type ?? null,
      },
      classes: hasHighlight
        ? highlight?.nodeIds.has(String(node.id))
          ? "path"
          : "dim"
        : "",
    }));
  const edges = (graph.edges || [])
    .filter((edge) => edge && edge.source && edge.target)
    .map((edge, index) => {
      const id = `e-${index}-${edge.source}-${edge.target}`;
      return {
        data: {
          id,
          source: String(edge.source),
          target: String(edge.target),
          type: edge.type ?? "unknown",
          qualifier: edge.qualifier ?? null,
        },
        classes: hasHighlight ? (highlight?.edgeIds.has(id) ? "path" : "dim") : "",
      };
    });
  return [...nodes, ...edges];
}

export default function Graph({
  graph,
  highlight,
}: {
  graph?: GraphData | null;
  highlight?: HighlightConfig;
}) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const cyRef = useRef<Core | null>(null);
  const [tooltip, setTooltip] = useState<{ x: number; y: number; text: string } | null>(null);

  const elements = useMemo(() => buildElements(graph, highlight), [graph, highlight]);

  useEffect(() => {
    if (!containerRef.current) return;
    if (cyRef.current) {
      cyRef.current.destroy();
    }
    const cy = cytoscape({
      container: containerRef.current,
      elements,
      layout: { name: "cose", animate: true, padding: 20 },
      style: [
        {
          selector: "node",
          style: {
            label: "data(id)",
            "text-valign": "center",
            "text-halign": "center",
            "font-size": 10,
            "background-color": EVENT_COLOR,
            color: "#fff",
            shape: "ellipse",
            width: 40,
            height: 40,
            "border-color": EVENT_BORDER,
            "border-width": 2,
          },
        },
        {
          selector: "node[type = 'Object']",
          style: {
            "background-color": DEFAULT_OBJECT_COLOR,
            shape: "round-rectangle",
            width: 60,
            height: 30,
            "border-color": "#6e2f1b",
            "border-width": 1,
          },
        },
        ...Object.entries(OBJECT_COLORS).map(([objectType, color]) => ({
          selector: `node[type = 'Object'][object_type = '${objectType}']`,
          style: {
            "background-color": color,
          },
        })),
        {
          selector: "node[type = 'Event']",
          style: {
            shape: "diamond",
            "background-color": EVENT_COLOR,
          },
        },
        {
          selector: "edge",
          style: {
            "line-color": "#b8aa96",
            "target-arrow-color": "#b8aa96",
            "target-arrow-shape": "triangle",
            width: 1.4,
            "curve-style": "bezier",
          },
        },
        {
          selector: ".dim",
          style: {
            opacity: 0.15,
          },
        },
        {
          selector: "edge.path",
          style: {
            "line-color": "#111827",
            "target-arrow-color": "#111827",
            width: 2.2,
          },
        },
        {
          selector: "node.path",
          style: {
            opacity: 1,
            "border-width": 3,
            "border-color": "#111827",
          },
        },
      ],
    });

    cy.on("mouseover", "node", (event) => {
      const node = event.target;
      const activity = node.data("activity");
      const objectType = node.data("object_type");
      const id = node.id();
      const label = [id, activity, objectType].filter(Boolean).join(" | ");
      const pos = event.renderedPosition || { x: 0, y: 0 };
      setTooltip({ x: pos.x, y: pos.y, text: label });
    });

    cy.on("mouseout", "node", () => setTooltip(null));
    cyRef.current = cy;

    return () => {
      cy.destroy();
    };
  }, [elements]);

  return (
    <div style={{ position: "relative" }}>
      <div ref={containerRef} className="graph-wrap" />
      <button
        className="button secondary"
        type="button"
        style={{ position: "absolute", top: 12, right: 12 }}
        onClick={() => cyRef.current?.fit()}
      >
        Fit to screen
      </button>
      {tooltip && (
        <div
          className="panel"
          style={{
            position: "absolute",
            left: tooltip.x,
            top: tooltip.y,
            padding: "6px 10px",
            fontSize: 12,
            pointerEvents: "none",
            transform: "translate(6px, 6px)",
          }}
        >
          {tooltip.text}
        </div>
      )}
      <div
        className="panel"
        style={{
          position: "absolute",
          left: 12,
          bottom: 12,
          padding: "8px 10px",
          fontSize: 12,
          maxWidth: 220,
        }}
      >
        <div className="small" style={{ marginBottom: 6 }}>
          Legend
        </div>
        <div className="stack">
          {Object.entries(OBJECT_COLORS).map(([key, color]) => (
            <div key={key} className="split" style={{ alignItems: "center" }}>
              <span
                style={{
                  width: 12,
                  height: 12,
                  borderRadius: 3,
                  background: color,
                  display: "inline-block",
                }}
              />
              <span className="small">{key}</span>
            </div>
          ))}
          <div className="split" style={{ alignItems: "center" }}>
            <span
              style={{
                width: 12,
                height: 12,
                borderRadius: "50%",
                background: EVENT_COLOR,
                border: `2px solid ${EVENT_BORDER}`,
                display: "inline-block",
              }}
            />
            <span className="small">event</span>
          </div>
        </div>
      </div>
    </div>
  );
}
