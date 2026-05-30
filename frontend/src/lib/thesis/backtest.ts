// Backtest baselines loader — fetches GET /api/baselines, which runs the
// real retrospective backtest over the FULL labeled set (cohort positives
// + signal-bearing negatives). This is the honest source of per-strategy
// precision@k + lift; the client-side precisionAt() in real.ts can only
// see the positives-only cohort, so every strategy ties there.
//
// Returns source: "unavailable" (not throwing) when the API is down or the
// horizon is in the future, so View 2 can fall back to its caption rather
// than blanking.

import { apiGet } from "./client";
import type { BacktestResult, BacktestScore, BacktestStrategy } from "./types";

// months-since-2014-01 → "YYYY-MM-01" (UTC, month start).
export function monthsToISODate(t: number): string {
  const year = 2014 + Math.floor(t / 12);
  const month = (t % 12) + 1; // 1-indexed for the ISO string
  return `${year}-${String(month).padStart(2, "0")}-01`;
}

// The backtest is computed at discrete retrospective dates (quarterly,
// 2019–2024 — see scripts/materialise_view_cache.py). The slider sends an
// arbitrary month, so we snap the request to the nearest available date.
// This keeps the readout populated everywhere instead of going blank between
// the sampled dates.
const BACKTEST_DATES: string[] = (() => {
  const out: string[] = [];
  for (let y = 2019; y <= 2024; y++) for (const m of [1, 4, 7, 10]) out.push(`${y}-${String(m).padStart(2, "0")}-01`);
  return out;
})();

function snapToBacktestDate(date: string): string {
  const target = Date.parse(date);
  let best = BACKTEST_DATES[0];
  let bestDelta = Infinity;
  for (const d of BACKTEST_DATES) {
    const delta = Math.abs(Date.parse(d) - target);
    if (delta < bestDelta) {
      bestDelta = delta;
      best = d;
    }
  }
  return best;
}

interface RawRow {
  strategy: string;
  k: number;
  n_hits: number;
  base_rate: number;
  precision_at_k: number;
  lift_at_k: number;
}

const STRATEGY_ORDER: BacktestStrategy[] = ["two_tier", "random", "signal_volume", "recency"];

// Small in-memory cache keyed by (date,k) so dragging the slider back to a
// visited position is instant and doesn't re-hit the API.
const cache = new Map<string, BacktestResult>();

export async function fetchBacktest(t: number, k: number): Promise<BacktestResult> {
  // Snap the slider month to the nearest computed backtest date.
  const date = snapToBacktestDate(monthsToISODate(t));
  const key = `${date}:${k}`;
  const cached = cache.get(key);
  if (cached) return cached;

  const empty: BacktestResult = { date, k, baseRate: 0, scores: [], source: "unavailable" };

  try {
    const json = (await apiGet(`/api/baselines?date=${date}&k=${k}`)) as { rows?: RawRow[] } | null;
    if (!json) return empty;
    const rows = json.rows ?? [];
    if (rows.length === 0) return empty;

    const byStrategy = new Map<string, RawRow>(rows.map(r => [r.strategy, r]));
    const scores: BacktestScore[] = STRATEGY_ORDER.filter(s => byStrategy.has(s)).map(s => {
      const r = byStrategy.get(s)!;
      return {
        strategy: s,
        k: r.k,
        nHits: r.n_hits,
        baseRate: r.base_rate,
        precision: r.precision_at_k,
        lift: r.lift_at_k,
      };
    });
    const result: BacktestResult = {
      date,
      k,
      baseRate: scores[0]?.baseRate ?? 0,
      scores,
      source: "backend",
    };
    cache.set(key, result);
    return result;
  } catch {
    // Network error / API down — fall back silently to "unavailable".
    return empty;
  }
}
