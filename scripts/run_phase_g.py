"""Phase G orchestrator — multi-date backtest, robustness sweep, Monte Carlo.

Produces the four Phase-G CSVs (the timeline CSVs come from
`analysis.discovery_timeline`):

  data/processed/backtest_results.csv      (multi-date, 5 strategies)
  data/processed/robustness_sweep.csv      (alpha × K × window)
  data/processed/monte_carlo_projection.csv (K ∈ {5,10,20,50,100})

All three are lookahead-safe: rankings at each date T use only signals <= T
(enforced in `combine.combined_ranking`). Monte Carlo is explicitly framed as a
framework demonstration, not a claim beyond the cohort.

Usage: python -m scripts.run_phase_g
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from models.allocation_framework.backtest import _load_labels, _precision_at_k, run_backtest
from models.allocation_framework.combine import TierConfig, combined_ranking
from models.monte_carlo import simulate_portfolio

logger = logging.getLogger(__name__)

_SCORED = Path("data/processed/scored_signals.parquet")
_TRENDS = Path("data/interim/topic_momentum.parquet")
_LABELS = Path("data/processed/outcome_labels.csv")
_BACKTEST_CSV = Path("data/processed/backtest_results.csv")
_ROBUSTNESS_CSV = Path("data/processed/robustness_sweep.csv")
_MC_CSV = Path("data/processed/monte_carlo_projection.csv")


def monthly_grid(start: str = "2018-01-01", end: str | None = None) -> list[datetime]:
    end_ts = pd.Timestamp(end) if end else pd.Timestamp.now()
    grid = pd.date_range(start=start, end=end_ts, freq="MS")
    return [d.to_pydatetime() for d in grid]


# ---------------------------------------------------------------------------
# 1. Multi-date backtest (delegates to run_backtest with a monthly grid)
# ---------------------------------------------------------------------------


def run_multi_date_backtest() -> pd.DataFrame:
    grid = monthly_grid()
    logger.info("multi-date backtest over %d monthly dates", len(grid))
    return run_backtest(
        backtest_dates=grid,
        k_values=(3, 5, 10),
        scored_path=_SCORED,
        trends_path=_TRENDS,
        labels_path=_LABELS,
        out_csv=_BACKTEST_CSV,
    )


# ---------------------------------------------------------------------------
# 2. Robustness sweep: alpha × K × window
# ---------------------------------------------------------------------------


def run_robustness_sweep(
    alphas=(0.0, 0.25, 0.5, 0.75, 1.0),
    ks=(5, 10, 20),
    windows_months=(6, 12),
    eval_dates: list[datetime] | None = None,
) -> pd.DataFrame:
    """precision@K for the two-tier ranking under each (alpha, K, window).

    `window` truncates each ranking date's scored signals to the trailing
    `window` months (a recency window the framework could plausibly use).
    Precision is averaged across `eval_dates`.
    """
    labels = _load_labels(_LABELS)
    positives = set(labels[labels["emerged"] == 1]["person_id"].astype(str))
    if eval_dates is None:
        # A few representative dates across the cohort emergence span.
        eval_dates = [datetime(2021, 1, 1), datetime(2022, 1, 1),
                      datetime(2023, 1, 1), datetime(2024, 1, 1)]

    rows: list[dict] = []
    for alpha in alphas:
        cfg = TierConfig(alpha=alpha)
        for window in windows_months:
            for k in ks:
                precisions: list[float] = []
                for date_t in eval_dates:
                    win_start = date_t - pd.DateOffset(months=window)
                    ranked = _windowed_ranking(date_t, win_start.to_pydatetime(), cfg)
                    precisions.append(_precision_at_k(ranked, positives, k))
                rows.append(
                    {
                        "alpha": alpha,
                        "k": k,
                        "window_months": window,
                        "mean_precision_at_k": float(np.mean(precisions)),
                        "n_eval_dates": len(eval_dates),
                    }
                )
    df = pd.DataFrame(rows)
    _ROBUSTNESS_CSV.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(_ROBUSTNESS_CSV, index=False)
    print(f"robustness sweep | {len(df)} rows (alpha×K×window) -> {_ROBUSTNESS_CSV}")
    return df


def _windowed_ranking(date_t: datetime, win_start: datetime, cfg: TierConfig) -> list[str]:
    """Two-tier ranking at date_t, restricted to signals in [win_start, date_t).

    Implemented by truncating the scored parquet to the window into a temp
    view via combined_ranking's date filter plus a manual lower-bound prune.
    """
    import pyarrow.parquet as pq  # noqa: PLC0415

    if not _SCORED.exists():
        return []
    df = pq.read_table(_SCORED).to_pandas()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    lo = pd.Timestamp(win_start, tz="UTC")
    hi = pd.Timestamp(date_t, tz="UTC")
    windowed = df[(df["timestamp"] >= lo) & (df["timestamp"] < hi)]
    if len(windowed) == 0:
        return []
    tmp = _SCORED.parent / "_robustness_window.parquet"
    windowed.to_parquet(tmp, index=False)
    try:
        ranked = combined_ranking(date_t, cfg=cfg, scored_path=tmp, trends_path=_TRENDS)
        return ranked["person_id"].drop_duplicates().tolist() if len(ranked) else []
    finally:
        tmp.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# 3. Monte Carlo portfolio projection
# ---------------------------------------------------------------------------


def _emergence_probs() -> np.ndarray:
    """Per-person emergence probabilities, derived from the final tier2 scores.

    Min-max normalised into [0.05, 0.95] so the simulation has non-degenerate
    priors. Framework demonstration only.
    """
    from analysis.discovery_timeline import score_at  # noqa: PLC0415

    final = score_at(pd.Timestamp.now(tz="UTC"), scored_path=_SCORED)
    if len(final) == 0:
        return np.array([])
    s = final["score"].to_numpy(dtype=float)
    if s.max() == s.min():
        return np.full(len(s), 0.3)
    norm = (s - s.min()) / (s.max() - s.min())
    return 0.05 + 0.90 * norm


def run_monte_carlo(ks=(5, 10, 20, 50, 100), n_iter: int = 10_000) -> pd.DataFrame:
    probs_all = np.sort(_emergence_probs())[::-1]  # strongest first
    rows: list[dict] = []
    for k in ks:
        if len(probs_all) == 0:
            continue
        # Top-K portfolio (pad by sampling with replacement if cohort < K, so
        # the "framework demonstration" can project larger funds honestly).
        if len(probs_all) >= k:
            probs = probs_all[:k]
        else:
            reps = int(np.ceil(k / len(probs_all)))
            probs = np.tile(probs_all, reps)[:k]
        weights = np.full(k, 1.0 / k)
        _, summary = simulate_portfolio(probs, weights, n_iter=n_iter, random_seed=42)
        rows.append(
            {
                "k": k,
                "n_iter": n_iter,
                "mean_emergence_rate": summary["mean"],
                "rate_lower_ci_95": summary["lower_ci"],
                "rate_upper_ci_95": summary["upper_ci"],
                "n_winners_mean": summary["n_winners_mean"],
                "n_winners_lower_ci_95": summary["n_winners_lower_ci"],
                "n_winners_upper_ci_95": summary["n_winners_upper_ci"],
                "concentration_hhi": summary["concentration_hhi"],
            }
        )
    df = pd.DataFrame(rows)
    _MC_CSV.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(_MC_CSV, index=False)
    print(f"monte carlo | {len(df)} rows (K∈{list(ks)}) -> {_MC_CSV}")
    return df


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    bt = run_multi_date_backtest()
    rob = run_robustness_sweep()
    mc = run_monte_carlo()
    # Headline rows.
    print("\n=== headline ===")
    if len(bt):
        tt = bt[bt["strategy"] == "two_tier"]
        print("two_tier mean precision@5:",
              round(tt[tt["k"] == 5]["precision_at_k"].mean(), 3))
    if len(rob):
        best = rob.loc[rob["mean_precision_at_k"].idxmax()]
        print("best robustness cell:", best.to_dict())
    if len(mc):
        print("MC K=20 mean emergence rate:",
              round(float(mc[mc["k"] == 20]["mean_emergence_rate"].iloc[0]), 3))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
