"use client";

import { HEADLINE } from "@/lib/thesis/headline";

// The ONE place on the page where precise statistical figures appear
// (spec: "For the technical reader"). Collapsed by default; the
// parent-readable story above never depends on opening it.

export function TechnicalReader() {
  const h = HEADLINE;
  return (
    <details className="lp-tech">
      <summary className="lp-tech-summary">
        <span className="mono">For the technical reader — the precise numbers</span>
        <span className="lp-tech-hint mono">click to expand</span>
      </summary>
      <div className="lp-tech-body mono">
        <table className="lp-tech-table">
          <tbody>
            <tr>
              <td>Evaluation set</td>
              <td>
                n = {h.n} ({h.nPos} positives, {h.nNeg} negatives), leave-one-out CV
              </td>
            </tr>
            <tr>
              <td>ROC-AUC (flat features)</td>
              <td>
                {h.rocAuc.toFixed(3)} &nbsp;95% CI [{h.rocAucCiLo.toFixed(3)},{" "}
                {h.rocAucCiHi.toFixed(3)}]
              </td>
            </tr>
            <tr>
              <td>PR-AUC</td>
              <td>{h.prAuc.toFixed(3)}</td>
            </tr>
            <tr>
              <td>Lift@5</td>
              <td>{h.liftAt5.toFixed(1)}× over base rate ({h.baseRatePct}%)</td>
            </tr>
            <tr>
              <td>Precision@10 (backtest)</td>
              <td>
                {h.precAt10Model.toFixed(2)} best strategy vs{" "}
                {h.precAt10Random.toFixed(2)} random, 102 monthly dates
              </td>
            </tr>
            <tr>
              <td>Pre-emergence lead</td>
              <td>
                median +{h.leadMedianMonths} mo (max +{h.leadMaxMonths}) across{" "}
                {h.leadFounders} founders with sufficient history
              </td>
            </tr>
            <tr>
              <td>Honest nulls</td>
              <td>
                KG features ΔROC-AUC ≈ −0.002; two-tier composite precision@5{" "}
                {h.frameworkPrecAt5.toFixed(2)} vs volume heuristic{" "}
                {h.volumePrecAt5.toFixed(2)}
              </td>
            </tr>
          </tbody>
        </table>
        <p className="lp-tech-note">
          Full method, equations, robustness sweeps and per-figure provenance:
          see the thesis and the repository (every number traces to a CSV).
        </p>
      </div>
    </details>
  );
}
