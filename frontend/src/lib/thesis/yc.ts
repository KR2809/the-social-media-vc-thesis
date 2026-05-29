// YC overlap loader — fetches GET /api/yc-overlap, a documented, provenance-
// carrying cross-reference of the cohort against YC's public company
// directory. The overlap is intentionally small (the cohort is bootstrapped /
// indie, largely orthogonal to YC's accelerator model) — that's the honest
// finding, and where overlap exists (e.g. Cluely X25) it's external
// validation. Lookahead-safe: gated by batch-announcement date.

import { API_BASE_URL } from "./config";
import { monthsToISODate } from "./backtest";

export interface YCRecord {
  person_id: string;
  founder_name: string;
  venture: string;
  in_yc: boolean;
  in_yc_as_of: boolean;
  yc_batch: string | null;
  yc_company: string | null;
  evidence: string;
  batch_announced: string | null;
}

export interface YCOverlapResult {
  nCohort: number;
  nInYc: number;
  overlapPct: number;
  asOf: string | null;
  records: YCRecord[];
  methodology: string;
  source: "backend" | "unavailable";
}

const cache = new Map<string, YCOverlapResult>();

export async function fetchYCOverlap(t: number): Promise<YCOverlapResult> {
  const date = monthsToISODate(t);
  const cached = cache.get(date);
  if (cached) return cached;

  const empty: YCOverlapResult = {
    nCohort: 0,
    nInYc: 0,
    overlapPct: 0,
    asOf: date,
    records: [],
    methodology: "",
    source: "unavailable",
  };

  try {
    const res = await fetch(`${API_BASE_URL}/api/yc-overlap?date=${date}`, {
      headers: { accept: "application/json" },
    });
    if (!res.ok) return empty;
    const j = await res.json();
    const result: YCOverlapResult = {
      nCohort: j.n_cohort ?? 0,
      nInYc: j.n_in_yc ?? 0,
      overlapPct: j.overlap_pct ?? 0,
      asOf: j.as_of ?? date,
      records: (j.records ?? []) as YCRecord[],
      methodology: j.methodology ?? "",
      source: "backend",
    };
    cache.set(date, result);
    return result;
  } catch {
    return empty;
  }
}
