"use client";

import { useState } from "react";

// 📡 Score Anyone — the live screen. Pick a platform, paste a handle, and
// the system reads their recent public posts and gives a founder-trail
// reading through the same lens the study used. HN / Reddit / Bluesky are
// fetched live (free public APIs); X and everything else fall back to
// pasting posts. Fail-closed: budget/key problems surface as a friendly
// "scorer is asleep" message from the API.

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
  n_posts: number;
  source: string;
}

const FAMILIES: { key: keyof ApiResult; label: string; blurb: string }[] = [
  { key: "doing", label: "Doing", blurb: "building & shipping in public" },
  { key: "telling", label: "Telling", blurb: "saying the goal out loud" },
  { key: "connecting", label: "Connecting", blurb: "pulling the right people in" },
];

export function ScoreAnyone() {
  const [platform, setPlatform] = useState<Platform>("hn");
  const [handle, setHandle] = useState("");
  const [pasted, setPasted] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ApiResult | null>(null);

  const live = PLATFORMS.find((p) => p.id === platform)?.live ?? false;
  const ready = live ? handle.trim().length > 1 : pasted.trim().length > 40;

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
    <section className="lp-section dm-score-anyone" aria-label="Score anyone">
      <p className="lp-kicker mono">📡 Score anyone · live</p>
      <h2 className="lp-h2">Point the system at a real person.</h2>
      <p className="lp-body">
        Pick where they post and drop in their handle — the system reads their
        recent public posts through the same lens the study used and gives its
        honest read. Nothing is saved.
      </p>

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
              platform === "bluesky" ? "handle (e.g. pfrazee.com)" : "handle (no @ needed)"
            }
            value={handle}
            onChange={(e) => setHandle(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && ready && !busy && submit()}
            aria-label="handle"
          />
          <button className="lp-tm-play dm-go mono" disabled={!ready || busy} onClick={submit}>
            {busy ? "reading…" : "score them ▶"}
          </button>
        </div>
      ) : (
        <>
          <p className="dm-sa-note">
            {platform === "x"
              ? "X doesn't let websites read profiles for free — so paste a few of their (or your) recent posts instead. The reading is exactly the same."
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
            <button className="lp-tm-play dm-go mono" disabled={!ready || busy} onClick={submit}>
              {busy ? "reading…" : "score the posts ▶"}
            </button>
          </div>
        </>
      )}

      {error && <p className="dm-sa-error">{error}</p>}

      {result && (
        <div className="dm-sa-card">
          <p className="dm-sa-source mono">
            read {result.n_posts} recent posts · {result.source}
          </p>
          <div className="dm-sa-headline">
            <span className="dm-sa-num mono">{result.score}</span>
            <span className="dm-sa-outof mono">/10</span>
            <span className="dm-sa-what">founder-trail strength</span>
          </div>
          <div className="dm-sa-families">
            {FAMILIES.map((f) => {
              const v = result[f.key] as number;
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
          {result.read && <p className="dm-sa-read">&ldquo;{result.read}&rdquo;</p>}
          <p className="lp-tm-honesty">
            Honest footnote: a high reading means &ldquo;worth a look
            early&rdquo;, not &ldquo;future winner&rdquo; — and the lens was
            calibrated on indie builders, so it will misread celebrities and
            companies. Nothing you score here is stored.
          </p>
        </div>
      )}
    </section>
  );
}
