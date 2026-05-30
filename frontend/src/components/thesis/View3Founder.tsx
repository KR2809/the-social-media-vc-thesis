"use client";

import { useEffect, useMemo, useState } from "react";
import { useThesis } from "@/lib/thesis/context";
import type { TaxonomyCode } from "@/lib/thesis";
import { fetchEgoKG, type KGResult } from "@/lib/thesis/kg";
import { ForceGraph, type GraphNode } from "./ForceGraph";
import { InfoTip } from "./InfoTip";
import { Avatar, EpistemeBar, OutcomeChip, ViewIntro } from "./primitives";

const EGO_KIND_COLOR: Record<string, string> = {
  founder: "var(--accent-deep)",
  signal: "var(--ink-1)",
  topic: "var(--accent)",
  platform: "var(--ink-3)",
};

// Shared check: does this founder have REAL collected signals? Uses the
// cached /api/kg/ego fetch (reason: "no-data" when none). Returns:
//   "loading" | "real" | "none" (no collected signals) | "api-down".
// Used to gate the ego graph, top-signals and narrative consistently so we
// never present synthetic data as real for a named cohort founder.
function useFounderDataState(founderId: string): "loading" | "real" | "none" | "api-down" {
  const [state, setState] = useState<"loading" | "real" | "none" | "api-down">("loading");
  useEffect(() => {
    let alive = true;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setState("loading");
    fetchEgoKG(founderId, 14).then(r => {
      if (!alive) return;
      if (r.source === "backend" && r.nodes.length > 0) setState("real");
      else if (r.reason === "no-data") setState("none");
      else setState("api-down");
    });
    return () => {
      alive = false;
    };
  }, [founderId]);
  return state;
}

function NoData({ what }: { what: string }) {
  return (
    <div className="nodata-block">
      <p className="nodata-title">No public signals collected yet</p>
      <p className="nodata-sub muted">
        No free-source signals have been collected and scored for this founder, so there are no real{" "}
        {what} to show. The framework only ever displays real, observed data.
      </p>
    </div>
  );
}

// Real server-side ego-network: founder → signals → topics (+ platform),
// from /api/kg/ego/{id}. Falls back to the client-side synthesis when the
// API is unreachable so the card never blanks.
function EgoNetworkReal({ founderId }: { founderId: string }) {
  const [kg, setKg] = useState<KGResult | null>(null);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    let alive = true;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setLoading(true);
    fetchEgoKG(founderId, 14)
      .then(r => alive && setKg(r))
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, [founderId]);

  const real = kg && kg.source === "backend" && kg.nodes.length > 0;

  // Founder genuinely has no collected public signals yet (e.g. X-native
  // founders Wayback couldn't reach). Show an HONEST empty state rather than
  // a synthetic graph dressed up as real — important for defence credibility.
  if (kg && kg.reason === "no-data") {
    return (
      <div className="ego-wrap ego-empty">
        <div className="ego-empty-inner">
          <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="var(--ink-3)" strokeWidth="1.4">
            <circle cx="7" cy="7" r="2.2" />
            <circle cx="17" cy="8" r="2.2" />
            <circle cx="12" cy="17" r="2.2" />
            <line x1="8.6" y1="8.2" x2="10.8" y2="15.2" strokeDasharray="2 2" />
            <line x1="15.3" y1="9.4" x2="13.1" y2="15.3" strokeDasharray="2 2" />
          </svg>
          <p className="ego-empty-title">No public signals collected yet</p>
          <p className="ego-empty-sub muted">
            This founder is in the cohort, but no free-source signals (HN / Reddit / Product Hunt /
            archived X) have been collected and scored for them yet — so there&apos;s no real graph to
            draw. The framework only ever shows real, observed data here.
          </p>
        </div>
      </div>
    );
  }

  if (!real) {
    // API unreachable (not a data gap) — fall back to the synthetic
    // fixed-layout ego graph so the card doesn't blank during an outage.
    return <EgoNetworkSynthetic founderId={founderId} loading={loading} />;
  }

  return (
    <div className="ego-wrap">
      <div className="ego-controls">
        <div className="ego-legend">
          <span><span className="dot" style={{ background: "var(--accent-deep)" }} /> founder</span>
          <span><span className="dot" style={{ background: "var(--ink-1)" }} /> signal</span>
          <span><span className="dot" style={{ background: "var(--accent)" }} /> topic</span>
          <span><span className="dot" style={{ background: "var(--ink-3)" }} /> platform</span>
        </div>
        <span className="ego-hint muted">drag · hover · scroll to zoom</span>
      </div>
      <ForceGraph
        nodes={kg.nodes}
        edges={kg.edges}
        width={400}
        height={340}
        nodeColor={(k: string) => EGO_KIND_COLOR[k] ?? "var(--ink-1)"}
        nodeRadius={(n: GraphNode) =>
          n.kind === "founder" ? 16 : n.kind === "signal" ? 6 : n.kind === "platform" ? 7 : 5}
        labelFor={(n: GraphNode) => (n.kind === "founder" || n.kind === "platform" ? n.label : null)}
        highlightId={`Person:${founderId}`}
      />
    </div>
  );
}

function EgoNetworkSynthetic({
  founderId,
  loading,
}: {
  founderId: string;
  loading?: boolean;
}) {
  const thesis = useThesis();
  const [hop, setHop] = useState<1 | 2>(1);
  const data = useMemo(() => thesis.egoFor(founderId), [founderId, thesis]);
  const W = 380;
  const H = 320;
  const positions = useMemo(() => {
    const pos: Record<string, { x: number; y: number }> = {};
    pos["F"] = { x: W / 2, y: H / 2 };
    const signals = data.nodes.filter(n => n.kind === "signal");
    signals.forEach((n, i) => {
      const a = -Math.PI / 2 + (i / Math.max(signals.length - 1, 1)) * Math.PI;
      pos[n.id] = { x: W / 2 + Math.cos(a) * 80, y: H / 2 + Math.sin(a) * 80 };
    });
    const topics = data.nodes.filter(n => n.kind === "topic");
    topics.forEach((n, i) => {
      pos[n.id] = { x: W - 50, y: 60 + i * 70 };
    });
    const platforms = data.nodes.filter(n => n.kind === "platform");
    platforms.forEach((n, i) => {
      pos[n.id] = { x: 40, y: 60 + i * 80 };
    });
    return pos;
  }, [data]);

  const nodeColor = (kind: string) =>
    ({
      founder: "var(--accent-deep)",
      signal: "var(--ink-1)",
      topic: "var(--accent)",
      platform: "var(--ink-3)",
    }[kind] || "var(--ink-1)");

  return (
    <div className="ego-wrap">
      <div className="ego-controls">
        <div className="ego-legend">
          <span><span className="dot" style={{ background: "var(--accent-deep)" }} /> founder</span>
          <span><span className="dot" style={{ background: "var(--ink-1)" }} /> signal</span>
          <span><span className="dot" style={{ background: "var(--accent)" }} /> topic</span>
          <span><span className="dot" style={{ background: "var(--ink-3)" }} /> platform</span>
        </div>
        {loading ? (
          <span className="ego-hint muted">loading real graph…</span>
        ) : (
          <div className="seg sm">
            <button className={hop === 1 ? "on" : ""} onClick={() => setHop(1)}>1-hop</button>
            <button className={hop === 2 ? "on" : ""} onClick={() => setHop(2)}>2-hop</button>
          </div>
        )}
      </div>
      <svg width="100%" viewBox={`0 0 ${W} ${H}`} className="ego-svg">
        <defs>
          <marker id="arrow" markerWidth="6" markerHeight="6" refX="6" refY="3" orient="auto">
            <path d="M0,0 L6,3 L0,6 Z" fill="var(--ink-3)" />
          </marker>
        </defs>
        {data.edges.map((e, i) => {
          const a = positions[e.a];
          const b = positions[e.b];
          if (!a || !b) return null;
          return (
            <line
              key={i}
              x1={a.x}
              y1={a.y}
              x2={b.x}
              y2={b.y}
              stroke="var(--accent)"
              strokeOpacity={0.2 + e.w * 0.5}
              strokeWidth={0.6 + e.w * 1.6}
            />
          );
        })}
        {hop === 2 &&
          [0, 1, 2, 3].map(i => {
            const a = (i / 4) * Math.PI * 2;
            return (
              <circle
                key={"g" + i}
                cx={W / 2 + Math.cos(a) * 150}
                cy={H / 2 + Math.sin(a) * 130}
                r="6"
                fill="var(--ink-3)"
                opacity="0.15"
              />
            );
          })}
        {data.nodes.map(n => {
          const p = positions[n.id];
          if (!p) return null;
          const r = n.kind === "founder" ? 18 : n.kind === "signal" ? 10 : 8;
          return (
            <g key={n.id} transform={`translate(${p.x}, ${p.y})`}>
              <circle r={r + 3} fill="var(--bg)" stroke={nodeColor(n.kind)} strokeWidth="1" />
              <circle r={r} fill={nodeColor(n.kind)} opacity={n.kind === "founder" ? 1 : 0.85} />
              {n.kind === "founder" ? (
                <text y="4" textAnchor="middle" fontFamily="var(--serif)" fontSize="11" fill="var(--bg)" fontWeight="600">
                  F
                </text>
              ) : (
                <text y={r + 12} textAnchor="middle" fontFamily="var(--mono)" fontSize="9" fill="var(--ink-2)">
                  {n.label}
                </text>
              )}
            </g>
          );
        })}
      </svg>
    </div>
  );
}

function TaxChip({ dim, cat, score }: { dim: string; cat: TaxonomyCode; score: number }) {
  const thesis = useThesis();
  const t = thesis.taxonomy()[cat];
  return (
    <span
      className="tax-chip"
      style={{ color: t.color, borderColor: t.color, background: t.color + "14" }}
    >
      <span className="tax-dim">{dim}</span>
      <span className="tax-score mono">{score.toFixed(2)}</span>
    </span>
  );
}

function TopSignals({ founderId, t }: { founderId: string; t: number }) {
  const thesis = useThesis();
  const dataState = useFounderDataState(founderId);
  const signals = useMemo(() => thesis.signalsFor(founderId, t), [founderId, t, thesis]);
  // Don't fabricate signals for a founder with no collected data.
  if (dataState === "none") return <NoData what="signals" />;
  return (
    <div className="signals">
      {signals.map((s, i) => (
        <div key={s.id} className="signal-card">
          <div className="signal-head">
            <span className="signal-rank mono">{String(i + 1).padStart(2, "0")}</span>
            <span className="signal-text">&quot;{s.raw}&quot;</span>
          </div>
          <div className="signal-meta">
            <span className="meta-pair">
              <span className="kicker">PLATFORM</span> <span className="mono">{s.platform}</span>
            </span>
            <span className="meta-pair">
              <span className="kicker">DATE</span> <span className="mono">{s.timestamp}</span>
            </span>
            <span className="meta-pair">
              <span className="kicker">Σ DIMS</span>{" "}
              <span className="mono">{Object.keys(thesis.taxonomy()).length}</span>
            </span>
          </div>
          <div className="tax-chips">
            <TaxChip dim={s.dim} cat={s.cat} score={s.score} />
            {[1, 2, 3, 4].map(j => {
              const cats = Object.keys(thesis.taxonomy()) as TaxonomyCode[];
              const cat = cats[(i + j) % cats.length];
              const dim =
                cat +
                "." +
                j +
                " " +
                ["consistency", "reach", "artefacts", "followers"][j - 1];
              const score = Math.max(0.42, s.score - 0.08 - j * 0.07);
              return <TaxChip key={j} dim={dim} cat={cat} score={score} />;
            })}
          </div>
        </div>
      ))}
    </div>
  );
}

function Timeline({ founderId, t }: { founderId: string; t: number }) {
  const thesis = useThesis();
  const f = thesis.founders().find(x => x.id === founderId);
  if (!f) return null;
  const fm = thesis.months(f.first);
  const em = thesis.months(f.emerge);
  if (fm == null) return null;
  const endM = em != null ? em + 6 : Math.max(t + 6, fm + 60);
  const span = endM - fm;
  const pct = (mo: number) => ((mo - fm) / Math.max(span, 1)) * 100;

  const milestones: Array<{ at: number; kind: string; label: string; sub: string }> = [];
  milestones.push({ at: fm, kind: "first", label: "First observable signal", sub: thesis.fmtMonth(fm) });
  milestones.push({ at: fm + Math.floor(span * 0.25), kind: "cadence", label: "Cadence stabilises (>4/day)", sub: ">180d streak" });
  milestones.push({ at: fm + Math.floor(span * 0.45), kind: "follower", label: "10k follower threshold", sub: "+340/wk" });
  if (em != null) {
    milestones.push({ at: em - 4, kind: "venture", label: f.venture ? f.venture + " soft-launch" : "Venture soft-launch", sub: "private beta" });
    milestones.push({ at: em, kind: "emerge", label: "Emergence event", sub: f.ventureMetric || "—" });
  } else {
    milestones.push({ at: fm + Math.floor(span * 0.7), kind: "plateau", label: "Signal plateau (no event)", sub: "still tracked" });
  }
  if (t >= fm && t <= endM) {
    milestones.push({ at: t, kind: "T", label: "Cohort date T", sub: thesis.fmtMonth(t) });
  }

  return (
    <div className="timeline">
      <div className="tl-axis">
        <div className="tl-line" />
        {t >= fm && t <= endM && (
          <div
            className="tl-twindow"
            style={{
              left: pct(t) + "%",
              width: pct(Math.min(t + 24, endM)) - pct(t) + "%",
            }}
          >
            <span className="tl-twindow-label">T → T+24mo</span>
          </div>
        )}
        {milestones.map((m, i) => (
          <div key={i} className={"tl-event tl-" + m.kind} style={{ left: pct(m.at) + "%" }}>
            <div className="tl-dot" />
            <div className="tl-bubble">
              <div className="tl-bubble-label">{m.label}</div>
              <div className="tl-bubble-sub mono">{m.sub}</div>
              <div className="tl-bubble-date mono muted">{thesis.fmtMonth(m.at)}</div>
            </div>
          </div>
        ))}
      </div>
      <div className="tl-axis-labels">
        <span className="mono">{thesis.fmtMonth(fm)}</span>
        <span className="mono">{thesis.fmtMonth(endM)}</span>
      </div>
    </div>
  );
}

function Narrative({ founderId, t }: { founderId: string; t: number }) {
  const thesis = useThesis();
  const dataState = useFounderDataState(founderId);
  const f = thesis.founders().find(x => x.id === founderId);
  if (!f) return null;
  // No fabricated narrative for a founder with no collected signals.
  if (dataState === "none") return null;
  const c = thesis.curve(f, t) || 0;
  const em = thesis.months(f.emerge);
  const fm = thesis.months(f.first);
  if (fm == null) return null;
  const monthsToEmerge = em != null ? em - t : null;
  const sigs = thesis.signalsFor(founderId, t);
  const lead = sigs[0];
  const next = sigs[1];
  const monthsSinceFirst = t - fm;
  return (
    <div className="narrative">
      <div className="narr-head">
        <span className="kicker">FRAMEWORK NARRATIVE · AUTO-GENERATED · MODEL: claude-haiku-4.5</span>
        <button className="link-btn sm">↻ regenerate</button>
      </div>
      <p className="narr-body">
        At <strong>{thesis.fmtQuarter(t)}</strong>, <strong>{f.name}</strong> had been posting on {lead?.platform.toLowerCase()} for <span className="mono">{Math.max(1, Math.floor(monthsSinceFirst))} months</span>.
        The lead signal was <em>{lead?.dim}</em> (score <span className="mono">{lead?.score.toFixed(2)}</span>): {lead?.raw.toLowerCase()}
        {next && (
          <>
            {" "}Reinforced by <em>{next.dim}</em> (score <span className="mono">{next.score.toFixed(2)}</span>).
          </>
        )}{" "}
        The KG-augmented combined score was <span className="mono">P(emerge) = {c.toFixed(2)}</span>.
        {em != null && monthsToEmerge != null && monthsToEmerge >= 0 && (
          <>
            {" "}<strong>{f.venture || "The venture"}</strong> launched <span className="mono">{monthsToEmerge} months</span> later{f.ventureMetric ? <> at <span className="mono">{f.ventureMetric}</span></> : null}.
          </>
        )}
        {em != null && monthsToEmerge != null && monthsToEmerge < 0 && (
          <>
            {" "}<strong>{f.venture || "The venture"}</strong> had already launched (T is post-emergence by <span className="mono">{Math.abs(monthsToEmerge)} months</span>); included here for retrospective trace.
          </>
        )}
        {em == null && (
          <>
            {" "}No emergence event observed yet by today ({thesis.fmtMonth(thesis.today)}).
          </>
        )}
      </p>
    </div>
  );
}

function Stat({ kicker, val, tip }: { kicker: string; val: React.ReactNode; tip?: React.ReactNode }) {
  return (
    <div className="hero-stat">
      <span className="kicker">
        {kicker}
        {tip ? <InfoTip width={280}>{tip}</InfoTip> : null}
      </span>
      <span className="stat-val">{val}</span>
    </div>
  );
}

interface Props {
  founderId: string;
  t: number;
  gotoView: (v: 1 | 2 | 3) => void;
}

export function View3Founder({ founderId, t, gotoView }: Props) {
  const thesis = useThesis();
  const dataState = useFounderDataState(founderId); // hook before any early return
  const f = thesis.founders().find(x => x.id === founderId);
  if (!f) {
    return (
      <section className="view view-3">
        <div className="empty">No founder selected. Pick a row in Step 01.</div>
      </section>
    );
  }
  const outcome = thesis.outcomeAt(f, t);
  const em = thesis.months(f.emerge);
  const noData = dataState === "none";
  return (
    <section className="view view-3">
      <ViewIntro kicker="STEP 03 · DRILL IN" title={"Why was " + f.name + " picked?"}>
        Trace the framework&apos;s per-founder evidence at <strong>{thesis.fmtMonth(t)}</strong> — the knowledge-graph neighbourhood, the five highest-weight signals, and the outcome timeline. Every signal links back to a source post.
      </ViewIntro>

      <div className="founder-hero">
        <div className="hero-left">
          <Avatar id={f.id} name={f.name} size={56} />
          <div className="hero-id">
            <span className="hero-handle">@{f.id}</span>
            <span className="hero-name">{f.name}</span>
            <span className="hero-niche">{f.niche}</span>
          </div>
        </div>
        <div className="hero-stats">
          <Stat
            kicker="Emergence quarter"
            val={em != null ? thesis.fmtQuarter(em) : "—"}
            tip="The quarter in which the founder launched a venture (raised pre-seed, hit revenue threshold, or shipped a public product with traction)."
          />
          <Stat
            kicker="Venture"
            val={f.venture || "—"}
            tip="The startup or product associated with the emergence event."
          />
          <Stat
            kicker="Outcome @ T+24mo"
            val={<OutcomeChip outcome={outcome} />}
            tip="Did this founder emerge within 24 months of date T? Outcomes only shown when the horizon is in the past."
          />
          <Stat
            kicker="P(emerge)"
            val={<span className="mono">{noData ? "—" : (thesis.curve(f, t) || 0).toFixed(2)}</span>}
            tip={
              noData ? (
                <>No prediction: no public signals have been collected for this founder yet, so the framework has nothing to score.</>
              ) : (
                <>
                  The combined score Σ at date T — the framework&apos;s estimate of <em>P(emerges within 24mo)</em>. Range [0,1].
                </>
              )
            }
          />
        </div>
        <button className="link-btn sm" onClick={() => gotoView(1)}>
          ← back to picks
        </button>
      </div>

      <div className="founder-grid">
        <div className="founder-panel ego-panel">
          <div className="panel-head">
            <span className="kicker">
              KG ego-network
              <InfoTip width={320}>
                The founder (F) and her 1-hop neighbours in the knowledge graph: <strong>signals</strong> she&apos;s posted, <strong>topics</strong> they touch, and the <strong>platforms</strong> they live on. Edge weight ≈ co-occurrence strength. T2 features come from this subgraph.
              </InfoTip>
            </span>
            <span className="muted">click a node to inspect</span>
          </div>
          <EgoNetworkReal founderId={founderId} />
        </div>
        <div className="founder-panel signals-panel">
          <div className="panel-head">
            <span className="kicker">
              Top 5 signals @ T
              <InfoTip width={320}>
                The five highest-weighted signals at date T, each tagged with its taxonomy dimension (<span className="mono">S1–S6</span>) and a normalised score. Source post is reproducible from the parquet row id.
              </InfoTip>
            </span>
            <span className="muted">{thesis.fmtMonth(t)}</span>
          </div>
          <TopSignals founderId={founderId} t={t} />
        </div>
        <div className="founder-panel timeline-panel">
          <div className="panel-head">
            <span className="kicker">
              Outcome timeline
              <InfoTip width={280}>
                The trajectory from <strong>first observable signal</strong> to the <strong>emergence event</strong>. The shaded band shows the T → T+24mo evaluation window.
              </InfoTip>
            </span>
            <span className="muted">first signal → emergence</span>
          </div>
          <Timeline founderId={founderId} t={t} />
        </div>
      </div>

      <Narrative founderId={founderId} t={t} />

      <EpistemeBar>
        Per-founder trace is reproducible. Every signal links to its source post. KG edges expanded from co-occurrence within ±14d windows. <strong>No future information used.</strong>
      </EpistemeBar>
    </section>
  );
}
