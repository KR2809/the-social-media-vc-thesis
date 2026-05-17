"use client";

import { useMemo } from "react";
import { thesis } from "@/lib/thesis";
import type { BaselinePick, RankedPick } from "@/lib/thesis";
import { InfoTip } from "./InfoTip";
import { CIBar, EpistemeBar, fmtPct, ViewIntro } from "./primitives";

function PrecisionHeadline({ picks, t, K }: { picks: RankedPick[]; t: number; K: number }) {
  const { hits, k, precision } = thesis.precisionAt(picks, t);
  const [lo, hi] = thesis.bootCI(hits, k);
  const evaluable = k > 0;
  return (
    <div className="precision-card">
      <div className="precision-left">
        <span className="kicker">
          Precision @ K · two-tier framework
          <InfoTip width={340}>
            <strong>Precision @ K</strong> = of the K founders picked at date T, what fraction emerged (launched a fundable venture) within 24 months?
            <br /><br />
            <span className="mono">P@K = hits / K</span>
            <br /><br />
            Higher is better. Random picking from this pool would give around 25–35% at K=20.
          </InfoTip>
        </span>
        <div className="precision-fraction">
          <span className="big-frac">{hits}</span>
          <span className="frac-sep">/</span>
          <span className="big-frac-denom">{evaluable ? k : "—"}</span>
          <span className="frac-eq">=</span>
          <span className="big-pct">{evaluable ? fmtPct(precision) : "—"}</span>
        </div>
        <div className="ci-row">
          <span className="kicker">
            95% bootstrap CI
            <InfoTip width={340}>
              <strong>95% confidence interval</strong> via bootstrap resampling (10,000 draws). The K picks are resampled with replacement; we recompute precision each draw. The central 95% of those values forms the band. Wider band = less certain.
            </InfoTip>
          </span>
          <span className="mono">
            [{fmtPct(lo)}, {fmtPct(hi)}]
          </span>
        </div>
        <CIBar value={precision} lo={lo} hi={hi} width={420} primary />
        <div className="caption muted">
          <span className="mono">{hits}</span> hits + <span className="mono">{Math.max(0, k - hits)}</span> misses across <span className="mono">{k}</span> evaluable picks. CIs reflect small-sample uncertainty.
        </div>
      </div>
      <div className="precision-right">
        <div className="precision-stat">
          <span className="kicker">Cohort date T</span>
          <span className="stat-val mono">{thesis.fmtMonth(t)}</span>
        </div>
        <div className="precision-stat">
          <span className="kicker">Evaluation horizon</span>
          <span className="stat-val mono">T+24mo = {thesis.fmtMonth(t + 24)}</span>
        </div>
        <div className="precision-stat">
          <span className="kicker">K (portfolio size)</span>
          <span className="stat-val mono">{K}</span>
        </div>
        <div className="precision-stat">
          <span className="kicker">Status</span>
          <span className="stat-val">
            {evaluable ? (
              <span className="status-pill">
                <span className="status-dot ok" /> evaluable
              </span>
            ) : (
              <span className="status-pill">
                <span className="status-dot mu" /> horizon in the future
              </span>
            )}
          </span>
        </div>
      </div>
    </div>
  );
}

const BASELINE_TIPS: Record<string, string> = {
  ours: "The full two-tier framework: T1 (social-signal LightGBM) re-ranked by T2 (KG features). The thing we're trying to validate.",
  random: "K founders drawn uniformly at random from the pool observable at date T. The dumbest possible baseline. If we can't beat this, we have nothing.",
  volume: "Top K by raw post-volume only. Captures the 'who posts the most' hypothesis — ignores content, signal quality, and network.",
  recency: "Top K by recency of first observable signal. Captures 'bet on the newest accounts' — the trend-chaser baseline.",
};

function BaselineCard({
  title,
  kicker,
  tipKey,
  picks,
  t,
  primary,
  K,
  onFocusFounder,
}: {
  title: string;
  kicker: string;
  tipKey: keyof typeof BASELINE_TIPS;
  picks: ReadonlyArray<BaselinePick | RankedPick>;
  t: number;
  primary?: boolean;
  K: number;
  onFocusFounder?: (id: string) => void;
}) {
  const { hits, k, precision } = thesis.precisionAt(picks, t);
  const [lo, hi] = thesis.bootCI(hits, k);
  return (
    <div className={"baseline-card " + (primary ? "primary" : "")}>
      <div className="baseline-head">
        <span className="kicker">
          {kicker}
          <InfoTip width={300}>{BASELINE_TIPS[tipKey]}</InfoTip>
        </span>
        <span className="baseline-title">{title}</span>
      </div>
      <div className="baseline-num">
        <span className="baseline-pct">{k ? fmtPct(precision) : "—"}</span>
        <span className="baseline-frac mono">
          {hits} / {k || "—"}
        </span>
      </div>
      <CIBar value={precision} lo={lo} hi={hi} width={220} primary={primary} />
      <div className="ci-readout mono">
        95% CI [{fmtPct(lo)}, {fmtPct(hi)}]
      </div>
      <div className="baseline-picks">
        <span className="kicker muted">top-K picks</span>
        <div className="pick-list">
          {picks.slice(0, K).map(p => {
            const f = thesis.founders().find(x => x.id === p.id);
            const em = thesis.months(f ? f.emerge : null);
            const t24 = t + 24;
            const hit = em != null && em <= t24;
            return (
              <span
                key={p.id}
                className={"pick-tag " + (hit ? "hit" : "miss")}
                onClick={() => onFocusFounder && onFocusFounder(p.id)}
                title={f ? f.name + (hit ? " · emerged" : " · not yet") : p.id}
              >
                {hit ? "●" : "○"} {p.id}
              </span>
            );
          })}
        </div>
      </div>
    </div>
  );
}

function Verdict({
  picks,
  baselines,
  t,
}: {
  picks: RankedPick[];
  baselines: Record<string, BaselinePick[]>;
  t: number;
  K: number;
}) {
  const our = thesis.precisionAt(picks, t);
  if (our.k === 0) return null;
  let best: { name: string; precision: number } | null = null;
  for (const [name, bPicks] of Object.entries(baselines)) {
    const p = thesis.precisionAt(bPicks, t);
    if (!best || p.precision > best.precision) best = { name, precision: p.precision };
  }
  const lift = our.precision - (best ? best.precision : 0);
  const liftPts = (lift * 100).toFixed(1);
  const liftPositive = lift > 0.005;
  return (
    <div className={"verdict " + (liftPositive ? "verdict-good" : "verdict-flat")}>
      <span className={"verdict-icon " + (liftPositive ? "good" : "flat")}>
        {liftPositive ? "↑" : "≈"}
      </span>
      <span className="verdict-text">
        At <span className="mono">{thesis.fmtMonth(t)}</span>, the framework&apos;s precision of <strong>{fmtPct(our.precision)}</strong> {liftPositive ? "beats" : "matches"} the best baseline (<strong>{best?.name}</strong>, {fmtPct(best?.precision ?? 0)}) by <strong>{liftPositive ? "+" : ""}{liftPts} pts</strong>.
        <span className="muted"> Read the CIs: overlapping bands mean the lift isn&apos;t yet statistically separated at this sample size.</span>
      </span>
    </div>
  );
}

function YCDonut({
  value,
  a,
  b,
  labelA,
  labelB,
}: {
  value: number;
  a: number;
  b: number;
  labelA: string;
  labelB: string;
}) {
  const r = 36;
  const c = 2 * Math.PI * r;
  return (
    <div className="yc-donut">
      <svg width="100" height="100" viewBox="0 0 100 100">
        <circle cx="50" cy="50" r={r} fill="none" stroke="var(--hairline)" strokeWidth="10" />
        <circle
          cx="50"
          cy="50"
          r={r}
          fill="none"
          stroke="var(--accent)"
          strokeWidth="10"
          strokeDasharray={`${c * value} ${c}`}
          transform="rotate(-90 50 50)"
          strokeLinecap="butt"
        />
        <text x="50" y="48" textAnchor="middle" fontFamily="var(--mono)" fontSize="16" fill="var(--ink-1)">
          {fmtPct(value, 0)}
        </text>
        <text x="50" y="62" textAnchor="middle" fontFamily="var(--mono)" fontSize="9" fill="var(--ink-2)">
          {a} of {b}
        </text>
      </svg>
      <div className="donut-cap">
        <strong>{labelA}</strong>
        <br />
        <span className="muted">{labelB}</span>
      </div>
    </div>
  );
}

function YCOverlap({ picks }: { picks: RankedPick[]; t: number }) {
  const ycIds = ["marclou", "kaiwon_d", "tom_under", "owen_drafts", "cosma_kim", "rhea_pixels", "leyla_codes", "june_codes"];
  const ours = new Set(picks.map(p => p.id));
  const ycSet = new Set(ycIds);
  const overlap = [...ours].filter(id => ycSet.has(id));
  const inOursFromYC = overlap.length;
  const inYCFromOurs = overlap.length;
  const pct1 = picks.length ? inOursFromYC / picks.length : 0;
  const pct2 = ycIds.length ? inYCFromOurs / ycIds.length : 0;
  return (
    <div className="yc-overlap">
      <div className="yc-head">
        <span className="kicker">YC BATCH OVERLAP (W22 · S22 · W23 · S23)</span>
        <span className="muted">— exploratory, not an endorsement</span>
      </div>
      <div className="yc-grid">
        <YCDonut value={pct1} a={inOursFromYC} b={picks.length} labelA="our top-K" labelB="picks were in a YC batch" />
        <YCDonut value={pct2} a={inYCFromOurs} b={ycIds.length} labelA="YC creator-economy founders" labelB="were in our top-K" />
        <div className="yc-names">
          <span className="kicker">SHARED NAMES</span>
          <div className="yc-name-list">
            {overlap.length === 0 && <span className="muted">— no overlap at this date</span>}
            {overlap.map(id => (
              <span key={id} className="pick-tag hit">
                ● {id}
              </span>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

interface Props {
  t: number;
  K: number;
  picks: RankedPick[];
  onFocusFounder: (id: string) => void;
  gotoView: (v: 1 | 2 | 3) => void;
}

export function View2Outcome({ t, K, picks, onFocusFounder, gotoView }: Props) {
  const baselineR = useMemo(() => thesis.baselineRandom(t, K, 42), [t, K]);
  const baselineV = useMemo(() => thesis.baselineVolume(t, K), [t, K]);
  const baselineY = useMemo(() => thesis.baselineRecency(t, K), [t, K]);
  const t24 = t + 24;
  const canEval = t24 <= thesis.today;
  return (
    <section className="view view-2">
      <ViewIntro kicker="STEP 02 · SCORE" title="How did the picks perform?">
        Of the <span className="mono">{K}</span> founders picked at <strong>{thesis.fmtMonth(t)}</strong>, how many launched a fundable venture within <strong>24 months</strong>? We compare the framework against three naive baselines. <strong>Hover any &quot;?&quot;</strong> to see the math.
      </ViewIntro>

      <PrecisionHeadline picks={picks} t={t} K={K} />

      {canEval && (
        <Verdict
          picks={picks}
          t={t}
          K={K}
          baselines={{ Random: baselineR, Volume: baselineV, Recency: baselineY }}
        />
      )}

      <div className="baseline-grid">
        <BaselineCard
          title="Two-tier framework"
          kicker="OURS"
          tipKey="ours"
          picks={picks}
          t={t}
          primary
          K={K}
          onFocusFounder={id => {
            onFocusFounder(id);
            gotoView(3);
          }}
        />
        <BaselineCard
          title="Random portfolio"
          kicker="BASELINE 1"
          tipKey="random"
          picks={baselineR}
          t={t}
          K={K}
          onFocusFounder={id => {
            onFocusFounder(id);
            gotoView(3);
          }}
        />
        <BaselineCard
          title="Signal-volume"
          kicker="BASELINE 2"
          tipKey="volume"
          picks={baselineV}
          t={t}
          K={K}
          onFocusFounder={id => {
            onFocusFounder(id);
            gotoView(3);
          }}
        />
        <BaselineCard
          title="Recency"
          kicker="BASELINE 3"
          tipKey="recency"
          picks={baselineY}
          t={t}
          K={K}
          onFocusFounder={id => {
            onFocusFounder(id);
            gotoView(3);
          }}
        />
      </div>

      {canEval && <YCOverlap picks={picks} t={t} />}

      {!canEval && (
        <div className="future-banner">
          <span className="kicker">Evaluation horizon in the future</span>
          <span>
            T+24mo for the current cohort is <span className="mono">{thesis.fmtMonth(t24)}</span>, after today (<span className="mono">{thesis.fmtMonth(thesis.today)}</span>). Outcomes are intentionally hidden — drag the slider further into the past to evaluate.
          </span>
        </div>
      )}

      <EpistemeBar>
        Precision @ K with bootstrap CIs (10,000 resamples). <strong>Not a returns claim.</strong> Baselines drawn from the same cohort pool at date T. Sample sizes are small by design — this is a thesis-defence operationalisation, not a fund track record.
      </EpistemeBar>
    </section>
  );
}
