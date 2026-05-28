"""Weights and thresholds for `ranking.rank_handles`.

All numeric constants live here so they're easy to tweak from one place and
easy to re-derive from data once negative-peer signals exist (B2.b in
PROGRESS.md). Today's placeholders are rooted in the empirical Σ distribution
across the 9-person scored cohort:

    per-person Σ on 2026-05-20:  thejustinwelsh < lennysan < ucx6... <
                                 anthilemoon < pg < marclou < dickiebush <
                                 arvidkahl < dvassallo
    quantiles:                   p25=0.086  p50=0.143  p75=0.193  max=0.294

So the thresholds are picked so the cohort splits roughly:

    Σ ≥ 0.15   → tracked   (dvassallo, arvidkahl, dickiebush, marclou)
    Σ ≥ 0.085  → watchlist (+ pg, anthilemoon)
    else       → pass

The CI-tightness gates (`SIGMA_CI_LOWER_TRACKED`, `SIGMA_CI_UPPER_WATCHLIST`)
make a handle's verdict robust to the bootstrap interval, not just the point
estimate.

When B2.b lands and negatives are scored, re-derive in this order:

    SIGMA_TRACKED     ← (positive_median + negative_median) / 2
    SIGMA_WATCHLIST   ← negative_p75
    SIGMA_CI_LOWER_TRACKED   ← negative_p75
    SIGMA_CI_UPPER_WATCHLIST ← negative_p90
"""
from __future__ import annotations

from pathlib import Path

# ---------------------------------------------------------------------------
# Tier weights (Σ_i = w_T1 * T1_i + w_T2 * T2_i)
# ---------------------------------------------------------------------------

W_T1: float = 0.4
W_T2: float = 0.6

# ---------------------------------------------------------------------------
# Verdict thresholds
# TODO(B2.b): re-derive from negative-peer Σ distribution once available.
# ---------------------------------------------------------------------------

SIGMA_TRACKED: float = 0.15
SIGMA_CI_LOWER_TRACKED: float = 0.10
SIGMA_WATCHLIST: float = 0.085
SIGMA_CI_UPPER_WATCHLIST: float = 0.15

# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------

N_BOOTSTRAP: int = 1_000
CI_PCT: float = 0.90  # ⇒ 5th / 95th percentile

# ---------------------------------------------------------------------------
# Cold-handle compute budget (seconds) before /api/rank returns 202
# ---------------------------------------------------------------------------

COMPUTE_BUDGET_SEC: float = 30.0

# ---------------------------------------------------------------------------
# IO paths
# ---------------------------------------------------------------------------

SCORED_SIGNALS_PATH: Path = Path("data/processed/scored_signals.parquet")
HANDLE_VERDICTS_PATH: Path = Path("data/processed/handle_verdicts.parquet")
LLM_LOG_PATH: Path = Path("data/interim/llm_run_log.jsonl")

# ---------------------------------------------------------------------------
# Default LLM for the verdict rationale (Haiku per CLAUDE.md §3)
# ---------------------------------------------------------------------------

RATIONALE_MODEL: str = "claude-haiku-4-5-20251001"
RATIONALE_PROMPT_PATH: Path = Path("ranking/prompts/v1/verdict_rationale.md")
RATIONALE_PROMPT_VERSION: str = "v1"
RATIONALE_MAX_TOKENS: int = 220

# Hard $25 ceiling at which we stop spending; absolute hard stop is $30 in
# CLAUDE.md §3. Surfaced from `scoring.score_signals.running_cost_usd`.
COST_CEILING_USD: float = 25.0
