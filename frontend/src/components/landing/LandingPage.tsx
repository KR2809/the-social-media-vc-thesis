"use client";

import { useEffect, useState } from "react";
import { loadTimeline, type TimelineData } from "@/lib/thesis/timeline";

// Composition root for the single-scroll landing page (spec:
// docs/superpowers/specs/2026-06-09-landing-page-design.md).
//
// Loads the static real-data bundle ONCE, then renders the six story
// sections in order. Until each section component lands (plan T5-T10),
// a labelled stub keeps the scroll skeleton honest and testable.

function SectionStub({ id, label }: { id: string; label: string }) {
  return (
    <section id={id} className="lp-section lp-stub" aria-label={label}>
      <span className="lp-stub-label mono">{label}</span>
    </section>
  );
}

export function LandingPage() {
  const [data, setData] = useState<TimelineData | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    loadTimeline()
      .then((d) => alive && setData(d))
      .catch((e) => alive && setError(String(e)));
    return () => {
      alive = false;
    };
  }, []);

  if (error) {
    return (
      <main className="lp lp-loading">
        <p className="lp-error">
          The data bundle failed to load. Please refresh — nothing is shown
          from fallback or invented data.
        </p>
      </main>
    );
  }

  if (!data) {
    return (
      <main className="lp lp-loading" aria-busy="true">
        <div className="lp-shimmer" />
      </main>
    );
  }

  return (
    <main className="lp">
      <SectionStub id="hook" label="§1 HOOK" />
      <SectionStub id="problem" label="§2 PROBLEM" />
      <SectionStub id="idea" label="§3 THE IDEA" />
      <SectionStub id="time-machine" label="§4 TIME MACHINE" />
      <SectionStub id="proof" label="§5 THE PROOF" />
      <SectionStub id="footer" label="§6 FOOTER" />
    </main>
  );
}
