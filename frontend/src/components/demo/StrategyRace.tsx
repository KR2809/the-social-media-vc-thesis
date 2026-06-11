"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { loadDemoStats, type RaceData } from "@/lib/thesis/demoData";

// 🏁 The Strategy Race — five picking strategies replayed over the real
// backtest. Each lane shows: of that strategy's top-K picks at this date,
// what share went on to launch. Lanes re-rank live as the clock advances.
// Honest by construction: the numbers come straight from backtest_results.csv.

const STRATEGIES: { key: string; label: string; note: string; accent?: boolean }[] = [
  {
    key: "two_tier",
    label: "The system",
    note: "the full read: what they do, what they say, who they pull in",
    accent: true,
  },
  {
    key: "signal_volume",
    label: "Whoever posts most",
    note: "the embarrassingly simple one",
  },
  {
    key: "tier1_only",
    label: "The system, halved",
    note: "same data, half the signals",
  },
  { key: "recency", label: "Most recently active", note: "whoever posted latest" },
  { key: "random", label: "Random luck", note: "names out of a hat" },
];

const ROW_H = 64;

export function StrategyRace() {
  const [race, setRace] = useState<RaceData | null>(null);
  const [failed, setFailed] = useState(false);
  const [k, setK] = useState(5);
  const [idx, setIdx] = useState(0);
  const [playing, setPlaying] = useState(false);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    let alive = true;
    loadDemoStats()
      .then((d) => alive && (d.race ? setRace(d.race) : setFailed(true)))
      .catch(() => alive && setFailed(true));
    return () => {
      alive = false;
    };
  }, []);

  // Only race over dates where the system has a reading (early grid is empty).
  const liveIdxs = useMemo(() => {
    if (!race) return [];
    const sys = race.series[`two_tier|${k}`] ?? [];
    return race.dates.map((_, i) => i).filter((i) => sys[i] != null);
  }, [race, k]);

  useEffect(() => {
    setIdx(0);
    setPlaying(false);
  }, [k]);

  useEffect(() => {
    if (!playing || liveIdxs.length === 0) return;
    timer.current = setInterval(() => {
      setIdx((i) => {
        if (i + 1 >= liveIdxs.length) {
          setPlaying(false);
          return i;
        }
        return i + 1;
      });
    }, 110);
    return () => {
      if (timer.current) clearInterval(timer.current);
    };
  }, [playing, liveIdxs.length]);

  if (failed) {
    return (
      <section className="lp-section">
        <p className="lp-error">The race data didn&apos;t load. Try a refresh.</p>
      </section>
    );
  }
  if (!race) {
    return (
      <section className="lp-section">
        <div className="lp-tm-loading mono">loading the real backtest…</div>
      </section>
    );
  }

  const di = liveIdxs[Math.min(idx, Math.max(0, liveIdxs.length - 1))] ?? 0;
  const date = race.dates[di] ?? "";
  const atEnd = idx >= liveIdxs.length - 1;

  const standings = STRATEGIES.map((s) => {
    const v = race.series[`${s.key}|${k}`]?.[di];
    return { ...s, v: v == null ? null : v };
  }).sort((a, b) => (b.v ?? -1) - (a.v ?? -1));

  return (
    <section className="lp-section dm-race" aria-label="The strategy race">
      <p className="lp-kicker mono">🏁 The strategy race</p>
      <h2 className="lp-h2">Five ways to pick. One has hindsight checked off.</h2>
      <p className="lp-body">
        We replayed history month by month. At every date, each strategy names
        its top {k} people using only what was public <em>then</em> — and the
        bar shows how many of those picks went on to launch a company. Press
        play and watch the field re-order itself.
      </p>

      <div className="dm-race-controls">
        <button
          className="lp-tm-play mono"
          onClick={() => {
            if (atEnd) setIdx(0);
            setPlaying(!playing);
          }}
          aria-label={playing ? "pause" : "play"}
        >
          {playing ? "⏸" : atEnd && idx > 0 ? "↺" : "▶"}
        </button>
        <input
          className="lp-tm-range"
          type="range"
          min={0}
          max={Math.max(0, liveIdxs.length - 1)}
          value={Math.min(idx, liveIdxs.length - 1)}
          onChange={(e) => {
            setPlaying(false);
            setIdx(parseInt(e.target.value, 10));
          }}
          aria-label="race date"
        />
        <span className="lp-tm-date mono">{date.slice(0, 7)}</span>
      </div>

      <div className="dm-race-ks mono" role="tablist" aria-label="picks per strategy">
        {race.ks.map((kk) => (
          <button
            key={kk}
            role="tab"
            aria-selected={k === kk}
            className={"dm-chip" + (k === kk ? " is-on" : "")}
            onClick={() => setK(kk)}
          >
            top {kk}
          </button>
        ))}
      </div>

      <div className="dm-lanes" style={{ height: STRATEGIES.length * ROW_H }}>
        {standings.map((s, rank) => (
          <div
            key={s.key}
            className={"dm-lane" + (s.accent ? " is-system" : "")}
            style={{ transform: `translateY(${rank * ROW_H}px)` }}
          >
            <div className="dm-lane-head">
              <span className="dm-lane-name">{s.label}</span>
              <span className="dm-lane-note">{s.note}</span>
            </div>
            <div className="dm-lane-track" aria-hidden>
              <div
                className="dm-lane-fill"
                style={{ width: `${(s.v ?? 0) * 100}%` }}
              />
            </div>
            <span className="dm-lane-pct mono">
              {s.v == null ? "—" : `${Math.floor(s.v * 100)}% launched`}
            </span>
          </div>
        ))}
      </div>

      <p className="lp-tm-honesty">
        Honest footnote: &ldquo;whoever posts most&rdquo; keeps up with the
        system on this chart — final rankings aren&apos;t where the edge is.
        The system&apos;s real advantage is flagging people <em>years</em>{" "}
        before launch, which a volume count can&apos;t time. Every number here
        is a real measured result, not a projection.
      </p>
    </section>
  );
}
