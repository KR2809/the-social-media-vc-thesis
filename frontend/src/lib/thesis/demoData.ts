// Data layer for the /demo screens. Two small static bundles, lazy-loaded
// per screen (the landing page never pays for these).

export interface RaceData {
  dates: string[];
  ks: number[];
  series: Record<string, (number | null)[]>; // "strategy|k" -> precision/date
}

export interface McRow {
  k: number;
  rate: number;
  lo: number;
  hi: number;
}

export interface DemoStats {
  race: RaceData | null;
  mc: McRow[] | null;
}

export interface FounderPost {
  date: string;
  platform: string;
  text: string;
  strength: number;
  signals: string[]; // plain-named, already translated at export
}

export interface FounderPosts {
  person_id: string;
  founder_name: string;
  venture: string;
  flag_date: string;
  emergence_date: string | null;
  lead_time_months: number | null;
  posts: FounderPost[];
}

let statsCache: Promise<DemoStats> | null = null;
export function loadDemoStats(): Promise<DemoStats> {
  statsCache ??= fetch("/demo_stats.json").then((r) => {
    if (!r.ok) throw new Error(`demo_stats: ${r.status}`);
    return r.json();
  });
  return statsCache;
}

let postsCache: Promise<{ founders: FounderPosts[] }> | null = null;
export function loadFounderPosts(): Promise<{ founders: FounderPosts[] }> {
  postsCache ??= fetch("/founder_posts.json").then((r) => {
    if (!r.ok) throw new Error(`founder_posts: ${r.status}`);
    return r.json();
  });
  return postsCache;
}

/** Collected post text sometimes carries HTML entities (HN/Twitter sources);
 *  decode the common ones for display. Never alters the words themselves. */
export function plainText(s: string): string {
  return s
    .replace(/&#x27;|&#39;/g, "'")
    .replace(/&quot;/g, '"')
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&amp;/g, "&");
}

// ---------------------------------------------------------------------------
// VC-game helpers (pure; operate on the main timeline bundle)
// ---------------------------------------------------------------------------

import type { TimelineData, TimelineFounder } from "./timeline";

/** Score of a person at `date` = last trajectory point at/before it. */
export function scoreAt(f: TimelineFounder, date: string): number {
  let s = 0;
  for (const p of f.trajectory) {
    if (p.date <= date) s = p.score;
    else break;
  }
  return s;
}

export interface GameCandidate {
  f: TimelineFounder;
  score: number;
  rising: boolean;
  quote: string | null;
}

/** The system's candidate board at a date: top `n` by score, with context. */
export function boardAt(
  data: TimelineData,
  date: string,
  n = 12,
): GameCandidate[] {
  const yearAgo = `${parseInt(date.slice(0, 4), 10) - 1}${date.slice(4)}`;
  return data.founders
    .map((f) => ({
      f,
      score: scoreAt(f, date),
      rising: scoreAt(f, date) > scoreAt(f, yearAgo),
      quote: (() => {
        const t = f.top_signals_at_pickup.find(
          (s) => s.text && (s.timestamp ?? "") <= date,
        )?.text;
        return t ? plainText(t) : null;
      })(),
    }))
    .filter((c) => c.score > 0)
    .sort((a, b) => b.score - a.score)
    .slice(0, n);
}

/** Did this person emerge (per the study's outcome) — at any point. */
export function everEmerged(f: TimelineFounder): boolean {
  return f.is_positive && f.emergence_date !== null;
}

/** Deterministic pseudo-random picks so "random" is fair but reproducible. */
export function seededPicks<T>(pool: T[], n: number, seed: number): T[] {
  const arr = [...pool];
  let s = seed >>> 0;
  const rand = () => ((s = (s * 1664525 + 1013904223) >>> 0) / 2 ** 32);
  for (let i = arr.length - 1; i > 0; i--) {
    const j = Math.floor(rand() * (i + 1));
    [arr[i], arr[j]] = [arr[j], arr[i]];
  }
  return arr.slice(0, n);
}
