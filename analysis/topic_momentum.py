"""Topic momentum analyzer (Tier-1 framework extension).

Reads `data/interim/topic_momentum.parquet` (long-format weekly Google
Trends interest per keyword) and computes per-keyword momentum metrics:

  - slope_4w     OLS slope over the most recent 4 weeks
  - slope_12w    OLS slope over the most recent 12 weeks
  - delta_4w     latest_4w_mean - prior_4w_mean
  - delta_12w    latest_12w_mean - prior_12w_mean
  - latest       most recent weekly interest value
  - peak         max interest value in the window
  - n_weeks      number of weeks in the input
  - acceleration slope_4w - slope_12w (4w slope relative to longer trend)

The "topic_momentum" framework dimension is one of the two framework
extensions documented in `signal_taxonomy_v1.md` §S6. The output of
this module powers the S6.4 topic-trajectory marker that each scored
signal inherits.

Output: `data/processed/topic_momentum_metrics.parquet`.
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

logger = logging.getLogger(__name__)

_INPUT_DEFAULT = Path("data/interim/topic_momentum.parquet")
_OUTPUT_DEFAULT = Path("data/processed/topic_momentum_metrics.parquet")


def _ols_slope(y: np.ndarray) -> float:
    """OLS slope of y vs. its index. Returns 0.0 for n<2 or all-equal y."""
    n = len(y)
    if n < 2:
        return 0.0
    x = np.arange(n, dtype=float)
    x_mean = x.mean()
    y_mean = float(y.mean())
    denom = float(((x - x_mean) ** 2).sum())
    if denom == 0.0:
        return 0.0
    return float(((x - x_mean) * (y - y_mean)).sum() / denom)


def _window_mean(arr: np.ndarray, k: int) -> float:
    if len(arr) == 0:
        return 0.0
    return float(arr[-k:].mean()) if len(arr) >= k else float(arr.mean())


def compute_keyword_metrics(df_kw: pd.DataFrame) -> dict[str, float | int]:
    """One row of metrics for a single keyword. Input must be date-sorted."""
    y = df_kw["interest"].to_numpy(dtype=float)
    n = len(y)
    slope_4 = _ols_slope(y[-4:]) if n >= 2 else 0.0
    slope_12 = _ols_slope(y[-12:]) if n >= 2 else 0.0

    latest_4 = y[-4:].mean() if n >= 1 else 0.0
    prior_4 = y[-8:-4].mean() if n >= 8 else (y[:-4].mean() if n > 4 else 0.0)
    delta_4 = float(latest_4 - prior_4)

    latest_12 = y[-12:].mean() if n >= 1 else 0.0
    prior_12 = y[-24:-12].mean() if n >= 24 else (y[:-12].mean() if n > 12 else 0.0)
    delta_12 = float(latest_12 - prior_12)

    return {
        "slope_4w": slope_4,
        "slope_12w": slope_12,
        "delta_4w": delta_4,
        "delta_12w": delta_12,
        "latest": float(y[-1]) if n else 0.0,
        "peak": float(y.max()) if n else 0.0,
        "n_weeks": int(n),
        "acceleration": float(slope_4 - slope_12),
    }


def compute_all_metrics(
    input_path: Path = _INPUT_DEFAULT,
    output_path: Path = _OUTPUT_DEFAULT,
) -> Path:
    """Read topic_momentum.parquet, compute per-keyword metrics, write parquet."""
    if not input_path.exists():
        logger.warning("no topic_momentum parquet at %s — writing empty metrics", input_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(
            columns=[
                "keyword", "geo", "slope_4w", "slope_12w", "delta_4w", "delta_12w",
                "latest", "peak", "n_weeks", "acceleration",
            ]
        ).to_parquet(output_path, index=False)
        return output_path

    df = pq.read_table(input_path).to_pandas()
    if len(df) == 0:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(
            columns=[
                "keyword", "geo", "slope_4w", "slope_12w", "delta_4w", "delta_12w",
                "latest", "peak", "n_weeks", "acceleration",
            ]
        ).to_parquet(output_path, index=False)
        print(f"topic_momentum | empty input | written to {output_path}")
        return output_path

    df = df.sort_values(["keyword", "geo", "date"])
    rows: list[dict] = []
    for (kw, geo), grp in df.groupby(["keyword", "geo"]):
        m = compute_keyword_metrics(grp)
        m["keyword"] = kw
        m["geo"] = geo
        rows.append(m)

    out = pd.DataFrame(rows)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(output_path, index=False)
    print(
        f"topic_momentum | {len(out)} keywords | "
        f"mean_n_weeks={out['n_weeks'].mean():.1f} | written to {output_path}"
    )
    return output_path


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    compute_all_metrics()
