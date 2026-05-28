# PROGRESS.md — Build status for Cowork

**Last updated:** 2026-05-27
**Branch:** `feature/auto-discovery` (active development; merge target = `main`); PR #6 raw-archive merged 2026-05-27
**Tests:** 245 pass + 3 pre-existing API failures on baseline · **Ruff:** clean · **Cost incurred:** $5.45 / $30 monthly cap

This file is the single source of truth Cowork should consult to understand what
has been built, what remains, and what's blocked. For decision rationale see
`~/Documents/Claude/Projects/Thesis/00_PLANNING/DECISION_LOG.md` (iter-11 added
2026-05-14). For session-by-session journaling see `STATUS_UPDATES.md`.

---

## TL;DR

The full Phase 2 → Phase 5 chain is **built, tested, and wired into a single
CLI**. Real data flows through clean → person-features → KG → KG-features →
topic-momentum end-to-end. The LLM scoring layer and the eval/backtest/lock
layers are inert pending two external inputs:

1. `ANTHROPIC_API_KEY` in `.env` (unblocks Claude Haiku 4.5 scoring).
2. Negative-peer registrations via `ingestion/negative_peers.py` (unblocks
   the eval + backtest + allocation layers — model layer refuses to train on
   single-class data by design).

Everything else — Monte Carlo, two-tier framework, May-31 lock harness,
self-case, auto-topic discovery, dashboard — is functional now.

---

## 1. Thesis identity (current locks)

### 1.1 The one-sentence thesis (iter-12, 2026-05-14)

> *"A pre-seed allocation framework built entirely from free public social-media signals can identify creator-economy founders before they formally launch, at materially higher rates than naïve baselines, operationalised as a transparent live portfolio with locked prospective predictions."*

This sentence is the load-bearing claim — it goes on the cover page, in the abstract, in the Tovstiga email, in the dashboard header. Everything in this repo flows from it.

**Critically, what this thesis does NOT claim:**

- ❌ "Beats Sequoia / a16z / YC on returns" — real VC pick data is private, action spaces don't match, introduces a returns claim we cannot defend.
- ❌ "$X capital becomes $Y" — no IRR claim, no exit-value data.
- ❌ "Excess returns" — not a returns claim. A *prediction* claim that we *operationalise* as portfolio selection.

**What it DOES claim, and how we prove it:**

| Claim | Evidence |
|---|---|
| Public social-media signals carry predictive info about who becomes a founder | LLM-scored signals → KG-augmented logistic model → ROC + PR-AUC with bootstrap CIs |
| The framework captures that info at materially higher rates than naïve baselines | Portfolio precision@k at retrospective dates vs 4 in-framework baselines (random / signal-volume / recency / Tier-1-only) + YC-batch overlap (if sourceable) |
| The framework is testable, transparent, replicable from free public data | Public GitHub repo + locked v1.0 tag + live dashboard + zero-cost data stack |
| Operationalised as an auditable paper portfolio | 3-view frontend (Replay / Outcome / Founder card) + May-31 locked predictions JSON with SHA-256 + git commit hash |

### 1.2 Locked elements

| Element | Value | Source |
|---|---|---|
| Title | *From Social Signals to Pre-Seed Allocation: A Systematic Framework for Data-Driven Venture Capital Inspired by QuantumLight Capital* | DECISION_LOG iter-11 (2026-05-14) |
| Central RQ | *Does a two-tier framework built exclusively on free public social-media signals identify creator-economy founders at materially higher rates than naïve baselines over a retrospective replay, with rates measured as precision@k at the §4.1 emergence horizon?* | DECISION_LOG iter-12 |
| Empirical claim | Portfolio-level precision@k with bootstrap CIs vs 4 baselines | iter-12 |
| Cohort | 20 positive founders, named (`cohort_verified.md`) + project-level anonymous negatives (`ingestion/negative_peers.py`, registry currently empty) | iter-6 |
| "Social media" scope | Creator-platform digital exhaust: X (Wayback), YouTube, Reddit, HN, Product Hunt, Google Trends. Explicitly NOT LinkedIn / press releases / company filings | iter-12 |
| Self-case | Kris using the framework on his own X handle (`@kristian_ratkov`) | iter-11 |
| Outcome composite | §4.1 of `COMPREHENSIVE_PLAN.md` (≥10k followers/sub OR ≥$5k MRR / ≥$60k ARR OR funding/acq/top-100, within 24mo of first signal) | iter-2 |
| Default LLM | Claude Haiku 4.5 (cheap); Sonnet 4.6 for taxonomy refinement only | CLAUDE.md §3.3 |
| Budget cap | $30/month | CLAUDE.md §3.4 |
| Prediction lock date | **2026-05-31 (sacred)** — reframed as a "live portfolio" publication, re-evaluated at +12mo / +24mo | Move A (iter-5), reframed iter-12 |
| Submission | 2026-06-30; defence 2026-07-18 | EDHEC |
| Demo | 3-view frontend (Replay / Outcome / Founder card) — see [`FRONTEND_SPEC.md`](FRONTEND_SPEC.md) | iter-12 |

---

## 2. Code architecture — every module, what it does, what it needs

### 2.1 `ingestion/` — Data collection

| Module | Purpose | Status | Needs |
|---|---|---|---|
| `schema.py` | Frozen Pydantic `SignalEvent` shape + parquet round-trip | ✅ shipped | — |
| `cohort.py` | Parses `cohort_verified.md` → 20 `CohortMember` objects | ✅ shipped | — |
| `twitter_collect.py` | Wayback CDX fallback (snscrape dead since 2023) | ✅ shipped | per-founder Wayback density investigation |
| `youtube_collect.py` | YouTube Data API, quota-cheap pagination | ✅ shipped | per-founder channel IDs (override file) |
| `reddit_collect.py` | PRAW + client-side date filter | ✅ shipped | `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`, `REDDIT_USERNAME` |
| `hackernews_collect.py` | Firebase API, concurrent fetch | ✅ shipped | — (free, no auth) |
| `producthunt_collect.py` | GraphQL queries | ✅ shipped | `PRODUCTHUNT_DEV_TOKEN` |
| `trends_collect.py` | pytrends weekly time-series | ✅ shipped | — |
| `sweep.py` | Cohort-wide orchestrator (parallel platforms) | ✅ shipped | — |
| `clean.py` | Concatenates raw parquets → `signal_events.parquet` (601 rows on real data) | ✅ shipped | — |
| `negative_peers.py` | Anonymous project-level negative registry + materialiser | ✅ shipped | **Kris hand-picks matched negatives** |
| `raw_archive.py` | Verbatim HTTP-payload archive: SHA-256-addressed gz files + parquet index. Every collector calls `persist()` once per fetch. Powers the thesis reproducibility appendix via `scripts/raw_archive_report.py`. | ✅ shipped (PR #6, merged 2026-05-27) | — |
| `config.py` | Three knobs for the raw-archive subsystem (`RAW_ARCHIVE_DIR`, `RAW_ARCHIVE_ENABLED`, `RAW_ARCHIVE_MAX_BYTES`). | ✅ shipped | — |

### 2.2 `scoring/` — LLM signal scoring

| Module | Purpose | Status | Needs |
|---|---|---|---|
| `score_signals.py` | Per-signal Claude Haiku 4.5 driver. Idempotent re-runs, $30/mo budget guard, flush-every-25 for crash safety, JSON-only response parsing | ✅ shipped, 8 tests | `ANTHROPIC_API_KEY` |

**Scoring prompt:** `prompts/v1/signal_scoring.md` encodes the S1–S6 taxonomy
from `signal_taxonomy_v1.md` as a strict-JSON contract (25 sub-signal scores
per signal + topic label + flags).

**Expected cost on first real run:** 601 signals × ~$0.0025 = ~$1.50.

### 2.3 `analysis/` — Per-person analytics + framework extensions

| Module | Purpose | Status | Needs |
|---|---|---|---|
| `person_features.py` | Per-person flat rollups (cadence, platform diversity, S1–S4 means, BIP/goal/recruitment counts) | ✅ shipped | scored signals |
| `build_graph.py` | NetworkX MultiDiGraph (Person/SignalEvent/Topic/Platform + EXPRESSED/ABOUT/ON_PLATFORM/CO_OCCURS_WITH). Writes GraphML for Gephi + pickle for fast reload | ✅ shipped, 4 tests | scored signals |
| `kg_features.py` | Per-person degree centrality, clustering coeff, topic-diversity entropy, BIP-triad count, mean signal strength | ✅ shipped, 3 tests | graph |
| `topic_momentum.py` | 4w/12w OLS slopes + delta + acceleration on the trends parquet. Smoke-tested on real "indie hacker" data | ✅ shipped, 6 tests | trends parquet |
| `topic_discovery.py` | **Auto-topic discovery** (iter-11). Hybrid: Pass A clusters cohort `s6_topic_label` weighted by strength × recency; Pass B pulls pytrends `related_queries` for forward-looking candidates. Merged ranked output. | ✅ shipped, 6 tests | scored signals |
| `cohort_balance.py` | Markdown table of signal counts per founder × platform | ✅ shipped | clean parquet |
| `allocation.py` | Fractional Kelly allocation (default 1/4-Kelly @ 30x payoff, 10% per-person cap) | ✅ shipped, 6 tests | model probabilities |
| `seed_labels.py` | Writes 20 cohort positives → `outcome_labels.csv` | ✅ shipped, 2 tests | — |
| `lock_predictions.py` | **May-31 lock harness**. Loads locked KG-aug model, predicts P(emerge) for prospective cohort, writes JSON + SHA-256 + git commit hash for audit | ✅ shipped, 5 tests | trained model + prospective handles |
| `self_case.py` | **Self-case** (iter-11). `register_self_case()` adds Kris to labels with `emerged=-1` (excluded from training); `self_case_view()` pulls features + prediction + cohort percentile for the dashboard | ✅ shipped, 5 tests | feature row for `@kristian_ratkov` |

### 2.4 `models/` — Predictive layer

| Module | Purpose | Status | Needs |
|---|---|---|---|
| `baselines/baseline_model.py` | Logistic regression (Arroyo-style flat features). `class_weight=balanced`. Refuses single-class fit. Filters `emerged ∉ {0,1}` (so self-case row at `-1` is excluded from training) | ✅ shipped, 3 tests | labels with ≥1 neg + ≥1 pos |
| `kg_augmented/kg_model.py` | Same pipeline + KG features. Drops duplicate cols on merge | ✅ shipped, 1 test | KG features |
| `evaluation/eval.py` | LOO CV (n≤30) or 5-fold stratified. ROC + PR AUC, F1, precision@k, lift@k, Brier. `evaluate_with_ci()` attaches 95% bootstrap CIs via `models/monte_carlo.bootstrap_metric_ci` | ✅ shipped, 3 tests | both models trained |
| `monte_carlo.py` | **Monte Carlo simulation**, full cc_prompt spec: `bootstrap_metric_ci`, `simulate_founder_emergence`, `simulate_topic_trajectory` (mainstream/niche/faded), `simulate_portfolio` (Gaussian-copula correlated Bernoullis). Every function carries the "framework demonstration" epistemic claim in its docstring | ✅ shipped, 25 tests | — |
| `allocation_framework/combine.py` | **Two-tier framework** (iter-4). Combines Tier-1 topic momentum + Tier-2 founder emergence into ranked (person, topic) pairs with the `alpha` knob. Lookahead-bias filter on both tiers | ✅ shipped, 4 tests | scored signals + trends |
| `allocation_framework/backtest.py` | **Phase 4 backtest**. Applies the framework at retrospective dates against three baselines (random / signal_volume / recency). Writes CSV + markdown report | ✅ shipped, 2 tests | labels + scored signals |

### 2.4b `ranking/` — Per-handle Σ scoring + verdicts (iter-14, 2026-05-26, on `feature/auto-discovery`)

| Module | Purpose | Status | Needs |
|---|---|---|---|
| `rank_handles.py` | Per-handle Σ = 0.4·T1 + 0.6·T2 (T1 = mean of numeric `s6_*`, T2 = mean of `s1_..s4_`). 5/95 pct bootstrap CI over per-signal contribution vector. Emits `{tracked, watchlist, pass}` verdict with optional Haiku rationale. CLI: `--cohort-only / --handles / --input-file / --collect`. Output → `data/processed/handle_verdicts.parquet` | ✅ shipped, 15 tests (1 skipped pending B2.b) | thresholds re-derived after B2.b lands |
| `config.py` | Σ thresholds (TRACKED=0.15, WATCHLIST=0.085 — placeholders derived from cohort quantiles; `TODO(B2.b)` block specifies re-derivation formula) | ✅ shipped | B2.b negatives |
| `prompts/v1/verdict_rationale.md` | Haiku rationale template (best-effort, gated by $25 cost ceiling) | ✅ shipped | — |

### 2.4c `discovery/` — Forward-looking topic + candidate discovery (iter-14, 2026-05-26, on `feature/auto-discovery`)

| Module | Purpose | Status | Needs |
|---|---|---|---|
| `topic_discovery.py` | Wraps `analysis.topic_discovery` Pass-A seeds with Haiku-driven clustering (5–15 thematic groups), then harvests candidate handles from Reddit public JSON + HN Algolia (no auth). Aggregates with cross-platform bonus: `strength = n_appearances × (1 + 0.5·(n_platforms - 1))`. Offline fallback returns single cluster | ✅ shipped, 13 tests | — |
| `prompts/v1/cluster_topics.md` | Cluster-naming prompt | ✅ shipped | — |

### 2.4d `api/main.py` — FastAPI surface (extended iter-14)

| Endpoint | Purpose | Status |
|---|---|---|
| `GET /api/rank/{handle}` | 200 hot-path; 404 cold-path unless `RANK_API_ALLOW_COLLECT=1`; 202+job_id over 30s budget | ✅ shipped |
| `POST /api/rank/batch` | Batch handle ranking | ✅ shipped |
| `GET /api/rank/jobs/{job_id}` | Async job status (1h TTL in-memory `JOBS` dict) | ✅ shipped |
| `GET /api/discover/topics` | Read-only over cached parquet | ✅ shipped |
| `GET /api/discover/candidates/{cluster_id}` | Read-only over cached CSV | ✅ shipped |

**Frontend wiring (Stream D):** the discovery → rank UX (buttons calling `POST /api/rank/batch` with `GET /api/discover/candidates/{cluster_id}` payloads) is **not yet wired**.

### 2.5 `pipeline.py` — End-to-end CLI

```
python pipeline.py all                  # full chain
python pipeline.py clean person graph   # specific stages
python pipeline.py --help               # options
```

Stage order (idempotent, partial-runnable):

```
clean → score → person → graph → kg-features → topic
  → discover-topics → seed-labels → eval → allocate → backtest
```

### 2.6 `dashboard/app.py` — Streamlit prototype (8 pages, kept as a working artefact)

The Streamlit dashboard is now positioned as the **working prototype + supervisor-touchpoint demo (Tovstiga email, Fri May 16)**. It is NOT the defence demo. The defence demo is the 3-view Next.js app specified in [`FRONTEND_SPEC.md`](FRONTEND_SPEC.md) (iter-12, 2026-05-14).

| Page | Surfaces | Status |
|---|---|---|
| Thesis claim | Locked one-sentence thesis + RQ + five differentiators + lit comparison | ✅ live |
| Methodology | 4-phase columns + outcome composite + data sources | ✅ live |
| Cohort status | 20-founder table + per-platform balance | ✅ live (data via `dashboard/data/cohort_status.json`) |
| Results | `eval_metrics.csv` + `allocation.csv` with Δ AUC headline | ✅ wired, populates after `pipeline.py eval allocate` |
| Backtest | `backtest_results.csv` pivot (precision@k × strategy × date) + lift table | ✅ wired |
| Simulation | 3 tabs — founder emergence + portfolio + topic trajectory — all interactive, all wired to `models/monte_carlo` | ✅ live |
| Self-case | Features + KG features + P(emerge) + cohort percentile for `@kristian_ratkov` | ✅ wired |
| Roadmap | Gantt timeline from `dashboard/data/roadmap.json` + next-milestone metric | ✅ live |

Deployable to Streamlit Community Cloud free-tier from the public repo.
README has deploy instructions.

### 2.7 Defence-grade frontend — 3 views (iter-12, design phase)

**The defence demo is not a Streamlit dashboard.** It is a polished Next.js + Tailwind app reading the same parquet/csv outputs the Streamlit prototype reads, with three connected views:

1. **Replay mode** — slider for date T. Capital $1M. K = 20. Drag the slider; the framework re-ranks in real time. Show "as of this date, the framework picked: …". Highlight which picks had *not yet emerged* at T (the real test of pre-emergence prediction).
2. **Outcome panel** — at T + 24mo, mark each picked founder ✅ emerged / ❌ not-yet / ❓ unknown. Headline metric = precision@k with bootstrap CI bar underneath. Four baseline-portfolio cards (random / signal-volume / recency / Tier-1-only) shown side-by-side for comparison.
3. **Founder card** drill-down — pick one founder from the portfolio. Show their KG ego-network, top 5 signals at time T (what the model "saw" then), their actual outcome path. The storytelling layer.

Full spec: [`FRONTEND_SPEC.md`](FRONTEND_SPEC.md). Build order: design (Kris + Claude Design) → static prototype → wire to the existing parquet/csv outputs via a thin FastAPI layer → deploy to Vercel free tier.

**What this frontend does NOT include** (locked iter-12):

- ❌ Stranger-handle live-scoring (cohort replay + self-case only — see DECISION_LOG iter-12 for reasoning)
- ❌ Fund-returns dashboards (P&L curves, IRR numbers) — would require return data we don't have and breaks the prediction-claim defensibility
- ❌ "vs a16z / Sequoia" comparisons — only the 4 in-framework baselines + YC-batch overlap (if sourceable)

---

## 3. Test surface

134 tests across 16 files. Coverage by area:

| Area | Tests | File(s) |
|---|---:|---|
| Ingestion (each platform + schema + cohort + clean + sweep) | 39 | `tests/test_{twitter,youtube,reddit,hackernews,producthunt,trends,cohort,clean}_collect.py` |
| Scoring | 8 | `tests/test_score_signals.py` |
| Topic momentum | 6 | `tests/test_topic_momentum.py` |
| Topic discovery (iter-11) | 6 | `tests/test_topic_discovery.py` |
| KG construction + features | 7 | `tests/test_kg.py` |
| Person features + baseline + KG-aug + eval | 7 | `tests/test_models.py` |
| Allocation | 6 | `tests/test_allocation.py` |
| Allocation framework (combine + backtest) | 6 | `tests/test_allocation_framework.py` |
| Monte Carlo (4 functions × ≥4 + 2 integration) | 25 | `tests/test_monte_carlo.py` |
| Lock harness | 5 | `tests/test_lock_predictions.py` |
| Negative-peer protocol | 6 | `tests/test_negative_peers.py` |
| Self-case (iter-11) | 5 | `tests/test_self_case.py` |
| Seed labels | 2 | `tests/test_seed_labels.py` |
| Dashboard data | 2 | `tests/test_dashboard_data.py` |

All Anthropic calls are mocked. No tests hit a real LLM. The cost-accounting +
budget-guard plumbing is verified via mocked token counts.

---

## 3b. Storage architecture (DECISION_LOG iter-13, 2026-05-14)

**Option C — Hybrid (locked).** Three storage layers that should always agree; the parquet/csv files are the source of truth.

```
┌─────────────────────────────────────┐
│  data/raw/, data/interim/,          │   Local source of truth.
│  data/processed/ (gitignored)       │   All model code reads from here.
│                                     │   ~250 KB now → ~30-70 MB projected.
└──────────────┬──────────────────────┘
               │
               ├──> scripts/publish_data_snapshot.py (TODO, F1.5)
               │       └──> GitHub Releases (`data_snapshot_YYYY-MM-DD.tar.gz`)
               │           Cite from thesis appendix; examiners can `gh release download`.
               │
               └──> scripts/sync_to_supabase.py (TODO, F1.5)
                       └──> Supabase Postgres (500 MB free tier)
                           ├── `signal_events` table (mirror of signal_events.parquet)
                           ├── `scored_signals` table
                           ├── `person_features` table
                           ├── `kg_features` table
                           ├── `outcome_labels` table
                           ├── `eval_metrics` table
                           ├── `backtest_results` table
                           └── `allocation` table
```

**What the FastAPI layer reads from:**
- `--source local` (default in dev): reads `data/processed/*.parquet` directly via pyarrow
- `--source supabase` (default in prod): reads via Supabase Postgres client

**What lives where:**

| Asset | Local parquet | GitHub release | Supabase |
|---|---|---|---|
| Source of truth | ✅ | mirror | mirror |
| Used by all model code (`pipeline.py`, tests) | ✅ | — | — |
| Used by the live demo frontend | — | — | ✅ |
| Cited in the thesis appendix | ✅ (instructions) | ✅ (tag URL) | ✅ (project URL) |
| Updated when scoring re-runs | ✅ first | next snapshot | next sync run |
| The May-31 locked predictions JSON | committed to `04_RETROSPECTIVE_CASES/` | ✅ in release tag `v1.0-thesis-submission` | also mirrored to `locked_predictions` table |

**What this architecture DOES buy:**
- ✅ The "where's your database" defence question has a clean answer (Supabase queryable URL + schema)
- ✅ Postgres `created_at` defaults give an independent ingestion-timestamp record (reinforces lookahead-bias-discipline claim)
- ✅ The May-31 lock gets a second provenance anchor (Postgres row-insert time, on top of git hash + SHA-256)
- ✅ Strongest reproducibility position of any BBA thesis at EDHEC: examiner picks 1 of 3 paths to verify (release tar.gz / live Supabase query / local clone + pipeline run)

**What this architecture DOES NOT buy:**
- ❌ Faster queries (parquet already fast at <100 MB)
- ❌ "Real-time" anything (data updates a few times during thesis cycle)
- ❌ Vector search (pgvector available if needed, but signal embeddings explicitly out of scope per iter-2)

**Pause-on-idle risk:** Supabase free-tier projects pause after 7 days of inactivity; first request takes ~30s to wake. Hourly cron keepalive (Vercel cron or GitHub Actions) is the workaround. **Explicitly deferred to post-deployment** per iter-13 ("the last last element"). Defence-day mitigation regardless: manually warm up the project 24h before defence.

---

## 4. Real-data state (as of 2026-05-14)

| Asset | Where | What's in it |
|---|---|---|
| `data/raw/hackernews/*.parquet` | per-founder | 599 signals across 22 files (20 cohort + 2 smoke) |
| `data/raw/youtube/*.parquet` | per-founder | 2 signals (mostly empty — YouTube channel IDs missing for cohort) |
| `data/raw/trends/*.parquet` | per-keyword | 53 weeks for "indie hacker" |
| `data/interim/signal_events.parquet` | unified | 601 rows (HN-dominated) |
| `data/interim/topic_momentum.parquet` | unified | 53 rows, 1 keyword |
| `data/processed/scored_signals.parquet` | unified | **~1680 signals scored** (cohort + 377 HN negatives + 359 X-native positive backfill); ledger $9.66/$30 |
| `data/processed/outcome_labels.csv` | labels | 20 positives + 15 real signal-bearing negatives + 1 self-case; **10/20 positives + 15/15 negatives have features → eval n=25** |
| `data/processed/topic_momentum_metrics.parquet` | metrics | slope_4w=17.5, slope_12w=0.19, acceleration=17.31 for "indie hacker" (real Trends data) |
| `04_RETROSPECTIVE_CASES/cohort_balance.md` | report | per-founder signal counts (6/20 founders have non-trivial data) |

---

## 5. What's still pending and why

| # | Blocker | Owner | Unblocks |
|---|---|---|---|
| B1 | ~~`ANTHROPIC_API_KEY` in `.env`~~ — **CLOSED**. Real scoring runs; ledger $9.66/$30. | — | — |
| B2.a | ~~Candidate-longlist tool hits PH rate-limits~~ — **CLOSED 2026-05-20**. `scripts/find_negative_peer_candidates.py` produced 283 candidates across 12/15 PH niches in 30 min using 18% of the PH budget; caches persist incrementally on disk. CSVs sit in `data/interim/negative_peer_candidates/` (see folder README). | — | — |
| B2.b | ~~Negative peers~~ — **CLOSED 2026-05-28**. 15 real **signal-bearing** negatives ingested from the HN discovery harvest (`scripts/ingest_signal_bearing_negatives.py`): people who posted in-niche but never emerged. Eval now genuine — ROC AUC **0.895** (was artifactual 1.000), PR AUC baseline 0.884 → KG-aug 0.913. Earlier zero-feature-placeholder approach (`ingestion/negative_peers.py`) kept as fallback + guarded by `detect_zero_feature_negatives`. | — | — |
| B3 | Reddit + ProductHunt API credentials | Kris | Re-running the cohort sweep with these roughly doubles per-founder data coverage |
| B4 | YouTube channel-ID overrides for cohort (most aren't YouTube-first) | Kris | YouTube coverage in the KG |
| B5 | Twitter Wayback density sweep — **PARTIAL 2026-05-28**. 3 X-native positives backfilled (levelsio, yongfook, damengchen) via `scripts/backfill_one_handle.py` (isolated, snapshot-capped). Remaining 10 positives stay thin: Wayback throttles snapshot HTML fetches under batch load (~10s each, hang). Full backfill needs a non-Wayback X source. Positive coverage 7 → 10/20; eval n=25. | CC / non-Wayback X source | Stronger n for the eval |
| B6 | First scored data → topic-discovery Pass A meaningful output | Depends on B1 | Auto-topic discovery's cohort-grounded pass produces empty results until LLM scoring runs and populates `s6_topic_label` |
| B7 | Kris's own X handle ingested + scored | Depends on B1 + sweep | Self-case page surfaces a real P(emerge) prediction |

Out-of-scope tonight (Kris-side decisions, not blockers for me):
- Tovstiga email + dashboard URL share (Phase 1.6, due 2026-05-16)
- 10 shortlisted topics for the cohort momentum sweep (task 2.6 — partially superseded now that auto-discovery exists)

---

## 6. Roadmap re-tagged against shipped code

| Roadmap task | Status |
|---|---|
| Phase 0 — Unlock | ✅ shipped (commit `4a7b1ec` and earlier) |
| Phase 1.x — Cohort + ingestion modules | ✅ shipped (all 5 platforms + Wayback + Trends) |
| Phase 2.4 — Trends collector | ✅ shipped |
| Phase 2.5 — Cohort sweep | ✅ shipped |
| Phase 2.9 — Unified parquet | ✅ shipped |
| Phase 2.10 — Cohort balance report | ✅ shipped |
| Phase 3.1 — LLM scoring prompts v1 | ✅ shipped (`prompts/v1/signal_scoring.md`) |
| Phase 3.2 — Inter-rater check | ⚠ deferred (Kris hand-picks 5 signals once scoring runs) |
| Phase 3.3 — score_signals.py | ✅ shipped |
| Phase 3.4 — Full scoring pass | 🔒 blocked on B1 |
| Phase 3.5 — Topic momentum | ✅ shipped + auto-discovery layered on top (iter-11) |
| Phase 3.6 — KG construction | ✅ shipped |
| Phase 3.8 — Per-person KG features | ✅ shipped |
| Phase 3.9 — Baseline + KG-augmented models | ✅ shipped (LogReg both; RF not done — LogReg interpretable + sufficient at n=20) |
| Phase 3.10 — Cross-validation + DeLong | ✅ AUC/PR-AUC + bootstrap CIs shipped; DeLong specifically NOT implemented — bootstrap CIs serve the same purpose with cleaner small-n properties |
| Phase 4 — Allocation framework + backtest | ✅ shipped (`allocation_framework/combine.py` + `backtest.py`) |
| Phase 4.5–4.7 — May-31 prediction lock | ✅ harness shipped (`analysis/lock_predictions.py`); actual lock = 2026-05-31 |
| Phase 4 framework extensions | ✅ Monte Carlo (iter-10) + auto-topic discovery (iter-11) shipped |
| Phase 5.1–5.2 — Dashboard | ✅ 8 pages shipped (claim, methodology, cohort, results, backtest, simulation, self-case, roadmap) |
| Phase 5.3–5.8 — Writing | 🔒 Cowork-owned, blocked on real model output |
| Phase 6 — Supervisor preview | Scheduled for Jun 8 (Tovstiga touchpoint) |
| Phase 7–10 — Polish + Urkund + defence | On schedule |

---

## 7. How Cowork should use this file

1. **Before drafting a chapter:** check section 2 to know exactly what
   modules + outputs exist for the methodology chapter to cite.
2. **Before proposing new code in a CC prompt:** check section 5 to see if
   the prerequisite has shipped or is blocked. If blocked, the prompt should
   either unblock it or focus elsewhere.
3. **Before writing the Findings chapter:** wait for B1 + B2 to resolve.
   Until then, the eval + backtest tables surface single-class refusals,
   not lift numbers.
4. **For the Tovstiga email (2026-05-16):** sections 1–2 + the live
   dashboard URL are the substance.
5. **For DECISION_LOG sync:** iter-11 entries are already added. Future
   architectural changes should add a new iteration to DECISION_LOG +
   update this file's tables in lockstep.
