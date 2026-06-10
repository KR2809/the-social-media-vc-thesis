"use client";

import { HEADLINE } from "@/lib/thesis/headline";

// §1 HOOK — clarity-first hero (spec §3, locked decision 3).
// Calm, legible, zero jargon. The one sentence, then one plain proof line.
// Figures come from lib/thesis/headline.ts (the page's single number source,
// traced to the run CSVs) and are rendered as WORDS here — HARD RULE: no
// stats terms in the main flow. No fetch: this section paints instantly.

function leadPhrase(median: number): string {
  if (median >= 10 && median <= 14) return "about a year before they launch";
  return `about ${median} months before they launch`;
}

export function SectionHook() {
  const pct = Math.round(HEADLINE.rocAuc * 100);
  return (
    <section id="hook" className="lp-section lp-hook" aria-label="Introduction">
      <p className="lp-eyebrow mono">From social signals to pre-seed allocation</p>
      <h1 className="lp-h1">
        An AI that spots future startup founders from their public posts —{" "}
        <em>before they launch</em>.
      </h1>
      <p className="lp-hook-sub">
        Shown a real founder and a random person, it picks the founder{" "}
        <strong>{pct} times out of 100</strong> — and it flags them{" "}
        <strong>{leadPhrase(HEADLINE.leadMedianMonths)}</strong>.
      </p>
      <p className="lp-hook-trust">
        Built only from public posts. No private data, no paid access.
      </p>
      <a className="lp-scroll-cue" href="#problem" aria-label="Scroll to the story">
        <span className="lp-scroll-cue-text">scroll</span>
        <span className="lp-scroll-cue-arrow" aria-hidden>↓</span>
      </a>
    </section>
  );
}
