"use client";

import { useCallback, useEffect, useState } from "react";

/**
 * Onboarding / landing guide — a 5-step welcome modal shown on first
 * visit (localStorage-gated). Split layout: illustration left, copy
 * right; dot progress; Skip / Back / Next controls. Re-openable via the
 * "?" help control in the TopBar.
 *
 * Design: ported from the Claude Design "Thesis Demo" landing guide
 * (the share-link version layered on top of the local design-source
 * bundle). Dark + light themes via the same CSS tokens as the rest of
 * the demo.
 */

const STORAGE_KEY = "thesis-onboarding-seen-v1";

export interface GuideStep {
  eyebrow: string; // e.g. "WELCOME"
  title: string;
  body: React.ReactNode;
  illo: React.ReactNode; // left-pane illustration
}

interface Props {
  open: boolean;
  onClose: () => void;
}

// ---------------------------------------------------------------------------
// Illustrations (inline SVG so they theme via currentColor + tokens)
// ---------------------------------------------------------------------------

function IlloWelcome() {
  return (
    <svg viewBox="0 0 320 220" className="og-illo-svg" role="img" aria-label="Signals feeding a pre-seed portfolio">
      {/* signal rows */}
      {[0, 1, 2, 3, 4].map(i => (
        <g key={i} transform={`translate(8, ${20 + i * 38})`}>
          <circle cx="14" cy="12" r="5" fill="var(--accent)" opacity={0.9} />
          <rect x="28" y="7" width={120 - i * 6} height="10" rx="5" fill="var(--ink-3)" opacity={0.55} />
        </g>
      ))}
      {/* arrow */}
      <path d="M168 110 L210 110" stroke="var(--accent)" strokeWidth="2.5" fill="none" markerEnd="url(#arrowhead)" />
      <defs>
        <marker id="arrowhead" markerWidth="8" markerHeight="8" refX="6" refY="4" orient="auto">
          <path d="M0,0 L8,4 L0,8 Z" fill="var(--accent)" />
        </marker>
      </defs>
      {/* portfolio card */}
      <g transform="translate(218, 64)">
        <rect x="0" y="0" width="92" height="92" rx="8" fill="none" stroke="var(--accent)" strokeWidth="1.5" />
        <text x="46" y="40" textAnchor="middle" className="og-illo-label" fill="var(--accent)">
          Pre-Seed
        </text>
        <text x="46" y="56" textAnchor="middle" className="og-illo-label-sm" fill="var(--ink-2)" fontStyle="italic">
          portfolio
        </text>
        {[0, 1, 2].map(i => (
          <rect key={i} x="20" y={66 + i * 8} width={52 - i * 12} height="3.5" rx="2" fill="var(--ink-3)" opacity={0.5} />
        ))}
      </g>
    </svg>
  );
}

// Generic placeholder illustration for steps whose final artwork is TBD.
function IlloPlaceholder({ label }: { label: string }) {
  return (
    <svg viewBox="0 0 320 220" className="og-illo-svg" role="img" aria-label={label}>
      <rect x="20" y="20" width="280" height="180" rx="10" fill="none" stroke="var(--hairline-2)" strokeWidth="1.5" strokeDasharray="5 5" />
      <text x="160" y="115" textAnchor="middle" className="og-illo-label-sm" fill="var(--ink-3)">
        {label}
      </text>
    </svg>
  );
}

// ---------------------------------------------------------------------------
// Steps. Step 1 is final (from the design). 2–5 are scaffolded with
// working copy; swap illustrations/copy as the remaining design steps land.
// ---------------------------------------------------------------------------

export const GUIDE_STEPS: GuideStep[] = [
  {
    eyebrow: "WELCOME",
    title: "A systematic framework for pre-seed venture capital",
    body: (
      <>
        <p>
          This demo operationalises Kristian Ratkov&apos;s MSc thesis on{" "}
          <strong>turning social-media activity into pre-seed investment decisions</strong>. The
          argument: founders broadcast measurable signals long before they incorporate — cadence,
          ambition, network density, distribution loops — and a disciplined framework can pick the
          eventual emergers out of the noise.
        </p>
        <p className="og-muted">
          It&apos;s a working artefact, not a fund. Use it to inspect the logic, replay any date in
          history, and stress-test the picks against naïve baselines.
        </p>
      </>
    ),
    illo: <IlloWelcome />,
  },
  {
    eyebrow: "PICK",
    title: "Replay any date — who would the framework have backed?",
    body: (
      <>
        <p>
          Drag the <strong>date slider</strong> to any point in history. The framework re-ranks the
          cohort using <strong>only</strong> signals observable on or before that date — no
          lookahead. The top-K founders become the portfolio.
        </p>
        <p className="og-muted">
          Every pick is auditable: each row links back to the source posts the model scored.
        </p>
      </>
    ),
    illo: <IlloPlaceholder label="View 1 · Replay" />,
  },
  {
    eyebrow: "SCORE",
    title: "How did the picks perform?",
    body: (
      <>
        <p>
          Fast-forward 24 months. <strong>Precision@K</strong> counts how many picks actually
          emerged as fundable founders, with a <strong>95% bootstrap CI</strong> for small-sample
          honesty.
        </p>
        <p className="og-muted">
          The framework is compared head-to-head against naïve baselines — random, signal-volume,
          recency — so any edge is measured, not asserted.
        </p>
      </>
    ),
    illo: <IlloPlaceholder label="View 2 · Outcome" />,
  },
  {
    eyebrow: "DRILL IN",
    title: "Why was each founder picked?",
    body: (
      <>
        <p>
          Open any founder to trace the evidence: their{" "}
          <strong>knowledge-graph neighbourhood</strong>, the five highest-weight signals at date T,
          and the outcome timeline from first signal to emergence.
        </p>
        <p className="og-muted">Every signal carries its taxonomy scores and links to the original post.</p>
      </>
    ),
    illo: <IlloPlaceholder label="View 3 · Founder card" />,
  },
  {
    eyebrow: "METHOD · INTEGRITY",
    title: "Built from free public signals, locked against hindsight",
    body: (
      <>
        <p>
          Every signal carries a <strong>collected-at</strong> and <strong>observed-at</strong>{" "}
          timestamp; predictions at date T use only signals observable by T. The prospective
          predictions are <strong>cryptographically locked</strong> (SHA-256 + git commit) so they
          can&apos;t be tuned after the fact.
        </p>
        <p className="og-muted">
          Data comes entirely from free public sources. The whole pipeline is open and reproducible.
        </p>
      </>
    ),
    illo: <IlloPlaceholder label="Lookahead-bias guard" />,
  },
];

// ---------------------------------------------------------------------------
// First-visit helper (used by App to decide initial open state)
// ---------------------------------------------------------------------------

export function shouldShowOnboarding(): boolean {
  if (typeof window === "undefined") return false;
  try {
    return localStorage.getItem(STORAGE_KEY) == null;
  } catch {
    return false;
  }
}

export function markOnboardingSeen(): void {
  try {
    localStorage.setItem(STORAGE_KEY, "1");
  } catch {
    /* ignore */
  }
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function OnboardingGuide({ open, onClose }: Props) {
  const [step, setStep] = useState(0);
  const steps = GUIDE_STEPS;
  const last = steps.length - 1;

  const close = useCallback(() => {
    markOnboardingSeen();
    onClose();
  }, [onClose]);

  // Reset to step 0 each time it (re)opens. The modal stays mounted
  // (renders null when closed), so we resync on the open transition.
  // setState-in-effect is the right tool here per the codebase convention.
  useEffect(() => {
    if (open) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setStep(0);
    }
  }, [open]);

  // Keyboard: Esc closes, ←/→ navigate. Capture-phase so it wins over the
  // app-level slider shortcuts while the modal is open.
  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") {
        e.stopPropagation();
        close();
      } else if (e.key === "ArrowRight") {
        e.stopPropagation();
        setStep(s => Math.min(last, s + 1));
      } else if (e.key === "ArrowLeft") {
        e.stopPropagation();
        setStep(s => Math.max(0, s - 1));
      }
    }
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [open, last, close]);

  if (!open) return null;
  const cur = steps[step];

  return (
    <div className="og-scrim" role="dialog" aria-modal="true" aria-label="Demo walkthrough">
      <div className="og-modal">
        <button className="og-close icon-btn" onClick={close} aria-label="Close walkthrough">
          ×
        </button>

        <div className="og-illo" aria-hidden="true">
          {cur.illo}
        </div>

        <div className="og-content">
          <div className="og-eyebrow kicker">
            STEP {step + 1} OF {steps.length} · {cur.eyebrow}
          </div>
          <h2 className="og-title">{cur.title}</h2>
          <div className="og-body">{cur.body}</div>
        </div>

        <div className="og-footer">
          <div className="og-dots" role="tablist" aria-label="Walkthrough progress">
            {steps.map((_, i) => (
              <button
                key={i}
                role="tab"
                aria-selected={i === step}
                aria-label={`Step ${i + 1}`}
                className={"og-dot" + (i === step ? " on" : i < step ? " done" : "")}
                onClick={() => setStep(i)}
              />
            ))}
          </div>
          <div className="og-actions">
            <button className="og-skip" onClick={close}>
              Skip
            </button>
            <button className="og-back" onClick={() => setStep(s => Math.max(0, s - 1))} disabled={step === 0}>
              ← Back
            </button>
            {step < last ? (
              <button className="og-next" onClick={() => setStep(s => Math.min(last, s + 1))}>
                Next →
              </button>
            ) : (
              <button className="og-next" onClick={close}>
                Start exploring →
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
