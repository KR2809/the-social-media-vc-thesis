// Real-data DataSource (Phase C.1 — cohort loader).
//
// Swaps the founder roster from a hardcoded list to the live cohort served
// by FastAPI (/api/cohort + /api/timeline-bounds). Everything else still
// delegates to the synthetic source — see TODO(phase-c.*) markers below.
//
// What's swapped in C.1:
//   * founders() → real cohort from /api/cohort
//   * today      → derived from /api/timeline-bounds.latest
//   * source     → "hybrid" (real founders, synthetic everything else)
//
// What's still synthetic (deliberately — out of C.1 scope):
//   * curve / tier1 / tier2          (C.3 scoring loader)
//   * baselineRandom / Volume / Recency (C.4 baseline loader)
//   * precisionAt / bootCI           (C.4 baseline loader)
//   * signalsFor                     (C.6 signals loader)
//   * egoFor                         (C.5 KG loader)
//   * paletteFor / taxonomy          (UI helpers, not swappable)
//   * Founder.emerge / venture /
//     ventureMetric / emphasis       (C.2 outcome loader)
//
// On fetch failure (FastAPI not running, network error, bad shape) this
// module logs a console.warn and returns the synthetic source — the demo
// stays viewable. Failures are NOT silently swallowed.

import { syntheticSource } from "./synthetic";
import type {
  BaselinePick,
  DataSource,
  Founder,
  Outcome,
  PrecisionResult,
  RankedPick,
} from "./types";
import { API_BASE_URL } from "./config";

interface CohortResponse {
  n: number;
  members: Array<{
    person_id: string;
    display_name: string;
    venture: string | null;
    niche: string;
    emergence_quarter: string | null;
    data_score: number;
  }>;
}

interface TimelineBoundsResponse {
  earliest: string | null; // ISO timestamp (UTC)
  latest: string | null;
  n_signals: number;
}

function isoToMonthsSince2014(iso: string): number {
  const d = new Date(iso);
  const y = d.getUTCFullYear();
  const m = d.getUTCMonth(); // 0-indexed
  return (y - 2014) * 12 + m;
}

function isoToMonthString(iso: string): string {
  // "YYYY-MM" — the format synthetic.months() parses.
  const d = new Date(iso);
  const y = d.getUTCFullYear();
  const m = String(d.getUTCMonth() + 1).padStart(2, "0");
  return `${y}-${m}`;
}

async function fetchJSON<T>(path: string): Promise<T> {
  const url = `${API_BASE_URL}${path}`;
  const res = await fetch(url);
  if (!res.ok) {
    throw new Error(`GET ${url} → ${res.status} ${res.statusText}`);
  }
  return (await res.json()) as T;
}

function mapCohortToFounders(
  cohort: CohortResponse,
  firstMonth: string | null,
): Founder[] {
  return cohort.members.map((m) => ({
    id: m.person_id,
    name: m.display_name,
    niche: m.niche,
    // First-signal date: C.1 uses the global timeline.earliest as a coarse
    // shared floor for all founders. Per-founder first dates require a
    // separate /api/founder/{id} call per member — deferred to C.6 when
    // signals are loaded anyway.
    first: firstMonth ?? "2014-01",
    // TODO(phase-c.2): swap from null once outcome loader lands.
    emerge: null,
    // TODO(phase-c.2): swap from null once outcome loader lands.
    venture: null,
    // TODO(phase-c.2): swap from null once outcome loader lands.
    ventureMetric: null,
    // TODO(phase-c.3): swap from [] once scoring picks an emphasis per founder.
    emphasis: [],
  }));
}

function buildHybridSource(
  founders: Founder[],
  today: number,
): DataSource {
  // Per-founder helpers delegate to synthetic — but list-iterating methods
  // (rankAt, baselines, precisionAt) re-implement with the real founder
  // roster, otherwise they'd silently rank the synthetic 30-row cohort.

  const foundersById = new Map(founders.map((f) => [f.id, f]));

  function outcomeAt(f: Founder, t: number): Outcome {
    const em = syntheticSource.months(f.emerge);
    const t24 = t + 24;
    if (em == null) return t24 <= today ? "not_yet" : "unknown";
    return em <= t24 ? "emerged" : t24 <= today ? "not_yet" : "unknown";
  }

  function rankAt(t: number, K: number): RankedPick[] {
    const rows: RankedPick[] = [];
    for (const f of founders) {
      const c = syntheticSource.curve(f, t);
      if (c == null) continue;
      rows.push({
        id: f.id,
        name: f.name,
        niche: f.niche,
        t1: syntheticSource.tier1(f, t),
        t2: syntheticSource.tier2(f, t),
        combined: c,
        emerge: f.emerge,
        first: f.first,
        outcome: outcomeAt(f, t),
      });
    }
    rows.sort((a, b) => b.combined - a.combined);
    return rows.slice(0, K);
  }

  function eligible(t: number): Founder[] {
    return founders.filter((f) => {
      const m = syntheticSource.months(f.first);
      return m != null && m <= t;
    });
  }

  function baselineRandom(t: number, K: number, seed: number): BaselinePick[] {
    // Deterministic linear-congruential shuffle — mirrors synthetic.ts.
    let x = seed >>> 0;
    const r = () => {
      x = (x * 1664525 + 1013904223) >>> 0;
      return x / 4294967296;
    };
    return [...eligible(t)]
      .sort(() => r() - 0.5)
      .slice(0, K)
      .map((f) => ({ id: f.id, name: f.name }));
  }

  function baselineVolume(t: number, K: number): BaselinePick[] {
    return eligible(t)
      .map((f) => ({
        id: f.id,
        name: f.name,
        score: t - (syntheticSource.months(f.first) as number),
      }))
      .sort((a, b) => b.score - a.score)
      .slice(0, K);
  }

  function baselineRecency(t: number, K: number): BaselinePick[] {
    return eligible(t)
      .map((f) => ({
        id: f.id,
        name: f.name,
        score: -(t - (syntheticSource.months(f.first) as number)),
      }))
      .sort((a, b) => b.score - a.score)
      .slice(0, K);
  }

  function precisionAt(
    picks: ReadonlyArray<BaselinePick | RankedPick>,
    t: number,
  ): PrecisionResult {
    if (!picks || picks.length === 0) return { hits: 0, k: 0, precision: 0 };
    const t24 = t + 24;
    let hits = 0;
    let evaluable = 0;
    for (const p of picks) {
      const f = foundersById.get(p.id);
      if (!f) continue;
      const em = syntheticSource.months(f.emerge);
      if (em != null && em <= t24) hits++;
      if (t24 <= today) evaluable++;
    }
    return { hits, k: evaluable, precision: evaluable ? hits / evaluable : 0 };
  }

  return {
    source: "hybrid",
    today,
    taxonomy: syntheticSource.taxonomy,
    founders: () => founders,
    months: syntheticSource.months,
    fmtMonth: syntheticSource.fmtMonth,
    fmtQuarter: syntheticSource.fmtQuarter,
    curve: syntheticSource.curve,
    tier1: syntheticSource.tier1,
    tier2: syntheticSource.tier2,
    rankAt,
    outcomeAt,
    baselineRandom,
    baselineVolume,
    baselineRecency,
    precisionAt,
    bootCI: syntheticSource.bootCI,
    // TODO(phase-c.6): swap in real signal evidence per founder.
    signalsFor: syntheticSource.signalsFor,
    // TODO(phase-c.5): swap in real KG ego-network per founder.
    egoFor: syntheticSource.egoFor,
    paletteFor: syntheticSource.paletteFor,
  };
}

// Module-level cache: one fetch per page lifecycle (no localStorage by
// repo convention). Reset on full reload.
let cached: Promise<DataSource> | null = null;

export async function loadRealSource(): Promise<DataSource> {
  if (cached) return cached;

  cached = (async () => {
    try {
      const [cohort, bounds] = await Promise.all([
        fetchJSON<CohortResponse>("/api/cohort"),
        fetchJSON<TimelineBoundsResponse>("/api/timeline-bounds"),
      ]);

      if (!cohort.members || cohort.members.length === 0) {
        throw new Error("/api/cohort returned no members");
      }

      const today =
        bounds.latest != null
          ? isoToMonthsSince2014(bounds.latest)
          : syntheticSource.today;
      const firstMonth =
        bounds.earliest != null ? isoToMonthString(bounds.earliest) : null;

      const founders = mapCohortToFounders(cohort, firstMonth);
      return buildHybridSource(founders, today);
    } catch (err) {
      console.warn(
        "[thesis] real data unavailable — falling back to synthetic source:",
        err,
      );
      return syntheticSource;
    }
  })();

  return cached;
}

// Test-only hook: reset the in-memory cache so each test starts fresh.
export function __resetRealSourceCacheForTests(): void {
  cached = null;
}
