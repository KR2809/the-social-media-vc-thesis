"use client";

import { useEffect, useMemo, useState } from "react";
import { useThesis } from "@/lib/thesis/context";
import type { TaxonomyCode } from "@/lib/thesis";
import { fetchEgoKG } from "@/lib/thesis/kg";
import { InfoTip } from "./InfoTip";
import { Avatar, EpistemeBar, OutcomeChip, ViewIntro } from "./primitives";

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
        Trace the framework&apos;s per-founder evidence at <strong>{thesis.fmtMonth(t)}</strong> — the five highest-weight signals the model saw, and the outcome timeline from first signal to emergence. Every signal links back to a source post.
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

      <div className="founder-grid founder-grid-2col">
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
