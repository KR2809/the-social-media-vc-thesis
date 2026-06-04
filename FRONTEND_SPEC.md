# FRONTEND_SPEC.md — Defence-grade demo (iter-12 lock)

**Status:** design phase. Spec locked 2026-05-14.
**Owner of design:** Kris (with Claude Design as tooling).
**Owner of implementation:** CC (next session, after Kris's mockups land).
**Target hosting:** Vercel free tier.
**Goal:** the 3-minute defence demo + the live URL Tovstiga clicks.

---

## 0. Why this frontend exists

The Streamlit prototype (`dashboard/app.py`) is fine for working-artefact / supervisor-touchpoint purposes. It is **not the defence demo**. The defence is 30% of the grade; a research-notebook aesthetic in a thesis that claims to operationalise a VC framework leaves grade points on the table.

This frontend is the literal instantiation of the thesis's one-sentence claim. Nothing more, nothing less:

> *"A pre-seed allocation framework built entirely from free public social-media signals can identify creator-economy founders before they formally launch, at materially higher rates than naïve baselines, operationalised as a transparent live portfolio with locked prospective predictions."*

If the demo claims more than this sentence (e.g. "we beat a16z by 3x"), the gap between paper and demo hurts the grade. If the demo claims less (e.g. "here are some scored signals in a table"), the QuantumLight-VC framing collapses. The 3 views below operationalise the exact sentence — no more, no less.

---

## 1. Information architecture (3 views + connective tissue)

The defence demo is **3 connected views + a header + a footer**. The user moves between them via a clear horizontal flow (date slider on top, drill-down panel on the right).

### 1.1 Top chrome (persistent across all views)

- **Thesis title + subtitle** ("From Social Signals to Pre-Seed Allocation" / "A Systematic Framework…")
- **Date-T slider** — the load-bearing control. Drags from earliest cohort signal (~2014) to "today". Updates every panel live.
- **Capital + K selectors** — `$1M` (editable) and `K=20` (editable, range 5–50). Set the portfolio sizing knobs.
- **Allocation rule dropdown** — "Two-tier (α=0.5)" / "Tier-2 only" / "Tier-1 only" / "Equal-weight top-K". Shows the alpha knob from `models/allocation_framework/combine.py`.

### 1.2 View 1 — Replay (the "watch the framework decide" view)

**Centre:** ranked list of top-K (person, topic) pairs as of date T. Each row = founder card with:
- Avatar (X profile pic via Wayback fallback when needed)
- Handle + display name
- Tier-1 score · Tier-2 score · combined score
- Dollar allocation (from `analysis/allocation.py` Kelly fraction)
- Outcome chip if T + 24mo has elapsed (✅ emerged / ❌ not yet / ❓ unknown)

**Left rail:** small KG mini-map of the cohort at T. Person nodes light up as they enter the top-K.

**Right rail:** "What just changed" — small audit log of how the slider movement re-ordered the list. Names that entered or exited the top-K with a Δ rank.

**Underneath the list:** small horizon-bar showing T → T+24mo + a "Reveal outcomes" button (only enabled when T+24mo has elapsed).

### 1.3 View 2 — Outcome panel (the "did the framework get it right" view)

Triggered by clicking "Reveal outcomes" on View 1, or by jumping directly from the nav.

**Header card (full width):** the precision@k headline.
- Headline metric: `precision@K = X / K = Y%` for the picked portfolio.
- Bootstrap CI bar (10k resamples via `models/monte_carlo.bootstrap_metric_ci`). Shows `mean [lower_ci, upper_ci]`.
- Honest framing line directly below: "n = 20 (positives) + N negatives. CIs reflect small-sample uncertainty."

**Comparison cards (4 side-by-side, equal width):**
- Two-tier (our framework) — same precision@k + CI bar (this is the headline metric, duplicated for visual comparison)
- Random portfolio — baseline 1
- Signal-volume portfolio — baseline 2
- Recency portfolio — baseline 3
- (Tier-1-only as a 5th if there's space)

Each card: name · precision@k · CI bar · ranked list of top-K it would have picked.

**Optional footer panel:** YC-batch overlap card (if YC W20 / W21 / W22 picks are sourceable from public batch announcements). Compares our top-K at YC-app deadline T against the actual YC batch members. "Of the founders we picked, X were in YC's batch; of YC's batch, Y were in our picks."

### 1.4 View 3 — Founder card (the "why did the framework pick this person" view)

Triggered by clicking any founder row in View 1 or View 2.

**Hero panel:** profile photo · handle · niche · emergence quarter · current outcome status.

**Three side-by-side sub-panels:**

1. **KG ego-network.** D3 or react-flow rendering of this founder's 1-hop graph (signals → topics → platforms). Edge thickness = co-occurrence weight. Node colours by kind. Hover = signal preview.
2. **Top 5 signals at time T.** What the model literally saw. Each signal: raw_text + platform + timestamp + the 4–5 highest-scoring taxonomy dimensions. Visual emphasis on the load-bearing signals (S1.3 build-in-public, S3.1 explicit goal, S3.5 recruitment).
3. **Outcome timeline.** From "first signal observed" to "emergence event" (if emerged) or "no event yet" (if not). Horizontal timeline with annotated milestones.

**Bottom strip:** "framework's read at T" — one-paragraph narrative auto-generated from the top signals. Example: *"At Q1 2022, Marc Lou had been posting 'I want to ship one product every month this year' (S3.1 explicit goal, score 0.9) for 8 months and engaging consistently with Pieter Levels (S4.2 mentor density). The framework's KG-augmented prediction was P(emerge) = 0.81. ShipFast launched 14 months later at $200k MRR."*

### 1.5 Out-of-scope for the defence demo (do not build)

- ❌ Stranger-handle live-scoring (cohort replay + self-case only)
- ❌ Fund-returns P&L curves, IRR numbers
- ❌ "vs a16z / Sequoia" comparisons (only 4 in-framework baselines + YC if sourceable)
- ❌ User authentication / multi-tenant features
- ❌ Editable cohort (the cohort is read-only at the file level)
- ❌ Real-time ingestion (the demo replays from already-scored parquet)

---

## 2. Design principles

These are the load-bearing constraints. Anything that conflicts with them gets cut.

### 2.1 Trust signals come from rigor, not chrome

The demo should *feel* like a VC's internal tool. That means:
- Dense information layouts (closer to Bloomberg / Pitchbook / Affinity than to consumer SaaS)
- Honest uncertainty (CI bars wherever there's a point estimate; "n = X" annotations on every metric)
- Auditable traces (every score is clickable to "see the raw signals that produced this")
- Monospace for IDs and numerical metrics; serif for prose; sans for UI chrome

### 2.2 Reading order is left → right, top → bottom

The defence committee should be able to grok the demo with no narration. Top-left = date slider (the input). Centre = ranked list (the output). Right = drill-down (the why). Bottom = outcome metrics (the proof).

### 2.3 Every claim cites its source

If a metric is shown, its parquet/csv file is named in a footnote on hover. Example: hovering over precision@k shows "source: data/processed/backtest_results.csv, row(strategy=two_tier, k=20, T=2022-01-01)".

### 2.4 Honest about what the framework can't do

Each view has a small, persistent "epistemic status" caption:
- View 1 (Replay): "Framework picks based on signals observable at date T only. Lookahead-bias guard active."
- View 2 (Outcome): "Precision@k with bootstrap CIs. Not a returns claim. n = X, see §1.1 of `PROGRESS.md`."
- View 3 (Founder card): "Outcome timeline reconstructed from public signals. Outcomes per §4.1 emergence composite."

### 2.5 Visual style

To be locked by Kris + Claude Design. Recommendations:
- **Palette:** EDHEC blue (`#1F4E79`) as primary accent. Off-white background. Dark slate text. Minimal use of greens / reds — reserve them for ✅ emerged / ❌ not-yet outcome chips.
- **Typography:** serif for titles + body prose (Lora, Source Serif, or Georgia fallback); sans for UI chrome (Inter); monospace for IDs / numbers (JetBrains Mono).
- **Density:** higher than typical SaaS. ~14px base. Tight line-heights. This is a tool, not a marketing page.
- **No animations except:** slider drag → ranked list re-order (lerp ~150ms), reveal-outcomes flip (~300ms), KG ego-network entrance (~400ms).

---

## 3. Data flow (how the frontend connects to the existing repo)

The Next.js app reads the same processed data the model code produces. No model re-training in the browser. Per **DECISION_LOG iter-13**, storage is hybrid (Option C): parquet/csv files are the source of truth; GitHub Releases hold versioned snapshots for citability; Supabase Postgres mirrors the rows for the live demo.

```
pipeline.py all                    (existing — produces all parquet/csv in data/processed/)
  ↓
  ├──> scripts/publish_data_snapshot.py (F1.5)
  │       └──> GitHub Release artifact (data_snapshot_YYYY-MM-DD.tar.gz)
  │
  └──> scripts/sync_to_supabase.py (F1.5, idempotent)
          └──> Supabase Postgres (free tier, 500 MB)
                ↓
FastAPI thin layer (api/, F1)      (--source local OR --source supabase)
  ↓
Next.js frontend (web/, F2-F8)     (deployed to Vercel; in prod reads via FastAPI → Supabase)
```

**Local development:** FastAPI runs with `--source local`; reads from `data/processed/*.parquet` directly via pyarrow. No Supabase dependency for dev work.

**Production:** FastAPI runs with `--source supabase`; reads from the mirrored tables. Local parquet is the upstream — `sync_to_supabase.py` is run on demand whenever the pipeline produces new outputs.

**The thesis appendix cites three reproducibility paths:**
1. `gh release download v1.0-thesis-submission` → tar.gz of the data snapshot
2. Live Supabase project URL (read-only credentials in the appendix)
3. `git clone + uv sync + pipeline.py all` (full local reproduction from raw)

### 3.1 FastAPI endpoints to build (small, focused)

| Endpoint | Returns | Source file |
|---|---|---|
| `GET /api/portfolio?date=T&k=20&alpha=0.5` | Top-K picks at date T with scores | `models/allocation_framework/combine.py` `combined_ranking(T, …)` |
| `GET /api/baselines?date=T&k=20` | Baseline portfolios (random / volume / recency / Tier-1) | `models/allocation_framework/backtest.py` `_baseline_*` helpers |
| `GET /api/precision-at-k?date=T&k=20` | precision@k + bootstrap CI for our two-tier ranking | `models/monte_carlo.bootstrap_metric_ci` over backtest output |
| `GET /api/founder/{person_id}?date=T` | Founder card data: feature row, KG ego-network, top-5 signals at T, outcome timeline | combines `data/processed/{person_features,kg_features,scored_signals}.parquet` + `04_RETROSPECTIVE_CASES/cohort_verified.md` |
| `GET /api/cohort` | List of cohort person_ids + display names + niches | `ingestion/cohort.py` `load_cohort()` |
| `GET /api/timeline-bounds` | Earliest + latest valid date T | derived from `data/interim/signal_events.parquet` |
| `GET /api/locked-predictions` | The May-31 locked predictions JSON, read-only | `04_RETROSPECTIVE_CASES/prospective_predictions_2026-05-31.json` |

Each endpoint is thin — it calls one or two existing functions, marshals the result, and returns JSON. No new business logic in the API layer. Total estimated work: ~3-4 hours.

### 3.2 Frontend data model (TypeScript)

```ts
type PortfolioPick = {
  rank: number;
  person_id: string;
  display_name: string;
  niche: string;
  topic: string;
  tier1_score: number;
  tier2_score: number;
  combined_score: number;
  pair_strength: number;
  n_signals: number;
  dollar_allocation: number;
  outcome_at_horizon: "emerged" | "not_yet" | "unknown" | null;
};

type PrecisionAtK = {
  date: string;
  k: number;
  precision: number;
  ci_lower: number;
  ci_upper: number;
  n_iter: number;
};

type FounderCard = {
  person_id: string;
  display_name: string;
  niche: string;
  emergence_quarter: string | null;
  feature_row: Record<string, number>;
  kg_features: Record<string, number>;
  ego_network: { nodes: Node[]; edges: Edge[] };
  top_signals_at_t: Signal[];
  outcome_timeline: TimelineEvent[];
  framework_narrative: string;  // generated server-side from the top signals
};
```

---

## 4. Build phases

| Phase | Deliverable | Owner | Estimate |
|---|---|---|---|
| F0 | Design mockups (Figma / Claude Design) — all 3 views + chrome + states | Kris | 1–2 sessions |
| F1 | FastAPI layer (`api/`) with the 7 endpoints above, reading from local parquet (`--source local`). Mocked rows where data is empty (e.g. scored signals before API key) | CC | 3–4h |
| **F1.5** | **Storage migration to Option C (iter-13)** — `scripts/publish_data_snapshot.py` + `scripts/sync_to_supabase.py` + Supabase project setup + schema design + verification script. FastAPI gains `--source supabase` flag | CC | 6–8h |
| F2 | Next.js scaffold + Tailwind + shadcn/ui + dark/light tokens + top chrome (slider + selectors) | CC | 2–3h |
| F3 | View 1 — Replay (ranked list + slider re-order animation + outcome chips) | CC | 3–4h |
| F4 | View 2 — Outcome panel (precision@k headline + 4 baseline comparison cards + CI bars) | CC | 3–4h |
| F5 | View 3 — Founder card (KG ego-network via react-flow + top-5 signals + outcome timeline + framework-narrative paragraph) | CC | 4–5h |
| F6 | Wire frontend to FastAPI (replace mocks with real fetches); add loading / error states. Production build points at Supabase | CC | 2h |
| F7 | Vercel deploy (`social-media-vc-thesis.vercel.app`, renamed from `thesis-demo` 2026-06-04) + analytics | CC | 1h |
| F8 | Polish pass: typography, microcopy, accessibility, mobile fallback | CC + Kris | 2–3h |
| **F9** | **Supabase keepalive cron** (the "last last" element per iter-13). Hourly Vercel cron or GitHub Actions ping to prevent pause-on-idle. ONLY built after F7 deploy + F8 verification | CC | 1h |

Total: ~27–34 hours of CC time + Kris's design time. F1, F1.5, F2 can run in parallel (different surfaces). Compressible to ~15h if View 3's KG drill-down is deferred to a polish session.

---

## 5. Acceptance criteria (what "defence-ready" means)

The frontend is defence-ready when **all** of the following are true:

1. ✅ Dragging the date slider re-ranks the top-K portfolio in under 200ms.
2. ✅ The Outcome panel shows precision@k with a real bootstrap CI bar from `models/monte_carlo.bootstrap_metric_ci` on the live backtest data.
3. ✅ Four baseline portfolios render alongside the two-tier portfolio with identical precision@k computation.
4. ✅ Clicking any founder opens View 3 with their ego-network rendered, top-5 signals shown, and an outcome-timeline visualisation.
5. ✅ The framework-narrative paragraph on View 3 is generated server-side from the actual signals, not hardcoded.
6. ✅ The "as of date T" epistemic-status caption is visible on every view.
7. ✅ The site loads to a meaningful default state (T = 2024-01-01) without user input.
8. ✅ Mobile responsive at least to the level of "viewable on iPad" (the defence committee may project it).
9. ✅ Lighthouse score ≥ 90 on performance + accessibility (it's a research demo, not a SaaS — both should pass).
10. ✅ No claim anywhere in the UI exceeds what's claimed in §1 of `PROGRESS.md`.

---

## 6. Risks and mitigations

| Risk | Likelihood | Mitigation |
|---|---|---|
| KG ego-network renders too dense / unreadable for cohort founders with many signals | High | Limit ego-network to 1-hop with top-10 strongest edges. "Expand" button for full graph. |
| Bootstrap CIs take too long to compute in real time | Medium | Pre-compute bootstrap traces at common (T, K) values; cache to a separate parquet; API hits the cache. |
| Slider drag re-orders feel laggy | Medium | Debounce slider input to 100ms. Pre-compute top-K at a grid of dates; interpolate between grid points client-side. |
| YC-batch overlap data turns out unsourceable / messy | Medium | Drop YC card; keep 4 in-framework baselines. Not a blocker. |
| The 3 views start scope-creeping (e.g. "add a search bar" / "let users save portfolios") | High | This spec is the freeze. Any new feature request goes into a "vNext" file, not built before defence. |
| Streamlit prototype drift: changes there don't reach the Next.js app | Low | Both read the same parquet/csv. The FastAPI layer is the single seam; tests in `tests/test_api/` (NEW) assert endpoint correctness. |
| Supabase free-tier project pauses after 7 days idle; first request post-pause = ~30s wake-up | Medium | F9 keepalive cron deferred to post-deployment per iter-13. Defence-day mitigation: manually warm up project 24h before defence regardless of cron status. |
| Parquet → Postgres schema drift in F1.5 mirror | Medium | One-time careful schema design + verification script that asserts `row_count(parquet) == row_count(supabase)` after every sync. CI test runs the sync against a small fixture. |
| Live Supabase contains stale data because nobody re-ran `sync_to_supabase.py` after a pipeline re-run | High | Pipeline.py final stage calls the sync script (opt-in flag `--push-to-supabase`). Snapshot publisher tags both the GitHub release and the Supabase project with the same version string for cross-check. |
| Supabase free-tier hits the 500MB Postgres limit | Very Low | Projected total is 30-70MB. Even with 10x growth we have headroom. If we ever approach the limit, drop the raw_response text column (largest by far) — it's audit-only, not used downstream. |

---

## 7. What this spec is NOT

- Not a marketing site. No hero section with a gradient. No testimonials. No "Get started" CTA.
- Not a SaaS. No accounts, no billing, no multi-tenant. One-and-done static-ish deploy.
- Not a Streamlit port. The information architecture is fundamentally different (3 connected views, not 8 loose pages).
- Not the academic paper. The frontend operationalises the paper's claim; it does not replace or extend it.

---

## 8. Next actions

1. **Kris:** create Figma / Claude Design mockups for all 3 views + chrome states. Hand back to CC.
2. **CC (next session, blocked on F0):** build F1 (FastAPI) and F2 (Next.js scaffold). Mock outputs first so F3-F5 can proceed in parallel with the real data pipeline.
3. **Both:** verify the spec still holds as the design lands. Any change → new iteration in `DECISION_LOG.md`.

---

## 9. Static time-travel contract — `frontend_timeline.json` (iter-15, 2026-06-04)

The Replay view can cold-load a single static JSON instead of the live API, so
the demo works from the public repo with no DB. Generated by
`scripts/export_frontend_timeline.py` from `first_pickup_dates.csv` +
`timeline_snapshots.parquet` (themselves produced by
`analysis/discovery_timeline.py`). Written to `data/processed/frontend_timeline.json`
and copied to `frontend/public/frontend_timeline.json`.

### Shape

```jsonc
{
  "meta": {
    "generated_at": "2026-06-04T12:00:00",
    "git_commit": "<hash>",
    "grid_start": "2018-01-01",      // first slider stop
    "grid_end":   "2026-06-01",      // last slider stop (today)
    "tracked_threshold": 0.1234,     // score >= this => "tracked" verdict
    "n_founders": 36,
    "n_dates": 102
  },
  "dates": ["2018-01-01", "2018-02-01", ...],   // monthly grid = slider stops
  "founders": [
    {
      "person_id": "marclou",
      "first_pickup_date": "2023-09-01",   // null if never picked up
      "emergence_date":   "2023-09-01",    // null for negatives / undated
      "lead_time_months": 0,                // emergence - first_pickup; can be <0
      "peak_score": 0.83,
      "is_positive": true,                  // cohort founder vs negative
      "trajectory": [                       // one entry per grid date
        {"date": "2023-08-01", "score": 0.07, "verdict": "pass",     "emerged_by_then": false},
        {"date": "2023-09-01", "score": 0.41, "verdict": "tracked",  "emerged_by_then": true},
        ...
      ],
      "top_signals_at_pickup": [            // <=5, for the Founder card
        {"signal_id": "hn_123", "platform": "hackernews",
         "timestamp": "2023-08-15", "strength": 0.9, "text": "Show HN: ShipFast ..."}
      ]
    }
  ]
}
```

### Replay-view behaviour driven by this file

- **Slider** iterates `dates`. At date T, a founder is **on the board** iff
  `first_pickup_date != null && first_pickup_date <= T`; otherwise off-board.
- **Not-yet-emerged marker**: for an on-board founder at T, read their
  `trajectory` entry for T — `emerged_by_then == false` ⇒ show the "predicted,
  not yet emerged" badge (the real test of pre-emergence prediction).
- **Outcome panel** at T + `lead_time_months` shows the emergence event.
- **Founder card** shows `top_signals_at_pickup` — what the model "saw" at the
  moment it first flagged them.
- **Lookahead-safe by construction**: every `trajectory[t].score` was computed
  using only signals with timestamp ≤ t (enforced in `discovery_timeline.py`,
  asserted by `tests/test_discovery_timeline.py`).

If full API wiring is deferred, this static file + the existing
`View1Replay.tsx` is sufficient for a working Replay prototype.
