# CLAUDE.md — the-social-media-vc-thesis

This file is read automatically by Claude Code on every session. It defines
how to work in this repo.

## 1. First-session orientation (read these BEFORE editing anything)

This code repo lives outside the thesis workspace tree. Reference docs are
in `~/Documents/Claude/Projects/Thesis/`. Read in order:

1. `/Users/k.ratkov/Documents/Claude/Projects/Thesis/CLAUDE.md` — workspace-level
   rules, EDHEC compliance, voice rules, AI delegation pattern
2. `/Users/k.ratkov/Documents/Claude/Projects/Thesis/00_PLANNING/COMPREHENSIVE_PLAN.md` —
   strategic plan
3. `/Users/k.ratkov/Documents/Claude/Projects/Thesis/00_PLANNING/EXECUTION_ROADMAP.md` —
   week-by-week sequence
4. `/Users/k.ratkov/Documents/Claude/Projects/Thesis/11_THESIS_DOC/chapters/00_outline_v2.md` —
   locked thesis outline
5. `/Users/k.ratkov/Documents/Claude/Projects/Thesis/04_RETROSPECTIVE_CASES/cohort_verified.md` —
   the cohort
6. `/Users/k.ratkov/Documents/Claude/Projects/Thesis/03_DATA/outcome_sources_plan.md` —
   the data stack

## 2. Status reporting protocol (the way you "talk to Cowork")

After every meaningful work session, **append** an entry to
`STATUS_UPDATES.md` (this repo, root). Format:

```
---
## YYYY-MM-DD HH:MM — <short session title>

**What I did:** 1–3 bullets, factual.
**Decisions made:** any non-obvious choices and the reasoning.
**Blockers:** anything I couldn't finish + what's needed to unblock.
**Next steps:** what should happen next, who should do it (CC / Kris / Cowork).
**Files changed:** list of files added/modified in this session.
**Cost incurred:** running total of LLM API spend, if any.
---
```

`STATUS_UPDATES.md` is append-only. Newest entries at the bottom. When Kris
returns to Cowork chat, Cowork reads this file to catch up on what happened.

Also: every meaningful change should be a git commit with a descriptive
message. Use Conventional Commits: `feat:`, `fix:`, `refactor:`, `docs:`,
`chore:`, `test:`.

## 3. Hard rules

1. **Never commit secrets.** `.env` is gitignored; if you find a hardcoded
   key in any file, refuse to commit and surface it as a blocker.
2. **Never commit raw or processed data.** `data/raw/`, `data/interim/`,
   `data/processed/` are gitignored. Only the folder structure is preserved
   via `.gitkeep`.
3. **Default LLM = Claude Haiku 4.5** (cheap). Use Sonnet 4.6 only for
   taxonomy refinement, cross-case synthesis, and code review. Log every API
   call's token count + cost to `data/interim/llm_run_log.jsonl`.
4. **Hard monthly Anthropic budget: $30.** If running cost approaches $25,
   pause and surface as a blocker.
5. **Lookahead-bias discipline.** Every signal must carry a `collected_at`
   and `observed_at` timestamp. Models that predict outcomes at time T must
   only use signals with `observed_at <= T`.
6. **No paid APIs.** snscrape + Wayback for X, free public APIs for everything
   else. If a free source breaks, fall back to manual collection rather than
   spending.
7. **The May 31, 2026 prediction lock is sacred.** Once predictions are
   committed to git on that date, the framework is frozen. No retroactive
   tuning of prompts, features, weights, or model parameters.

## 4. Stack

- Python 3.11 + uv (or pip)
- pandas / polars for tabular
- networkx for KG operations (in-memory; sufficient at our scale)
- scikit-learn + statsmodels for models
- anthropic SDK for LLM scoring
- streamlit for dashboard
- pytest for tests; ruff + black for code quality

## 5. Working agreement

- Make small, focused commits. One concern per commit.
- Write a test for any non-trivial function before moving on.
- Prefer explicit, readable code over clever code. Kris is a comfortable
  reader of Python, not a writer. Optimise for him being able to skim the
  diff and understand it.
- If a task feels under-specified, **stop and ask** via `STATUS_UPDATES.md`
  rather than guessing.
