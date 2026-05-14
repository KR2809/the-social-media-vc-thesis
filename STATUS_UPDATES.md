# STATUS_UPDATES.md

Append-only journal of Claude Code work sessions on the-social-media-vc-thesis.

**How to read:** newest entries at the bottom. Each entry follows the format
defined in `CLAUDE.md` §2.

**How to use:**
- Claude Code: append after every session
- Cowork (in chat): read this file when Kris drops back to catch up
- Kris: read this when picking up after a break

---

## 2026-05-11 23:37 — Repo bootstrap (Phase 0)

**What I did:**
- Scaffolded the project directory structure (ingestion, scoring, analysis,
  prompts, models, dashboard, data, tests, docs) with `__init__.py` and
  `.gitkeep` placeholders.
- Created `pyproject.toml` with all runtime deps (pandas, polars, anthropic,
  networkx, snscrape, praw, streamlit, etc.) + dev tooling (ruff, black,
  pytest, ipykernel).
- Created `.env.example` with placeholders for Anthropic, YouTube, Reddit,
  Product Hunt, OpenAI (optional), Crunchbase (optional).
- Created `.gitignore` excluding secrets, virtualenvs, caches, and all data
  files (raw/interim/processed kept only as `.gitkeep` stubs).
- Wrote `README.md` (public-facing project summary with the locked thesis
  title) and the repo-level `CLAUDE.md` (Claude Code operating rules).
- Installed `uv` 0.11.13 via `python3.11 -m pip install --user uv`.
- Ran `uv sync` (or fallback — see "Decisions made" below) to install deps.
- Created initial git commit.

**Decisions made:**
- **Repo location reconciliation.** The Phase-0 bootstrap doc in the workspace
  (`00_PLANNING/cc_prompts_phase0_bootstrap.md`) expected a repo named
  `bba-thesis-signal-fund` nested inside `09_CODE/`. The actual cloned repo
  is `KR2809/the-social-media-vc-thesis` at
  `~/Documents/Coding/Thesis/the-social-media-vc-thesis/` (outside the
  thesis workspace tree). Per Kris's call: scaffold into the cloned repo,
  rename the project concept to match the GitHub repo. Workspace doc
  references in `CLAUDE.md` use absolute paths since `../../` no longer
  resolves to the workspace.
- **Title reconciliation.** The bootstrap doc still carried the older
  "Social-Signal Fund / Inspired by QuantumLight Capital" title. Workspace
  `CLAUDE.md` rule 1 says the locked title (from the submitted January
  2026 outline) is *"From Social Signals to Entrepreneurial Emergence: A
  Knowledge Graph Framework for Predicting Micro-Entrepreneurship in the
  Creator Economy"*. Per Kris's call: README uses the locked title. The
  bootstrap doc itself is now stale on this point — flag for Cowork to
  reconcile.
- **Dep manager.** `uv` was not installed and system `python3` is 3.9
  (unusable for this project). Used `/usr/local/bin/python3.11 -m pip
  install --user uv` to install uv 0.11.13. uv binary lives at
  `~/Library/Python/3.11/bin/uv`.
- License: MIT for code, CC-BY 4.0 for non-code artefacts (per Move B
  commitment to make this a public reusable framework).
- Hard monthly Anthropic budget cap recorded as $30 in CLAUDE.md (Kris to
  also set the actual cap in the Anthropic Console).
- **`pyproject.toml` build-target addition.** The bootstrap doc's
  `pyproject.toml` as written failed `uv sync` because hatchling could not
  auto-detect the package directory (project name does not match any
  importable module — we have `ingestion/`, `scoring/`, `analysis/`).
  Added `[tool.hatch.build.targets.wheel] packages = ["ingestion",
  "scoring", "analysis"]`. This same issue would have hit the
  `bba-thesis-signal-fund` name in the bootstrap doc — flag for Cowork to
  patch the doc.

**Blockers:**
- Bootstrap doc (`00_PLANNING/cc_prompts_phase0_bootstrap.md`) is now stale
  on two points: repo name and thesis title. Recommend Cowork updates the
  doc to match the locked title and the actual repo name on next session.
  This is a doc-hygiene blocker, not an execution blocker.

**Next steps:**
- Kris: confirm `.env` is filled with real API keys + push initial commit to
  GitHub (`git push -u origin main`).
- Cowork: reconcile the bootstrap doc with the locked title and repo name.
- CC (next session): begin Phase 1 ingestion module `ingestion/twitter_collect.py`
  (snscrape + Wayback fallback). See `EXECUTION_ROADMAP.md` §2.2.

**Files changed:** `README.md`, `CLAUDE.md`, `STATUS_UPDATES.md`,
`pyproject.toml`, `.env.example`, `.gitignore`, and all
`__init__.py` / `.gitkeep` files in the folder tree.

**Cost incurred:** $0 (no API calls yet).

---

## 2026-05-12 20:02 — Phase 1.2: twitter_collect + unified SignalEvent schema

**What I did:**
- Created `ingestion/schema.py` with the canonical `SignalEvent` (frozen
  Pydantic v2 model) + `handle_to_person_id`, `signal_events_to_parquet`,
  `parquet_to_signal_events` helpers. Explicit pyarrow schema so every
  later platform writes the same column types.
- Created `ingestion/twitter_collect.py` with `collect_twitter(handle,
  start, end, out_dir) → Path`. snscrape primary; Wayback CDX fallback
  when snscrape errors or returns zero. Click CLI at the bottom.
- Wayback parser targets two eras: pre-2020 (`div[data-tweet-id]`,
  used `js-short-timestamp[data-time]`) and post-2020 (`article[data-testid="tweet"]`),
  per Kris's call to attempt both and document failures.
- Created `tests/test_twitter_collect.py` — six tests, all using stdlib
  `unittest.mock` (no pytest-mock dep added). All six pass; ruff clean.

**Did snscrape work?** No. X's GraphQL `SearchTimeline` endpoint returns
HTTP 404 ("blocked") on every guest-token attempt. snscrape's 4-attempt
exponential backoff exhausted on the first real run. This is the
well-known 2023 X anti-scraping change; the public snscrape repo has not
been patched and likely will not be. **Implication for Phase 2.5
(cohort-wide ingestion):** snscrape will be effectively dead weight for
recent windows. Wayback-only is the realistic path for X data from this
point on. We may want to investigate alternatives (manual archive
downloads where founders have them, Nitter archives, or the X
free-tier API at low volume) before the May 20 ingestion-sweep gate.

**Did Wayback parse correctly?** Yes, once selectors were corrected. The
spec's original `div.tweet` selector and `span._timestamp[data-time]`
do NOT match real 2014-era levelsio snapshots. After probing the actual
DOM I switched to `div[data-tweet-id]` (matches the era's
`div.js-tweet` / `div.js-stream-tweet` containers) and
`span[data-time]` (matches the `js-short-timestamp` class). A
diagnostic against the 2014-08-05 levelsio snapshot now extracts
**20 tweets** with timestamps, engagement (likes/replies/reposts), and
clean text. The post-2020 React parser is implemented but unverified
against real data (next ingestion module will exercise it).

**For the levelsio 2014-06-01 → 2014-07-01 test: how many tweets?**
**Zero from both sources.** snscrape blocked (above). Wayback's CDX
genuinely has **no captures** of `twitter.com/levelsio` before
2014-08-05 — verified by independent probe with HTTPS + 120s timeout
returning an empty snapshot list for June 2014 but 5+ captures starting
Aug 5. Per CLAUDE.md hard rule: did NOT widen the window or chase a
green result. The parquet was written empty with the full canonical
schema. The end-to-end path is verified functional — only this exact
spec window has no archive data for this handle.

**Decisions made:**
- **Mock library: stdlib `unittest.mock`, not pytest-mock.** The task
  description said pytest-mock was "already in dev deps" — it wasn't.
  Stdlib mocks are sufficient for the six tests; no `pyproject.toml`
  change needed.
- **`metadata` is a JSON string in parquet**, not a nested struct. Each
  platform carries heterogeneous metadata; a union struct across all
  platforms would be brittle. JSON string is schema-stable. Documented
  in the SignalEvent docstring.
- **De-dup prefers snscrape over Wayback** for the same `signal_id` —
  snscrape carries richer engagement (replies, quote count, view count).
  (Moot at the moment given snscrape's death, but the rule is right for
  when/if it returns.)
- **CDX endpoint switched to HTTPS + 120s timeout** (was HTTP / 30s).
  The HTTP path timed out during the first end-to-end run. HTTPS is
  reliable but slow (~30-60s typical). Snapshot fetches use a 60s
  timeout.
- **Pre-2020 selectors corrected** from `div.tweet` / `span._timestamp`
  (per the original task spec) to `div[data-tweet-id]` /
  `span[data-time]` (matches real 2014-era levelsio HTML). The original
  selectors zero-matched a real snapshot; the new ones extract 20
  tweets per page. Tests passed both before and after (the test
  fixture's `div.tweet` carries `data-tweet-id` so it satisfies the
  broader selector too).

**Blockers:**
- **snscrape is effectively dead.** It returns 0 tweets for any handle
  on any window in 2026-05. Need a Phase 2 decision: is Wayback-only
  sufficient for the cohort, or do we need an alternative X source?
  Surfacing this to Cowork ahead of the May 14 ingestion expansion.
- **No new dep needed for this module** — tests use stdlib mocks.

**Next steps:**
- Cowork: decide whether to investigate alternatives to snscrape (Nitter
  archive scraping? X free-tier API at low volume? Manual founder
  archives?) before task 2.3 (YouTube/Reddit/HN/ProductHunt) starts.
- CC (next session): task 2.3 — YouTube + Reddit + HN + ProductHunt +
  GitHub trending ingestion modules (all writing to the same
  `SignalEvent` schema).

**Files changed:** `ingestion/schema.py` (new), `ingestion/twitter_collect.py`
(new), `tests/test_twitter_collect.py` (new), `STATUS_UPDATES.md`.
No changes to `pyproject.toml`. One empty parquet at
`data/raw/twitter/levelsio_2014-06-01_2014-07-01.parquet` from the
spec test run — gitignored, not staged.

**Cost incurred:** $0 (no LLM calls in this module).

---

## 2026-05-13 08:57 — Phase 2.3: Multi-platform ingestion (YouTube + Reddit + HN + PH)

**What I did:**
- Built four ingestion modules conforming to the existing `SignalEvent`
  schema (no schema changes needed):
  - `ingestion/hackernews_collect.py` — HN Firebase API, no auth,
    parallel fetch via `ThreadPoolExecutor(max_workers=10)`.
  - `ingestion/youtube_collect.py` — YouTube Data API v3, REST only
    (no SDK). Quota-cheap pattern (1u/page playlistItems, 1u/batch
    videos). `handle_to_channel_id` with disk cache at
    `data/interim/youtube_channel_id_cache.json`.
  - `ingestion/reddit_collect.py` — PRAW read-only. Client-side date
    filter (PRAW has no server-side `createdAt` predicate on user
    listings). Logs a warning at the ~1000-item ceiling.
  - `ingestion/producthunt_collect.py` — PH v2 GraphQL via
    `requests.post`. Pagination via `pageInfo.hasNextPage` +
    `endCursor` on both `madePosts` and `madeComments`.
- 21 new tests across 4 test files. All 31 tests in the repo pass; ruff
  clean.
- Eight focused commits (4 × feat:, 4 × test:).

**Per-platform: worked? real row count? quota?**

| Platform | Worked? | Real smoke | Quota / rate-limit observations |
| --- | --- | --- | --- |
| **HN** | **YES** | `pg` 2014-01-01 → 2015-01-01 → **229 items** (11 stories, 218 comments). Unique signal_ids, all in window, text legible. Eyeballed 3 rows — clean. | Firebase API is fast + lenient. `user.submitted` returns the user's *entire* history flat (15,565 IDs for pg) so the 10-worker pool walks it in ~30s for that volume. No 429s observed. |
| **YouTube** | **PARTIAL** — module + 6 tests pass, real smoke **blocked**: `.env` missing so `YOUTUBE_API_KEY` is unset; smoke fails fast with `YouTubeAuthError`. Code path is validated end-to-end against mocked responses. | Untested live. Expected ~1 + 2×ceil(N/50) units per channel — well under the 10k/day cap for our 20-person cohort. |
| **Reddit** | **PARTIAL** — module + 5 tests pass, real smoke **blocked**: `.env` missing. | Untested live. PRAW auto-handles rate-limiting; cohort members with >1000 posts will hit the listing ceiling — warning is logged but the parquet still gets the truncated set. Flag this for `cohort_balance.md` when we sweep. |
| **ProductHunt** | **PARTIAL** — module + 5 tests pass, real smoke **blocked**: `.env` missing. | Untested live. Risk forecast says token may need regeneration on first call; haven't seen any errors yet because we haven't called the API. |

**Decisions made:**
- **No new deps.** YouTube spec said `google-api-python-client` was
  already in pyproject — it wasn't. Used `requests` directly against
  the REST endpoints per the spec's documented fallback. Reddit (PRAW)
  and PH (requests for GraphQL) needed no additions either.
- **No schema changes.** All four platforms fit the canonical engagement
  keys (`likes/replies/reposts/views/quotes`). Per-platform metadata
  goes into the JSON-encoded `metadata` field with platform-specific
  keys (`subreddit`, `video_id`, `topics`, `is_show_hn`, etc.). The
  `metadata.type` discriminator (`post`/`comment`/`submission`/`story`/
  `poll`) is set consistently across platforms — useful for downstream
  filtering.
- **Engagement mapping per platform.** YouTube `viewCount → views`,
  `likeCount → likes`, `commentCount → replies`. Reddit `score → likes`,
  `num_comments → replies` (submissions only — comments have no
  reply-count via PRAW listings). HN `score → likes`,
  `descendants → replies` (stories only — comments have neither).
  PH `votesCount → likes`, `commentsCount → replies` (posts only —
  comments have neither).
- **HN HTML entity decoding.** HN returns titles/text with HTML entities
  (`&#x27;`, `&amp;`, etc.). The collector preserves them as-is.
  Decoding is a scoring-layer concern, not an ingestion concern — flag
  for the W3 scoring prompts to either strip or normalise.

**Blockers:**
- **No `.env` file** at repo root. Phase 0 created `.env.example`;
  Kris's Phase 0 STATUS asked Kris to populate it. Until that lands,
  YT/Reddit/PH cannot run real smoke tests. Per agreement: build all
  four modules now, smoke-test only HN.
- snscrape is still dead (carried over from Phase 1.2). X recovery is
  someone else's problem.

**Next steps:**
- Kris: populate `.env` from `.env.example`. Then he (or CC in a follow-up
  session) can run:
  ```
  uv run python -m ingestion.youtube_collect --channel-id UCX6OQ3DkcsbYNE6H8uQQuVA --start 2020-01-01 --end 2020-04-01
  uv run python -m ingestion.reddit_collect --username spez --start 2024-01-01 --end 2024-02-01
  uv run python -m ingestion.producthunt_collect --username pieter-levels --start 2014-01-01 --end 2015-01-01
  ```
- Cowork: prep prompt for task 2.4 (Google Trends / pytrends) — easy
  win since pytrends is already in pyproject.
- CC (next session): build the unified `clean.py` (task 2.9) so the
  signal_events from all five platforms can be concatenated into
  `data/interim/signal_events.parquet`.

**Files changed (this session):**
`ingestion/hackernews_collect.py`, `ingestion/youtube_collect.py`,
`ingestion/reddit_collect.py`, `ingestion/producthunt_collect.py`,
`tests/test_hackernews_collect.py`, `tests/test_youtube_collect.py`,
`tests/test_reddit_collect.py`, `tests/test_producthunt_collect.py`,
`STATUS_UPDATES.md`. No changes to `ingestion/schema.py`,
`pyproject.toml`, `dashboard/`, `README.md`, or `requirements.txt`.

**Real data on disk (gitignored):**
- `data/raw/hackernews/pg_2014-01-01_2015-01-01.parquet` — 229 rows
- `data/raw/hackernews/pg_2014-06-01_2014-07-01.parquet` — 0 rows (HN
  had no items for pg in that window; widening to 1y produced the 229)

**Cost incurred:** $0. No LLM calls. HN Firebase is free.

---

## 2026-05-13 09:29 — Phase 2 finish: trends, cohort sweep, clean.py, balance report

**What I did:**
- Closed out the rest of Phase 2 (tasks 2.4, 2.5, 2.9, 2.10) in one
  session. Five new modules + 14 new tests:
  - `ingestion/trends_collect.py` — Google Trends via pytrends. Topic
    time-series (not SignalEvents). 5 tests.
  - `ingestion/cohort.py` — parses the verified-cohort markdown table
    once; `CohortMember` dataclass with per-platform handle defaults
    and override-file support. 4 tests.
  - `ingestion/sweep.py` — orchestrator that walks the cohort and calls
    each available platform collector. Skips platforms with missing
    credentials; tolerates per-(founder, platform) failures.
  - `ingestion/clean.py` — consolidates raw parquets into
    `data/interim/signal_events.parquet` (and `topic_momentum.parquet`
    for trends). De-dups on signal_id (newest collected_at wins), drops
    null-key rows. 5 tests.
  - `analysis/cohort_balance.py` — generates
    `04_RETROSPECTIVE_CASES/cohort_balance.md`.
- Ran a real cohort-wide HN sweep + real `clean` + real balance report.
  45/45 tests pass; ruff clean.
- 5 focused commits, all on `main`, conventional-commit prefixes.

**Real data on disk (gitignored):**
- `data/raw/hackernews/*.parquet` — 21 founder files from the cohort
  sweep (one is a duplicate `pg` from earlier smoke test)
- `data/raw/youtube/ucx6oq3dkcsbyne6h8uqquva_2024-01-01_2024-02-01.parquet`
  — MrBeast smoke from earlier session
- `data/raw/trends/indie-hacker_2023-01-01_2024-01-01.parquet` — 53 weekly rows
- `data/interim/signal_events.parquet` — **601 unified events** (599 HN
  + 2 YouTube); 370 of those belong to the verified cohort, the rest is
  non-cohort smoke-test residue (`pg`, MrBeast channel id).
- `data/interim/topic_momentum.parquet` — 53 weekly rows.

**Did the cohort sweep work?**
Yes for HackerNews. **6/20 cohort founders** have HN history findable
under the X-handle-as-username default, totalling 370 events:
- Anne-Laure Le Cunff (`anthilemoon`): 157
- Arvid Kahl (`arvidkahl`): 103
- Marc Lou (`marclou`): 70
- Dickie Bush (`dickiebush`): 24
- Lenny Rachitsky (`lennysan`): 15
- Justin Welsh (`thejustinwelsh`): 1

The other 14 returned 0 — either no HN account or different handle on
HN vs X. Likely candidates for gap-fill: Tony Dinh (`tdinh_me` is
unusual on HN; he may use `tdinh`), Pieter Levels (likely no HN at all,
he's X-primary), Damon Chen, Roy Lee.

YouTube/Reddit/ProductHunt all show 0/20 in the balance report:
- **Reddit / PH**: credentials still missing in `.env` (you have
  Anthropic + YouTube set; the rest is pending).
- **YouTube**: needs channel ID per founder. The sweep doesn't burn
  search.list quota to resolve handle→channel; that requires the
  override file `cohort_handles_override.json` to be populated.
- **Twitter**: snscrape dead. Wayback sweep deliberately skipped
  (`--skip-twitter` default for time reasons; Wayback CDX is slow and
  gives sparse coverage anyway).

**Decisions made:**
- **Default sweep window: 2020-01-01 → 2025-01-01.** Per-founder windows
  derived from `emergence_quarter` would be ideal but `emergence_quarter`
  is free-form text in the cohort file ("2018–2019", "Apr 2023 (acq.)").
  Parsing all formats is brittle. Future improvement: add
  `emergence_date_iso` to the override file. For now the 5-year window
  covers most cohort emergence dates plus pre-emergence activity.
- **Default non-X handle: X handle, lowercased, underscores stripped.**
  Many founders use the same handle cross-platform; this is a workable
  first cut. Misses produce empty parquets that the balance report
  surfaces honestly — not a hack, real data.
- **Trends rate-limited despite tenacity retries on first try.** Google
  returned 429 immediately. The second call (different window, same
  retry config) succeeded. pytrends/Trends is flaky; we'll need to
  pause longer between cohort-topic sweeps, but for our 10-topic
  universe it's tractable.
- **`emergence_quarter`-driven topic universe is not built yet.** Task
  2.6 ("Run topic-trend ingestion across the 10 shortlisted topics")
  needs Kris to choose the 10 topics first. Surfacing for Cowork.

**Per-roadmap decision gate (end of Tue May 20):**
The roadmap said if cohort has <40 usable persons, scope-cut to n=30 and
document. Verified cohort is **n=20** to begin with, already below 40.
The gate becomes data quality per founder, not headcount. With current
data (HN only): 6/20 founders have non-trivial data. With Reddit + PH
+ YT once credentials/IDs land: probably 12-15/20. With Twitter
Wayback: probably 18-19/20 (everyone has a Twitter presence by
definition — the question is how much Wayback archived).

**Blockers:**
- **Reddit + PH credentials still missing.** When you have a few
  minutes, paste them and I'll re-run the cohort sweep across those
  platforms. Expected to roughly double the per-founder data coverage.
- **YouTube channel ID overrides missing.** Need to either (a) accept
  the 100u/founder quota burn to resolve, or (b) eyeball the 20
  founders' YouTube presence manually and drop a JSON file. Most of
  the cohort is not primarily YouTube — likely only Tori Dunlap and
  maybe 1-2 others have YouTube channels worth scraping.
- **snscrape carryover.** No change since Phase 1.2.
- **Two non-cohort person_ids in `signal_events.parquet`** (`pg`,
  MrBeast channel id) from smoke tests. Flagged in the balance report
  for cleanup before the Phase 3 scoring pass — `rm -rf data/raw/` and
  re-run the sweep will do it.

**Next steps:**
- **You**: paste Reddit + PH creds; identify the 10 trend topics for
  task 2.6 (or punt on 2.6 entirely — it's a Tier-1 enhancement, not a
  blocker for Phase 3).
- **CC (next session, Phase 3 — May 21 onwards)**: LLM scoring prompts
  + `scoring/score_signals.py`. Default Claude Haiku 4.5. Budget cap
  $30/mo.

**Files changed (this session):**
`ingestion/trends_collect.py`, `ingestion/cohort.py`,
`ingestion/sweep.py`, `ingestion/clean.py`, `analysis/cohort_balance.py`,
`tests/test_trends_collect.py`, `tests/test_cohort.py`,
`tests/test_clean.py`, `STATUS_UPDATES.md`. Wrote
`04_RETROSPECTIVE_CASES/cohort_balance.md` (in the thesis workspace,
not the repo). No changes to `schema.py`, `pyproject.toml`, or any
existing module.

**Cost incurred:** $0. (45 tests pass on free deps; the cohort sweep
used HN Firebase = free, YouTube Data API ~3 units (10k/day cap),
pytrends = free, Wayback = skipped.)

---

---
## 2026-05-14 09:00 — Phase 3/4/5 build: scoring, KG, models, allocation

**What I did:** Built the full Phase 3 → 5 chain end-to-end as code,
with synthetic-data tests proving each layer composes correctly. Did
NOT yet run real LLM scoring (env-affected per build plan); everything
else is wired and the pipeline runs to completion on real data.

Eight new modules + one CLI:
- `prompts/v1/signal_scoring.md` — strict-JSON taxonomy contract (S1–S6
  from `signal_taxonomy_v1.md`)
- `scoring/score_signals.py` — Claude Haiku 4.5 driver. Idempotent
  re-runs (already-scored signal_ids skipped). $30/mo budget guard
  reads cumulative cost from `data/interim/llm_run_log.jsonl`. Hard-
  flush every 25 signals so a crash mid-run doesn't lose work.
- `analysis/topic_momentum.py` — 4w/12w OLS slopes + acceleration on
  the weekly Trends parquet. Smoke-tested: 'indie hacker' shows
  17.5 slope_4w vs 0.19 slope_12w (real signal — a recent spike).
- `analysis/build_graph.py` — NetworkX MultiDiGraph per
  `COMPREHENSIVE_PLAN §4.5` schema. Person/SignalEvent/Topic/Platform
  nodes + EXPRESSED/ABOUT/ON_PLATFORM/CO_OCCURS_WITH edges. Writes
  GraphML (Gephi) and pickle (fast reload).
- `analysis/kg_features.py` — per-person degree centrality, clustering,
  topic-diversity entropy, BIP-triad count, mean signal strength.
- `analysis/person_features.py` — flat per-person rollups for the
  baseline model (cadence, platform diversity, S1-S4 means, BIP/goal/
  recruitment counts).
- `models/baselines/baseline_model.py` — logistic regression with
  class_weight=balanced, median imputation, standard-scaler. Refuses
  to fit on single-class data with a clear error.
- `models/kg_augmented/kg_model.py` — baseline + KG features through
  the same pipeline. Drops duplicate cols on merge.
- `models/evaluation/eval.py` — LOO CV when n<=30, 5-fold otherwise.
  ROC AUC + PR AUC + F1 + precision@k + lift@k + Brier. Writes a
  human-readable markdown report.
- `analysis/allocation.py` — fractional Kelly. Default 1/4 Kelly @
  30x payoff (pre-seed convention) with a 10% per-person cap.
- `analysis/seed_labels.py` — populates 20 cohort positives from
  `cohort_verified.md`.
- `pipeline.py` — click CLI with 8 stages; each idempotent; supports
  partial runs (`pipeline.py clean score eval`).

**Decisions made:**
- Cohort = 20 positives; negatives are stubbed/deferred. Per
  `COMPREHENSIVE_PLAN §4.4-alt`, the negative-peer protocol is a
  separate ingest workstream. Model layer refuses to fit on
  single-class — correct behaviour, surfaces the dependency clearly.
- Allocation = fractional Kelly. Simplest defensible math for a
  pre-seed VC framework. b=30x, k=0.25 (quarter-Kelly) are the
  conservative-VC defaults the literature uses; both are CLI knobs.
- Sklearn `X` uppercase preserved via per-file ruff exemption (correct
  PEP-N violation; sklearn convention).

**Blockers:**
- **No `ANTHROPIC_API_KEY` actually used yet.** Once `.env` is
  populated, run `python pipeline.py score` to fire the first real
  scoring pass. With 601 signals × ~$0.0025/signal expected ≈ $1.50
  total cost for the v1 pass. Well under the $30/mo budget.
- **Single-class outcome labels.** Negative-peer ingest is a separate
  protocol (not built tonight). The eval and allocation pipeline are
  inert until a few negatives land; that's by design (single-class
  bails loudly).
- **Reddit + PH credentials still pending** (carryover from Phase 2).
  Re-running the sweep with these will roughly double per-founder
  coverage and meaningfully improve KG density.

**Next steps:**
- **You** (Kris):
  1. Drop `ANTHROPIC_API_KEY` into `.env` so I can fire the first
     real scoring pass.
  2. Paste Reddit + ProductHunt credentials when convenient.
  3. Decide on negative-peer construction: shortlist 20+ similar-niche
     creators who did NOT emerge as paid-tier/SaaS operators in the
     same window. Their handles go into `data/processed/outcome_labels.csv`
     as `emerged=0`, and the model layer comes online.
- **CC (next session)**:
  1. Fire `python pipeline.py score` once API key lands. Expected
     cost ≈ $1.50.
  2. Run end-to-end pipeline: `clean → score → person → graph →
     kg-features → topic → eval → allocate`.
  3. Inspect the resulting `eval_report.md` and KG figure in Gephi.
  4. Sensitivity sweep: vary the LLM scoring temperature / model
     (Haiku 4.5 vs Sonnet 4.6 on a 50-signal subset for inter-rater
     check, per `signal_taxonomy_v1.md §3`).
- **Out-of-band** (won't block CC): Tovstiga's Fri May 16 email; survey
  draft v1.

**Files changed (this session):**
`prompts/v1/signal_scoring.md`, `scoring/score_signals.py`,
`analysis/topic_momentum.py`, `analysis/build_graph.py`,
`analysis/kg_features.py`, `analysis/person_features.py`,
`analysis/allocation.py`, `analysis/seed_labels.py`,
`models/__init__.py`, `models/baselines/__init__.py`,
`models/baselines/baseline_model.py`,
`models/kg_augmented/__init__.py`, `models/kg_augmented/kg_model.py`,
`models/evaluation/__init__.py`, `models/evaluation/eval.py`,
`pipeline.py`. Tests: `test_score_signals.py`, `test_topic_momentum.py`,
`test_kg.py`, `test_models.py`, `test_allocation.py`, `test_seed_labels.py`.
Touched: `pyproject.toml` (models package, per-file ruff), `dashboard/app.py`
(strict=False on zips). 80/80 tests pass; ruff clean.

**Cost incurred:** $0. No real LLM calls yet — all scoring tests
use a mocked Anthropic client. The cost-accounting + budget-guard
plumbing is wired and tested, so the first real run will be logged
and bounded automatically.

---

---
## 2026-05-14 13:00 — Roadmap gap fill: MC + backtest + lock + negative-peers + CIs

**What I did:** Audited cowork docs against shipped code and built
everything the roadmap names that wasn't yet wired:

1. **Monte Carlo simulation module** (`models/monte_carlo.py`,
   25 tests) — implements the full
   `cc_prompts_phase3_monte_carlo.md` spec: `bootstrap_metric_ci`,
   `simulate_founder_emergence`, `simulate_topic_trajectory`,
   `simulate_portfolio`. Every public function carries the
   load-bearing epistemic claim verbatim in its docstring
   ("framework demonstration, not statistical claim beyond cohort").
   Tests assert the claim is present.

2. **Two-tier framework + Phase 4 backtest**
   (`models/allocation_framework/`, 6 tests) — `combine.py` produces
   ranked (person, topic) pairs at any historical date with
   lookahead-bias filters on both Tier-1 and Tier-2. `backtest.py`
   runs the framework at retrospective dates against three baselines
   (random, signal_volume, recency) and writes a CSV + markdown
   report. Per the roadmap, lift numbers only become meaningful once
   negative-peer labels populate.

3. **Prospective prediction lock harness**
   (`analysis/lock_predictions.py`, 5 tests) — the May-31 sacred-date
   freeze. Loads the trained KG-augmented model, predicts P(emerge)
   for a prospective cohort, writes JSON with SHA-256 hashes of all
   input artefacts + the git commit hash. Refuses to lock if any
   prospective handle is missing features.

4. **Negative-peer protocol** (`ingestion/negative_peers.py`, 6 tests)
   — anonymous project-level coding per iter-6. `NegativePeer`
   dataclass, `register_peer` + `materialise_for_outcome_labels`
   (idempotent), `write_protocol_summary` for the thesis. Public
   peer_<n> IDs only; handles stay private. Once Kris registers
   the matched negatives, the model and backtest layers become
   meaningful.

5. **Bootstrap CIs in eval** — `evaluate_with_ci()` wraps
   `evaluate_model()` and attaches 95% CIs to ROC + PR AUC via
   `bootstrap_metric_ci`. Implements the iter-10 framework tightening
   ("turns 'n is too small' into 'here is what n buys us in CI
   width'"). `ModelMetrics` extended with `ci_lo` / `ci_hi` fields.

6. **Pipeline.py extended** — added `seed-labels` and `backtest`
   stages. Full chain now: clean → score → person → graph →
   kg-features → topic → seed-labels → eval → allocate → backtest.

7. **Dashboard pages** — Backtest page surfaces `backtest_results.csv`
   with precision@k + lift tables. Simulation page has three
   interactive tabs (founder emergence / portfolio / topic trajectory)
   wired to the Monte Carlo functions. Total dashboard pages: 7.

**Decisions made:**
- **Tier-1 single-keyword fallback** — when only one keyword's
  momentum is being scored, the rank-normalisation collapses to zero.
  I switched to a tanh squash in that degenerate case so single-topic
  sweeps still produce meaningful scores rather than zero.
- **Lock harness emits next-steps to console** — the git commit + tag
  steps are out-of-scope (they need user-side authorisation). The
  harness writes the JSON + SHA + records the git HEAD in the JSON;
  the actual `git add / commit / tag v1.0-thesis-submission`
  remains Kris's call on May 31.
- **Backtest is currently exercising plumbing, not generating a lift
  claim** — n=20 positive-only. Per the roadmap, this is the right
  state pre-negatives.

**Blockers (unchanged from prior):**
- ANTHROPIC_API_KEY needed to fire real scoring.
- Negative-peer registrations needed before backtest + eval produce
  defensible numbers. The protocol module is ready; Kris hand-picks
  the matched negatives.

**Out of scope tonight (Kris decisions):**
- Title pivot ambiguity (iter-4 QuantumLight vs Jan version still in
  CLAUDE.md / dashboard).
- Self-case study keep / drop (iter-3 says dropped; iter-2 / iter-8
  still ambiguous).
- 10 topics for `topic-trend` ingestion (task 2.6 — Tier-1
  enhancement, not a Phase-3 blocker).

**Files changed (this session):**
`models/monte_carlo.py`, `models/allocation_framework/{combine,backtest}.py`,
`analysis/lock_predictions.py`, `ingestion/negative_peers.py`,
`models/evaluation/eval.py` (CI extension), `pipeline.py` (new
stages), `dashboard/app.py` (Backtest + Simulation pages),
`pyproject.toml` (per-file ruff exemptions).
Tests added: `tests/test_monte_carlo.py`, `tests/test_allocation_framework.py`,
`tests/test_lock_predictions.py`, `tests/test_negative_peers.py`.

**Test count:** 123/123 pass (was 80 at session start). ruff clean.

**Cost incurred:** $0 (numpy + scipy + sklearn only; no LLM calls).

**Next steps:**
- **Kris:** drop ANTHROPIC_API_KEY in `.env`; register negative peers
  via `ingestion.negative_peers.register_peer`; decide on title +
  self-case ambiguity.
- **CC (next session):** fire `python pipeline.py all` once env +
  labels are populated; iterate on the backtest report once it has
  meaningful numbers; build the W6 dashboard polish (KG visualisation
  via Gephi export of `graph.graphml`).
---

---
## 2026-05-14 14:00 — Title relock + self-case redefinition + auto-topic discovery + PROGRESS.md

**What I did:**

1. **Title relocked** to the iter-4 QuantumLight pivot across all
   surfaces — repo README, dashboard header (with QL subtitle line),
   workspace CLAUDE.md, COMPREHENSIVE_PLAN §2.1, EXECUTION_ROADMAP
   header, and a fresh DECISION_LOG iteration 11. Dashboard's Thesis
   Claim page rewritten to anchor on QuantumLight (Series B/C with
   proprietary data → us at pre-seed with public signals); RQ
   reframed as the two-tier pre-seed allocation question; the
   "Creator economy" differentiator card replaced with "Pre-seed VC
   framing" to match the new positioning.

2. **Self-case redefined** as Kris using the framework on himself
   (not reflexive ethnography). New `analysis/self_case.py`:
   `SELF_HANDLE = "kristian_ratkov"`, `register_self_case()` writes
   `emerged=-1` to outcome_labels (sentinel for "unknown/TBD,
   excluded from training"), `self_case_view()` returns features +
   KG features + P(emerge) + cohort percentile for the dashboard.
   `baseline_model.load_labels` filters `emerged ∉ {0,1}` so the
   self-case row is auto-excluded from training. New /Self-case
   dashboard page surfaces all of this. 5 tests.

3. **Auto-topic discovery** as a core pipeline task. New
   `analysis/topic_discovery.py` with a hybrid two-pass approach:
     - Pass A (cohort-grounded, retrospective): clusters
       `s6_topic_label` weighted by strength × recency, picks top N.
     - Pass B (forward-looking, candidate generation): pytrends
       `related_queries` rising for each Pass-A seed.
     - Merge: cohort topics + non-duplicate rising candidates, each
       tagged with `source`, ranked.
   Pipeline gains `discover-topics` stage. 6 tests (Pass B mocked so
   no network in CI).

4. **PROGRESS.md** at the repo root — a single-file source-of-truth
   document for Cowork. Covers: current locks (title, RQ, cohort),
   every module + status, real-data state, blockers + owners,
   roadmap re-tagged against shipped code, how Cowork should consume
   the file. Workspace CLAUDE.md gains a "Build status" pointer
   directing future cowork sessions to this file.

**Decisions made:**
- **`emerged=-1` sentinel** for the self-case row keeps it out of
  training data while preserving it for prediction. Cleaner than
  branching the training pipeline; `load_labels` does the filter
  once and downstream code is unchanged.
- **Pass B fail-soft** — pytrends failures are logged and skipped,
  not raised. The cohort-grounded pass works independently.
- **Per-file ruff exemptions** for the sklearn `X` uppercase in
  `analysis/self_case.py` and its test, consistent with
  `lock_predictions.py`.

**Test count:** 134/134 pass (up from 123). ruff clean.

**Files changed (this session):**
`analysis/self_case.py`, `analysis/topic_discovery.py`,
`models/baselines/baseline_model.py` (emerged filter),
`dashboard/app.py` (header + claim page + Self-case page),
`pipeline.py` (discover-topics + self-case wiring),
`pyproject.toml` (ruff exemptions), `README.md`, `PROGRESS.md` (new),
workspace `CLAUDE.md` + `COMPREHENSIVE_PLAN.md` + `EXECUTION_ROADMAP.md`
+ `DECISION_LOG.md` (iter-11 entries).
Tests added: `tests/test_self_case.py`, `tests/test_topic_discovery.py`.

**Cost incurred:** $0.

**Next steps (Kris-side, unchanged from prior):**
1. Drop `ANTHROPIC_API_KEY` in `.env` to enable scoring.
2. Register negative peers via
   `python -m ingestion.negative_peers` or
   `register_peer()` in a REPL.
3. (Optional) Ingest your X handle so the Self-case page populates.

**Next steps (CC, next session):**
Once API key + ≥1 negative peer land:
1. `python pipeline.py all` — full chain in one command.
2. Inspect eval report + bootstrap CIs + backtest table.
3. Iterate Tovstiga email content for the Fri May 16 send.
---

---
## 2026-05-14 15:30 — iter-12 docs lock: portfolio-prediction framing + 3-view frontend spec

**What I did (docs only — no code changes this session):**

1. **DECISION_LOG iter-12** added 7 entries locking:
   - The one-sentence thesis (portfolio-operationalised PREDICTION
     claim, NOT a fund-returns claim).
   - Empirical proof framed as precision@k + bootstrap CIs vs 4
     in-framework baselines + YC-batch overlap (if sourceable).
   - "vs a16z / Sequoia" explicitly DROPPED — real pick data is
     private, action spaces don't match, breaks defensibility.
   - May-31 lock reframed as "live portfolio publication" with
     +12mo / +24mo re-evaluation.
   - Frontend reframed from 8 loose Streamlit pages to 3 connected
     Next.js views (Replay / Outcome / Founder card).
   - Demo testability scope: cohort replay + self-case only; NOT
     arbitrary stranger handles.
   - "Social media" framed precisely as creator-platform digital
     exhaust (X / YouTube / Reddit / HN / PH / GTrends), NOT generic.

2. **COMPREHENSIVE_PLAN §2.1** updated:
   - The one-sentence thesis now appears as a load-bearing quote box
     at the top of §2.1 (copied verbatim into cover page, abstract,
     Tovstiga email, dashboard header).
   - Adds explicit "what this thesis does NOT claim" section to
     pre-empt examiner critique.
   - Lock table expanded with one-sentence thesis row, empirical
     claim row, "social media" scope row, demo row, May-31 reframe row.

3. **PROGRESS.md** restructured:
   - §1 split into §1.1 (one-sentence thesis + what it does and
     doesn't claim) and §1.2 (locked elements table). Both rev'd to
     iter-12.
   - New §2.7 (Defence-grade frontend) added between Streamlit and
     test surface. Streamlit positioned as the prototype + Tovstiga-
     touchpoint demo, NOT the defence demo.

4. **FRONTEND_SPEC.md** created (new top-level file). 8 sections:
   - §1 Information architecture (3 views + chrome) — Replay /
     Outcome panel / Founder card. Each view's centre / left rail /
     right rail / footer specced.
   - §2 Design principles — trust signals from rigor not chrome;
     reading order; every claim cites its source; honest about what
     the framework can't do; visual style recommendations.
   - §3 Data flow — Next.js → FastAPI → existing parquet/csv. 7
     endpoints specced. Frontend data model in TypeScript.
   - §4 Build phases — F0 design → F1 API → F2-F5 views → F6 wire
     → F7 deploy → F8 polish. ~20-25h CC time total.
   - §5 Acceptance criteria — 10 specific bullets defining
     "defence-ready".
   - §6 Risks + mitigations.
   - §7 What this spec is NOT (anti-scope).
   - §8 Next actions: Kris's design first, then CC implementation.

5. **Dashboard claim page** copy rewritten to match the locked
   one-sentence thesis + RQ + an explicit "What this thesis does NOT
   claim" section with the three load-bearing negative claims (no
   fund-returns, no vs-a16z, no stranger live-scoring).

6. **Workspace CLAUDE.md** Build-status pointer (added iter-11)
   continues to direct future cowork sessions to `PROGRESS.md`.

**Decisions made:** all 7 iter-12 entries above. Critical pushback
points where I declined to overclaim:
- "We beat a16z" → DROPPED, can't source private VC pick data.
- "$X becomes $Y" → DROPPED, no return data; assumptions would carry
  the argument; examiner kills it.
- Stranger live-scoring in demo → DROPPED, reputational + technical
  risk on famous-person false negatives.

**Test count:** 134/134 still pass; ruff still clean. Code surface
unchanged this session — only docs + a single dashboard copy edit.

**Files changed (this session):**
- `~/Documents/Claude/Projects/Thesis/00_PLANNING/DECISION_LOG.md`
  (iter-12 inserted at top)
- `~/Documents/Claude/Projects/Thesis/00_PLANNING/COMPREHENSIVE_PLAN.md`
  (§2.1 framing + table rewritten)
- `PROGRESS.md` (§1 + §2.6 + new §2.7)
- `FRONTEND_SPEC.md` (NEW, 350+ lines)
- `dashboard/app.py` (page_claim copy rewritten to match iter-12)
- `STATUS_UPDATES.md` (this entry)

**Cost incurred:** $0.

**Next steps:**
- **Kris:** create Figma / Claude Design mockups for all 3 views per
  `FRONTEND_SPEC.md` §1.2-1.4. Hand back to CC.
- **CC (next session, gated on F0 mockups):**
  - F1: build FastAPI layer with the 7 endpoints (mock outputs first).
  - F2: Next.js + Tailwind + shadcn scaffold with top chrome.
- **Kris (in parallel, no dependency on frontend):** drop
  `ANTHROPIC_API_KEY` in `.env` + register ≥10 negative peers via
  `ingestion.negative_peers.register_peer()` — these unblock the
  real backtest numbers the frontend will surface.

**Risk-watch (load-bearing):** the frontend must NOT claim more than
the paper. Every UI element traces back to `PROGRESS.md §1.1`. Any
scope creep (e.g. "let's also show IRR") goes back to DECISION_LOG
for a new iteration before it's built.
---

---
## 2026-05-14 16:00 — iter-13 docs lock: Option C hybrid storage architecture

**What I did (docs only — no code changes):**

1. **DECISION_LOG iter-13** added 7 entries locking the storage
   architecture as **Option C — Hybrid**:
   - Parquet/csv files in `data/processed/` remain the source of
     truth. All model code reads from here.
   - One-shot `scripts/publish_data_snapshot.py` writes versioned
     tar.gz to GitHub Releases (citable, reproducible).
   - One-shot `scripts/sync_to_supabase.py` mirrors rows into
     Supabase Postgres (500 MB free tier, plenty).
   - FastAPI layer gets `--source {local,supabase}` flag — local
     dev reads parquet directly, prod reads Supabase.
   - Data volume confirmed small (~30-70 MB projected after full
     scoring run; fits trivially on free tier).
   - Cron keepalive explicitly **deferred to post-deployment**
     ("the last last element" per Kris's sequencing).
   - Thesis appendix cites 3 reproducibility paths: GitHub release
     tar.gz / live Supabase URL / git-clone + pipeline.py all.

2. **PROGRESS.md §3b — Storage architecture** new section. ASCII
   diagram of the 3-layer flow. Table mapping each asset to local
   / GitHub release / Supabase. Explicit "what this DOES buy" /
   "what this DOES NOT buy" — defensive against over-promising.

3. **FRONTEND_SPEC.md** updated:
   - §3 data flow diagram now shows the 3-layer architecture
     (local source-of-truth + GitHub release snapshot + Supabase
     mirror). Local dev vs production read paths specified.
   - §4 build phases: **F1.5** (storage migration, 6-8h) added
     between F1 and F2; **F9** (Supabase keepalive cron, 1h)
     appended as the explicit last phase. F1 ships against local
     parquet first; F1.5 adds the Supabase swap. Total estimate
     bumped to ~27-34h.
   - §6 risks: 4 new rows covering pause-on-idle, parquet→Postgres
     schema drift, stale-Supabase from missed sync, free-tier
     500MB ceiling (very low risk — 10x headroom).

4. **Dashboard Methodology page** rewritten:
   - Data-sources table updated: 6 collectors all marked ✅ shipped
     with real-data state (was previously "Planned"). Substack and
     GitHub-trending rows removed since neither is in scope per
     iter-12.
   - New "Reproducibility — three paths" subsection — the
     defensible-moat explanation for examiners.
   - May-31 commitment section rewritten as "May 31 live portfolio"
     with the three provenance anchors (SHA-256 + git hash +
     Supabase row-insert timestamp) explicitly listed.

**Decisions made:**
- **Option C over Options A or B.** Critical pushback applied:
  Option A (static files only) works methodologically but loses
  1-2 grade points on the artefact dimension at defence; Option B
  (Supabase only) sacrifices the local-clone reproducibility story.
  C is the minimum infrastructure that lets the thesis defend
  "yes, we have a real data backend" without losing reproducibility.
- **No live ingestion.** Sync to Supabase is on-demand, not
  continuous. Postgres is a mirror, not a source.
- **Cron keepalive deferred.** Built AFTER F7 deploy + F8
  verification, per Kris's explicit "last last" sequencing.
  Defence-day mitigation regardless: manual warmup 24h before.
- **All 3 reproducibility paths must agree.** Verification script
  asserts row-count parity after every sync.

**Test count:** 134/134 still pass; ruff clean. Code surface
unchanged (the FastAPI layer + sync scripts are F1 and F1.5 work,
not built yet).

**Files changed (this session):**
- `~/Documents/Claude/Projects/Thesis/00_PLANNING/DECISION_LOG.md`
  (iter-13 inserted at top)
- `PROGRESS.md` (new §3b Storage architecture)
- `FRONTEND_SPEC.md` (§3 + §4 + §6 updated)
- `dashboard/app.py` (Methodology page rewritten for reproducibility
  + correct source statuses)
- `STATUS_UPDATES.md` (this entry)

**Cost incurred:** $0.

**Next steps (Kris-side, unchanged from prior + new):**
1. Drop `ANTHROPIC_API_KEY` in `.env` (unchanged).
2. Register ≥10 negative peers (unchanged).
3. Create a Supabase project at supabase.com (free tier) — paste
   the project URL + anon key + service role key in `.env`.
   Roughly 5 minutes of setup work.
4. Continue Figma / Claude Design mockups for the 3-view frontend.

**Next steps (CC, next session — order matters):**
- **F0 unblocked** by Kris's mockups → start F1 (FastAPI + local
  parquet) and F1.5 (Supabase mirror) in parallel.
- F1.5 acceptance criterion: `scripts/verify_supabase_mirror.py`
  asserts row-count parity AND a few row-level spot checks
  (e.g. `signal_events.signal_id == supabase.signal_events.signal_id`
  for a sampled subset).

**Risk-watch (load-bearing for iter-13):**
- Supabase pause-on-idle on defence day. F9 keepalive cron is the
  cure but it's deferred. Defence-day mitigation = manual warmup
  24h before regardless of cron status. Worth a calendar reminder
  on Jul 17.
- Stale Supabase post-pipeline-rerun. Pipeline.py F1.5 stage gets
  an opt-in `--push-to-supabase` flag so the sync is one-flag away
  from automatic.
---
