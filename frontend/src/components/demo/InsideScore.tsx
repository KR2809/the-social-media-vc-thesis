"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { loadTimeline, type TimelineData } from "@/lib/thesis/timeline";
import {
  loadFounderPosts,
  plainText,
  scoreAt,
  type FounderPosts,
} from "@/lib/thesis/demoData";

// 🔍 Inside the Score — read the actual posts the system read, in time
// order, and watch the score climb as the evidence stacks up. Every post is
// real (export skips anything without raw text); the climbing meter is the
// founder's real trajectory sampled at each post's date. Names shown are
// emerged founders only, per the negatives protocol.

const PLATFORM_ICON: Record<string, string> = {
  twitter: "𝕏",
  hackernews: "Y",
  reddit: "r/",
  github: "gh",
  producthunt: "P",
};

export function InsideScore() {
  const [bundle, setBundle] = useState<{ founders: FounderPosts[] } | null>(null);
  const [timeline, setTimeline] = useState<TimelineData | null>(null);
  const [failed, setFailed] = useState(false);
  const [pid, setPid] = useState<string | null>(null);
  const [shown, setShown] = useState(0); // posts revealed so far
  const [playing, setPlaying] = useState(false);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);
  const feedEnd = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    let alive = true;
    Promise.all([loadFounderPosts(), loadTimeline()])
      .then(([p, t]) => {
        if (!alive) return;
        setBundle(p);
        setTimeline(t);
        const first = p.founders.find((f) => f.posts.length >= 5);
        setPid(first?.person_id ?? p.founders[0]?.person_id ?? null);
      })
      .catch(() => alive && setFailed(true));
    return () => {
      alive = false;
    };
  }, []);

  const founder = useMemo(
    () => bundle?.founders.find((f) => f.person_id === pid) ?? null,
    [bundle, pid],
  );
  const tf = useMemo(
    () => timeline?.founders.find((f) => f.person_id === pid) ?? null,
    [timeline, pid],
  );

  useEffect(() => {
    setShown(0);
    setPlaying(false);
  }, [pid]);

  useEffect(() => {
    if (!playing || !founder) return;
    timer.current = setInterval(() => {
      setShown((n) => {
        if (n + 1 >= founder.posts.length) {
          setPlaying(false);
          return founder.posts.length;
        }
        return n + 1;
      });
    }, 900);
    return () => {
      if (timer.current) clearInterval(timer.current);
    };
  }, [playing, founder]);

  useEffect(() => {
    if (shown > 1) feedEnd.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [shown]);

  if (failed) {
    return (
      <section className="lp-section">
        <p className="lp-error">The post feed didn&apos;t load. Try a refresh.</p>
      </section>
    );
  }
  if (!bundle || !founder) {
    return (
      <section className="lp-section">
        <div className="lp-tm-loading mono">loading the real posts…</div>
      </section>
    );
  }

  const visible = founder.posts.slice(0, Math.max(shown, 1));
  const lastDate = visible[visible.length - 1]?.date ?? founder.flag_date;
  const score = tf ? scoreAt(tf, lastDate) : 0;
  const done = shown >= founder.posts.length;
  const flagged = founder.flag_date <= lastDate;

  return (
    <section className="lp-section dm-inside" aria-label="Inside the score">
      <p className="lp-kicker mono">🔍 Inside the score</p>
      <h2 className="lp-h2">The posts the system actually read.</h2>
      <p className="lp-body">
        Pick a founder. These are their real public posts, oldest first, with
        the habits the system noticed underneath each one. The meter on the
        right is the system&apos;s read of them climbing as the evidence
        stacks up.
      </p>

      <div className="dm-inside-people" role="tablist" aria-label="founder">
        {bundle.founders
          .filter((f) => f.posts.length >= 3)
          .map((f) => (
            <button
              key={f.person_id}
              role="tab"
              aria-selected={pid === f.person_id}
              className={"dm-chip" + (pid === f.person_id ? " is-on" : "")}
              onClick={() => setPid(f.person_id)}
            >
              {f.founder_name}
            </button>
          ))}
      </div>

      <div className="dm-inside-meta mono">
        {founder.venture && <span>→ went on to found {founder.venture}</span>}
        {founder.lead_time_months != null && founder.lead_time_months > 0 && (
          <span>
            · flagged {Math.floor(founder.lead_time_months)} months before launch
          </span>
        )}
      </div>

      <div className="dm-inside-stage">
        <div className="dm-feed">
          {visible.map((p, i) => (
            <article className="dm-post" key={`${p.date}-${i}`}>
              <header className="dm-post-head mono">
                <span className="dm-post-platform">
                  {PLATFORM_ICON[p.platform] ?? p.platform}
                </span>
                <span className="dm-post-date">{p.date}</span>
              </header>
              <p className="dm-post-text">{plainText(p.text)}</p>
              {p.signals.length > 0 && (
                <footer className="dm-post-signals">
                  {p.signals.map((s) => (
                    <span key={s} className="dm-post-signal mono">
                      {s}
                    </span>
                  ))}
                </footer>
              )}
            </article>
          ))}
          <div ref={feedEnd} />
        </div>

        <aside className="dm-meterbox">
          <div className="dm-meter" aria-label="system score">
            <div
              className="dm-meter-fill"
              style={{ height: `${Math.min(100, score * 100)}%` }}
            />
          </div>
          <div className="dm-meter-cap mono">
            the system&apos;s read
            {flagged && <span className="dm-meter-flag">⚑ flagged</span>}
          </div>
        </aside>
      </div>

      <div className="dm-inside-controls">
        <button
          className="lp-tm-play dm-go mono"
          onClick={() => {
            if (done) setShown(1);
            setPlaying(!playing);
          }}
        >
          {playing ? "⏸ pause" : done ? "↺ replay" : "▶ play the evidence"}
        </button>
        <button
          className="dm-ghost mono"
          disabled={done}
          onClick={() => {
            setPlaying(false);
            setShown((n) => Math.min(founder.posts.length, n + 1));
          }}
        >
          next post →
        </button>
        <span className="mono dm-inside-count">
          {Math.max(shown, 1)}/{founder.posts.length} posts
        </span>
      </div>

      <p className="lp-tm-honesty">
        Honest footnote: these are this founder&apos;s strongest posts, not
        every post — and only people who actually launched are named here.
        Posts are shown exactly as collected; nothing is paraphrased or
        invented.
      </p>
    </section>
  );
}
