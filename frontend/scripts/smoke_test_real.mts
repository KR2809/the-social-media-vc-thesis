// Smoke test for the Phase C.1 real-data cohort loader.
//
// Run with:  npm run test:smoke
//
// Mocks global fetch (Node 20+ built-in) to simulate /api/cohort and
// /api/timeline-bounds, then asserts loadRealSource() behaves correctly.
// Avoids Vitest as a devDep to keep the C.1 surface small — when the
// test suite grows beyond a handful of cases, swap to Vitest.

import {
  loadRealSource,
  __resetRealSourceCacheForTests,
} from "../src/lib/thesis/real";

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

interface MockHandler {
  (url: string): { ok: boolean; status: number; statusText: string; body: unknown };
}

function installFetchMock(handler: MockHandler): () => void {
  const realFetch = globalThis.fetch;
  // @ts-expect-error replacing fetch with a minimal mock
  globalThis.fetch = async (input: string | URL | Request): Promise<Response> => {
    const url = typeof input === "string" ? input : input.toString();
    const r = handler(url);
    return new Response(JSON.stringify(r.body), {
      status: r.status,
      statusText: r.statusText,
    });
  };
  return () => {
    globalThis.fetch = realFetch;
  };
}

function silenceWarn(): () => string[] {
  const seen: string[] = [];
  const real = console.warn;
  console.warn = (...args: unknown[]) => {
    seen.push(args.map(String).join(" "));
  };
  return () => {
    console.warn = real;
    return seen;
  };
}

// -------------------------- Case 1: happy path --------------------------

console.log("Case 1: /api/cohort + /api/timeline-bounds happy path");
__resetRealSourceCacheForTests();
{
  const restore = installFetchMock((url) => {
    if (url.endsWith("/api/cohort")) {
      return {
        ok: true,
        status: 200,
        statusText: "OK",
        body: {
          n: 3,
          members: [
            { person_id: "levelsio", display_name: "Pieter Levels", venture: "Nomad List", niche: "Indie hacker", emergence_quarter: "2015-Q1", data_score: 9 },
            { person_id: "marclou", display_name: "Marc Lou", venture: "ShipFast", niche: "Solopreneur", emergence_quarter: "2023-Q1", data_score: 8 },
            { person_id: "yongfook", display_name: "Yongfook", venture: "Bannerbear", niche: "Indie SaaS", emergence_quarter: "2022-Q2", data_score: 8 },
          ],
        },
      };
    }
    if (url.endsWith("/api/timeline-bounds")) {
      return {
        ok: true,
        status: 200,
        statusText: "OK",
        body: { earliest: "2014-04-15T00:00:00+00:00", latest: "2026-05-12T00:00:00+00:00", n_signals: 1000 },
      };
    }
    return { ok: false, status: 404, statusText: "Not Found", body: { error: "unknown route" } };
  });

  const src = await loadRealSource();
  assert(src.source === "hybrid", `source === "hybrid" (got "${src.source}")`);

  const founders = src.founders();
  assert(founders.length === 3, `founders().length === 3 (got ${founders.length})`);
  const names = founders.map((f) => f.name).join(", ");
  assert(
    names.includes("Pieter Levels") && names.includes("Marc Lou") && names.includes("Yongfook"),
    `founder names are real (got: ${names})`,
  );
  assert(
    !founders.some((f) => /Founder \d+/.test(f.name)),
    `no placeholder "Founder N" names`,
  );

  // C.1 contract: emerge/venture/ventureMetric/emphasis stay null/empty.
  const f0 = founders[0];
  assert(f0.emerge === null, "founder.emerge === null (deferred to C.2)");
  assert(f0.venture === null, "founder.venture === null (deferred to C.2)");
  assert(f0.ventureMetric === null, "founder.ventureMetric === null (deferred to C.2)");
  assert(
    Array.isArray(f0.emphasis) && f0.emphasis.length === 0,
    "founder.emphasis === [] (deferred to C.3)",
  );

  // today derived from /api/timeline-bounds.latest (May 2026 → 148 months since 2014-01).
  const expectedToday = (2026 - 2014) * 12 + 4; // May = month index 4
  assert(src.today === expectedToday, `today === ${expectedToday} (got ${src.today})`);

  // first ← earliest (April 2014 → "2014-04")
  assert(f0.first === "2014-04", `founder.first === "2014-04" (got "${f0.first}")`);

  restore();
}

// -------------------------- Case 2: fetch failure ----------------------

console.log("\nCase 2: /api/cohort fetch failure → synthetic fallback");
__resetRealSourceCacheForTests();
{
  const restoreWarn = silenceWarn();
  const restore = installFetchMock(() => ({
    ok: false,
    status: 503,
    statusText: "Service Unavailable",
    body: { error: "FastAPI not running" },
  }));

  const src = await loadRealSource();
  assert(src.source === "synthetic", `source === "synthetic" on fetch failure (got "${src.source}")`);

  const warnings = restoreWarn();
  assert(
    warnings.some((w) => w.includes("real data unavailable")),
    `console.warn fired with fallback notice (saw ${warnings.length} warning(s))`,
  );
  restore();
}

// -------------------------- Case 3: empty cohort -----------------------

console.log("\nCase 3: /api/cohort returns empty members → synthetic fallback");
__resetRealSourceCacheForTests();
{
  const restoreWarn = silenceWarn();
  const restore = installFetchMock((url) => {
    if (url.endsWith("/api/cohort")) {
      return { ok: true, status: 200, statusText: "OK", body: { n: 0, members: [] } };
    }
    return {
      ok: true,
      status: 200,
      statusText: "OK",
      body: { earliest: null, latest: null, n_signals: 0 },
    };
  });

  const src = await loadRealSource();
  assert(src.source === "synthetic", `source === "synthetic" on empty cohort (got "${src.source}")`);
  restoreWarn();
  restore();
}

// -------------------------- Summary -----------------------------------

console.log(`\n${passed} passed, ${failed} failed`);
if (failed > 0) {
  process.exit(1);
}
