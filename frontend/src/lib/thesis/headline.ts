// Canonical headline results from the expanded-backtest run (2026-06-04, n=139).
//
// Single source of truth for the hero / landing numbers. Each value traces to a
// file in data/processed/ (see RESULTS_FOR_THESIS.md). When the static
// `thesis_data.json` bundle lands (FRONTEND_REDESIGN §6), these can be read from
// it instead — keep this module as the typed contract.
//
// Honesty note: we headline ROC-AUC and precision@10 (robust, large margin over
// random). We do NOT headline precision@3 — at the very top of the list the lift
// over random is small. See the thesis findings write-up.

export interface Headline {
  n: number;
  nPos: number;
  nNeg: number;
  baseRatePct: number; // positives / labeled pool, %
  rocAuc: number;
  rocAucCiLo: number;
  rocAucCiHi: number;
  // precision@10: of the 10 highest-ranked, how many emerged.
  precAt10Model: number; // best in-framework strategy at k=10
  precAt10Random: number;
  precAt10K: number; // = 10, the K the headline uses
  leadFounders: number; // founders flagged before emergence
  leadMedianMonths: number;
  leadMaxMonths: number;
  // For the technical-reader block + the honest nulls (thesis §VI.3/§VI.6).
  prAuc: number;
  liftAt5: number;
  frameworkPrecAt5: number; // the two-tier composite (honest null)
  volumePrecAt5: number; // the simple volume heuristic that ties/beats it
}

// Source: data/processed/eval_metrics.csv (baseline row) +
// outcome_labels.csv (base rate) + backtest_results.csv (precision@10) +
// first_pickup_dates.csv (lead time). Run 2026-06-04.
export const HEADLINE: Headline = {
  n: 139,
  nPos: 21,
  nNeg: 118,
  baseRatePct: 11.7,
  rocAuc: 0.967,
  rocAucCiLo: 0.913,
  rocAucCiHi: 0.996,
  precAt10Model: 0.78,
  precAt10Random: 0.28,
  precAt10K: 10,
  leadFounders: 8,
  leadMedianMonths: 12,
  leadMaxMonths: 44,
  prAuc: 0.905,
  liftAt5: 6.6,
  frameworkPrecAt5: 0.5,
  volumePrecAt5: 0.73,
};

// "~8" and "~3" out of 10 — rounded for the intuitive comparison.
export const modelHitsPer10 = Math.round(HEADLINE.precAt10Model * HEADLINE.precAt10K);
export const randomHitsPer10 = Math.round(HEADLINE.precAt10Random * HEADLINE.precAt10K);
