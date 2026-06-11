"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  loadFounderPosts,
  plainText,
  type FounderPosts,
} from "@/lib/thesis/demoData";

// /demo — the live read. One serious instrument, no games: point the system
// at a real public profile (HN / Reddit / Bluesky live; paste for X or
// anything else) and it reads their recent posts through the study's lens.
//
// While the research API budget is empty the live call fails closed and the
// page leans on the SAMPLE READ — assembled verbatim from the study's real
// scored records (real posts, real flag/launch dates), clearly labelled.

type Platform = "hn" | "reddit" | "bluesky" | "x" | "other";

const PLATFORMS: { id: Platform; label: string; live: boolean }[] = [
  { id: "hn", label: "Hacker News", live: true },
  { id: "reddit", label: "Reddit", live: true },
  { id: "bluesky", label: "Bluesky", live: true },
  { id: "x", label: "X / Twitter", live: false },
  { id: "other", label: "anywhere else", live: false },
];

interface ApiResult {
  score: number;
  doing: number;
  telling: number;
  connecting: number;
  read: string;
  evidence: { excerpt: string; note: string }[];
  n_posts: number;
  source: string;
}

const FAMILIES: { key: "doing" | "telling" | "connecting"; label: string; blurb: string }[] = [
  { key: "doing", label: "Doing", blurb: "building and shipping in public" },
  { key: "telling", label: "Telling", blurb: "saying the goal out loud" },
  { key: "connecting", label: "Connecting", blurb: "pulling the right people in" },
];

function band(score: number): string {
  if (score >= 8) return "an unmistakable founder trail";
  if (score >= 6) return "a strong founder trail";
  if (score >= 4) return "a developing trail";
  if (score >= 2) return "a faint trail";
  return "no meaningful trail";
}

const STATUS_LINES = [
  "fetching their public posts…",
  "reading the posts…",
  "weighing the three families…",
  "writing the read…",
];

export function LiveRead() {
  const [platform, setPlatform] = useState<Platform>("hn");
  const [handle, setHandle] = useState("");
  const [pasted, setPasted] = useState("");
  const [busy, setBusy] = useState(false);
  const [statusIdx, setStatusIdx] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ApiResult | null>(null);
  const [sample, setSample] = useState<FounderPosts | null>(null);
  const [sampleOpen, setSampleOpen] = useState(false);
  const statusTimer = useRef<ReturnType<typeof setInterval> | null>(null);

  const live = PLATFORMS.find((p) => p.id === platform)?.live ?? false;
  const ready = live ? handle.trim().length > 1 : pasted.trim().length > 40;

  // Sample read: the study's real record for one founder it flagged early.
  useEffect(() => {
    let alive = true;
    loadFounderPosts()
      .then((b) => {
        if (!alive) return;
        const pick =
          b.founders
            .filter(
              (f) =>
                (f.lead_time_months ?? 0) >= 6 &&
                f.posts.filter((p) => p.signals.length > 0).length >= 3,
            )
            .sort(
              (a, z) => (z.lead_time_months ?? 0) - (a.lead_time_months ?? 0),
            )[0] ?? b.founders[0];
        setSample(pick ?? null);
      })
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, []);

  useEffect(() => {
    if (!busy) {
      if (statusTimer.current) clearInterval(statusTimer.current);
      setStatusIdx(0);
      return;
    }
    statusTimer.current = setInterval(
      () => setStatusIdx((i) => Math.min(i + 1, STATUS_LINES.length - 1)),
      1600,
    );
    return () => {
      if (statusTimer.current) clearInterval(statusTimer.current);
    };
  }, [busy]);

  const samplePosts = useMemo(() => {
    if (!sample) return [];
    return [...sample.posts]
      .filter((p) => p.signals.length > 0)
      .sort((a, z) => z.strength - a.strength)
      .slice(0, 3)
      .sort((a, z) => (a.date < z.date ? -1 : 1));
  }, [sample]);

  const submit = async () => {
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const body = live
        ? { platform, handle: handle.trim() }
        : {
            platform,
            posts: pasted
              .split(/\n\s*\n|\n/)
              .map((s) => s.trim())
              .filter((s) => s.length > 10)
              .slice(0, 10),
          };
      const r = await fetch("/api/score", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await r.json();
      if (!r.ok) setError(data.error ?? "Something hiccuped — try again.");
      else setResult(data as ApiResult);
    } catch {
      setError("Network hiccup — try again in a moment.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="lp dm">
      <header className="dm-top">
        <a className="dm-back mono" href="/">
          ← the story
        </a>
      </header>

      <section className="lp-section dm-live" aria-label="Live read">
        <p className="lp-kicker mono">Founder Radar · the live demo</p>
        <h1 className="dm-h1">A live read on any builder.</h1>
        <p className="lp-body">
          This is the study&apos;s lens, pointed at the present. Pick where
          someone posts, drop in their handle, and the system reads their
          recent public posts and writes its honest read — the same three
          things it looked for in the research:
        </p>

        <ul className="dm-fam-key">
          {FAMILIES.map((f) => (
            <li key={f.key}>
              <strong>{f.label}</strong> — {f.blurb}
            </li>
          ))}
        </ul>

        <div className="dm-console">
          <div className="dm-sa-platforms" role="tablist" aria-label="platform">
            {PLATFORMS.map((p) => (
              <button
                key={p.id}
                role="tab"
                aria-selected={platform === p.id}
                className={"dm-chip" + (platform === p.id ? " is-on" : "")}
                onClick={() => {
                  setPlatform(p.id);
                  setResult(null);
                  setError(null);
                }}
              >
                {p.label}
                {p.live && <span className="dm-chip-live"> ●</span>}
              </button>
            ))}
          </div>

          {live ? (
            <div className="dm-sa-row">
              <input
                className="dm-sa-input mono"
                type="text"
                placeholder={
                  platform === "bluesky"
                    ? "handle (e.g. pfrazee.com)"
                    : "handle (no @ needed)"
                }
                value={handle}
                onChange={(e) => setHandle(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && ready && !busy && submit()}
                aria-label="handle"
              />
              <button
                className="lp-tm-play dm-go mono"
                disabled={!ready || busy}
                onClick={submit}
              >
                {busy ? "reading…" : "run the read ▶"}
              </button>
            </div>
          ) : (
            <>
              <p className="dm-sa-note">
                {platform === "x"
                  ? "X doesn't let websites read profiles for free — paste a few of their (or your) recent posts instead. The reading is exactly the same."
                  : "Paste a few recent public posts — one per line. The reading is exactly the same."}
              </p>
              <textarea
                className="dm-sa-paste mono"
                rows={7}
                placeholder={"One post per line, up to ten…"}
                value={pasted}
                onChange={(e) => setPasted(e.target.value)}
                aria-label="pasted posts"
              />
              <div className="dm-sa-row">
                <button
                  className="lp-tm-play dm-go mono"
                  disabled={!ready || busy}
                  onClick={submit}
                >
                  {busy ? "reading…" : "run the read ▶"}
                </button>
              </div>
            </>
          )}

          {busy && (
            <p className="dm-status mono" aria-live="polite">
              {STATUS_LINES[statusIdx]}
            </p>
          )}
          {error && <p className="dm-sa-error">{error}</p>}
        </div>

        {result && (
          <article className="dm-readout" aria-label="the read">
            <p className="dm-readout-meta mono">
              read · {result.n_posts} recent posts · {result.source} · not stored
            </p>
            <p className="dm-readout-verdict">
              {result.read || "The system has written no note for this one."}
            </p>
            <p className="dm-readout-band">
              <span className="dm-readout-score mono">{result.score}/10</span>
              {" — "}
              {band(result.score)}
            </p>
            <div className="dm-sa-families">
              {FAMILIES.map((f) => {
                const v = result[f.key];
                return (
                  <div key={f.key} className="dm-sa-family">
                    <span className="dm-sa-family-label">{f.label}</span>
                    <span className="dm-sa-family-track" aria-hidden>
                      <span
                        className="dm-sa-family-fill"
                        style={{ width: `${Math.min(100, v * 100)}%` }}
                      />
                    </span>
                    <span className="dm-sa-family-blurb">{f.blurb}</span>
                  </div>
                );
              })}
            </div>
            {result.evidence.length > 0 && (
              <div className="dm-evidence">
                <p className="dm-evidence-title mono">what shaped the read</p>
                {result.evidence.map((e, i) => (
                  <blockquote key={i} className="dm-evidence-item">
                    <p className="dm-post-text">“{plainText(e.excerpt)}”</p>
                    {e.note && <footer className="dm-evidence-note mono">{e.note}</footer>}
                  </blockquote>
                ))}
              </div>
            )}
            <p className="lp-tm-honesty">
              Honest footnote: a high reading means &ldquo;worth a look
              early&rdquo;, not &ldquo;future winner&rdquo; — and the lens was
              calibrated on indie builders, so it will misread celebrities and
              companies. Nothing you run here is stored.
            </p>
          </article>
        )}

        {sample && (
          <div className="dm-sample">
            <button
              className="dm-ghost mono"
              onClick={() => setSampleOpen(!sampleOpen)}
              aria-expanded={sampleOpen}
            >
              {sampleOpen ? "hide the sample read" : "see a sample read from the study →"}
            </button>

            {sampleOpen && (
              <article className="dm-readout" aria-label="sample read">
                <p className="dm-readout-meta mono">
                  sample · from the study&apos;s real records · {sample.founder_name}
                </p>
                <p className="dm-readout-verdict">
                  The system flagged {sample.founder_name.split(" ")[0]}{" "}
                  {sample.lead_time_months != null && sample.lead_time_months > 0
                    ? `${Math.floor(sample.lead_time_months)} months before`
                    : "before"}{" "}
                  {sample.venture ? `${sample.venture} launched` : "launch"} — from
                  posts like these.
                </p>
                <div className="dm-evidence">
                  {samplePosts.map((p, i) => (
                    <blockquote key={i} className="dm-evidence-item">
                      <p className="dm-post-head mono">
                        <span className="dm-post-date">{p.date}</span>
                      </p>
                      <p className="dm-post-text">“{plainText(p.text)}”</p>
                      <footer className="dm-evidence-note mono">
                        {p.signals.join(" · ")}
                      </footer>
                    </blockquote>
                  ))}
                </div>
                <p className="lp-tm-honesty">
                  These are real posts and real dates from the study&apos;s
                  records — flagged{" "}
                  {sample.flag_date && <span className="mono">{sample.flag_date}</span>}
                  {sample.emergence_date && (
                    <>
                      , launched <span className="mono">{sample.emergence_date}</span>
                    </>
                  )}
                  . Nothing here is generated for show.
                </p>
              </article>
            )}
          </div>
        )}
      </section>
    </main>
  );
}
