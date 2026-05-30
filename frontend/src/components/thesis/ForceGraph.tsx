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
  // Re-heat target for the cooling schedule: 0 = freeze, >0 = keep warm
  // (set to 0.3 on drag so the layout responds, back to 0 on release).
  const alphaTarget = useRef(0);
  const [hover, setHover] = useState<string | null>(null);
  const [drag, setDrag] = useState<string | null>(null);
  const svgRef = useRef<SVGSVGElement | null>(null);
  const [view, setView] = useState({ k: 1, x: 0, y: 0 });

  // (Re)seed positions DETERMINISTICALLY when the node set changes — a
  // phyllotaxis spiral by index, so the layout is reproducible run-to-run
  // (no Math.random) and converges from a spread-out start.
  useEffect(() => {
    const pos = posRef.current;
    const ids = new Set(nodes.map(n => n.id));
    for (const id of [...pos.keys()]) if (!ids.has(id)) pos.delete(id);
    nodes.forEach((n, i) => {
      if (!pos.has(n.id)) {
        if (n.id === highlightId) {
          pos.set(n.id, { x: width / 2, y: height / 2, vx: 0, vy: 0 });
          return;
        }
        // phyllotaxis: golden-angle spiral fills space evenly + deterministically
        const a = i * 2.399963; // golden angle (radians)
        const r = 12 + Math.sqrt(i) * 18;
        pos.set(n.id, { x: width / 2 + Math.cos(a) * r, y: height / 2 + Math.sin(a) * r, vx: 0, vy: 0 });
      }
    });
  }, [nodes, width, height, highlightId]);

  // Simulation loop with a real cooling schedule (d3-force style): forces
  // are scaled by alpha; alpha decays each tick and the sim STOPS when it
  // drops below alphaMin — so the layout settles and freezes (no drift).
  useEffect(() => {
    const pos = posRef.current;
    const radiusOf = new Map(nodes.map(n => [n.id, radius(n)] as const));
    const adj = edges
      .map(e => [e.src, e.dst, e.weight ?? 1] as const)
      .filter(([a, b]) => pos.has(a) && pos.has(b));
    const ALPHA_DECAY = 0.0228;
    const ALPHA_MIN = 0.001;
    const VELOCITY_DECAY = 0.4; // friction: v *= (1 - 0.4)
    let alpha = 1;
    let raf = 0;

    function step() {
      // 1. cool
      alpha += (alphaTarget.current - alpha) * ALPHA_DECAY;
      const arr = nodes.map(n => n.id).filter(id => pos.has(id));

      // 2a. many-body repulsion (charge) — scaled by alpha for global spread
      for (let i = 0; i < arr.length; i++) {
        const a = pos.get(arr[i])!;
        for (let j = i + 1; j < arr.length; j++) {
          const b = pos.get(arr[j])!;
          let dx = a.x - b.x;
          let dy = a.y - b.y;
          let d2 = dx * dx + dy * dy;
          if (d2 < 0.01) {
            dx = ((i % 7) - 3) * 0.1 + 0.05;
            dy = ((j % 7) - 3) * 0.1 + 0.05;
            d2 = dx * dx + dy * dy || 0.01;
          }
          const d = Math.sqrt(d2);
          const f = (1800 / d2) * alpha;
          a.vx += (dx / d) * f;
          a.vy += (dy / d) * f;
          b.vx -= (dx / d) * f;
          b.vy -= (dy / d) * f;
        }
      }
      // 2b. collision: hard local non-overlap (radius + padding)
      for (let i = 0; i < arr.length; i++) {
        const a = pos.get(arr[i])!;
        const ra = (radiusOf.get(arr[i]) ?? 6) + 6;
        for (let j = i + 1; j < arr.length; j++) {
          const b = pos.get(arr[j])!;
          const rb = (radiusOf.get(arr[j]) ?? 6) + 6;
          const dx = b.x - a.x;
          const dy = b.y - a.y;
          const min = ra + rb;
          const d = Math.sqrt(dx * dx + dy * dy) || 0.01;
          if (d < min) {
            const push = ((min - d) / d) * 0.5 * 0.8; // strength 0.8
            a.x -= dx * push;
            a.y -= dy * push;
            b.x += dx * push;
            b.y += dy * push;
          }
        }
      }
      // 2c. link springs — scaled by alpha
      for (const [s, t, w] of adj) {
        const a = pos.get(s)!;
        const b = pos.get(t)!;
        const dx = b.x - a.x;
        const dy = b.y - a.y;
        const d = Math.sqrt(dx * dx + dy * dy) || 1;
        const target = 64;
        const f = (d - target) * 0.04 * Math.min(1 + w * 0.06, 1.8) * alpha;
        a.vx += (dx / d) * f;
        a.vy += (dy / d) * f;
        b.vx -= (dx / d) * f;
        b.vy -= (dy / d) * f;
      }
      // 3. centering (scaled by alpha) + friction + integrate + clamp
      const pad = 16;
      for (const id of arr) {
        const p = pos.get(id)!;
        if (id === drag) continue;
        p.vx += (width / 2 - p.x) * 0.02 * alpha;
        p.vy += (height / 2 - p.y) * 0.02 * alpha;
        if (id === highlightId) {
          p.vx += (width / 2 - p.x) * 0.06 * alpha;
          p.vy += (height / 2 - p.y) * 0.06 * alpha;
        }
        p.vx *= 1 - VELOCITY_DECAY;
        p.vy *= 1 - VELOCITY_DECAY;
        p.x += p.vx;
        p.y += p.vy;
        // hard clamp so nodes never drift off-canvas
        const r = radiusOf.get(id) ?? 6;
        p.x = Math.max(pad + r, Math.min(width - pad - r, p.x));
        p.y = Math.max(pad + r, Math.min(height - pad - r, p.y));
      }
      publish();
      // 4. stop when cooled (or keep going while re-heated via alphaTarget)
      if (alpha > ALPHA_MIN || alphaTarget.current > 0) {
        raf = requestAnimationFrame(step);
      }
    }
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
    // Re-run the sim when the graph identity changes.
  }, [nodes, edges, width, height, drag, highlightId, radius]);

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
    alphaTarget.current = 0.3; // keep the sim warm while dragging
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
      alphaTarget.current = 0; // let it cool + freeze again
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
  // Focus = the hovered node, else the highlighted (founder) node. Its
  // incident edges render bright; everything else is faint. This is the
  // single biggest anti-hairball move — we never show all edges at full
  // strength at once.
  const focusId = hover ?? highlightId ?? null;
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
          const incident = neighbours && neighbours.has(e.src) && neighbours.has(e.dst);
          // Faint by default (structure visible but not a hairball); the
          // focused node's edges light up.
          const op = incident ? 0.55 : neighbours ? 0.03 : 0.08;
          return (
            <line
              key={i}
              x1={a.x}
              y1={a.y}
              x2={b.x}
              y2={b.y}
              stroke="var(--accent)"
              strokeOpacity={op}
              strokeWidth={incident ? 1 + Math.min((e.weight ?? 1) * 0.4, 3) : 0.6}
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
                  stroke="var(--bg-card)"
                  strokeWidth={3}
                  paintOrder="stroke"
                  style={{ pointerEvents: "none" }}
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
