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
  parseEmergenceQuarter,
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
            { person_id: "levelsio", display_name: "Pieter Levels", venture: "Nomad List", niche: "Indie hacker", emergence_quarter: "2018–2019", data_score: 9, first_signal_at: "2014-04-20T00:00:00+00:00" },
            { person_id: "marclou", display_name: "Marc Lou", venture: "ShipFast", niche: "Solopreneur", emergence_quarter: "May 2023", data_score: 8, first_signal_at: "2020-02-23T23:51:22+00:00" },
            { person_id: "yongfook", display_name: "Yongfook", venture: "Bannerbear", niche: "Indie SaaS", emergence_quarter: "2022-Q2", data_score: 8, first_signal_at: null },
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
    // /api/founder/levelsio — return a 2-signal sample with realistic shape
    if (url.includes("/api/founder/levelsio")) {
      return {
        ok: true,
        status: 200,
        statusText: "OK",
        body: {
          person_id: "levelsio",
          cohort: { display_name: "Pieter Levels", venture: "Nomad List", niche: "Indie hacker" },
          feature_row: {},
          kg_features: {},
          outcome: { emerged: 1, source: "cohort_verified.md" },
          top_signals_at_t: [
            {
              signal_id: "hn_1", person_id: "levelsio", platform: "hackernews",
              timestamp: "2018-09-01T12:00:00+00:00",
              overall_signal_strength: 0.82,
              s1_build_in_public: 0.95, s2_distribution_breadth: 0.4, s3_explicit_goal: 0.6,
              s6_topic_label: "12 startups in 12 months",
              raw_text: "Just shipped Nomad List v2 — paying customers from week 1",
            },
            {
              signal_id: "hn_2", person_id: "levelsio", platform: "twitter",
              timestamp: "2020-01-15T08:00:00+00:00",
              overall_signal_strength: 0.71,
              s1_build_in_public: 0.6, s4_operator_proximity: 0.85,
              s6_topic_label: "Indie hacker movement",
              raw_text: "RemoteOK MRR breakdown shared publicly",
            },
          ],
          n_total_signals: 2,
          partial: true,
        },
      };
    }
    // All other founders: 404 to exercise the per-founder fallback path.
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

  // C.2 contract: emerge + venture come from the API; ventureMetric +
  // emphasis stay deferred to C.3.
  const levels = founders.find((f) => f.id === "levelsio")!;
  const lou = founders.find((f) => f.id === "marclou")!;
  const yong = founders.find((f) => f.id === "yongfook")!;

  assert(levels.emerge === "2018-Q1", `levels.emerge === "2018-Q1" (range lower bound; got "${levels.emerge}")`);
  assert(lou.emerge === "2023-05", `marclou.emerge === "2023-05" (month-year; got "${lou.emerge}")`);
  assert(yong.emerge === "2022-Q2", `yongfook.emerge === "2022-Q2" (already-quarter passthrough; got "${yong.emerge}")`);

  assert(levels.venture === "Nomad List", `venture mapped from API (got "${levels.venture}")`);
  assert(levels.ventureMetric === null, "ventureMetric === null (deferred to C.3)");
  assert(
    Array.isArray(levels.emphasis) && levels.emphasis.length === 0,
    "emphasis === [] (deferred to C.3)",
  );

  // today derived from /api/timeline-bounds.latest (May 2026 → 148 months since 2014-01).
  const expectedToday = (2026 - 2014) * 12 + 4; // May = month index 4
  assert(src.today === expectedToday, `today === ${expectedToday} (got ${src.today})`);

  // Per-founder first: from first_signal_at when present; fallback to
  // timeline.earliest when null.
  assert(levels.first === "2014-04", `levels.first === "2014-04" from first_signal_at (got "${levels.first}")`);
  assert(lou.first === "2020-02", `marclou.first === "2020-02" from first_signal_at (got "${lou.first}")`);
  assert(yong.first === "2014-04", `yongfook.first === "2014-04" (fallback to timeline.earliest; got "${yong.first}")`);

  // C.6 partial: signalsFor uses real per-founder cache when populated,
  // falls back to synthetic for cohort members without real signals.
  // Cache for levelsio holds 2 signals timestamped 2018-09 and 2020-01.
  // At slider t = 2019-Q1 (months=60), only the 2018 signal qualifies.
  const tEarly = (2019 - 2014) * 12 + 0; // Jan 2019
  const sigsEarly = src.signalsFor("levelsio", tEarly);
  assert(sigsEarly.length === 1, `signalsFor(levelsio, 2019-01) returns 1 real signal (got ${sigsEarly.length})`);
  if (sigsEarly.length === 1) {
    assert(sigsEarly[0].cat === "S1", `signal cat dominates S1 build_in_public (got ${sigsEarly[0].cat})`);
    assert(sigsEarly[0].raw.includes("Nomad List"), `signal raw text from API (got "${sigsEarly[0].raw.slice(0,50)}")`);
    assert(sigsEarly[0].platform === "hackernews", `platform passed through (got ${sigsEarly[0].platform})`);
  }
  // At t = 2021, both real signals qualify.
  const tLate = (2021 - 2014) * 12 + 0;
  const sigsLate = src.signalsFor("levelsio", tLate);
  assert(sigsLate.length === 2, `signalsFor(levelsio, 2021-01) returns 2 real signals (got ${sigsLate.length})`);
  // Fallback path: marclou has no per-founder data → falls back to synthetic.
  const sigsMarcLou = src.signalsFor("marclou", tLate);
  assert(sigsMarcLou.length > 0, `signalsFor(marclou) falls back to synthetic (got ${sigsMarcLou.length} signals)`);

  // C.5 partial: egoFor builds a real KG from cached signals when present,
  // falls back to synthetic when not.
  const ego = src.egoFor("levelsio");
  const founderNode = ego.nodes.find((n) => n.kind === "founder");
  assert(founderNode?.label === "Pieter Levels", `egoFor center labels founder name (got ${JSON.stringify(founderNode)})`);
  const sigNodes = ego.nodes.filter((n) => n.kind === "signal");
  assert(sigNodes.length === 2, `egoFor includes 2 signal nodes (one per cached signal; got ${sigNodes.length})`);
  const topicNodes = ego.nodes.filter((n) => n.kind === "topic");
  assert(topicNodes.length === 2, `egoFor extracts 2 distinct topics (12 startups…, Indie hacker movement; got ${topicNodes.length})`);
  const platformNodes = ego.nodes.filter((n) => n.kind === "platform");
  assert(
    platformNodes.length === 2 && platformNodes.some((n) => n.label === "HN") && platformNodes.some((n) => n.label === "X"),
    `egoFor maps platforms hackernews+twitter → HN, X (got ${JSON.stringify(platformNodes.map(n => n.label))})`,
  );
  // Center → each signal edge weighted by overall_signal_strength.
  const fEdges = ego.edges.filter((e) => e.a === "F");
  assert(fEdges.length === 2, `2 founder→signal edges (got ${fEdges.length})`);
  assert(
    fEdges.some((e) => Math.abs(e.w - 0.82) < 0.001) && fEdges.some((e) => Math.abs(e.w - 0.71) < 0.001),
    `edge weights match signal strengths (got ${fEdges.map(e => e.w).join(", ")})`,
  );

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

// -------------------------- Case 4: emergence parser ------------------

console.log("\nCase 4: parseEmergenceQuarter — every shape we see in cohort_verified.md");
{
  // Real raw values pulled from /api/cohort (see STATUS_UPDATES C.2 entry).
  const cases: Array<[string | null, string | null, string]> = [
    [null, null, "null passthrough"],
    ["", null, "empty string → null"],
    ["2020", "2020-Q1", "bare year → Q1"],
    ["2018–2019", "2018-Q1", "year range → lower bound"],
    ["2019–2021", "2019-Q1", "year range → lower bound"],
    ["2023", "2023-Q1", "bare year"],
    ["2019 (exit)", "2019-Q1", "year + (modifier)"],
    ["2020 onward", "2020-Q1", "year + onward"],
    ["2019 → 2025 (1M subs)", "2019-Q1", "year arrow → lower year"],
    ["Apr 2023 (acq.)", "2023-04", "month-year + modifier"],
    ["May 2020", "2020-05", "month-year"],
    ["Nov 2021", "2021-11", "month-year"],
    ["Apr 2025", "2025-04", "month-year"],
    ["Dec 2020 → scale", "2020-12", "month-year + arrow modifier"],
    ["Early 2026", "2026-Q1", "Early → Q1"],
    ["2020-Q3", "2020-Q3", "already-quarter passthrough"],
    ["fish soup", null, "non-parseable → null"],
  ];

  for (const [raw, expected, label] of cases) {
    const got = parseEmergenceQuarter(raw);
    assert(got === expected, `parseEmergenceQuarter(${JSON.stringify(raw)}) === ${JSON.stringify(expected)} — ${label} (got ${JSON.stringify(got)})`);
  }
}

// -------------------------- Summary -----------------------------------

console.log(`\n${passed} passed, ${failed} failed`);
if (failed > 0) {
  process.exit(1);
}
