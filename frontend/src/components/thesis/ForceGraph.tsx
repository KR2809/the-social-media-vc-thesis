"use client";

import { useEffect, useMemo, useRef, useState } from "react";

// Minimal hand-rolled force-directed graph in SVG — no d3/external deps.
// Verlet-ish integration: charge repulsion (Coulomb) + link springs (Hooke)
// + gentle centering gravity. Good for up to a few hundred nodes. Matches
// the demo's hand-styled aesthetic; nodes are draggable, graph pans/zooms.

export interface GraphNode {
  id: string;
  kind: string;
  label: string;
  weight?: number;
  shared?: boolean;
  n_founders?: number;
}
export interface GraphEdge {
  src: string;
  dst: string;
  relation?: string;
  weight?: number;
}

interface Pt {
  x: number;
  y: number;
  vx: number;
  vy: number;
}

interface Props {
  nodes: GraphNode[];
  edges: GraphEdge[];
  width?: number;
  height?: number;
  nodeColor: (kind: string) => string;
  nodeRadius?: (n: GraphNode) => number;
  labelFor?: (n: GraphNode) => string | null;
  onNodeClick?: (n: GraphNode) => void;
  /** Pin these node ids near the centre (e.g. the focused founder). */
  highlightId?: string | null;
}

export function ForceGraph({
  nodes,
  edges,
  width = 720,
  height = 520,
  nodeColor,
  nodeRadius,
  labelFor,
  onNodeClick,
  highlightId,
}: Props) {
  const radius = useMemo(
    () => nodeRadius ?? ((n: GraphNode) => 5 + Math.sqrt(n.weight ?? 1) * 2),
    [nodeRadius],
  );

  // Stable mutable positions for the sim (ref), plus a published snapshot
  // the render reads from (state) — avoids reading refs during render.
  const posRef = useRef<Map<string, Pt>>(new Map());
  const [snapshot, setSnapshot] = useState<Map<string, Pt>>(new Map());
  const publish = () => setSnapshot(new Map(posRef.current));
  const [hover, setHover] = useState<string | null>(null);
  const [drag, setDrag] = useState<string | null>(null);
  const svgRef = useRef<SVGSVGElement | null>(null);
  const [view, setView] = useState({ k: 1, x: 0, y: 0 });

  // (Re)seed positions when the node set changes.
  useEffect(() => {
    const pos = posRef.current;
    const ids = new Set(nodes.map(n => n.id));
    for (const id of [...pos.keys()]) if (!ids.has(id)) pos.delete(id);
    nodes.forEach((n, i) => {
      if (!pos.has(n.id)) {
        // seed on a ring so the sim unfolds cleanly
        const a = (i / Math.max(nodes.length, 1)) * Math.PI * 2;
        const r = n.id === highlightId ? 0 : 120 + (i % 5) * 30;
        pos.set(n.id, { x: width / 2 + Math.cos(a) * r, y: height / 2 + Math.sin(a) * r, vx: 0, vy: 0 });
      }
    });
  }, [nodes, width, height, highlightId]);

  // Simulation loop.
  useEffect(() => {
    const pos = posRef.current;
    const adj = edges
      .map(e => [e.src, e.dst, e.weight ?? 1] as const)
      .filter(([a, b]) => pos.has(a) && pos.has(b));
    let frame = 0;
    let raf = 0;
    const MAX_FRAMES = 320;

    function step() {
      frame++;
      const arr = nodes.map(n => n.id).filter(id => pos.has(id));
      // charge repulsion (O(n^2) — fine at our scale)
      for (let i = 0; i < arr.length; i++) {
        const a = pos.get(arr[i])!;
        for (let j = i + 1; j < arr.length; j++) {
          const b = pos.get(arr[j])!;
          let dx = a.x - b.x;
          let dy = a.y - b.y;
          let d2 = dx * dx + dy * dy;
          if (d2 < 0.01) {
            dx = Math.random() - 0.5;
            dy = Math.random() - 0.5;
            d2 = 0.01;
          }
          const f = 2400 / d2;
          const d = Math.sqrt(d2);
          a.vx += (dx / d) * f;
          a.vy += (dy / d) * f;
          b.vx -= (dx / d) * f;
          b.vy -= (dy / d) * f;
        }
      }
      // link springs
      for (const [s, t, w] of adj) {
        const a = pos.get(s)!;
        const b = pos.get(t)!;
        const dx = b.x - a.x;
        const dy = b.y - a.y;
        const d = Math.sqrt(dx * dx + dy * dy) || 1;
        const target = 70;
        const f = (d - target) * 0.015 * Math.min(1 + w * 0.1, 2);
        a.vx += (dx / d) * f;
        a.vy += (dy / d) * f;
        b.vx -= (dx / d) * f;
        b.vy -= (dy / d) * f;
      }
      // centering gravity + integrate
      for (const id of arr) {
        const p = pos.get(id)!;
        if (id === drag) continue;
        p.vx += (width / 2 - p.x) * 0.002;
        p.vy += (height / 2 - p.y) * 0.002;
        if (id === highlightId) {
          p.vx += (width / 2 - p.x) * 0.04;
          p.vy += (height / 2 - p.y) * 0.04;
        }
        p.vx *= 0.85;
        p.vy *= 0.85;
        p.x += p.vx;
        p.y += p.vy;
      }
      publish();
      if (frame < MAX_FRAMES) raf = requestAnimationFrame(step);
    }
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
    // Re-run the sim when the graph identity changes.
  }, [nodes, edges, width, height, drag, highlightId]);

  // Drag handling in SVG user space (account for zoom/pan).
  function toUser(clientX: number, clientY: number) {
    const svg = svgRef.current;
    if (!svg) return { x: 0, y: 0 };
    const r = svg.getBoundingClientRect();
    const px = ((clientX - r.left) / r.width) * width;
    const py = ((clientY - r.top) / r.height) * height;
    return { x: (px - view.x) / view.k, y: (py - view.y) / view.k };
  }

  useEffect(() => {
    if (!drag) return;
    function move(e: MouseEvent) {
      const p = posRef.current.get(drag!);
      if (!p) return;
      const u = toUser(e.clientX, e.clientY);
      p.x = u.x;
      p.y = u.y;
      p.vx = 0;
      p.vy = 0;
      publish();
    }
    function up() {
      setDrag(null);
    }
    window.addEventListener("mousemove", move);
    window.addEventListener("mouseup", up);
    return () => {
      window.removeEventListener("mousemove", move);
      window.removeEventListener("mouseup", up);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [drag, view]);

  const pos = snapshot;
  const neighbours = useMemo(() => {
    if (!hover) return null;
    const s = new Set<string>([hover]);
    for (const e of edges) {
      if (e.src === hover) s.add(e.dst);
      if (e.dst === hover) s.add(e.src);
    }
    return s;
  }, [hover, edges]);

  return (
    <svg
      ref={svgRef}
      viewBox={`0 0 ${width} ${height}`}
      className="fg-svg"
      onWheel={e => {
        const delta = -e.deltaY * 0.0015;
        setView(v => ({ ...v, k: Math.min(3, Math.max(0.4, v.k + delta)) }));
      }}
    >
      <g transform={`translate(${view.x},${view.y}) scale(${view.k})`}>
        {edges.map((e, i) => {
          const a = pos.get(e.src);
          const b = pos.get(e.dst);
          if (!a || !b) return null;
          const dim = neighbours && !(neighbours.has(e.src) && neighbours.has(e.dst));
          return (
            <line
              key={i}
              x1={a.x}
              y1={a.y}
              x2={b.x}
              y2={b.y}
              stroke="var(--accent)"
              strokeOpacity={dim ? 0.04 : 0.18 + Math.min((e.weight ?? 1) * 0.05, 0.4)}
              strokeWidth={0.5 + Math.min((e.weight ?? 1) * 0.4, 3)}
            />
          );
        })}
        {nodes.map(n => {
          const p = pos.get(n.id);
          if (!p) return null;
          const r = radius(n);
          const dim = neighbours && !neighbours.has(n.id);
          const lab = labelFor ? labelFor(n) : n.label;
          return (
            <g
              key={n.id}
              transform={`translate(${p.x},${p.y})`}
              style={{ cursor: onNodeClick ? "pointer" : "grab", opacity: dim ? 0.25 : 1 }}
              onMouseEnter={() => setHover(n.id)}
              onMouseLeave={() => setHover(h => (h === n.id ? null : h))}
              onMouseDown={() => setDrag(n.id)}
              onClick={() => onNodeClick?.(n)}
            >
              <circle r={r} fill={nodeColor(n.kind)} fillOpacity={n.kind === "founder" ? 1 : 0.82} stroke="var(--bg-card)" strokeWidth={1.5} />
              {(n.kind === "founder" || (n.kind === "topic" && (n.weight ?? 0) > 1) || hover === n.id) && lab && (
                <text
                  y={r + 11}
                  textAnchor="middle"
                  fontFamily="var(--mono)"
                  fontSize={n.kind === "founder" ? 10 : 9}
                  fill={n.kind === "founder" ? "var(--ink-1)" : "var(--ink-2)"}
                  fontWeight={n.kind === "founder" ? 600 : 400}
                >
                  {lab.length > 22 ? lab.slice(0, 21) + "…" : lab}
                </text>
              )}
            </g>
          );
        })}
      </g>
    </svg>
  );
}
