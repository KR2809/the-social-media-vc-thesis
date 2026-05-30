// Real-data DataSource (Phases C.1 + C.2 + C.3 + C.6 partial).
//
// Phase C.1 (cohort loader): founders() comes from /api/cohort, today
// derives from /api/timeline-bounds.latest, source flips to "hybrid".
//
// Phase C.2 (outcome loader): Founder.emerge/venture/first parsed from
// the cohort row (emergence_quarter free-text → "YYYY-MM" or "YYYY-QN"
// via parseEmergenceQuarter; first ← first_signal_at fallback to
// timeline.earliest).
//
// Phase C.3 partial (scoring loader): curve/tier1/tier2/rankAt no
// longer delegate to synthetic. Each is computed from the cached
// scored signals: curve = mean overall_signal_strength of signals
// before t; tier1 = mean of S2 + S3 sub-dims (distribution + intent);
// tier2 = mean of S1 + S4 + S6 sub-dims (action + network + domain).
// Founders with no signals yet fall through to synthetic curves so
// the demo never goes blank; the visible "0pp lift vs random"
// resolves into meaningful spread as scoring completes more rows.
//
// Phase C.6 partial (signals loader): signalsFor() pulls real scored
// signals from /api/founder/{id} top_signals_at_t. Pre-fetched at load
// time so the sync DataSource interface still works; cache misses fall
// back to synthetic. As the scoring backend completes more rows, the
// next page reload picks up richer signal evidence with no code change.
//
// Phase C.5 partial (KG loader): egoFor() synthesises a per-founder
// 1-hop ego graph from the same cached signals — nodes = founder + top
// 5 signals + their s6_topic_label topics + platforms; edges weighted
// by overall_signal_strength. Once analysis/build_graph.py produces a
// populated graph.pkl + kg_features.parquet, we'll swap this for the
// server-side graph; until then this is a faithful client-side view of
// the same data the scorer produces.
//
// What's still synthetic (deliberately — separate C.* phases):
//   * baselineRandom/Volume/Recency    (C.4 baselines — blocked on negs)
//   * precisionAt                      (C.4 — blocked on negs)
//   * paletteFor / taxonomy            (UI helpers, not swappable)
//
// On fetch failure (FastAPI not running, network error, bad shape) this
// module logs a console.warn and returns the synthetic source — the demo
// stays viewable. Failures are NOT silently swallowed.

import { syntheticSource } from "./synthetic";
import type {
  BaselinePick,
  DataSource,
  EgoNetwork,
  Founder,
  FounderId,
  KGEdge,
  KGNode,
  Outcome,
  PrecisionResult,
  RankedPick,
  SignalEvidence,
  TaxonomyCode,
} from "./types";
import { apiGet } from "./client";

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

// One row from /api/founder/{id}.top_signals_at_t. Mirrors the schema
// produced by scoring/score_signals.py (s[1-6]_* sub-dim columns +
// s6_topic_label + overall_signal_strength) plus the joined raw_text.
interface ScoredSignalRow {
  signal_id: string;
  person_id: string;
  platform: string;
  timestamp: string; // ISO
  overall_signal_strength: number;
  s6_topic_label: string | null;
  raw_text: string;
  // Sub-dim score columns — Record<string, number>-ish, used to pick the
  // dominant signal dimension for the SignalEvidence.dim summary line.
  [k: string]: unknown;
}

interface FounderResponse {
  person_id: string;
  cohort: { display_name: string; venture: string | null; niche: string };
  feature_row: Record<string, unknown>;
  kg_features: Record<string, unknown>;
  outcome: { emerged?: number; source?: string };
  top_signals_at_t: ScoredSignalRow[];
  n_total_signals: number;
  partial: boolean;
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
  // Routes through the unified client: local FastAPI in dev, Supabase
  // view_cache in prod. Throws on miss so callers fall back to synthetic.
  const data = await apiGet(path);
  if (data == null) throw new Error(`no data for ${path}`);
  return data as T;
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

// Pick the highest-scoring sub-dim from a scored_signals row → "S1.3", "S2.4", etc.
// scored_signals columns are named "s1_build_in_public", "s2_distribution_breadth",
// etc; the leading "s[1-6]" maps onto the taxonomy code.
function pickDominantDim(row: ScoredSignalRow): { dim: string; cat: TaxonomyCode } {
  let bestKey: string | null = null;
  let bestVal = -Infinity;
  for (const [k, v] of Object.entries(row)) {
    if (typeof v !== "number") continue;
    if (!/^s[1-6]_/.test(k)) continue;
    if (v > bestVal) {
      bestVal = v;
      bestKey = k;
    }
  }
  if (!bestKey) {
    return { dim: row.s6_topic_label ?? "signal", cat: "S6" };
  }
  const cat = bestKey[0].toUpperCase() + bestKey[1]; // "s1_..." → "S1"
  // Replace the leading "sN_" with "SN.x " and humanise the sub-dim slug.
  const subDim = bestKey.replace(/^s[1-6]_/, "").replace(/_/g, "-");
  return { dim: `${cat}.${subDim}`, cat: cat as TaxonomyCode };
}

function mapScoredSignal(row: ScoredSignalRow, idx: number): SignalEvidence {
  const { dim, cat } = pickDominantDim(row);
  // Render timestamp as "MMM YYYY" using synthetic's fmtMonth, which expects a
  // months-since-2014 integer. Compute it from the ISO string.
  const d = new Date(row.timestamp);
  const monthsSince2014 = (d.getUTCFullYear() - 2014) * 12 + d.getUTCMonth();
  return {
    id: idx,
    dim,
    cat,
    score: row.overall_signal_strength,
    raw: row.raw_text || row.s6_topic_label || "(no source text)",
    platform: row.platform,
    timestamp: syntheticSource.fmtMonth(monthsSince2014),
  };
}

function buildHybridSource(
  founders: Founder[],
  today: number,
  signalsByFounder: Map<FounderId, ScoredSignalRow[]>,
): DataSource {
  // Per-founder helpers delegate to synthetic — but list-iterating methods
  // (rankAt, baselines, precisionAt) re-implement with the real founder
  // roster, otherwise they'd silently rank the synthetic 30-row cohort.

  const foundersById = new Map(founders.map((f) => [f.id, f]));

  // ────────────────────────────── C.3 partial ──────────────────────────────
  // Per-founder "score at time t" computed from real scored signals.
  // Aggregates the founder's cached signals with timestamp ≤ t. When a
  // founder has no scored signals (yet — scoring may still be running, or
  // collection hasn't caught the rest of the cohort), we fall back to the
  // synthetic curve so the demo never goes blank.
  //
  // Caching: tCutoffMs computed once per (founder, t) lookup; the cohort is
  // small so this stays cheap.

  function tToCutoffMs(t: number): number {
    const year = 2014 + Math.floor(t / 12);
    const month = t % 12;
    return Date.UTC(year, month, 1);
  }

  function signalsBefore(founderId: FounderId, t: number): ScoredSignalRow[] {
    const cached = signalsByFounder.get(founderId);
    if (!cached || cached.length === 0) return [];
    const cutoff = tToCutoffMs(t);
    return cached.filter((s) => new Date(s.timestamp).getTime() <= cutoff);
  }

  // Mean of a sub-dim group across a founder's signals. Used to project the
  // taxonomy onto two tiers (topic-side / founder-side) for the v1 framework.
  function meanSubDim(rows: ScoredSignalRow[], prefixes: string[]): number {
    let sum = 0;
    let n = 0;
    for (const row of rows) {
      for (const [k, v] of Object.entries(row)) {
        if (typeof v !== "number") continue;
        if (!prefixes.some((p) => k.startsWith(p))) continue;
        sum += v;
        n++;
      }
    }
    return n > 0 ? sum / n : 0;
  }

  function realCurve(f: Founder, t: number): number | null {
    const fm = syntheticSource.months(f.first);
    if (fm == null || t < fm) return null;
    const rows = signalsBefore(f.id, t);
    if (rows.length === 0) {
      // No real signals yet — synthetic curve keeps the demo populated.
      return syntheticSource.curve(f, t);
    }
    // Combined score = mean of overall_signal_strength across signals so far.
    // Clamp to [0, 0.99] to stay within the UI's expected range.
    const sum = rows.reduce((acc, r) => acc + r.overall_signal_strength, 0);
    return Math.max(0, Math.min(0.99, sum / rows.length));
  }

  function realTier1(f: Founder, t: number): number | null {
    const rows = signalsBefore(f.id, t);
    if (rows.length === 0) return syntheticSource.tier1(f, t);
    // Topic-side: distribution (S2) + intent/ambition (S3) sub-dims.
    return Math.max(0, Math.min(0.99, meanSubDim(rows, ["s2_", "s3_"])));
  }

  function realTier2(f: Founder, t: number): number | null {
    const rows = signalsBefore(f.id, t);
    if (rows.length === 0) return syntheticSource.tier2(f, t);
    // Founder-side: action (S1) + network density (S4) + domain depth (S6).
    return Math.max(0, Math.min(0.99, meanSubDim(rows, ["s1_", "s4_", "s6_"])));
  }

  function outcomeAt(f: Founder, t: number): Outcome {
    const em = syntheticSource.months(f.emerge);
    const t24 = t + 24;
    if (em == null) return t24 <= today ? "not_yet" : "unknown";
    return em <= t24 ? "emerged" : t24 <= today ? "not_yet" : "unknown";
  }

  function rankAt(t: number, K: number): RankedPick[] {
    const rows: RankedPick[] = [];
    for (const f of founders) {
      const c = realCurve(f, t);
      if (c == null) continue;
      rows.push({
        id: f.id,
        name: f.name,
        niche: f.niche,
        t1: realTier1(f, t),
        t2: realTier2(f, t),
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

  function signalsFor(founderId: FounderId, t: number): SignalEvidence[] {
    const cached = signalsByFounder.get(founderId);
    // No real data yet for this founder (scoring still in flight, or the
    // founder has no collected signals) — fall back to synthetic so the
    // demo never goes blank.
    if (!cached || cached.length === 0) {
      return syntheticSource.signalsFor(founderId, t);
    }
    // Date-filter on the client (we have all the founder's scored signals
    // cached): drop anything stamped AFTER the slider position t. Then
    // sort by overall_signal_strength desc and take the top 5.
    // t is months-since-2014-01; convert to Date at month start (UTC).
    const year = 2014 + Math.floor(t / 12);
    const month = t % 12; // 0-indexed; Date.UTC accepts 0-indexed month
    const cutoff = new Date(Date.UTC(year, month, 1));
    const filtered = cached.filter((s) => {
      const ts = new Date(s.timestamp);
      return ts <= cutoff;
    });
    if (filtered.length === 0) {
      return syntheticSource.signalsFor(founderId, t);
    }
    filtered.sort(
      (a, b) => b.overall_signal_strength - a.overall_signal_strength,
    );
    return filtered.slice(0, 5).map((row, i) => mapScoredSignal(row, i));
  }

  // ────────────────────────────── C.5 partial ──────────────────────────────
  // Real ego-network from cached scored signals. Until analysis/build_graph.py
  // produces a populated graph.pkl + kg_features.parquet, we synthesise a
  // 1-hop ego graph on the fly:
  //   nodes:  founder F, top-5 signals (by overall_signal_strength),
  //           up to 4 topics (s6_topic_label clusters), platforms touched
  //   edges:  F → each signal (weight = strength)
  //           signal → its topic
  //           signal → its platform
  //
  // For founders without scored data, fall back to synthetic so the
  // ego-network panel never goes blank.
  function realEgoFor(founderId: FounderId): EgoNetwork {
    const cached = signalsByFounder.get(founderId);
    const f = foundersById.get(founderId);
    if (!cached || cached.length === 0 || !f) {
      return syntheticSource.egoFor(founderId);
    }
    // Take the top-N strongest signals to keep the graph readable.
    const ranked = [...cached].sort(
      (a, b) => b.overall_signal_strength - a.overall_signal_strength,
    );
    const sigs = ranked.slice(0, 5);

    const center: KGNode = { id: "F", kind: "founder", label: f.name };
    const sigNodes: KGNode[] = sigs.map((s, i) => {
      const { dim } = pickDominantDim(s);
      return {
        id: `S${i}`,
        kind: "signal",
        label: dim.split(".")[0], // "S1" / "S4" / ... short label
        weight: s.overall_signal_strength,
      };
    });

    // Topic nodes: dedup by s6_topic_label across the picked signals.
    // Truncate labels so the graph remains visually compact.
    const topicMap = new Map<string, KGNode>();
    sigs.forEach((s, i) => {
      const raw = (s.s6_topic_label ?? "").trim();
      if (!raw) return;
      const truncated = raw.length > 22 ? raw.slice(0, 20) + "…" : raw;
      if (!topicMap.has(truncated)) {
        topicMap.set(truncated, { id: `T${topicMap.size}`, kind: "topic", label: truncated });
      }
      // tag the signal's topic node id for the edge pass below
      (sigNodes[i] as KGNode & { _topicId?: string })._topicId = topicMap.get(truncated)!.id;
    });
    const topicNodes = Array.from(topicMap.values());

    // Platform nodes: dedup by platform name.
    const platformMap = new Map<string, KGNode>();
    sigs.forEach((s, i) => {
      const p = (s.platform ?? "unknown").toLowerCase();
      // Short label for the graph chip.
      const short = p === "hackernews" ? "HN" : p === "twitter" ? "X" : p === "reddit" ? "RD" : p === "youtube" ? "YT" : p.slice(0, 3).toUpperCase();
      if (!platformMap.has(p)) {
        platformMap.set(p, { id: `P${platformMap.size}`, kind: "platform", label: short });
      }
      (sigNodes[i] as KGNode & { _platformId?: string })._platformId = platformMap.get(p)!.id;
    });
    const platformNodes = Array.from(platformMap.values());

    const edges: KGEdge[] = [];
    sigNodes.forEach((sNode, i) => {
      edges.push({ a: "F", b: sNode.id, w: sigs[i].overall_signal_strength });
      const tid = (sNode as KGNode & { _topicId?: string })._topicId;
      if (tid) edges.push({ a: sNode.id, b: tid, w: 0.6 });
      const pid = (sNode as KGNode & { _platformId?: string })._platformId;
      if (pid) edges.push({ a: sNode.id, b: pid, w: 0.4 });
    });

    return {
      nodes: [center, ...sigNodes, ...topicNodes, ...platformNodes],
      edges,
    };
  }

  return {
    source: "hybrid",
    today,
    taxonomy: syntheticSource.taxonomy,
    founders: () => founders,
    months: syntheticSource.months,
    fmtMonth: syntheticSource.fmtMonth,
    fmtQuarter: syntheticSource.fmtQuarter,
    curve: realCurve,
    tier1: realTier1,
    tier2: realTier2,
    rankAt,
    outcomeAt,
    baselineRandom,
    baselineVolume,
    baselineRecency,
    precisionAt,
    bootCI: syntheticSource.bootCI,
    signalsFor,
    // C.5 partial: ego-network synthesised from cached signals (no
    // graph.pkl pass needed). Falls back to synthetic when no signals.
    egoFor: realEgoFor,
    paletteFor: syntheticSource.paletteFor,
    coverage: () => {
      let withSignals = 0;
      let scored = 0;
      for (const rows of signalsByFounder.values()) {
        if (rows.length > 0) {
          withSignals++;
          scored += rows.length;
        }
      }
      return {
        totalFounders: founders.length,
        foundersWithSignals: withSignals,
        scoredEvents: scored,
      };
    },
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

      // Per-founder fetch in parallel. Cohort is small (~20), endpoint
      // returns up to top_signals=20 signals per founder. Failures per
      // founder are isolated — that founder just falls back to synthetic
      // for signalsFor(); the rest still get real data.
      const signalsByFounder = new Map<FounderId, ScoredSignalRow[]>();
      await Promise.all(
        founders.map(async (f) => {
          try {
            const r = await fetchJSON<FounderResponse>(
              `/api/founder/${encodeURIComponent(f.id)}?top_signals=20`,
            );
            signalsByFounder.set(f.id, r.top_signals_at_t ?? []);
          } catch {
            // Cohort member with no data yet — leave the map slot empty.
            signalsByFounder.set(f.id, []);
          }
        }),
      );

      return buildHybridSource(founders, today, signalsByFounder);
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
