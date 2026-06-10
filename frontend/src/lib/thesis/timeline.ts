// Data layer for the landing page. Loads + types the static
// `public/frontend_timeline.json` bundle (produced by
// scripts/export_frontend_timeline.py) and provides the pure date-math
// helpers the Time Machine renders from.
//
// Design notes:
// - Pure module: no React, no fetch side effects outside loadTimeline().
// - Dates are ISO `YYYY-MM-DD` strings; lexicographic comparison is
//   chronologically correct for that shape, so no Date parsing is needed.
// - hasSignals() is the no-fabrication guard: when a founder has no scored
//   signals the UI must say "limited public data" — never invent posts.

export interface TimelineSignal {
  signal_id: string;
  platform: string;
  timestamp: string | null;
  strength: number;
  text: string;
}

export interface TrajectoryPoint {
  date: string;
  score: number;
  verdict: string;
  emerged_by_then: boolean;
}

export interface TimelineFounder {
  person_id: string;
  founder_name: string;
  venture: string;
  handle: string;
  first_pickup_date: string | null;
  emergence_date: string | null;
  lead_time_months: number | null;
  peak_score: number;
  is_positive: boolean;
  trajectory: TrajectoryPoint[];
  top_signals_at_pickup: TimelineSignal[];
}

export interface HeadlineNumbers {
  roc_auc: number | null;
  roc_auc_ci_lo: number | null;
  roc_auc_ci_hi: number | null;
  pr_auc: number | null;
  lift_at_5: number | null;
  n: number | null;
  n_pos: number | null;
  base_rate_pct: number | null;
  prec_at_10_model: number | null;
  prec_at_10_random: number | null;
  lead_median_months: number | null;
  lead_max_months: number | null;
  lead_founders: number | null;
  framework_prec_at_5: number | null;
  volume_prec_at_5: number | null;
}

export interface TimelineMeta {
  generated_at: string;
  git_commit: string;
  grid_start: string | null;
  grid_end: string | null;
  tracked_threshold: number;
  n_founders: number;
  n_dates: number;
  headline: HeadlineNumbers;
}

export interface TimelineData {
  meta: TimelineMeta;
  dates: string[];
  founders: TimelineFounder[];
}

// ---------------------------------------------------------------------------
// Parse / load
// ---------------------------------------------------------------------------

/** Validate + type the raw JSON. Throws on a structurally broken bundle. */
export function parseTimeline(raw: unknown): TimelineData {
  const obj = raw as Record<string, unknown>;
  if (!obj || typeof obj !== "object") throw new Error("timeline: not an object");
  const meta = obj.meta as TimelineMeta | undefined;
  const dates = obj.dates as string[] | undefined;
  const founders = obj.founders as TimelineFounder[] | undefined;
  if (!meta || !Array.isArray(dates) || !Array.isArray(founders)) {
    throw new Error("timeline: missing meta/dates/founders");
  }
  if (!meta.headline) throw new Error("timeline: missing meta.headline");
  return { meta, dates, founders };
}

/** Fetch the static bundle shipped in /public. Cold-load friendly. */
export async function loadTimeline(): Promise<TimelineData> {
  const res = await fetch("/frontend_timeline.json");
  if (!res.ok) throw new Error(`timeline: fetch failed (${res.status})`);
  return parseTimeline(await res.json());
}

// ---------------------------------------------------------------------------
// Pure helpers (ISO-string date math; lexicographic == chronological)
// ---------------------------------------------------------------------------

/** Founders the model had flagged ("tracked") by `date`. */
export function foundersActiveAt(
  data: TimelineData,
  date: string,
): TimelineFounder[] {
  return data.founders.filter(
    (f) => f.first_pickup_date !== null && f.first_pickup_date <= date,
  );
}

/** Founders who had already emerged (launched) by `date`. */
export function foundersEmergedAt(
  data: TimelineData,
  date: string,
): TimelineFounder[] {
  return data.founders.filter(
    (f) => f.emergence_date !== null && f.emergence_date <= date,
  );
}

/** Lead time in months (negative = picked up after emergence; honest). */
export function leadMonths(f: TimelineFounder): number | null {
  return f.lead_time_months;
}

/** No-fabrication guard: does this founder have real scored signals? */
export function hasSignals(f: TimelineFounder): boolean {
  return f.top_signals_at_pickup.length > 0;
}
