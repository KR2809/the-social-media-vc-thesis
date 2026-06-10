"use client";

import { SectionHook } from "./SectionHook";
import { SectionProblem } from "./SectionProblem";
import { SectionIdea } from "./SectionIdea";
import { TimeMachine } from "./TimeMachine";

// Composition root for the single-scroll landing page (spec:
// docs/superpowers/specs/2026-06-09-landing-page-design.md).
//
// Architecture note: the page paints INSTANTLY — story sections take their
// numbers from lib/thesis/headline.ts (the page's single number source,
// traced to the run CSVs), so nothing gates on a network fetch. Only the
// Time Machine needs the 122-founder bundle; it fetches
// /frontend_timeline.json itself with a local loading state.

function SectionStub({ id, label }: { id: string; label: string }) {
  return (
    <section id={id} className="lp-section lp-stub" aria-label={label}>
      <span className="lp-stub-label mono">{label}</span>
    </section>
  );
}

export function LandingPage() {
  return (
    <main className="lp">
      <SectionHook />
      <SectionProblem />
      <SectionIdea />
      <TimeMachine />
      <SectionStub id="proof" label="§5 THE PROOF" />
      <SectionStub id="footer" label="§6 FOOTER" />
    </main>
  );
}
