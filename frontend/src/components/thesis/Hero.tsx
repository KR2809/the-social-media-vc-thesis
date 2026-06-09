"use client";

import { useThesis } from "@/lib/thesis/context";
import { HEADLINE, modelHitsPer10, randomHitsPer10 } from "@/lib/thesis/headline";
import { InfoTip } from "./InfoTip";

// Act 0 — the landing band shown above the Replay view. Frames the
// needle-in-a-haystack problem and the three headline results before the user
// touches the interactive board. Style matches the light editorial system
// (serif headings, EDHEC blue accent, mono numerals).

function Haystack() {
  // 100 dots; the ~12 "hits" are the emergence base rate, made visual.
  const hits = new Set([3, 11, 17, 24, 29, 38, 46, 55, 61, 70, 84, 92]);
  return (
    <div className="hero-haystack" aria-hidden>
      {Array.from({ length: 100 }, (_, i) => (
        <span key={i} className={"hay-dot" + (hits.has(i) ? " hit" : "")} />
      ))}
    </div>
  );
}

export function Hero({ onStart }: { onStart: () => void }) {
  const src = useThesis();
  // Live cohort size from the data source; fall back to the canonical run split.
  const cohortSize = src.founders().length || HEADLINE.nPos + HEADLINE.nNeg;

  return (
    <section className="hero">
      <div className="hero-badge mono">
        From social signals to pre-seed allocation · live backtest
      </div>

      <span className="kicker">The problem</span>
      <h1 className="hero-headline">
        Spotting a founder <em>before they launch</em> is a needle-in-a-haystack
        problem. We built a scoring system that finds the needles.
      </h1>
      <p className="hero-sub">
        Only about <strong>1 in 9</strong> people active in a startup niche ever
        emerge as a real founder. Scrolling social media at random is mostly
        misses.
      </p>

      <Haystack />
      <p className="hero-haycap">
        100 in-niche creators — only the{" "}
        <span className="hay-cap-hit">~12 highlighted</span> emerged as founders
        ({HEADLINE.baseRatePct}% base rate)
      </p>

      <div className="hero-stats">
        <div className="hero-card">
          <div className="hero-card-q">
            <InfoTip label="ROC-AUC">
              Given one real founder and one non-founder picked at random, how
              often the model ranks the founder higher. 0.5 = a coin flip,
              1.0 = perfect. 95% confidence interval in brackets.
            </InfoTip>
          </div>
          <div className="big-pct">{HEADLINE.rocAuc.toFixed(3)}</div>
          <div className="hero-card-lab">
            Ranks a real founder above a non-founder{" "}
            <strong>97% of the time</strong> ({HEADLINE.rocAucCiLo.toFixed(2)}–
            {HEADLINE.rocAucCiHi.toFixed(2)})
          </div>
        </div>

        <div className="hero-card">
          <div className="hero-card-q">
            <InfoTip label="precision@10">
              Of the 10 people the system ranks highest, how many actually
              emerged. Random picking lands near the {HEADLINE.baseRatePct}% base
              rate.
            </InfoTip>
          </div>
          <div className="hero-frac">
            <span className="big-frac">{modelHitsPer10}</span>
            <span className="big-frac-denom">/10</span>
          </div>
          <div className="hero-card-lab">
            Of the model&apos;s top 10 picks,{" "}
            <strong>~{modelHitsPer10} are real founders</strong> — vs ~
            {randomHitsPer10} of 10 picked at random
          </div>
        </div>

        <div className="hero-card">
          <div className="hero-card-q">
            <InfoTip label="lead time">
              For founders whose public history reaches back before they
              emerged: how many months earlier the model first flagged them as
              &quot;tracked.&quot;
            </InfoTip>
          </div>
          <div className="big-pct">
            +{HEADLINE.leadMedianMonths}
            <span className="hero-unit"> mo</span>
          </div>
          <div className="hero-card-lab">
            Median <strong>head-start</strong>: flagged {HEADLINE.leadFounders}{" "}
            founders ~{HEADLINE.leadMedianMonths} months (up to{" "}
            {HEADLINE.leadMaxMonths}) before they emerged
          </div>
        </div>
      </div>

      <p className="hero-foot">
        Built entirely from <strong>free public signals</strong> — Hacker News
        posts, archived tweets. No private data, no paid APIs. n = {HEADLINE.n}{" "}
        ({HEADLINE.nPos} founders, {HEADLINE.nNeg} in-niche peers) ·{" "}
        {cohortSize} named cohort founders.
      </p>

      <button className="hero-cta" onClick={onStart}>
        See it pick founders over time →
      </button>
    </section>
  );
}
