// Real knowledge-graph loaders — fetch the server-side KG projections
// (analysis/kg_views.py via /api/kg/*). Graceful "unavailable" fallback so
// the views degrade rather than blank when the API is down.

import { API_BASE_URL } from "./config";
import type { GraphEdge, GraphNode } from "@/components/thesis/ForceGraph";

export interface KGResult {
  nodes: GraphNode[];
  edges: GraphEdge[];
  source: "backend" | "unavailable";
  meta: Record<string, number>;
}

const cohortCache: { v: KGResult | null } = { v: null };
const egoCache = new Map<string, KGResult>();

function empty(): KGResult {
  return { nodes: [], edges: [], source: "unavailable", meta: {} };
}

export async function fetchCohortKG(): Promise<KGResult> {
  if (cohortCache.v) return cohortCache.v;
  try {
    const res = await fetch(`${API_BASE_URL}/api/kg/cohort`, { headers: { accept: "application/json" } });
    if (!res.ok) return empty();
    const j = await res.json();
    if (!j.nodes?.length) return empty();
    const r: KGResult = {
      nodes: j.nodes,
      edges: j.edges,
      source: "backend",
      meta: {
        n_founders: j.n_founders ?? 0,
        n_themes: j.n_themes ?? 0,
        n_shared_themes: j.n_shared_themes ?? 0,
      },
    };
    cohortCache.v = r;
    return r;
  } catch {
    return empty();
  }
}

export async function fetchEgoKG(personId: string, topSignals = 12): Promise<KGResult> {
  const key = `${personId}:${topSignals}`;
  const cached = egoCache.get(key);
  if (cached) return cached;
  try {
    const res = await fetch(
      `${API_BASE_URL}/api/kg/ego/${encodeURIComponent(personId)}?top_signals=${topSignals}`,
      { headers: { accept: "application/json" } },
    );
    if (!res.ok) return empty();
    const j = await res.json();
    if (!j.nodes?.length) return empty();
    const r: KGResult = {
      nodes: j.nodes,
      edges: j.edges,
      source: "backend",
      meta: { n_signals: j.n_signals ?? 0 },
    };
    egoCache.set(key, r);
    return r;
  } catch {
    return empty();
  }
}
