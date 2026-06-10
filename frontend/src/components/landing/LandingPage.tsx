"use client";

import { SectionHook } from "./SectionHook";
import { SectionProblem } from "./SectionProblem";
import { SectionIdea } from "./SectionIdea";
import { TimeMachine } from "./TimeMachine";
import { SectionProof } from "./SectionProof";
import { SectionFooter } from "./SectionFooter";

// Composition root for the single-scroll landing page (spec:
// docs/superpowers/specs/2026-06-09-landing-page-design.md).
//
// Architecture note: the page paints INSTANTLY — story sections take their
// numbers from lib/thesis/headline.ts (the page's single number source,
// traced to the run CSVs), so nothing gates on a network fetch. Only the
// Time Machine needs the 122-founder bundle; it fetches
// /frontend_timeline.json itself with a local loading state.

export function LandingPage() {
  return (
    <main className="lp">
      <SectionHook />
      <SectionProblem />
      <SectionIdea />
      <TimeMachine />
      <SectionProof />
      <SectionFooter />
    </main>
  );
}
