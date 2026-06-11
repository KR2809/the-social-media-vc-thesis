"use client";

// §6 FOOTER — academic framing worn openly (spec §3, locked decision 2:
// authorship lives here, not in the hero).
//
// Links degrade gracefully: GitHub always renders (real, public); the thesis
// PDF link renders ONLY when a URL is configured — never a broken link.

const GITHUB_URL = "https://github.com/KR2809/the-social-media-vc-thesis";
// Set when the paper is hosted somewhere public; null hides the link.
const THESIS_PAPER_URL: string | null = null;

export function SectionFooter() {
  return (
    <footer id="footer" className="lp-section lp-footer" aria-label="About this project">
      <div className="lp-footer-rule" />
      <p className="lp-kicker mono">About this project</p>
      <h2 className="lp-footer-title">
        This is the working prototype from my EDHEC International BBA thesis,{" "}
        <em>From Social Signals to Pre-Seed Allocation</em>.
      </h2>
      <p className="lp-body">
        &quot;Became a founder&quot; means something concrete here: within two
        years, the person reached a real audience, real revenue, or real
        funding with something they built themselves. The system&apos;s
        predictions for the <em>future</em>{" "}were locked and time-stamped on 31
        May 2026, before the outcomes are known — so it can be checked, not
        just believed. Everything — code, data pipeline, and every number on
        this page — is open and reproducible.
      </p>
      <div className="lp-footer-links">
        <a
          className="lp-footer-link"
          href={GITHUB_URL}
          target="_blank"
          rel="noopener noreferrer"
        >
          See the code &amp; method on GitHub →
        </a>
        <a className="lp-footer-link" href="/demo">
          Run a live read on anyone →
        </a>
        {THESIS_PAPER_URL && (
          <a
            className="lp-footer-link"
            href={THESIS_PAPER_URL}
            target="_blank"
            rel="noopener noreferrer"
          >
            Read the full thesis (PDF) →
          </a>
        )}
      </div>
      <p className="lp-footer-byline">
        Kristian Ratkov · EDHEC International BBA, Class of 2026 · supervised
        by Prof. George Tovstiga
      </p>
    </footer>
  );
}
