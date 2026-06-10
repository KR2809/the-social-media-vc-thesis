"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  loadTimeline,
  type TimelineData,
  type TimelineFounder,
} from "@/lib/thesis/timeline";
import { FounderDetail } from "./FounderDetail";

// §4 TIME MACHINE — the interactive centerpiece (spec §4).
//
// Drag time forward and watch the system flag real founders (blue) BEFORE
// their launch badge (gold) lands. Everything here is the real backtest:
// real names, real first-pickup dates, real emergence dates, real lead
// times. Honesty built in: founders whose public history starts too late
// show the badge before the flag, labelled as a data limit, never hidden.
//
// The scrubber is a native <input type="range"> — keyboard and touch
// accessible by default. Auto-plays once when first scrolled into view,
// then yields to the user on any interaction.

function fmtMonth(iso: string): string {
  const [y, m] = iso.split("-");
  const names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                 "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  return `${names[parseInt(m, 10) - 1]} ${y}`;
}

interface Row {
  f: TimelineFounder;
  pickupPct: number | null; // x-position 0..100 on the axis
  emergePct: number | null;
  lateData: boolean; // pickup after emergence (shallow history)
}

function buildRows(data: TimelineData): Row[] {
  const dates = data.dates;
  const x = (iso: string | null): number | null => {
    if (!iso) return null;
    const first = dates[0];
    const last = dates[dates.length - 1];
    if (iso <= first) return 0;
    if (iso >= last) return 100;
    // index of first grid date >= iso
    let idx = dates.findIndex((d) => d >= iso);
    if (idx < 0) idx = dates.length - 1;
    return (idx / (dates.length - 1)) * 100;
  };

  return data.founders
    .filter((f) => f.is_positive && f.first_pickup_date)
    .map((f) => ({
      f,
      pickupPct: x(f.first_pickup_date),
      emergePct: x(f.emergence_date),
      lateData: (f.lead_time_months ?? 0) < 0,
    }))
    // Earliest pickup first; founders with a true pre-launch lead on top.
    .sort((a, b) => {
      const la = a.f.lead_time_months ?? -999;
      const lb = b.f.lead_time_months ?? -999;
      return lb - la;
    });
}

export function TimeMachine() {
  const [data, setData] = useState<TimelineData | null>(null);
  const [error, setError] = useState(false);
  const [idx, setIdx] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [hasPlayed, setHasPlayed] = useState(false);
  const [selected, setSelected] = useState<TimelineFounder | null>(null);
  const sectionRef = useRef<HTMLElement | null>(null);
  const playTimer = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    let alive = true;
    loadTimeline()
      .then((d) => alive && setData(d))
      .catch(() => alive && setError(true));
    return () => {
      alive = false;
    };
  }, []);

  const rows = useMemo(() => (data ? buildRows(data) : []), [data]);

  // Auto-play once when the section first becomes visible.
  useEffect(() => {
    const el = sectionRef.current;
    if (!el || !data || hasPlayed) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      setIdx(data.dates.length - 1); // show the finished state, no animation
      setHasPlayed(true);
      return;
    }
    const obs = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) {
          setHasPlayed(true);
          setPlaying(true);
          obs.disconnect();
        }
      },
      { threshold: 0.35 },
    );
    obs.observe(el);
    return () => obs.disconnect();
  }, [data, hasPlayed]);

  // Drive the playhead.
  useEffect(() => {
    if (!playing || !data) return;
    playTimer.current = setInterval(() => {
      setIdx((i) => {
        if (i >= data.dates.length - 1) {
          setPlaying(false);
          return i;
        }
        return i + 1;
      });
    }, 42);
    return () => {
      if (playTimer.current) clearInterval(playTimer.current);
    };
  }, [playing, data]);

  const stopAutoplay = () => setPlaying(false);

  if (error) {
    return (
      <section id="time-machine" className="lp-section lp-tm">
        <p className="lp-kicker mono">The time machine</p>
        <p className="lp-body">
          The replay data failed to load — refresh to try again. (Nothing is
          shown from invented data.)
        </p>
      </section>
    );
  }

  const dates = data?.dates ?? [];
  const current = dates[Math.min(idx, dates.length - 1)] ?? "";
  const flagged = rows.filter((r) => r.f.first_pickup_date! <= current);
  const launched = rows.filter(
    (r) => r.f.emergence_date && r.f.emergence_date <= current,
  );

  return (
    <section
      id="time-machine"
      ref={sectionRef}
      className="lp-section lp-tm"
      aria-label="The time machine — replay the predictions"
    >
      <p className="lp-kicker mono">Try it — the time machine</p>
      <h2 className="lp-h2">Watch it call founders before they launch.</h2>
      <p className="lp-body">
        This is the real test, replayed. Drag through time: a{" "}
        <span className="lp-tm-key lp-tm-key-flag">blue dot</span> appears the
        month the system first flagged someone — using only what was public at
        that moment — and a{" "}
        <span className="lp-tm-key lp-tm-key-launch">gold badge</span> lands
        when they actually launched. The gap between the two is the head-start.
      </p>

      {!data ? (
        <div className="lp-tm-loading mono">loading the real replay data…</div>
      ) : (
        <>
          <div className="lp-tm-controls">
            <button
              className="lp-tm-play mono"
              onClick={() => {
                if (playing) {
                  stopAutoplay();
                } else {
                  if (idx >= dates.length - 1) setIdx(0);
                  setPlaying(true);
                }
              }}
              aria-label={playing ? "Pause replay" : "Play replay"}
            >
              {playing ? "❚❚" : "▶"}
            </button>
            <input
              type="range"
              className="lp-tm-range"
              min={0}
              max={dates.length - 1}
              value={idx}
              onChange={(e) => {
                stopAutoplay();
                setIdx(parseInt(e.target.value, 10));
              }}
              onPointerDown={stopAutoplay}
              aria-label="Replay date"
              aria-valuetext={fmtMonth(current)}
            />
            <div className="lp-tm-date mono" aria-live="polite">
              {fmtMonth(current)}
            </div>
          </div>

          <div className="lp-tm-counts mono">
            flagged so far: <strong>{flagged.length}</strong> · launched so
            far: <strong>{launched.length}</strong>
          </div>

          <div className="lp-tm-board" role="list">
            {rows.map((r) => {
              const picked = r.f.first_pickup_date! <= current;
              const emerged = !!r.f.emergence_date && r.f.emergence_date <= current;
              const lead = r.f.lead_time_months;
              return (
                <button
                  key={r.f.person_id}
                  role="listitem"
                  className={
                    "lp-tm-row" +
                    (picked ? " is-picked" : "") +
                    (emerged ? " is-emerged" : "")
                  }
                  onClick={() => setSelected(r.f)}
                  aria-label={`${r.f.founder_name} — open details`}
                >
                  <span className="lp-tm-name">
                    {r.f.founder_name}
                    {emerged && lead != null && lead > 0 && (
                      <span className="lp-tm-lead mono">
                        +{lead} mo early
                      </span>
                    )}
                    {emerged && r.lateData && (
                      <span className="lp-tm-late mono" title="Public history for this founder starts after their launch — shown honestly.">
                        data starts late
                      </span>
                    )}
                  </span>
                  <span className="lp-tm-track" aria-hidden>
                    {r.pickupPct != null && r.emergePct != null && (
                      <span
                        className="lp-tm-bar"
                        style={{
                          left: `${Math.min(r.pickupPct, r.emergePct)}%`,
                          width: `${Math.abs(r.emergePct - r.pickupPct)}%`,
                        }}
                      />
                    )}
                    {r.pickupPct != null && (
                      <span
                        className="lp-tm-dot"
                        style={{ left: `${r.pickupPct}%` }}
                      />
                    )}
                    {r.emergePct != null && (
                      <span
                        className="lp-tm-badge"
                        style={{ left: `${r.emergePct}%` }}
                      >
                        ✓
                      </span>
                    )}
                    <span
                      className="lp-tm-playhead"
                      style={{ left: `${(idx / Math.max(dates.length - 1, 1)) * 100}%` }}
                    />
                  </span>
                </button>
              );
            })}
          </div>

          <p className="lp-tm-honesty">
            Some well-known founders launched before our public data begins —
            for them the badge shows up before the flag. That&apos;s a limit of
            the data, shown honestly, not hidden.
          </p>

          {selected && (
            <FounderDetail
              founder={selected}
              onClose={() => setSelected(null)}
            />
          )}
        </>
      )}
    </section>
  );
}
