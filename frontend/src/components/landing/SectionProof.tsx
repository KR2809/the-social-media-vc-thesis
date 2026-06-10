"use client";

import { HEADLINE, modelHitsPer10, randomHitsPer10 } from "@/lib/thesis/headline";
import { useReveal } from "./useInView";
import { TechnicalReader } from "./TechnicalReader";

// §5 THE PROOF — plain words only (spec §3, HARD RULE).
// Beat 1: it works (8-of-10 vs 3-of-10 + "6x better than guessing").
// Beat 2: what DIDN'T work, stated straight — honesty as rigour.
// The precise figures live ONLY in the TechnicalReader block below.

function PeopleRow({ wins, kind }: { wins: number; kind: "ours" | "rnd" }) {
  return (
    <div className="lp-pf-people" aria-hidden>
      {Array.from({ length: 10 }, (_, i) => (
        <span key={i} className={"lp-pf-p" + (i < wins ? ` ${kind}` : "")} />
      ))}
    </div>
  );
}

export function SectionProof() {
  const [ref, revealCls] = useReveal<HTMLElement>();
  return (
    <section
      id="proof"
      ref={ref}
      className={"lp-section lp-proof " + revealCls}
      aria-label="The proof"
    >
      <p className="lp-kicker mono">Does it actually work?</p>
      <h2 className="lp-h2">
        Of its top 10 picks, about {modelHitsPer10} really became founders.
      </h2>
      <p className="lp-body">
        Pick 10 people at random from the same circles and only about{" "}
        {randomHitsPer10} would. Across the whole test the system is{" "}
        <strong>about {Math.round(HEADLINE.liftAt5)}× better than guessing</strong>{" "}
        — checked against the same people, the same dates, and only the
        information available at the time.
      </p>

      <div className="lp-pf-compare">
        <div className="lp-pf-col">
          <span className="lp-pf-who mono">10 picked at random</span>
          <PeopleRow wins={randomHitsPer10} kind="rnd" />
          <span className="lp-pf-verdict rnd">~{randomHitsPer10} founders</span>
        </div>
        <span className="lp-pf-vs mono" aria-hidden>vs</span>
        <div className="lp-pf-col">
          <span className="lp-pf-who mono">the system&apos;s top 10</span>
          <PeopleRow wins={modelHitsPer10} kind="ours" />
          <span className="lp-pf-verdict ours">~{modelHitsPer10} founders</span>
        </div>
      </div>

      <div className="lp-pf-honest">
        <h3 className="lp-pf-honest-title">
          And two things that didn&apos;t work — said plainly.
        </h3>
        <p className="lp-pf-honest-sub">
          A test you can&apos;t fail isn&apos;t worth running. Two of the
          project&apos;s engineering bets did not pay off, and both are
          reported straight:
        </p>
        <ul className="lp-pf-honest-list">
          <li>
            A fancier &quot;who-knows-whom&quot; network version added{" "}
            <strong>nothing</strong> — because free public data doesn&apos;t
            reveal who actually follows or replies to whom. It was dropped.
          </li>
          <li>
            For pure ranking, a much simpler rule — &quot;who posts the
            most&quot; — did <strong>just as well</strong> as the full scoring
            system. The system&apos;s real edge is the <em>early flag</em>, not
            the top-of-list ordering.
          </li>
        </ul>
      </div>

      <TechnicalReader />
    </section>
  );
}
