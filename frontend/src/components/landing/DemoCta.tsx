"use client";

// Bridge from the story to /demo — placed right after the Time Machine,
// while the reader's hands are still warm from the scrubber.

export function DemoCta() {
  return (
    <section className="lp-section lp-democta" aria-label="Try the full demo">
      <div className="lp-democta-card">
        <p className="lp-kicker mono">There&apos;s more to play with</p>
        <h2 className="lp-democta-title">
          Be the VC. Race the strategies. Score anyone.
        </h2>
        <p className="lp-body">
          The full demo lets you draft founders at any moment in history,
          watch five picking strategies race, and point the system at a real
          public profile — live.
        </p>
        <a className="lp-democta-btn mono" href="/demo">
          Try the full demo →
        </a>
      </div>
    </section>
  );
}
