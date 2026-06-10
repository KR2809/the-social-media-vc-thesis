// Smoke tests for the landing-page data layer (lib/thesis/timeline.ts).
//
// Run with:  npx --yes tsx scripts/smoke_landing.mts
//
// Mirrors the smoke_test_real.mts pattern (plain asserts, no Vitest dep).
// Tests run against a small inline fixture, NOT the real JSON, so they are
// deterministic and fast. The real file's shape is guarded separately by the
// headless visual smoke in plan Task 12.

import {
  parseTimeline,
  foundersActiveAt,
  foundersEmergedAt,
  leadMonths,
  hasSignals,
  type TimelineFounder,
} from "../src/lib/thesis/timeline";

let passed = 0;
let failed = 0;

function assert(cond: unknown, msg: string): void {
  if (cond) {
    console.log(`  ✓ ${msg}`);
    passed++;
  } else {
    console.log(`  ✗ ${msg}`);
    failed++;
  }
}

// ---------------------------------------------------------------------------
// Fixture — two positives (one early-pickup, one shallow-data post-hoc pickup)
// and one negative, exactly the shapes the export emits.
// ---------------------------------------------------------------------------

const fixture = {
  meta: {
    generated_at: "2026-06-09T00:00:00",
    git_commit: "abc123",
    grid_start: "2018-01-01",
    grid_end: "2026-06-01",
    tracked_threshold: 0.22,
    n_founders: 3,
    n_dates: 4,
    headline: {
      roc_auc: 0.967,
      roc_auc_ci_lo: 0.913,
      roc_auc_ci_hi: 0.996,
      pr_auc: 0.905,
      lift_at_5: 6.6,
      n: 139,
      n_pos: 21,
      base_rate_pct: 11.7,
      prec_at_10_model: 0.78,
      prec_at_10_random: 0.28,
      lead_median_months: 12,
      lead_max_months: 44,
      lead_founders: 8,
      framework_prec_at_5: 0.5,
      volume_prec_at_5: 0.73,
    },
  },
  dates: ["2019-05-01", "2020-01-01", "2023-01-01", "2026-06-01"],
  founders: [
    {
      person_id: "bentossell",
      founder_name: "Ben Tossell",
      venture: "Ben's Bites",
      handle: "bentossell",
      first_pickup_date: "2019-05-01",
      emergence_date: "2023-01-01",
      lead_time_months: 44,
      peak_score: 0.41,
      is_positive: true,
      trajectory: [
        { date: "2019-05-01", score: 0.25, verdict: "tracked", emerged_by_then: false },
        { date: "2023-01-01", score: 0.4, verdict: "tracked", emerged_by_then: true },
      ],
      top_signals_at_pickup: [
        {
          signal_id: "hn_1",
          platform: "hackernews",
          timestamp: "2019-04-15",
          strength: 0.9,
          text: "Show HN: a no-code thing",
        },
      ],
    },
    {
      person_id: "levelsio",
      founder_name: "Pieter Levels",
      venture: "Nomad List",
      handle: "levelsio",
      // Shallow data: pickup AFTER emergence (negative lead) — must be honest.
      first_pickup_date: "2020-01-01",
      emergence_date: "2015-02-01",
      lead_time_months: -59,
      peak_score: 0.38,
      is_positive: true,
      trajectory: [],
      top_signals_at_pickup: [],
    },
    {
      person_id: "NEG_x_01",
      founder_name: "NEG_x_01",
      venture: "",
      handle: "NEG_x_01",
      first_pickup_date: null,
      emergence_date: null,
      lead_time_months: null,
      peak_score: 0.1,
      is_positive: false,
      trajectory: [],
      top_signals_at_pickup: [],
    },
  ],
};

// ---------------------------------------------------------------------------
console.log("\nparseTimeline:");
const data = parseTimeline(fixture);
assert(data.founders.length === 3, "parses 3 founders");
assert(data.dates.length === 4, "parses 4 dates");
assert(data.meta.headline.roc_auc === 0.967, "headline numbers preserved");
assert(
  data.founders[0].founder_name === "Ben Tossell",
  "real display name preserved",
);

console.log("\nfoundersActiveAt (picked up by date):");
const at2019 = foundersActiveAt(data, "2019-06-01");
assert(at2019.length === 1 && at2019[0].person_id === "bentossell",
  "only Ben active mid-2019 (pickup 2019-05)");
const at2021 = foundersActiveAt(data, "2021-01-01");
assert(at2021.length === 2, "Ben + Levels active by 2021 (Levels pickup 2020-01)");
assert(foundersActiveAt(data, "2018-01-01").length === 0,
  "nobody active before any pickup");

console.log("\nfoundersEmergedAt:");
const em2016 = foundersEmergedAt(data, "2016-01-01");
assert(em2016.length === 1 && em2016[0].person_id === "levelsio",
  "Levels already emerged by 2016 (before his pickup — honest negative lead)");
assert(foundersEmergedAt(data, "2024-01-01").length === 2,
  "both positives emerged by 2024");

console.log("\nleadMonths:");
assert(leadMonths(data.founders[0]) === 44, "Ben lead +44");
assert(leadMonths(data.founders[1]) === -59, "Levels lead -59 (post-hoc, honest)");
assert(leadMonths(data.founders[2]) === null, "negative has no lead");

console.log("\nhasSignals (no-fabrication guard):");
assert(hasSignals(data.founders[0]) === true, "Ben has real signals");
assert(hasSignals(data.founders[1]) === false,
  "Levels has none -> UI must say 'limited public data', never invent");

// ---------------------------------------------------------------------------
console.log(`\n${passed} passed, ${failed} failed`);
if (failed > 0) process.exit(1);
