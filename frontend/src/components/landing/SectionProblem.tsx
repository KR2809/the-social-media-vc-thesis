"use client";

import { useMemo } from "react";
import { HEADLINE } from "@/lib/thesis/headline";
import { useReveal } from "./useInView";

// §2 PROBLEM — the haystack made physical (spec §3).
// 100 dots; the highlighted count comes from the REAL base rate in the
// bundle (≈12 for 11.7%). Dots stagger in on scroll. Plain words only.

// Deterministic spread of `count` highlighted indices across a 100-dot grid
// (stable between renders; no Math.random so SSR/CSR agree).
function spreadIndices(count: number): Set<number> {
  const out = new Set<number>();
  const step = 100 / count;
  for (let i = 0; i < count; i++) {
    // offset pattern keeps highlights visually scattered, not a stripe
    out.add(Math.min(99, Math.round(i * step + (i % 3) * 3 + 2)));
  }
  return out;
}

export function SectionProblem() {
  const [ref, revealCls] = useReveal<HTMLElement>();
  const hits = useMemo(
    () => spreadIndices(Math.max(1, Math.round(HEADLINE.baseRatePct))),
    [],
  );

  const oneInN = Math.round(100 / HEADLINE.baseRatePct);

  return (
    <section
      id="problem"
      ref={ref}
      className={"lp-section lp-problem " + revealCls}
      aria-label="The problem"
    >
      <p className="lp-kicker mono">The problem</p>
      <h2 className="lp-h2">
        Finding the next founder is a needle-in-a-haystack problem.
      </h2>
      <p className="lp-body">
        Only about <strong>1 in {oneInN}</strong>{" "}
        people active in startup
        circles ever becomes a real founder. Scrolling social media and hoping
        to spot them by hand doesn&apos;t scale. A few big investment firms
        attack this with data — but only <em>after</em>{" "}companies exist. Nobody
        had tried it earlier, at the moment it matters most:{" "}
        <strong>before the launch</strong>.
      </p>

      <div className="lp-haystack" role="img"
        aria-label={`100 people; about ${Math.round(HEADLINE.baseRatePct)} highlighted as the ones who became founders`}>
        {Array.from({ length: 100 }, (_, i) => (
          <span
            key={i}
            className={"lp-dot" + (hits.has(i) ? " lp-dot-hit" : "")}
            style={{ transitionDelay: `${(i % 25) * 28}ms` }}
          />
        ))}
      </div>
      <p className="lp-haycap">
        100 people posting in startup circles — the{" "}
        <span className="lp-haycap-hit">highlighted ones</span> are roughly how
        many ever become founders.
      </p>
    </section>
  );
}
