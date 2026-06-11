"use client";

import { useCallback, useEffect, useState } from "react";
import { VcGame } from "./VcGame";
import { StrategyRace } from "./StrategyRace";
import { FundSim } from "./FundSim";
import { InsideScore } from "./InsideScore";
import { ScoreAnyone } from "./ScoreAnyone";

// /demo — hub + screen switcher (hash-deep-linkable: /demo#game etc).
// One screen at a time, hub cards in the editorial style, every screen
// opens with one plain sentence of purpose. Real data only.

type Screen = "hub" | "game" | "race" | "fund" | "inside" | "score";

const SCREENS: {
  id: Exclude<Screen, "hub">;
  emoji: string;
  title: string;
  blurb: string;
  tag?: string;
}[] = [
  {
    id: "game",
    emoji: "🎲",
    title: "You be the VC",
    blurb:
      "Pick a moment in history, back five builders, then fast-forward and see how you did — against the machine, and against luck.",
    tag: "the game",
  },
  {
    id: "inside",
    emoji: "🔍",
    title: "Inside the score",
    blurb:
      "Read the actual posts the system read, and watch a founder's score climb as the evidence stacks up.",
  },
  {
    id: "race",
    emoji: "🏁",
    title: "The strategy race",
    blurb:
      "Five picking strategies compete across seven years — including the embarrassingly simple one that keeps up.",
  },
  {
    id: "fund",
    emoji: "💼",
    title: "The fund simulator",
    blurb:
      "If you backed the system's top picks, how many would launch? Drag the fund size and watch the odds move.",
  },
  {
    id: "score",
    emoji: "📡",
    title: "Score anyone",
    blurb:
      "Point it at a real public profile — or paste a few posts — and get a founder-trail reading, live.",
    tag: "live",
  },
];

function screenFromHash(): Screen {
  if (typeof window === "undefined") return "hub";
  const h = window.location.hash.replace("#", "");
  return (SCREENS.some((s) => s.id === h) ? h : "hub") as Screen;
}

export function DemoPage() {
  const [screen, setScreen] = useState<Screen>("hub");

  useEffect(() => {
    setScreen(screenFromHash());
    const onHash = () => setScreen(screenFromHash());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  const go = useCallback((s: Screen) => {
    window.location.hash = s === "hub" ? "" : s;
    setScreen(s);
    window.scrollTo({ top: 0 });
  }, []);

  return (
    <main className="lp dm">
      <header className="dm-top">
        <a className="dm-back mono" href="/">
          ← the story
        </a>
        {screen !== "hub" && (
          <button className="dm-back mono dm-back-btn" onClick={() => go("hub")}>
            all experiments
          </button>
        )}
      </header>

      {screen === "hub" && (
        <section className="lp-section dm-hub">
          <p className="lp-kicker mono">The full demo</p>
          <h1 className="dm-h1">Play with the real study.</h1>
          <p className="lp-body">
            Everything here runs on the study&apos;s real data — real founders,
            real dates, real outcomes. Nothing is simulated for show (the one
            projection is labelled as one).
          </p>
          <div className="dm-cards">
            {SCREENS.map((s) => (
              <button key={s.id} className="dm-card" onClick={() => go(s.id)}>
                <span className="dm-card-emoji" aria-hidden>
                  {s.emoji}
                </span>
                <span className="dm-card-title">
                  {s.title}
                  {s.tag && <span className="dm-card-tag mono">{s.tag}</span>}
                </span>
                <span className="dm-card-blurb">{s.blurb}</span>
                <span className="dm-card-go mono" aria-hidden>
                  open →
                </span>
              </button>
            ))}
          </div>
        </section>
      )}

      {screen === "game" && <VcGame />}
      {screen === "race" && <StrategyRace />}
      {screen === "fund" && <FundSim />}
      {screen === "inside" && <InsideScore />}
      {screen === "score" && <ScoreAnyone />}
    </main>
  );
}
