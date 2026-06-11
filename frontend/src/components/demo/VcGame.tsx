"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { loadTimeline, type TimelineData } from "@/lib/thesis/timeline";
import {
  boardAt,
  everEmerged,
  seededPicks,
  type GameCandidate,
} from "@/lib/thesis/demoData";

// 🎲 You Be the VC — the flagship game (full-demo design §2).
// Real trajectories decide who is on the board at your chosen date; real
// outcomes decide the scoreboard. Candidates are anonymised while you draft
// (that's the honest version of the decision a VC faces); after the reveal,
// founders who emerged show their real names — people who didn't stay
// anonymous, per the study's negatives protocol.

const YEARS = [2019, 2020, 2021, 2022, 2023];
const PICK_N = 5;

type Phase = "year" | "draft" | "forward" | "result";

export function VcGame() {
  const [data, setData] = useState<TimelineData | null>(null);
  const [phase, setPhase] = useState<Phase>("year");
  const [year, setYear] = useState<number | null>(null);
  const [picks, setPicks] = useState<Set<string>>(new Set());
  const [reveal, setReveal] = useState(false);
  const [ffDate, setFfDate] = useState<string | null>(null);
  const ffTimer = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    let alive = true;
    loadTimeline().then((d) => alive && setData(d));
    return () => {
      alive = false;
    };
  }, []);

  const date = year ? `${year}-01-01` : null;
  const board: GameCandidate[] = useMemo(
    () => (data && date ? boardAt(data, date, 12) : []),
    [data, date],
  );

  const systemPicks = useMemo(
    () => new Set(board.slice(0, PICK_N).map((c) => c.f.person_id)),
    [board],
  );
  const randomPicks = useMemo(
    () =>
      new Set(
        seededPicks(board, PICK_N, year ?? 1).map((c) => c.f.person_id),
      ),
    [board, year],
  );

  const hits = (set: Set<string>) =>
    board.filter((c) => set.has(c.f.person_id) && everEmerged(c.f)).length;

  // Fast-forward animation: month counter from the draft date to the end.
  // Progress is wall-clock based (not tick-counted) so browser timer
  // throttling in background tabs can't stall it.
  useEffect(() => {
    if (phase !== "forward" || !data || !date) return;
    const dates = data.dates.filter((d) => d >= date);
    const durationMs = Math.min(2600, dates.length * 38);
    const start = Date.now();
    ffTimer.current = setInterval(() => {
      const t = (Date.now() - start) / durationMs;
      if (t >= 1) {
        if (ffTimer.current) clearInterval(ffTimer.current);
        setFfDate(dates[dates.length - 1]);
        setTimeout(() => setPhase("result"), 450);
      } else {
        setFfDate(dates[Math.floor(t * (dates.length - 1))]);
      }
    }, 38);
    return () => {
      if (ffTimer.current) clearInterval(ffTimer.current);
    };
  }, [phase, data, date]);

  const toggle = (pid: string) => {
    setPicks((prev) => {
      const next = new Set(prev);
      if (next.has(pid)) next.delete(pid);
      else if (next.size < PICK_N) next.add(pid);
      return next;
    });
  };

  const reset = () => {
    setPhase("year");
    setYear(null);
    setPicks(new Set());
    setReveal(false);
    setFfDate(null);
  };

  if (!data) {
    return (
      <section className="lp-section">
        <div className="lp-tm-loading mono">loading the real data…</div>
      </section>
    );
  }

  return (
    <section className="lp-section dm-game" aria-label="You be the VC">
      <p className="lp-kicker mono">🎲 You be the VC</p>

      {phase === "year" && (
        <>
          <h2 className="lp-h2">First: pick your moment in history.</h2>
          <p className="lp-body">
            You&apos;ll see the people the system was watching at that date —
            scored using only what was public <em>then</em>. No hindsight
            allowed (for you or for it).
          </p>
          <div className="dm-years">
            {YEARS.map((y) => (
              <button
                key={y}
                className="dm-year mono"
                onClick={() => {
                  setYear(y);
                  setPhase("draft");
                }}
              >
                {y}
              </button>
            ))}
          </div>
        </>
      )}

      {phase === "draft" && date && (
        <>
          <h2 className="lp-h2">
            January {year}: back {PICK_N} of these builders.
          </h2>
          <p className="lp-body">
            Names hidden — that&apos;s the real decision a scout faces. Each
            card shows the system&apos;s read at the time, and a real post
            where there is one.
          </p>
          <div className="dm-board">
            {board.map((c, i) => {
              const picked = picks.has(c.f.person_id);
              return (
                <button
                  key={c.f.person_id}
                  className={"dm-cand" + (picked ? " is-picked" : "")}
                  onClick={() => toggle(c.f.person_id)}
                  aria-pressed={picked}
                >
                  <span className="dm-cand-head">
                    <span className="dm-cand-name">Builder #{i + 1}</span>
                    {c.rising && (
                      <span className="dm-cand-rising mono">rising ↗</span>
                    )}
                  </span>
                  <span className="dm-cand-meter" aria-hidden>
                    <span
                      className="dm-cand-fill"
                      style={{ width: `${Math.min(100, c.score * 200)}%` }}
                    />
                  </span>
                  {c.quote ? (
                    <span className="dm-cand-quote">“{c.quote.slice(0, 90)}”</span>
                  ) : (
                    <span className="dm-cand-quote dm-muted">
                      (quiet — little public signal yet)
                    </span>
                  )}
                  <span className="dm-cand-pick mono">
                    {picked ? "✓ in your five" : "tap to back"}
                  </span>
                </button>
              );
            })}
          </div>
          <div className="dm-draft-bar">
            <span className="mono">
              {picks.size}/{PICK_N} picked
            </span>
            <button
              className="dm-ghost mono"
              onClick={() => setPicks(new Set(systemPicks))}
            >
              let the machine pick
            </button>
            <button
              className="lp-tm-play dm-go mono"
              disabled={picks.size !== PICK_N}
              onClick={() => setPhase("forward")}
            >
              fast-forward ▶
            </button>
          </div>
        </>
      )}

      {phase === "forward" && (
        <div className="dm-ff">
          <p className="lp-kicker mono">fast-forwarding…</p>
          <div className="dm-ff-date mono">{ffDate?.slice(0, 7)}</div>
        </div>
      )}

      {phase === "result" && (
        <>
          <h2 className="lp-h2">The verdict, from real outcomes.</h2>
          <div className="dm-score">
            {[
              { label: "You", n: hits(picks) },
              { label: "The system", n: hits(systemPicks) },
              { label: "Random luck", n: hits(randomPicks) },
            ].map((row) => (
              <div key={row.label} className="dm-score-row">
                <span className="dm-score-label">{row.label}</span>
                <span className="dm-score-dots" aria-hidden>
                  {Array.from({ length: PICK_N }, (_, i) => (
                    <span
                      key={i}
                      className={"dm-score-dot" + (i < row.n ? " hit" : "")}
                    />
                  ))}
                </span>
                <span className="dm-score-n mono">
                  {row.n}/{PICK_N} became founders
                </span>
              </div>
            ))}
          </div>

          <div className="dm-result-board">
            {board.map((c, i) => {
              const emerged = everEmerged(c.f);
              const mine = picks.has(c.f.person_id);
              return (
                <div
                  key={c.f.person_id}
                  className={
                    "dm-result-row" +
                    (emerged ? " emerged" : "") +
                    (mine ? " mine" : "")
                  }
                >
                  <span className="dm-result-name">
                    {reveal && emerged ? c.f.founder_name : `Builder #${i + 1}`}
                    {reveal && emerged && c.f.venture && (
                      <span className="dm-result-venture"> · {c.f.venture}</span>
                    )}
                  </span>
                  <span className="mono dm-result-outcome">
                    {emerged ? "✓ launched" : "didn't (yet)"}
                  </span>
                  {mine && <span className="dm-result-yours mono">your pick</span>}
                </div>
              );
            })}
          </div>

          <div className="dm-result-actions">
            <button className="dm-ghost mono" onClick={() => setReveal(!reveal)}>
              {reveal ? "hide names" : "reveal who they were"}
            </button>
            <button className="dm-ghost mono" onClick={reset}>
              play another year ↺
            </button>
          </div>
          <p className="lp-tm-honesty">
            Honest footnote: across all dates, simply backing whoever posted
            the most also does well — the machine&apos;s real edge is how{" "}
            <em>early</em> it flags people, not the final ordering. Builders
            who didn&apos;t launch stay anonymous on purpose.
          </p>
        </>
      )}
    </section>
  );
}
