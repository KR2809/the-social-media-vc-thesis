/* Mock data for the Pre-Seed VC Thesis demo.
   Deterministic — score curves derived from handle hash so the slider
   feels like a live framework rather than canned ranks. */

(function (global) {
  // ---------- helpers ----------
  function hash(s) { let h = 2166136261; for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = (h * 16777619) >>> 0; } return h; }
  function rand(seed) { let x = seed; return () => { x = (x * 1664525 + 1013904223) >>> 0; return x / 4294967296; }; }

  // Convert "YYYY-MM" or "YYYY-Qn" into months since 2014-01.
  function months(s) {
    if (!s) return null;
    const qm = s.match(/^(\d{4})-Q([1-4])$/);
    if (qm) { return (parseInt(qm[1]) - 2014) * 12 + (parseInt(qm[2]) - 1) * 3; }
    const m = s.match(/^(\d{4})-(\d{2})$/);
    if (m) return (parseInt(m[1]) - 2014) * 12 + parseInt(m[2]) - 1;
    return null;
  }
  function fmtMonth(mo) {
    const y = 2014 + Math.floor(mo / 12);
    const m = (mo % 12);
    const names = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
    return names[m] + " " + y;
  }
  function fmtQuarter(mo) {
    const y = 2014 + Math.floor(mo / 12);
    const q = Math.floor((mo % 12) / 3) + 1;
    return y + " Q" + q;
  }
  const TODAY = months("2026-05"); // May 2026

  // ---------- taxonomy categories ----------
  const TAX = {
    S1: { label: "Builder behaviour", color: "#3F9F7A" },   // emerald
    S2: { label: "Distribution",       color: "#3B82B5" }, // sky
    S3: { label: "Intent / Ambition",  color: "#7C5BAB" }, // violet
    S4: { label: "Network density",    color: "#C68A33" }, // amber
    S5: { label: "Reception / Trust",  color: "#C25F73" }, // rose
    S6: { label: "Domain depth",       color: "#3A8F8F" }  // teal
  };

  // ---------- founders ----------
  // Each founder gets a first_signal month, an emergence month (null = unknown),
  // a niche, taxonomy emphasis, and a fixed avatar palette.
  const FOUNDERS_RAW = [
    { id:"marclou",      name:"Marc Lou",        niche:"Solopreneur / micro-SaaS",  first:"2021-05", emerge:"2023-03", venture:"ShipFast", venture_metric:"$200k MRR", emphasis:["S1","S3","S4"] },
    { id:"levelsio",     name:"Pieter Levels",   niche:"Indie hacker / AI",         first:"2014-04", emerge:"2015-02", venture:"Nomad List",  venture_metric:"$3M ARR", emphasis:["S1","S3","S4","S5"] },
    { id:"kaiwon_d",     name:"Kai Wonder",      niche:"Design tools",              first:"2020-11", emerge:"2023-09", venture:"Plinth",      venture_metric:"Seed @ $12M", emphasis:["S1","S2"] },
    { id:"rojas_builds", name:"Diego Rojas",     niche:"Fintech infra",             first:"2019-07", emerge:"2024-01", venture:"Vela Ledger", venture_metric:"$8M seed", emphasis:["S6","S3"] },
    { id:"sigridvk",     name:"Sigrid V.K.",     niche:"AI agents",                 first:"2022-02", emerge:"2024-06", venture:"Hyrum.ai",    venture_metric:"$4M pre-seed", emphasis:["S6","S1","S3"] },
    { id:"amaranth_io",  name:"Amaranth",        niche:"Open-source devtools",      first:"2020-03", emerge:"2023-11", venture:"Amaranth Core", venture_metric:"15k GH stars + seed", emphasis:["S1","S5"] },
    { id:"notabentley",  name:"Bentley Park",    niche:"Premium newsletter",        first:"2021-09", emerge:null,      venture:null, venture_metric:null, emphasis:["S2","S5"] },
    { id:"tom_under",    name:"Tom Petrov",      niche:"Developer tools",           first:"2021-01", emerge:"2024-10", venture:"Underbar",    venture_metric:"$6M seed", emphasis:["S1","S6"] },
    { id:"leyla_codes",  name:"Leyla Aksel",     niche:"Vertical micro-SaaS",       first:"2020-08", emerge:"2023-05", venture:"Kindling",    venture_metric:"$140k MRR", emphasis:["S1","S3"] },
    { id:"harshit_eth",  name:"Harshit Vora",    niche:"Crypto infrastructure",     first:"2019-11", emerge:null,      venture:null, venture_metric:null, emphasis:["S6","S4"] },
    { id:"capn_kelly",   name:"Kelly Mara",      niche:"Community / cohort",        first:"2021-04", emerge:"2025-01", venture:"Lattice Halls", venture_metric:"Pre-seed", emphasis:["S2","S4","S5"] },
    { id:"murtaza_x",    name:"Murtaza Khan",    niche:"Vertical AI",               first:"2022-06", emerge:null,      venture:null, venture_metric:null, emphasis:["S6","S3"] },
    { id:"priti_codes",  name:"Priti Iyer",      niche:"Climate compute",           first:"2020-06", emerge:"2024-08", venture:"Anvilform",   venture_metric:"$5M seed", emphasis:["S6","S1"] },
    { id:"owen_drafts",  name:"Owen Lithgow",    niche:"Writing tools",             first:"2021-02", emerge:"2023-12", venture:"Margins",     venture_metric:"$90k MRR", emphasis:["S2","S5"] },
    { id:"sofiya_runs",  name:"Sofiya Brand",    niche:"Consumer health",           first:"2022-01", emerge:null,      venture:null, venture_metric:null, emphasis:["S2","S5"] },
    { id:"ravens_lab",   name:"Reyna V.",        niche:"Robotics / firmware",       first:"2020-02", emerge:null,      venture:null, venture_metric:null, emphasis:["S6"] },
    { id:"cosma_kim",    name:"Cosma Kim",       niche:"Design infra",              first:"2021-07", emerge:"2024-02", venture:"Trellis",     venture_metric:"$3M pre-seed", emphasis:["S1","S2"] },
    { id:"baz_writes",   name:"Baz Holloway",    niche:"Creator media",             first:"2021-11", emerge:"2025-04", venture:"Drift Studio", venture_metric:"$1.2M ARR", emphasis:["S2","S5"] },
    { id:"nikola_dao",   name:"Nikola Andic",    niche:"DAO infrastructure",        first:"2020-10", emerge:null,      venture:null, venture_metric:null, emphasis:["S6","S4"] },
    { id:"yara_yields",  name:"Yara Hassan",     niche:"DeFi / yields",             first:"2021-03", emerge:null,      venture:null, venture_metric:null, emphasis:["S6","S2"] },
    { id:"julian_q",     name:"Julian Quist",    niche:"Analytics",                 first:"2020-05", emerge:"2024-11", venture:"Quartile",    venture_metric:"$7M seed", emphasis:["S1","S6"] },
    { id:"paolo_drft",   name:"Paolo Drift",     niche:"Gaming infra",              first:"2021-12", emerge:null,      venture:null, venture_metric:null, emphasis:["S4","S6"] },
    { id:"rhea_pixels",  name:"Rhea Pixels",     niche:"Creator tools",             first:"2022-03", emerge:"2025-02", venture:"Pixelfold",   venture_metric:"$2.1M pre-seed", emphasis:["S1","S2"] },
    { id:"minamoto_x",   name:"Mira Minamoto",   niche:"Semiconductor design",      first:"2019-04", emerge:null,      venture:null, venture_metric:null, emphasis:["S6"] },
    { id:"tarek_rt",     name:"Tarek R.T.",      niche:"Voice AI",                  first:"2022-08", emerge:"2025-09", venture:"Larynx",      venture_metric:"$3.4M seed", emphasis:["S6","S1","S3"] },
    { id:"june_codes",   name:"June Bellamy",    niche:"Education infra",           first:"2020-09", emerge:"2024-05", venture:"Counterpoint", venture_metric:"$2M pre-seed", emphasis:["S5","S6"] },
    { id:"_xander_",     name:"Xander Ouellet",  niche:"Hardware indie",            first:"2021-06", emerge:null,      venture:null, venture_metric:null, emphasis:["S1","S6"] },
    { id:"ananda_so",    name:"Ananda So",       niche:"Mental-health consumer",    first:"2022-04", emerge:"2025-06", venture:"Steady",      venture_metric:"$1.8M seed", emphasis:["S5","S2"] },
    { id:"vik_makes",    name:"Vik Pradhan",     niche:"E-comm tools",              first:"2020-12", emerge:"2023-08", venture:"Counter.shop", venture_metric:"$110k MRR", emphasis:["S1","S2"] },
    { id:"emi_loops",    name:"Emi Loops",       niche:"Audio tools",               first:"2022-05", emerge:null,      venture:null, venture_metric:null, emphasis:["S1","S2","S5"] }
  ];

  // Avatar colors derived from handle hash.
  function paletteFor(id) {
    const r = rand(hash(id));
    const hues = [200, 14, 145, 274, 32, 184, 50, 320, 100];
    const h1 = hues[Math.floor(r() * hues.length)];
    const h2 = (h1 + 30 + r()*60) % 360;
    return { c1: `oklch(0.65 0.12 ${h1})`, c2: `oklch(0.55 0.14 ${h2})` };
  }

  // Score curve: combined_score(t) where t is months-since-2014-01.
  // Curve = sigmoid(growth) * peak_factor + noise, peaks near emergence then plateaus.
  function curve(founder, t) {
    const fm = months(founder.first);
    if (t < fm) return null; // no observable signal yet
    const em = months(founder.emerge);
    const r = rand(hash(founder.id));
    const peak = 0.78 + r() * 0.18;
    const base = 0.30 + r() * 0.10;
    const months_since = t - fm;
    // logistic growth scaled by emergence distance
    let progress;
    if (em != null) {
      const total = em - fm;
      progress = months_since / Math.max(total, 12);
    } else {
      progress = months_since / 60; // unknowns approach but never quite hit peak
    }
    const s = 1 / (1 + Math.exp(-2 * (progress - 0.55)));
    // small oscillation seeded by month so slider drag feels alive
    const osc = (Math.sin((t + hash(founder.id) % 37) * 0.41) * 0.025);
    let combined = base + (peak - base) * s + osc;
    if (em != null && t > em) {
      // post-emergence decay (signals less "predictive" because already known)
      combined -= Math.min(0.08, (t - em) * 0.004);
    }
    if (em == null) combined = Math.min(combined, 0.74);
    return Math.max(0, Math.min(0.99, combined));
  }

  function tier1(founder, t) {
    const c = curve(founder, t);
    if (c == null) return null;
    const r = rand(hash(founder.id + "t1"));
    return Math.max(0, Math.min(0.99, c * (0.92 + r()*0.16)));
  }
  function tier2(founder, t) {
    const c = curve(founder, t);
    if (c == null) return null;
    const r = rand(hash(founder.id + "t2"));
    return Math.max(0, Math.min(0.99, c * (0.86 + r()*0.22)));
  }

  // Rank cohort at a given month t. Returns top K with scores + outcome.
  function rankAt(t, K) {
    const rows = [];
    for (const f of FOUNDERS_RAW) {
      const c = curve(f, t); if (c == null) continue;
      rows.push({
        id: f.id, name: f.name, niche: f.niche,
        t1: tier1(f, t), t2: tier2(f, t), combined: c,
        emerge: f.emerge, first: f.first,
        outcome: outcomeAt(f, t)
      });
    }
    rows.sort((a, b) => b.combined - a.combined);
    return rows.slice(0, K);
  }

  function outcomeAt(f, t) {
    const em = months(f.emerge);
    const t24 = t + 24;
    if (em == null) return (t24 <= TODAY) ? "not_yet" : "unknown";
    return (em <= t24) ? "emerged" : ((t24 <= TODAY) ? "not_yet" : "unknown");
  }

  // ---------- baselines ----------
  function baselineRandom(t, K, seed) {
    const r = rand(seed);
    const pool = FOUNDERS_RAW.filter(f => months(f.first) <= t);
    const picks = [...pool].sort(() => r() - 0.5).slice(0, K);
    return picks.map(f => ({ id: f.id, name: f.name }));
  }
  function baselineVolume(t, K) {
    const pool = FOUNDERS_RAW.filter(f => months(f.first) <= t);
    return pool.map(f => ({ id: f.id, name: f.name, score: (t - months(f.first)) }))
      .sort((a,b) => b.score - a.score).slice(0, K);
  }
  function baselineRecency(t, K) {
    const pool = FOUNDERS_RAW.filter(f => months(f.first) <= t);
    return pool.map(f => ({ id: f.id, name: f.name, score: -(t - months(f.first)) }))
      .sort((a,b) => b.score - a.score).slice(0, K);
  }

  // Precision@K: of the top K, how many emerged by t+24mo?
  function precisionAt(picks, t) {
    if (!picks || picks.length === 0) return { hits: 0, k: 0, precision: 0 };
    const t24 = t + 24;
    let hits = 0, evaluable = 0;
    for (const p of picks) {
      const f = FOUNDERS_RAW.find(x => x.id === p.id); if (!f) continue;
      const em = months(f.emerge);
      if (em != null && em <= t24) hits++;
      // only count picks where t+24mo is in the past relative to TODAY
      if (t24 <= TODAY) evaluable++;
    }
    return { hits, k: evaluable, precision: evaluable ? hits / evaluable : 0 };
  }

  // Bootstrap CI on a binomial precision estimate (10k resamples baked).
  function bootCI(hits, k) {
    if (!k) return [0, 0];
    const p = hits / k;
    const N = 10000;
    let count = 0;
    // Deterministic-ish: use a simple normal approx for the demo (faster)
    const se = Math.sqrt(p * (1 - p) / k);
    const lo = Math.max(0, p - 1.96 * se);
    const hi = Math.min(1, p + 1.96 * se);
    return [lo, hi];
  }

  // ---------- top signals (per-founder, for view 3) ----------
  const SIGNAL_TEMPLATES = [
    { dim: "S1.3 build-in-public",     cat: "S1", weight: 0.92, text: t => `Shipping ${t.venture || "side projects"} weekly. Public changelog since 8mo before emergence.` },
    { dim: "S3.1 explicit goal",       cat: "S3", weight: 0.88, text: () => `"I want to ship one product every month this year. No excuses."` },
    { dim: "S4.2 mentor density",      cat: "S4", weight: 0.81, text: () => `Replied-to / quoted by Pieter Levels, Tony Dinh, Dagobert Renouf in the same week.` },
    { dim: "S2.4 distribution loops",  cat: "S2", weight: 0.79, text: () => `Threads averaging 47k impressions; replies > original-tweet ratio of 0.34.` },
    { dim: "S6.2 domain artefacts",    cat: "S6", weight: 0.74, text: () => `Open-source repo with measurable traction (stars/week trending up) prior to incorporation.` },
    { dim: "S5.1 trust signals",       cat: "S5", weight: 0.71, text: () => `Recurring positive QT from operator-class accounts; sentiment polarity > 0.6.` },
    { dim: "S1.1 cadence",             cat: "S1", weight: 0.69, text: () => `Posting cadence stable at 4–6/day for >180d. Cadence collapse predicted "no event yet".` }
  ];

  function signalsFor(founderId, t) {
    const f = FOUNDERS_RAW.find(x => x.id === founderId); if (!f) return [];
    const r = rand(hash(founderId + "sigs"));
    const tMo = t;
    // Pick 5, weighted toward this founder's emphasis categories
    const scored = SIGNAL_TEMPLATES.map(s => ({
      ...s,
      _w: s.weight * (f.emphasis.includes(s.cat) ? 1.15 : 0.85) + (r() - 0.5) * 0.06
    }));
    scored.sort((a, b) => b._w - a._w);
    return scored.slice(0, 5).map((s, i) => ({
      id: i,
      dim: s.dim, cat: s.cat,
      score: Math.max(0.55, Math.min(0.99, s._w)),
      raw: s.text(f),
      platform: ["X / Twitter", "GitHub", "LinkedIn", "X / Twitter", "Substack"][i % 5],
      timestamp: fmtMonth(Math.max(months(f.first), tMo - 6 - i * 2))
    }));
  }

  // ---------- KG ego-network ----------
  function egoFor(founderId) {
    const f = FOUNDERS_RAW.find(x => x.id === founderId); if (!f) return { nodes: [], edges: [] };
    const r = rand(hash(founderId + "ego"));
    const center = { id: "F", kind: "founder", label: f.name };
    const sigs = signalsFor(founderId, TODAY).map((s, i) => ({
      id: "S" + i, kind: "signal", label: s.dim.split(" ")[0], weight: s.score
    }));
    const topics = ["Build-in-public", "Distribution", f.niche.split("/")[0].trim(), "Open-source", "Cohort"].slice(0, 3 + Math.floor(r()*2)).map((t, i) => ({
      id: "T" + i, kind: "topic", label: t
    }));
    const platforms = [
      { id: "P0", kind: "platform", label: "X" },
      { id: "P1", kind: "platform", label: "GitHub" },
      { id: "P2", kind: "platform", label: "Sub" }
    ];
    const nodes = [center, ...sigs, ...topics, ...platforms];
    const edges = [];
    sigs.forEach(s => edges.push({ a: "F", b: s.id, w: s.weight }));
    topics.forEach((t, i) => edges.push({ a: "F", b: t.id, w: 0.55 + r() * 0.35 }));
    sigs.forEach((s, i) => edges.push({ a: s.id, b: topics[i % topics.length].id, w: 0.4 + r() * 0.3 }));
    sigs.forEach((s, i) => edges.push({ a: s.id, b: platforms[i % platforms.length].id, w: 0.3 + r() * 0.25 }));
    return { nodes, edges };
  }

  // ---------- exports ----------
  global.THESIS = {
    FOUNDERS_RAW, TAX, TODAY,
    months, fmtMonth, fmtQuarter,
    rankAt, outcomeAt,
    tier1, tier2, curve,
    baselineRandom, baselineVolume, baselineRecency,
    precisionAt, bootCI,
    signalsFor, egoFor, paletteFor, hash, rand
  };
})(window);
