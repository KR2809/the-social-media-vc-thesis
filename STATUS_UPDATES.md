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
