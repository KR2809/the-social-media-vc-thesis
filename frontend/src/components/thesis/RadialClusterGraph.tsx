"use client";

import { useMemo, useState } from "react";
import type { GraphEdge, GraphNode } from "./ForceGraph";

// Deterministic radial / hub-and-spoke layout for the bipartite
// founder ↔ theme graph. Per KG-viz best practice, a bipartite "entities
// grouped by shared attribute" graph should NOT use a force sim (hairball +
// instability) — instead place the theme hubs on a ring and cluster each
// founder near its dominant theme. Fully deterministic: no simulation, no
// drift, identical every render. Edges render on hover only.

interface Props {
  nodes: GraphNode[];
  edges: GraphEdge[];
  width?: number;
  height?: number;
  nodeColor: (kind: string) => string;
  onFounderClick?: (personId: string) => void;
  focusedId?: string | null;
}

export function RadialClusterGraph({
  nodes,
  edges,
  width = 760,
  height = 560,
  nodeColor,
  onFounderClick,
  focusedId,
}: Props) {
  const [hover, setHover] = useState<string | null>(null);

  const layout = useMemo(() => {
    const cx = width / 2;
    const cy = height / 2;
    const themes = nodes.filter(n => n.kind === "topic");
    const founders = nodes.filter(n => n.kind === "founder");

    // Theme hubs evenly on an inner ring, ordered by share (biggest first)
    // so the largest clusters are spaced predictably.
    const themesSorted = [...themes].sort((a, b) => (b.n_founders ?? 0) - (a.n_founders ?? 0));
    const themeAngle = new Map<string, number>();
    const ringR = Math.min(width, height) * 0.26;
    const pos = new Map<string, { x: number; y: number }>();
    themesSorted.forEach((t, i) => {
      const a = (i / Math.max(themesSorted.length, 1)) * Math.PI * 2 - Math.PI / 2;
      themeAngle.set(t.id, a);
      pos.set(t.id, { x: cx + Math.cos(a) * ringR, y: cy + Math.sin(a) * ringR });
    });

    // Each founder's dominant theme = max-weight incident edge.
    const domTheme = new Map<string, string>();
    const founderWeight = new Map<string, number>();
    for (const e of edges) {
      const w = e.weight ?? 1;
      if (!founderWeight.has(e.src) || w > founderWeight.get(e.src)!) {
        founderWeight.set(e.src, w);
        domTheme.set(e.src, e.dst);
      }
    }

    // Group founders by dominant theme, fan them out on an outer arc around
    // that theme's angle — deterministic, no overlap within a cluster.
    const byTheme = new Map<string, GraphNode[]>();
    for (const f of founders) {
      const t = domTheme.get(f.id) ?? themesSorted[0]?.id;
      if (!t) continue;
      (byTheme.get(t) ?? byTheme.set(t, []).get(t)!).push(f);
    }
    const outerR = Math.min(width, height) * 0.44;
    for (const [themeId, fs] of byTheme) {
      const base = themeAngle.get(themeId) ?? 0;
      const spread = Math.min(0.5, 0.12 * fs.length);
      fs.sort((a, b) => (b.weight ?? 0) - (a.weight ?? 0));
      fs.forEach((f, i) => {
        const off = fs.length === 1 ? 0 : (i / (fs.length - 1) - 0.5) * spread * 2;
        const a = base + off;
        const rr = outerR + (i % 2) * 26; // alternate radius to de-collide
        pos.set(f.id, { x: cx + Math.cos(a) * rr, y: cy + Math.sin(a) * rr });
      });
    }
    return pos;
  }, [nodes, edges, width, height]);

  const focusId = hover ?? focusedId ?? null;
  const neighbours = useMemo(() => {
    if (!focusId) return null;
    const s = new Set<string>([focusId]);
    for (const e of edges) {
      if (e.src === focusId) s.add(e.dst);
      if (e.dst === focusId) s.add(e.src);
    }
    return s;
  }, [focusId, edges]);

  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="fg-svg">
      {/* edges: faint by default, the focused node's light up */}
      {edges.map((e, i) => {
        const a = layout.get(e.src);
        const b = layout.get(e.dst);
        if (!a || !b) return null;
        const incident = neighbours && neighbours.has(e.src) && neighbours.has(e.dst);
        const op = incident ? 0.5 : neighbours ? 0.03 : 0.07;
        return (
          <line
            key={i}
            x1={a.x}
            y1={a.y}
            x2={b.x}
            y2={b.y}
            stroke="var(--accent)"
            strokeOpacity={op}
            strokeWidth={incident ? 1.4 : 0.6}
          />
        );
      })}
      {nodes.map(n => {
        const p = layout.get(n.id);
        if (!p) return null;
        const isTheme = n.kind === "topic";
        const r = isTheme ? 7 + Math.min((n.n_founders ?? 1) * 1.6, 16) : 5;
        const dim = neighbours && !neighbours.has(n.id);
        const showLabel = isTheme || focusId === n.id || hover === n.id;
        return (
          <g
            key={n.id}
            transform={`translate(${p.x},${p.y})`}
            style={{ cursor: onFounderClick && !isTheme ? "pointer" : "default", opacity: dim ? 0.22 : 1 }}
            onMouseEnter={() => setHover(n.id)}
            onMouseLeave={() => setHover(h => (h === n.id ? null : h))}
            onClick={() => !isTheme && onFounderClick?.(n.id.replace(/^Person:/, ""))}
          >
            <circle
              r={r}
              fill={nodeColor(n.kind)}
              fillOpacity={isTheme ? 0.85 : 1}
              stroke="var(--bg-card)"
              strokeWidth={1.5}
            />
            {showLabel && (
              <text
                y={r + (isTheme ? 14 : 11)}
                textAnchor="middle"
                fontFamily={isTheme ? "var(--sans)" : "var(--mono)"}
                fontSize={isTheme ? 11.5 : 9}
                fontWeight={isTheme ? 600 : 400}
                fill={isTheme ? "var(--ink-1)" : "var(--ink-2)"}
                stroke="var(--bg-card)"
                strokeWidth={isTheme ? 3.5 : 3}
                paintOrder="stroke"
                style={{ pointerEvents: "none" }}
              >
                {isTheme ? n.label : n.label.length > 20 ? n.label.slice(0, 19) + "…" : n.label}
              </text>
            )}
          </g>
        );
      })}
    </svg>
  );
}
