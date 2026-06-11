"use client";

import { useEffect, useMemo, useState } from "react";
import { loadDemoStats, type McRow } from "@/lib/thesis/demoData";

// 💼 The Fund Simulator — the one screen that is a PROJECTION, and says so
// loudly. Rows come from monte_carlo_projection.csv: if you backed the
// system's top-K people, the simulated share that go on to launch, with the
// simulation's own low/high range. Headline counts use floor() so we never
// round a claim upwards.

export function FundSim() {
  const [mc, setMc] = useState<McRow[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [step, setStep] = useState(1); // index into mc rows

  useEffect(() => {
    let alive = true;
    loadDemoStats()
      .then((d) => alive && (d.mc?.length ? setMc(d.mc) : setFailed(true)))
      .catch(() => alive && setFailed(true));
    return () => {
      alive = false;
    };
  }, []);

  const row = mc?.[Math.min(step, (mc?.length ?? 1) - 1)] ?? null;

  const dots = useMemo(() => {
    if (!row) return [];
    const expected = Math.floor(row.rate * row.k);
    return Array.from({ length: row.k }, (_, i) => i < expected);
  }, [row]);

  if (failed) {
    return (
      <section className="lp-section">
        <p className="lp-error">The simulator data didn&apos;t load. Try a refresh.</p>
      </section>
    );
  }
  if (!mc || !row) {
    return (
      <section className="lp-section">
        <div className="lp-tm-loading mono">loading the simulation…</div>
      </section>
    );
  }

  const expected = Math.floor(row.rate * row.k);
  const lo = Math.floor(row.lo * row.k);
  const hi = Math.floor(row.hi * row.k);

  return (
    <section className="lp-section dm-fund" aria-label="The fund simulator">
      <p className="lp-kicker mono">💼 The fund simulator</p>
      <h2 className="lp-h2">If this were a fund, how would it do?</h2>
      <p className="lp-body">
        Drag the fund size. Each face is one builder the system would have
        backed; the filled ones are the share the simulation expects to launch
        a company.
      </p>

      <p className="dm-projection mono">
        ⚠ this screen is a projection, not a measured result
      </p>

      <div className="dm-fund-controls">
        <span className="mono dm-fund-klabel">back the top</span>
        <input
          type="range"
          className="lp-tm-range"
          min={0}
          max={mc.length - 1}
          step={1}
          value={step}
          onChange={(e) => setStep(parseInt(e.target.value, 10))}
          aria-label="fund size"
        />
        <span className="dm-fund-k mono">{row.k} builders</span>
      </div>

      <div className="dm-fund-grid" aria-hidden>
        {dots.map((hit, i) => (
          <span
            key={`${row.k}-${i}`}
            className={"dm-fund-dot" + (hit ? " hit" : "")}
            style={{ animationDelay: `${Math.min(i * 14, 700)}ms` }}
          />
        ))}
      </div>

      <p className="dm-fund-verdict">
        Back the system&apos;s top <strong>{row.k}</strong> and the simulation
        expects <strong>about {expected}</strong> of them to launch — its own
        range runs from {lo} to {hi}.
      </p>

      <p className="lp-tm-honesty">
        Honest footnote: this comes from re-running the study&apos;s real
        scores thousands of times with the luck shuffled — it is{" "}
        <em>not</em> something we observed. The real, measured results live in
        the strategy race and the game. And &ldquo;launch a company&rdquo; is
        the finish line here, not &ldquo;build a successful one&rdquo; — this
        study stops at day zero.
      </p>
    </section>
  );
}
