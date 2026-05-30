"use client";

import { useEffect, useMemo, useState } from "react";
import { useThesis } from "@/lib/thesis/context";
import { fetchBacktest } from "@/lib/thesis";
import type { BacktestResult, BacktestScore, BacktestStrategy, RankedPick } from "@/lib/thesis";
import { InfoTip } from "./InfoTip";
import { CIBar, EpistemeBar, fmtPct, ViewIntro } from "./primitives";
import { YCOverlapPanel } from "./YCOverlapPanel";

// ---------------------------------------------------------------------------
// Strategy display metadata
// ---------------------------------------------------------------------------

const STRATEGY_META: Record<
  BacktestStrategy,
  { title: string; kicker: string; tip: string }
> = {
  two_tier: {
    title: "Two-tier framework",
    kicker: "OURS",
    tip: "The framework under test: Tier-1 topic momentum × Tier-2 per-founder social-signal scores, combined into a ranking. This is what we're validating.",
  },
  random: {
    title: "Random portfolio",
    kicker: "BASELINE · RANDOM",
    tip: "K names drawn uniformly at random from the labeled pool observable at date T. The dumbest possible baseline — if we can't beat this, we have nothing.",
  },
  signal_volume: {
    title: "Signal-volume",
    kicker: "BASELINE · VOLUME",
    tip: "Top K by raw scored-signal count at date T. Captures the 'who posts the most' hypothesis — ignores content quality and network structure.",
  },
  recency: {
    title: "Recency",
    kicker: "BASELINE · RECENCY",
    tip: "Top K by most-recent signal timestamp at date T. The trend-chaser baseline — bet on whoever is active right now.",
  },
};

// ---------------------------------------------------------------------------
// "How to read this" explainer
// ---------------------------------------------------------------------------

function HowToRead({ baseRate, k }: { baseRate: number; k: number }) {
  return (
    <details className="how-to-read" open>
      <summary>
        <span className="kicker">How to read this panel</span>
        <span className="how-hint">click to collapse</span>
      </summary>
      <div className="how-body">
        <div className="how-item">
          <span className="how-q">What is precision@K?</span>
          <span className="how-a">
            Of the <span className="mono">K</span> founders a strategy picks at date T, the
            fraction that actually emerged within 24 months. <span className="mono">P@K = hits / K</span>. Higher is better.
          </span>
        </div>
        <div className="how-item">
          <span className="how-q">What&apos;s the base rate?</span>
          <span className="how-a">
            {baseRate > 0 ? (
              <>
                <span className="mono">{fmtPct(baseRate)}</span> of the labeled pool emerged. A strategy that
                just picks at random scores roughly this. <strong>Lift</strong> = P@K ÷ base
                rate; lift &gt; 1 means &quot;better than chance.&quot;
              </>
            ) : (
              <>The fraction of the labeled pool that emerged — random picking scores roughly this.</>
            )}
          </span>
        </div>
        <div className="how-item">
          <span className="how-q">Why do the bars overlap?</span>
          <span className="how-a">
            With a labeled pool this small (cohort + {k > 0 ? "negative peers" : "negatives"}), the 95% CIs
            are wide. Overlapping bands mean a gap isn&apos;t yet <em>statistically</em> separated — read
            the direction, not the decimal.
          </span>
        </div>
        <div className="how-item">
          <span className="how-q">What counts as a win?</span>
          <span className="how-a">
            Beating <strong>random</strong> is the floor. Beating <strong>volume</strong> and{" "}
            <strong>recency</strong> shows the framework adds something past &quot;who posts most / most
            recently.&quot; The aggregate story is in the eval (ROC/PR-AUC + the KG lift); per-date
            precision is the operational replay.
          </span>
        </div>
      </div>
    </details>
  );
}

// ---------------------------------------------------------------------------
// Backend-backed scoreboard (real separation incl. negatives)
// ---------------------------------------------------------------------------

function StrategyCard({
  score,
  best,
  bootCI,
}: {
  score: BacktestScore;
  best: boolean;
  bootCI: (hits: number, k: number) => [number, number];
}) {
  const meta = STRATEGY_META[score.strategy];
  const primary = score.strategy === "two_tier";
  const [lo, hi] = bootCI(score.nHits, score.k);
  return (
    <div className={"baseline-card " + (primary ? "primary " : "") + (best ? "best" : "")}>
      <div className="baseline-head">
        <span className="kicker">
          {meta.kicker}
          <InfoTip width={300}>{meta.tip}</InfoTip>
        </span>
        <span className="baseline-title">
          {meta.title}
          {best && <span className="best-badge">best @ this date</span>}
        </span>
      </div>
      <div className="baseline-num">
        <span className="baseline-pct">{fmtPct(score.precision)}</span>
        <span className="baseline-frac mono">
          {score.nHits} / {score.k}
        </span>
      </div>
      <CIBar value={score.precision} lo={lo} hi={hi} width={220} primary={primary} />
      <div className="ci-readout mono">
        95% CI [{fmtPct(lo)}, {fmtPct(hi)}] · lift {score.lift.toFixed(2)}×
      </div>
    </div>
  );
}

function Scoreboard({
  result,
  bootCI,
}: {
  result: BacktestResult;
  bootCI: (hits: number, k: number) => [number, number];
}) {
  const best = useMemo(() => {
    let b: BacktestScore | null = null;
    for (const s of result.scores) if (!b || s.precision > b.precision) b = s;
    return b;
  }, [result]);
  return (
    <div className="baseline-grid">
      {result.scores.map(s => (
        <StrategyCard
          key={s.strategy}
          score={s}
          best={best != null && s.strategy === best.strategy && best.precision > 0}
          bootCI={bootCI}
        />
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Honest verdict — handles win / tie / loss
// ---------------------------------------------------------------------------

function Verdict({ result, fmtMonth, t }: { result: BacktestResult; fmtMonth: (m: number) => string; t: number }) {
  const ours = result.scores.find(s => s.strategy === "two_tier");
  if (!ours) return null;
  const baselines = result.scores.filter(s => s.strategy !== "two_tier");
  let bestBase: BacktestScore | null = null;
  for (const s of baselines) if (!bestBase || s.precision > bestBase.precision) bestBase = s;
  const bestBaseP = bestBase?.precision ?? 0;
  const lift = ours.precision - bestBaseP;
  const beatsRandom = ours.precision > (result.baseRate || 0);

  let cls: string;
  let icon: string;
  let line: React.ReactNode;
  if (lift > 0.005) {
    cls = "verdict-good";
    icon = "↑";
    line = (
      <>
        At <span className="mono">{fmtMonth(t)}</span>, the framework&apos;s precision of{" "}
        <strong>{fmtPct(ours.precision)}</strong> beats the best baseline (
        <strong>{STRATEGY_META[bestBase!.strategy].title}</strong>, {fmtPct(bestBaseP)}) by{" "}
        <strong>+{((lift) * 100).toFixed(1)} pts</strong>.
      </>
    );
  } else if (lift > -0.005) {
    cls = "verdict-flat";
    icon = "≈";
    line = (
      <>
        At <span className="mono">{fmtMonth(t)}</span>, the framework{" "}
        <strong>matches</strong> the best baseline ({fmtPct(ours.precision)} vs {fmtPct(bestBaseP)}). The
        edge is in the aggregate eval, not every single date.
      </>
    );
  } else {
    cls = "verdict-flat";
    icon = "↓";
    line = (
      <>
        At <span className="mono">{fmtMonth(t)}</span>, a naïve baseline (
        <strong>{STRATEGY_META[bestBase!.strategy].title}</strong>, {fmtPct(bestBaseP)}){" "}
        <strong>out-picks</strong> the framework ({fmtPct(ours.precision)}) here.{" "}
        {beatsRandom ? "The framework still beats random — " : ""}at small n this happens on individual
        dates; the defensible claim is the aggregate ROC/PR-AUC + KG lift, not a per-date sweep.
      </>
    );
  }
  return (
    <div className={"verdict " + cls}>
      <span className={"verdict-icon " + (lift > 0.005 ? "good" : "flat")}>{icon}</span>
      <span className="verdict-text">
        {line}
        <span className="muted"> Read the CIs: overlapping bands mean the gap isn&apos;t statistically separated at this sample size.</span>
      </span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Cohort-recall headline (positives only) — reframed honestly
// ---------------------------------------------------------------------------

function RecallHeadline({ picks, t, K }: { picks: RankedPick[]; t: number; K: number }) {
  const thesis = useThesis();
  const { hits, k, precision } = thesis.precisionAt(picks, t);
  const [lo, hi] = thesis.bootCI(hits, k);
  const evaluable = k > 0;
  return (
    <div className="precision-card">
      <div className="precision-left">
        <span className="kicker">
          Cohort recall · two-tier ranking
          <InfoTip width={360}>
            Of the framework&apos;s top-K <strong>among the known cohort</strong>, how many had emerged by
            T+24mo. This is recall over labelled positives — it shows the ranking surfaces real emergers,
            but it can&apos;t separate strategies on its own (the cohort is all positives). The strategy
            comparison below uses the full labelled pool incl. negative peers.
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
              <strong>95% confidence interval</strong> via bootstrap resampling. The K picks are resampled
              with replacement; precision is recomputed each draw. The central 95% forms the band.
            </InfoTip>
          </span>
          <span className="mono">
            [{fmtPct(lo)}, {fmtPct(hi)}]
          </span>
        </div>
        <CIBar value={precision} lo={lo} hi={hi} width={420} primary />
        <div className="caption muted">
          <span className="mono">{hits}</span> emerged + <span className="mono">{Math.max(0, k - hits)}</span> not-yet across <span className="mono">{k}</span> evaluable cohort picks.
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

// ---------------------------------------------------------------------------

interface Props {
  t: number;
  K: number;
  picks: RankedPick[];
  onFocusFounder: (id: string) => void;
  gotoView: (v: 1 | 2 | 3) => void;
}

export function View2Outcome({ t, K, picks }: Props) {
  const thesis = useThesis();
  const t24 = t + 24;
  const canEval = t24 <= thesis.today;

  // Fetch the real, separated backtest (full labelled pool incl. negatives).
  const [bt, setBt] = useState<BacktestResult | null>(null);
  const [loading, setLoading] = useState(false);
  useEffect(() => {
    if (!canEval) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setBt(null);
      return;
    }
    let alive = true;
    setLoading(true);
    fetchBacktest(t, K)
      .then(r => {
        if (alive) setBt(r);
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [t, K, canEval]);

  const hasBackend = bt != null && bt.source === "backend" && bt.scores.length > 0;

  return (
    <section className="view view-2">
      <ViewIntro kicker="STEP 02 · SCORE" title="How did the picks perform?">
        Of the <span className="mono">{K}</span> founders picked at <strong>{thesis.fmtMonth(t)}</strong>, how
        many launched a fundable venture within <strong>24 months</strong>? We score the framework against
        three naïve baselines over the full labelled pool — <strong>cohort + negative peers</strong> — so the
        comparison is real, not a foregone conclusion.
      </ViewIntro>

      {canEval && <HowToRead baseRate={bt?.baseRate ?? 0} k={K} />}

      <RecallHeadline picks={picks} t={t} K={K} />

      {canEval && hasBackend && <Verdict result={bt} fmtMonth={thesis.fmtMonth} t={t} />}

      {canEval && hasBackend && (
        <>
          <div className="scoreboard-head">
            <span className="kicker">
              Precision @ K · framework vs baselines
              <InfoTip width={340}>
                Real backtest over the full labelled pool (cohort positives + signal-bearing negative peers)
                at date T. Each strategy picks K names; precision@K = how many emerged. Lift = precision ÷
                base rate.
              </InfoTip>
            </span>
            <span className="muted">
              base rate <span className="mono">{fmtPct(bt.baseRate)}</span> · labelled pool incl. negatives
            </span>
          </div>
          <Scoreboard result={bt} bootCI={thesis.bootCI} />
        </>
      )}

      {/* YC cross-reference is independent of the 24-month outcome horizon
          (it's a who-went-through-YC fact, not an emergence outcome), so it
          shows at any date — including recent ones where canEval is false. */}
      <YCOverlapPanel t={t} />

      {canEval && !hasBackend && (
        <div className="future-banner">
          <span className="kicker">{loading ? "Loading backtest…" : "Backtest unavailable"}</span>
          <span>
            {loading
              ? "Fetching the real per-strategy precision from the API."
              : "The backtest API (/api/baselines) isn't reachable, so the framework-vs-baseline scoreboard is hidden rather than faked. Start the FastAPI backend to populate it."}
          </span>
        </div>
      )}

      {!canEval && (
        <div className="future-banner">
          <span className="kicker">Evaluation horizon in the future</span>
          <span>
            T+24mo for the current cohort is <span className="mono">{thesis.fmtMonth(t24)}</span>, after today (
            <span className="mono">{thesis.fmtMonth(thesis.today)}</span>). Outcomes are intentionally hidden —
            drag the slider further into the past to evaluate.
          </span>
        </div>
      )}

      <EpistemeBar>
        Precision @ K with bootstrap CIs over the full labelled pool (cohort + signal-bearing negative
        peers). <strong>Not a returns claim.</strong> Sample sizes are small by design — this is a
        thesis-defence operationalisation, not a fund track record. The framework&apos;s aggregate edge is
        the ROC/PR-AUC + KG lift in the eval; per-date precision varies.
      </EpistemeBar>
    </section>
  );
}
