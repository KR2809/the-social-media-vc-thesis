/* View 2 — Outcome. Precision@K headline + 4-baseline comparison + YC overlap. */

const { useMemo: useMemo2 } = React;
const { Avatar: Av2, OutcomeChip: OC2, CIBar, EpistemeBar: EB2, ViewIntro: VI2, InfoTip: IT2, fmtPct: fp2 } = window.Chrome;

// ---------- precision headline ----------
function PrecisionHeadline({ picks, t, K }) {
  const { hits, k, precision } = THESIS.precisionAt(picks, t);
  const [lo, hi] = THESIS.bootCI(hits, k);
  const evaluable = k > 0;
  return (
    <div className="precision-card">
      <div className="precision-left">
        <span className="kicker">
          Precision @ K · two-tier framework
          <IT2 width={340}>
            <strong>Precision @ K</strong> = of the K founders picked at date T, what fraction emerged (launched a fundable venture) within 24 months?<br/><br/>
            <span className="mono">P@K = hits / K</span><br/><br/>
            Higher is better. Random picking from this pool would give around 25–35% at K=20.
          </IT2>
        </span>
        <div className="precision-fraction">
          <span className="big-frac">{hits}</span>
          <span className="frac-sep">/</span>
          <span className="big-frac-denom">{evaluable ? k : "—"}</span>
          <span className="frac-eq">=</span>
          <span className="big-pct">{evaluable ? fp2(precision) : "—"}</span>
        </div>
        <div className="ci-row">
          <span className="kicker">
            95% bootstrap CI
            <IT2 width={340}>
              <strong>95% confidence interval</strong> via bootstrap resampling (10,000 draws). The K picks are resampled with replacement; we recompute precision each draw. The central 95% of those values forms the band. Wider band = less certain.
            </IT2>
          </span>
          <span className="mono">[{fp2(lo)}, {fp2(hi)}]</span>
        </div>
        <CIBar value={precision} lo={lo} hi={hi} width={420} primary={true}/>
        <div className="caption muted">
          <span className="mono">{hits}</span> hits + <span className="mono">{Math.max(0, k - hits)}</span> misses across <span className="mono">{k}</span> evaluable picks. CIs reflect small-sample uncertainty.
        </div>
      </div>
      <div className="precision-right">
        <div className="precision-stat">
          <span className="kicker">Cohort date T</span>
          <span className="stat-val mono">{THESIS.fmtMonth(t)}</span>
        </div>
        <div className="precision-stat">
          <span className="kicker">Evaluation horizon</span>
          <span className="stat-val mono">T+24mo = {THESIS.fmtMonth(t + 24)}</span>
        </div>
        <div className="precision-stat">
          <span className="kicker">K (portfolio size)</span>
          <span className="stat-val mono">{K}</span>
        </div>
        <div className="precision-stat">
          <span className="kicker">Status</span>
          <span className="stat-val">
            {evaluable
              ? <span className="status-pill"><span className="status-dot ok"/> evaluable</span>
              : <span className="status-pill"><span className="status-dot mu"/> horizon in the future</span>}
          </span>
        </div>
      </div>
    </div>
  );
}

// ---------- baseline tooltips ----------
const BASELINE_TIPS = {
  ours:     "The full two-tier framework: T1 (social-signal LightGBM) re-ranked by T2 (KG features). The thing we're trying to validate.",
  random:   "K founders drawn uniformly at random from the pool observable at date T. The dumbest possible baseline. If we can't beat this, we have nothing.",
  volume:   "Top K by raw post-volume only. Captures the 'who posts the most' hypothesis \u2014 ignores content, signal quality, and network.",
  recency:  "Top K by recency of first observable signal. Captures 'bet on the newest accounts' \u2014 the trend-chaser baseline."
};

// ---------- baseline card ----------
function BaselineCard({ title, kicker, tipKey, picks, t, primary, K, onFocusFounder }) {
  const { hits, k, precision } = THESIS.precisionAt(picks, t);
  const [lo, hi] = THESIS.bootCI(hits, k);
  return (
    <div className={"baseline-card " + (primary ? "primary" : "")}>
      <div className="baseline-head">
        <span className="kicker">
          {kicker}
          <IT2 width={300}>{BASELINE_TIPS[tipKey]}</IT2>
        </span>
        <span className="baseline-title">{title}</span>
      </div>
      <div className="baseline-num">
        <span className="baseline-pct">{k ? fp2(precision) : "—"}</span>
        <span className="baseline-frac mono">{hits} / {k || "—"}</span>
      </div>
      <CIBar value={precision} lo={lo} hi={hi} width={220} primary={primary}/>
      <div className="ci-readout mono">95% CI [{fp2(lo)}, {fp2(hi)}]</div>
      <div className="baseline-picks">
        <span className="kicker muted">top-K picks</span>
        <div className="pick-list">
          {picks.slice(0, K).map(p => {
            const f = THESIS.FOUNDERS_RAW.find(x => x.id === p.id);
            const em = THESIS.months(f && f.emerge);
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

// ---------- verdict line (plain-English compare) ----------
function Verdict({ picks, baselines, t, K }) {
  const our = THESIS.precisionAt(picks, t);
  if (our.k === 0) return null;
  let best = null;
  for (const [name, bPicks] of Object.entries(baselines)) {
    const p = THESIS.precisionAt(bPicks, t);
    if (!best || p.precision > best.precision) best = { name, precision: p.precision };
  }
  const lift = our.precision - (best ? best.precision : 0);
  const liftPts = (lift * 100).toFixed(1);
  const liftPositive = lift > 0.005;
  return (
    <div className={"verdict " + (liftPositive ? "verdict-good" : "verdict-flat")}>
      <span className={"verdict-icon " + (liftPositive ? "good" : "flat")}>{liftPositive ? "↑" : "≈"}</span>
      <span className="verdict-text">
        At <span className="mono">{THESIS.fmtMonth(t)}</span>, the framework's precision of <strong>{fp2(our.precision)}</strong> {liftPositive ? "beats" : "matches"} the best baseline (<strong>{best.name}</strong>, {fp2(best.precision)}) by <strong>{liftPositive ? "+" : ""}{liftPts} pts</strong>.
        <span className="muted"> Read the CIs: overlapping bands mean the lift isn't yet statistically separated at this sample size.</span>
      </span>
    </div>
  );
}

// ---------- YC overlap ----------
function YCOverlap({ picks, t }) {
  // mock YC batch membership
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
        <YCDonut value={pct1} a={inOursFromYC} b={picks.length} labelA="our top-K" labelB="picks were in a YC batch"/>
        <YCDonut value={pct2} a={inYCFromOurs} b={ycIds.length} labelA="YC creator-economy founders" labelB="were in our top-K"/>
        <div className="yc-names">
          <span className="kicker">SHARED NAMES</span>
          <div className="yc-name-list">
            {overlap.length === 0 && <span className="muted">— no overlap at this date</span>}
            {overlap.map(id => <span key={id} className="pick-tag hit">● {id}</span>)}
          </div>
        </div>
      </div>
    </div>
  );
}

function YCDonut({ value, a, b, labelA, labelB }) {
  const r = 36, c = 2 * Math.PI * r;
  return (
    <div className="yc-donut">
      <svg width="100" height="100" viewBox="0 0 100 100">
        <circle cx="50" cy="50" r={r} fill="none" stroke="var(--hairline)" strokeWidth="10"/>
        <circle cx="50" cy="50" r={r} fill="none" stroke="var(--accent)" strokeWidth="10"
          strokeDasharray={`${c * value} ${c}`}
          transform="rotate(-90 50 50)"
          strokeLinecap="butt"/>
        <text x="50" y="48" textAnchor="middle" fontFamily="var(--mono)" fontSize="16" fill="var(--ink-1)">{fp2(value, 0)}</text>
        <text x="50" y="62" textAnchor="middle" fontFamily="var(--mono)" fontSize="9" fill="var(--ink-2)">{a} of {b}</text>
      </svg>
      <div className="donut-cap">
        <strong>{labelA}</strong><br/>
        <span className="muted">{labelB}</span>
      </div>
    </div>
  );
}

// ---------- View 2 root ----------
function View2Outcome({ t, K, picks, onFocusFounder, gotoView }) {
  const baselineR = useMemo2(() => THESIS.baselineRandom(t, K, 42), [t, K]);
  const baselineV = useMemo2(() => THESIS.baselineVolume(t, K), [t, K]);
  const baselineY = useMemo2(() => THESIS.baselineRecency(t, K), [t, K]);

  const t24 = t + 24;
  const canEval = t24 <= THESIS.TODAY;

  return (
    <section className="view view-2">
      <VI2 kicker="STEP 02 · SCORE" title="How did the picks perform?">
        Of the <span className="mono">{K}</span> founders picked at <strong>{THESIS.fmtMonth(t)}</strong>, how many launched a fundable venture within <strong>24 months</strong>? We compare the framework against three naive baselines. <strong>Hover any “?”</strong> to see the math.
      </VI2>

      <PrecisionHeadline picks={picks} t={t} K={K}/>

      {canEval && <Verdict picks={picks} t={t} K={K} baselines={{ Random: baselineR, Volume: baselineV, Recency: baselineY }}/>}

      <div className="baseline-grid">
        <BaselineCard title="Two-tier framework" kicker="OURS"       tipKey="ours"    picks={picks}    t={t} primary={true} K={K} onFocusFounder={(id) => { onFocusFounder(id); gotoView(3); }}/>
        <BaselineCard title="Random portfolio"   kicker="BASELINE 1" tipKey="random"  picks={baselineR} t={t} K={K} onFocusFounder={(id) => { onFocusFounder(id); gotoView(3); }}/>
        <BaselineCard title="Signal-volume"      kicker="BASELINE 2" tipKey="volume"  picks={baselineV} t={t} K={K} onFocusFounder={(id) => { onFocusFounder(id); gotoView(3); }}/>
        <BaselineCard title="Recency"            kicker="BASELINE 3" tipKey="recency" picks={baselineY} t={t} K={K} onFocusFounder={(id) => { onFocusFounder(id); gotoView(3); }}/>
      </div>

      {canEval && <YCOverlap picks={picks} t={t}/>}

      {!canEval && (
        <div className="future-banner">
          <span className="kicker">Evaluation horizon in the future</span>
          <span>T+24mo for the current cohort is <span className="mono">{THESIS.fmtMonth(t24)}</span>, after today (<span className="mono">{THESIS.fmtMonth(THESIS.TODAY)}</span>). Outcomes are intentionally hidden — drag the slider further into the past to evaluate.</span>
        </div>
      )}

      <EB2>
        Precision @ K with bootstrap CIs (10,000 resamples). <strong>Not a returns claim.</strong> Baselines drawn from the same cohort pool at date T. Sample sizes are small by design — this is a thesis-defence operationalisation, not a fund track record.
      </EB2>
    </section>
  );
}

window.View2Outcome = View2Outcome;
