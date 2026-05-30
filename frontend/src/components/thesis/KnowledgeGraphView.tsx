"use client";

import { useEffect, useState } from "react";
import { fetchCohortKG, type KGResult } from "@/lib/thesis/kg";
import { ForceGraph, type GraphNode } from "./ForceGraph";
import { InfoTip } from "./InfoTip";
import { EpistemeBar, ViewIntro } from "./primitives";

const KIND_COLOR: Record<string, string> = {
  founder: "var(--accent-deep)",
  topic: "var(--accent)",
  signal: "var(--ink-2)",
  platform: "var(--ink-3)",
};

function kgColor(kind: string): string {
  return KIND_COLOR[kind] ?? "var(--ink-1)";
}

export function KnowledgeGraphView() {
  const [kg, setKg] = useState<KGResult | null>(null);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    let alive = true;
    fetchCohortKG()
      .then(r => alive && setKg(r))
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, []);

  const ready = kg && kg.source === "backend";

  return (
    <section className="view view-kg">
      <ViewIntro kicker="KNOWLEDGE GRAPH" title="What the cohort is really made of">
        Every scored signal is a node in a knowledge graph; here we project the{" "}
        <strong>real graph</strong> down to <strong>founders and the themes they signal about</strong>{" "}
        (signals collapsed into edge weight). Founders wired to the same theme cluster together — drag
        a node, hover to isolate a neighbourhood, scroll to zoom.
      </ViewIntro>

      {ready && (
        <>
          <div className="kg-stats">
            <span className="kg-stat">
              <span className="kg-stat-num mono">{kg.meta.n_founders}</span> founders
            </span>
            <span className="kg-stat">
              <span className="kg-stat-num mono">{kg.meta.n_themes}</span> themes
              <InfoTip width={320}>
                The ~2,000 granular LLM topic labels are bucketed into coarse themes (SaaS &amp;
                bootstrapping, AI &amp; tooling, Audience &amp; newsletters, …) so shared interests
                surface as shared hubs. The underlying graph has 4,235 nodes / 178k edges.
              </InfoTip>
            </span>
            <span className="kg-stat">
              <span className="kg-stat-num mono">{kg.meta.n_shared_themes}</span> shared
            </span>
            <span className="kg-legend">
              <span><span className="dot" style={{ background: "var(--accent-deep)" }} /> founder</span>
              <span><span className="dot" style={{ background: "var(--accent)" }} /> theme</span>
            </span>
          </div>
          <div className="kg-canvas">
            <ForceGraph
              nodes={kg.nodes}
              edges={kg.edges}
              width={760}
              height={560}
              nodeColor={kgColor}
              nodeRadius={(n: GraphNode) =>
                n.kind === "founder" ? 7 : 6 + Math.min((n.n_founders ?? 1) * 2, 16)}
            />
          </div>
        </>
      )}

      {!ready && (
        <div className="future-banner">
          <span className="kicker">{loading ? "Loading knowledge graph…" : "Knowledge graph unavailable"}</span>
          <span>
            {loading
              ? "Projecting the real KG from the API."
              : "The KG API (/api/kg/cohort) isn't reachable — start the FastAPI backend to render the real graph."}
          </span>
        </div>
      )}

      <EpistemeBar>
        Projection of the real knowledge graph (<strong>4,235 nodes · 178k edges</strong>, also mirrored
        in Supabase). Themes are a coarse bucketing of the LLM topic labels for legibility; the full
        per-signal graph backs every node. Node size = how many founders share a theme.
      </EpistemeBar>
    </section>
  );
}
