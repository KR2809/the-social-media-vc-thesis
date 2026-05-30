"use client";

import { useEffect, useState } from "react";
import { fetchYCOverlap, type YCOverlapResult } from "@/lib/thesis/yc";
import { InfoTip } from "./InfoTip";
import { fmtPct } from "./primitives";

/**
 * Real YC cross-reference panel (replaces the old synthetic donut). Fetches
 * GET /api/yc-overlap, lookahead-gated by the slider date. The overlap is
 * intentionally small — the cohort is bootstrapped/indie, largely orthogonal
 * to YC — which is the honest, defensible finding. Where overlap exists
 * (Cluely X25) it's external validation by an independent gatekeeper.
 */
export function YCOverlapPanel({ t }: { t: number }) {
  const [yc, setYc] = useState<YCOverlapResult | null>(null);
  useEffect(() => {
    let alive = true;
    fetchYCOverlap(t).then(r => {
      if (alive) setYc(r);
    });
    return () => {
      alive = false;
    };
  }, [t]);

  if (!yc || yc.source !== "backend") return null;

  const matched = yc.records.filter(r => r.in_yc_as_of);

  return (
    <div className="yc-overlap">
      <div className="yc-head">
        <span className="kicker">
          YC cross-reference
          <InfoTip width={360}>
            How many cohort founders also went through Y Combinator, per YC&apos;s public company
            directory. The cohort is bootstrapped/indie creator-economy founders — largely
            orthogonal to YC&apos;s accelerator model — so a <strong>small overlap is the expected,
            honest result</strong>. Where it exists, it&apos;s independent validation. Lookahead-safe:
            a YC batch only counts once publicly announced.
          </InfoTip>
        </span>
        <span className="muted">— exploratory; hand-verified against public sources</span>
      </div>

      <div className="yc-stat-row">
        <div className="yc-bignum">
          <span className="yc-frac mono">
            {yc.nInYc}
            <span className="yc-frac-denom">/ {yc.nCohort}</span>
          </span>
          <span className="yc-frac-label">cohort founders are YC-backed (as of slider date)</span>
        </div>
        <div className="yc-names">
          <span className="kicker muted">matches at this date</span>
          <div className="yc-name-list">
            {matched.length === 0 && (
              <span className="muted">— none yet (no cohort venture had a public YC batch by this date)</span>
            )}
            {matched.map(r => (
              <span key={r.person_id} className="pick-tag hit" title={r.evidence}>
                ● {r.founder_name} · {r.yc_batch}
              </span>
            ))}
          </div>
        </div>
      </div>

      <p className="yc-takeaway muted">
        {yc.nInYc === 0 ? (
          <>
            At this date, <strong>0%</strong> overlap — the framework surfaces a population YC&apos;s
            pipeline hadn&apos;t reached. That&apos;s the point: pre-seed creator-economy founders are
            mostly invisible to accelerator funnels.
          </>
        ) : (
          <>
            <strong>{fmtPct(yc.overlapPct, 0)}</strong> of the cohort is YC-backed. The rest are
            bootstrapped — the framework&apos;s population is largely orthogonal to YC&apos;s, with the
            overlap acting as independent validation where it occurs.
          </>
        )}
      </p>
    </div>
  );
}
