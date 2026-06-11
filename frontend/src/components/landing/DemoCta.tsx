"use client";

// Bridge from the story to /demo — placed right after the Time Machine,
// while the reader's hands are still warm from the scrubber.

export function DemoCta() {
  return (
    <section className="lp-section lp-democta" aria-label="Try the live demo">
      <div className="lp-democta-card">
        <p className="lp-kicker mono">The live demo</p>
        <h2 className="lp-democta-title">Point it at a real person.</h2>
        <p className="lp-body">
          The same lens the study used, aimed at the present: give it a public
          handle on Hacker News, Reddit, or Bluesky and it reads their recent
          posts and writes its honest read. Nothing is stored.
        </p>
        <a className="lp-democta-btn mono" href="/demo">
          Run a live read →
        </a>
      </div>
    </section>
  );
}
