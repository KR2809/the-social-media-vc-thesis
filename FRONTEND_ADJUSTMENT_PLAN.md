# Frontend Adjustment Plan (2026-06-04)

Goal: make the demo (a) self-explanatory — clear what you're looking at, what it
means, how to use it; (b) actually wired to the real n=139 results, not mock
data; (c) present the knowledge graph so it's easy to follow and understand.

This is a PLAN. Nothing here is implemented yet. Items are ordered by priority
and tagged **[BLOCKER]**, **[HIGH]**, **[MED]**, **[LOW]**.

---

## 0. Current state (verified 2026-06-04) — read this first

The frontend already exists and is fairly complete:

- **3 views:** `View1Replay` (time-travel board + slider), `View2Outcome`
  (precision@k vs baselines), `View3Founder` (founder card + ego-network).
- **KG views:** `KnowledgeGraphView` (cohort graph via `RadialClusterGraph`)
  and per-founder ego-networks via `ForceGraph`.
- **Onboarding:** `OnboardingGuide`, `InfoTip` tooltips, `ViewIntro`/`EpistemeBar`
  primitives already exist.

**Data flow (the important part):**

```
data/processed/*.parquet,*.csv   ← the REAL n=139 results (this run)
        │
        ▼
api/main.py  (FastAPI)  → /api/cohort, /api/portfolio, /api/founder/{id},
        │                  /api/precision-at-k, /api/kg/cohort, /api/kg/ego/{id},
        │                  /api/timeline-bounds, /api/baselines, ...
        ▼
frontend  lib/thesis/real.ts (loadRealSource)  ── on any fetch failure ──▶ synthetic.ts (MOCK)
        ▼
   React views
```

**THE KEY FINDING:** the deployed Vercel app currently shows **synthetic mock
data**, not the real results, because:
1. `lib/thesis/context.tsx` and `index.ts` default the exported source to
   `syntheticSource`. The real source is only used if `loadRealSource()`
   succeeds.
2. `loadRealSource()` fetches from a **live FastAPI server** — which is not
   deployed alongside the static Vercel site, so in production every fetch
   fails and it silently falls back to mock data.
3. **Nothing reads `data/processed/frontend_timeline.json`** — the static,
   cold-loadable contract built in Phase H. It exists but is unused.

So "is everything we just did hooked up?" → **No.** The pipeline outputs are
correct (n=139, ROC-AUC 0.967) but the demo doesn't display them in production.
Fixing this is the plan's #1 priority.

Also stale: `KnowledgeGraphView.tsx` hardcodes "4,235 nodes / 178k edges" — the
real graph is **6,283 nodes / 370k edges**.

---

## 1. [BLOCKER] Wire the real results into production (the static-JSON path)

**Problem.** Production shows mock data; the real n=139 results never load
because they require a live API the static site doesn't have.

**Decision — use the static JSON contract, not a live API in prod.** Phase H
already produces `frontend_timeline.json` (+ a copy in `frontend/public/`). A
static file deployed with the site needs no server, never falls back to mock,
and matches the "cold-load works without a live DB" acceptance criterion in
FRONTEND_SPEC §9.

**Work:**
1. **Extend the static export** (`scripts/export_frontend_timeline.py`) to emit
   ONE bundle that covers every view, not just the replay timeline:
   - `meta` (n, metrics + CIs, KG Δ, run date, git hash, cost) — for headline
     banners and the "what am I looking at" copy.
   - `founders[]` (already there: pickup/emergence/lead/trajectory/top-signals).
   - `precision_at_k[]` by strategy × date (for View2 — from
     `backtest_results.csv`).
   - `baselines` summary (mean precision@5 per strategy).
   - `kg` block: cohort graph nodes/edges (downsampled for the browser) +
     per-founder ego-networks, from `graph.pkl` / `kg_features.parquet`.
   - `monte_carlo[]`, `robustness[]` (optional, for an "at scale" panel).
   Write to `frontend/public/thesis_data.json`.
2. **Add a static data source** `lib/thesis/static.ts` that reads
   `/thesis_data.json` (a plain `fetch` of a bundled public asset — always
   succeeds in prod) and implements the `DataSource` interface.
3. **Change the resolution order** in `lib/thesis/index.ts` /
   `context.tsx`: **static (real) → synthetic (only true offline dev
   fallback)**. Production should never show synthetic.
4. **Acceptance:** deploy to `social-media-vc-thesis.vercel.app`; the app shows
   36 cohort founders, n=139 metrics, ROC-AUC 0.967, real backtest curves — with
   the FastAPI server NOT running.

**Why this over fixing the FastAPI deploy:** the static bundle is smaller, has
zero infra, can't pause-on-idle (the Supabase risk), and is the examiner-proof
"download one file and it works" story. Keep FastAPI for local dev / interactive
stranger-handle scoring later.

---

## 2. [HIGH] Clarity — "what you see, what it means, how to use it"

Goal: a first-time viewer (examiner) understands each screen in <10 seconds
without being told.

**2.1 Persistent legend + plain-language headline on every view.**
- A one-sentence "what this shows" at the top of each view (the `ViewIntro`
  primitive already exists — ensure every view uses it with NON-jargon copy).
- Example (Replay): *"Drag the slider through time. Each founder appears on the
  board on the date the model first flagged them — using only what was knowable
  then. Gold = already emerged; blue = flagged but not yet emerged (the real
  test)."*

**2.2 A consistent visual vocabulary, documented on-screen.**
- Fixed meaning for colour/shape everywhere: positive vs negative, emerged vs
  not-yet, tracked vs watchlist vs pass. One small persistent legend component
  (not per-view reinvention).
- Whatever the marker for "predicted but not yet emerged" is, it must be the
  single most visually prominent state — it's the thesis's whole point.

**2.3 Headline numbers, stated honestly, up front.**
- A top banner / "Results at a glance" card: **ROC-AUC 0.967 [0.913, 0.996],
  n=139, median lead +12 months (8 founders)** — and, honestly, **"framework
  does not beat naive baseline; KG adds nothing (see Methodology)."** Reporting
  the nulls in the UI mirrors the thesis's integrity and pre-empts the obvious
  examiner question.

**2.4 Guided first-run tour.** `OnboardingGuide` exists — script it to walk the
three views in order with one sentence each, skippable, re-openable from a "?"
in the TopBar.

**2.5 "How to read this" affordances.** Keep `InfoTip` but audit every metric
(precision@k, lift, ROC-AUC, lead-time) has a plain-language tooltip — "ROC-AUC
0.97 means: pick a random founder and a random non-founder; the model ranks the
founder higher 97% of the time."

---

## 3. [HIGH] Verify everything is hooked up (acceptance checklist)

A literal checklist to run after §1 lands. Each must show the REAL value, not a
synthetic one.

| Surface | Must show (real n=139) | Source field |
|---|---|---|
| Cohort count | 36 founders | `meta.n_founders` / `founders[]` |
| Eval headline | ROC-AUC 0.967 [0.913,0.996] | `meta.eval` |
| KG delta | −0.002 (stated as "no improvement") | `meta.kg_delta` |
| Replay board | founders appear at real first_pickup_date | `founders[].first_pickup_date` |
| Not-yet-emerged marker | correct per date T | `founders[].trajectory[t].emerged_by_then` |
| Outcome / precision@k | real backtest curves, 5 strategies | `precision_at_k[]` |
| Baselines | signal_volume 0.73 > two_tier 0.50 (honest) | `baselines` |
| Founder card top signals | the real signals seen at pickup | `founders[].top_signals_at_pickup` |
| KG cohort graph | 6,283 nodes / 370k edges (downsampled view) | `kg.cohort` |
| Lead-time hero | +12mo median on 8 founders | `founders[].lead_time_months` |

- **Automated check:** add a tiny Playwright/Cypress (or even a `browse` skill)
  smoke test that loads the deployed URL and asserts the cohort count == 36 and
  the ROC-AUC text == "0.967" — so "is it wired?" is answered by a test, not by
  eyeballing. Wire into the deploy step.
- **Remove the synthetic fallback in prod builds** (or surface a loud "DEMO
  DATA" banner if it ever triggers) so a silent fallback can never masquerade as
  real results again.

---

## 4. [HIGH] Make the Knowledge Graph easy to follow

The KG view is currently abstract (a radial cluster of dots) and shows a stale
node count. Two goals: legibility, and honesty about what the KG does/doesn't do.

**4.1 Fix the stale numbers.** Replace the hardcoded "4,235 nodes / 178k edges"
with the real `kg.meta` (6,283 / 370k), read from the bundle.

**4.2 Make it readable, not a hairball.**
- **Downsample for the browser:** never render 6k nodes. Show Person nodes +
  the top-N shared Topic hubs; expand-on-click for a founder's signals.
- **Default to the ego-network, not the full graph.** Pick a founder → show
  their immediate neighbourhood (founder → top signals → shared topics → other
  founders who share those topics). This is the legible, story-shaped view.
- **Label the node types in-canvas** with the consistent legend (Person /
  Topic / Signal / Platform), each a fixed colour+shape.
- **Show WHY two founders are near each other:** highlight the shared-topic
  path between them on hover ("levelsio and marclou both signal about
  'indie SaaS'"). That makes "shared hubs" concrete.

**4.3 Tell the honest KG story in the UI (ties to the thesis write-up).**
- An `EpistemeBar` / info panel on the KG view: *"This graph connects founders
  through the themes they post about. In this study the graph did not improve
  prediction (Δ −0.002) — because free data gives us each person's posts but
  not who-replies-to-whom. With interaction data (replies, mentions, follows),
  the graph would show network proximity to prior emergence. See thesis §VIII."*
- This converts the visually-underwhelming KG into a teaching moment that
  matches the thesis's future-work argument — the graph's value is *latent*.

**4.4 Optional aspirational panel ("what the graph COULD show").** A small,
clearly-labelled "illustrative, not from data" mock of person-to-person edges +
a proximity-to-emergence highlight — to communicate the future-work vision
without claiming it as a result. Must be unmistakably marked as illustrative.

---

## 5. [MED] / [LOW] polish

- **[MED]** Mobile: the KG and replay board need the responsive treatment the
  components already started (`useElementWidth`); verify on a phone viewport.
- **[MED]** Loading/empty/error states for the static bundle (should be rare
  once static, but a corrupt bundle shouldn't show a blank screen).
- **[LOW]** Remove or gate the `YCOverlapPanel` if YC-overlap data isn't part of
  the canonical run (avoid showing a panel with no real backing).
- **[LOW]** Footer provenance line: git hash + run date + "data: n=139,
  2026-06-04" so every screenshot is self-dating.

---

## 6. Suggested execution order

1. **§1 static-JSON wiring** [BLOCKER] — without this, nothing else shows real data.
2. **§3 verification checklist + smoke test** — prove §1 worked.
3. **§4 KG legibility + honest framing** — your explicit ask #3, and it ties to
   the thesis write-up.
4. **§2 clarity pass** — headlines, legend, tooltips, onboarding.
5. **§5 polish** — mobile, states, footer.
6. **Deploy** to `social-media-vc-thesis.vercel.app` and re-run the smoke test.

Estimated: §1 ~2–3h, §3 ~1h, §4 ~3–4h, §2 ~2–3h, §5 ~2h. ~10–13h total, but §1
+ §3 + §4 (the load-bearing ~6–8h) deliver the examiner-ready demo.

---

## 7. Open decisions for Kris

- [ ] Confirm: static-JSON path for prod (recommended) vs deploying FastAPI too?
- [ ] Confirm: show the honest nulls (framework<baseline, KG Δ≈0) directly in
      the UI? (Recommended — matches the thesis's integrity.)
- [ ] Include the §4.4 aspirational "what the KG could show" panel, or keep the
      demo strictly to real data only?
