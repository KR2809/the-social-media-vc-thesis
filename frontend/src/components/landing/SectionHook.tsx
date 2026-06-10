"use client";

import type { HeadlineNumbers } from "@/lib/thesis/timeline";

// §1 HOOK — clarity-first hero (spec §3, locked decision 3).
// Calm, legible, zero jargon. The one sentence, then one plain proof line.
// All figures arrive as numbers from the data bundle and are rendered as
// words here (HARD RULE: no stats terms in the main flow).

function pct100(rocAuc: number | null): string {
  // 0.967 -> "97" (times out of 100). Plain-words form of discrimination.
  if (rocAuc == null) return "—";
  return String(Math.round(rocAuc * 100));
}

function leadPhrase(median: number | null): string {
  if (median == null) return "months before they launch";
  if (median >= 10 && median <= 14) return "about a year before they launch";
  return `about ${median} months before they launch`;
}

export function SectionHook({ headline }: { headline: HeadlineNumbers }) {
  return (
    <section id="hook" className="lp-section lp-hook" aria-label="Introduction">
      <p className="lp-eyebrow mono">From social signals to pre-seed allocation</p>
      <h1 className="lp-h1">
        An AI that spots future startup founders from their public posts —{" "}
        <em>before they launch</em>.
      </h1>
      <p className="lp-hook-sub">
        Shown a real founder and a random person, it picks the founder{" "}
        <strong>{pct100(headline.roc_auc)} times out of 100</strong> — and it
        flags them <strong>{leadPhrase(headline.lead_median_months)}</strong>.
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
