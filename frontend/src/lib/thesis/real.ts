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
    first_signal_at: string | null;
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

const MONTH_TOKENS: Record<string, string> = {
  jan: "01", feb: "02", mar: "03", apr: "04", may: "05", jun: "06",
  jul: "07", aug: "08", sep: "09", oct: "10", nov: "11", dec: "12",
};

// Parse the cohort's free-text `emergence_quarter` into a "YYYY-MM" or
// "YYYY-QN" string that synthetic.months() understands. Returns null for
// values we can't confidently interpret. Range values ("2018–2019") collapse
// to the LOWER bound — conservative for precision@k claims; flagged in
// STATUS_UPDATES for reviewer override.
export function parseEmergenceQuarter(raw: string | null): string | null {
  if (!raw) return null;
  const s = raw.toLowerCase().trim();

  // "YYYY-QN" — already in the shape synthetic understands.
  const qMatch = s.match(/(20\d{2})-q([1-4])/);
  if (qMatch) return `${qMatch[1]}-Q${qMatch[2]}`;

  // "Apr 2023" / "may 2020" / "dec 2020 → scale".
  const monMatch = s.match(/(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\w*\s+(20\d{2})/);
  if (monMatch) return `${monMatch[2]}-${MONTH_TOKENS[monMatch[1]]}`;

  // "Early 2026" / "Late 2020".
  if (/early\s+(20\d{2})/.test(s)) {
    const y = s.match(/(20\d{2})/)![1];
    return `${y}-Q1`;
  }
  if (/late\s+(20\d{2})/.test(s)) {
    const y = s.match(/(20\d{2})/)![1];
    return `${y}-Q4`;
  }

  // "2018–2019", "2019 → 2025", "2019 (exit)", "2020 onward", "2020": grab
  // the first 4-digit year and call it Q1 (lower bound on ranges; modifiers
  // like "(exit)" / "onward" get stripped).
  const yearMatch = s.match(/(20\d{2})/);
  if (yearMatch) return `${yearMatch[1]}-Q1`;

  return null;
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
  fallbackFirstMonth: string | null,
): Founder[] {
  return cohort.members.map((m) => ({
    id: m.person_id,
    name: m.display_name,
    niche: m.niche,
    // Per-founder first-signal date from the API. Falls back to the global
    // timeline.earliest for founders whose signals haven't been collected
    // yet — keeps them visible on the curve instead of dropping them.
    first: m.first_signal_at != null
      ? isoToMonthString(m.first_signal_at)
      : (fallbackFirstMonth ?? "2014-01"),
    // C.2: parse cohort_verified.md's free-text emergence_quarter. Lower
    // bound for ranges; null when the string is too noisy to interpret.
    emerge: parseEmergenceQuarter(m.emergence_quarter),
    // C.2: real venture name from the cohort row.
    venture: m.venture,
    // TODO(phase-c.3): no clean per-venture metric field in the API yet;
    // scoring will populate it from topic_label / signal-strength aggregates.
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
