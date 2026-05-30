// Unified data client: one seam for "where does the frontend read from".
//
// - DEV: NEXT_PUBLIC_SUPABASE_URL unset → hit the local FastAPI
//   (NEXT_PUBLIC_API_BASE_URL, default http://localhost:8000). Live compute.
// - PROD (Vercel): NEXT_PUBLIC_SUPABASE_URL set → read pre-computed view
//   JSON from the Supabase `view_cache` table (anon REST). No always-on API
//   server; payloads are byte-identical to the API (same Python source).
//
// apiGet(path) takes an API route like "/api/kg/ego/marclou?top_signals=14"
// and returns the parsed JSON from whichever backend is configured. Returns
// null on miss/error so callers fall back gracefully.

import { API_BASE_URL } from "./config";

const SUPABASE_URL = process.env.NEXT_PUBLIC_SUPABASE_URL;
const SUPABASE_ANON_KEY = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

export const usingSupabase = Boolean(SUPABASE_URL && SUPABASE_ANON_KEY);

// Map an API route → the view_cache key the materialiser wrote.
// Returns null for routes that aren't materialised (caller falls back).
function cacheKeyFor(path: string): string | null {
  const [route, query] = path.replace(/^\/api\//, "").split("?");
  const params = new URLSearchParams(query ?? "");

  if (route === "cohort") return "cohort";
  if (route === "timeline-bounds") return "timeline-bounds";
  if (route === "kg/cohort") return "kg/cohort";
  if (route.startsWith("kg/ego/")) return route; // kg/ego/<id>
  if (route.startsWith("founder/")) return route; // founder/<id> (if cached)
  if (route === "yc-overlap") {
    const d = params.get("date");
    return d ? `yc-overlap/${d}` : null;
  }
  if (route === "baselines") {
    const d = params.get("date");
    const k = params.get("k");
    return d && k ? `baselines/${d}/${k}` : null;
  }
  return null;
}

async function fromSupabase(path: string): Promise<unknown | null> {
  const key = cacheKeyFor(path);
  if (!key) return null;
  try {
    const url = `${SUPABASE_URL}/rest/v1/view_cache?key=eq.${encodeURIComponent(key)}&select=payload`;
    const res = await fetch(url, {
      headers: {
        apikey: SUPABASE_ANON_KEY!,
        Authorization: `Bearer ${SUPABASE_ANON_KEY}`,
        accept: "application/json",
      },
    });
    if (!res.ok) return null;
    const rows = (await res.json()) as Array<{ payload: unknown }>;
    return rows.length ? rows[0].payload : null;
  } catch {
    return null;
  }
}

async function fromApi(path: string): Promise<unknown | null> {
  try {
    const res = await fetch(`${API_BASE_URL}${path}`, { headers: { accept: "application/json" } });
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  }
}

export async function apiGet(path: string): Promise<unknown | null> {
  return usingSupabase ? fromSupabase(path) : fromApi(path);
}
