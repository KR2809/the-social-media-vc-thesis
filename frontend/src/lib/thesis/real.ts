// Real-data DataSource — currently a stub that overlays the bits of real
// state that exist on top of the synthetic fallback. As Phase 3 lands
// scoring outputs, fields are swapped in one at a time.
//
// What exists today (May 2026):
//   * data/processed/signal_events.parquet — handle list + first-signal
//     dates, gitignored. Cohort n=20 (different from the demo's n=30).
//   * No T1/T2 scores. No baselines. No KG features. No bootstrap CIs.
//   * No outcome labels beyond what the cohort_verified.md provides.
//
// Strategy: this module currently re-exports the synthetic source unchanged
// with `source: "hybrid"` once the cohort loader lands. Until then, return
// the synthetic source so the app renders. Each real-data field gets its
// own follow-up task in FRONTEND_PLAN.md.

import { syntheticSource } from "./synthetic";
import type { DataSource } from "./types";

export async function loadRealSource(): Promise<DataSource> {
  // TODO(phase-3): replace fields one-by-one as real outputs land.
  //   1. cohort/founders → read data/processed/cohort.json
  //   2. tier1/tier2/curve → read data/processed/scores.parquet
  //   3. baselines → call scoring/baselines.py via a Next.js route handler
  //   4. egoFor/signalsFor → read data/processed/kg.json
  return syntheticSource;
}
