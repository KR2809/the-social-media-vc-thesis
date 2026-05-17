"""Auto-topic discovery (Phase 3 framework extension, 2026-05-14 lock).

Per `DECISION_LOG.md` iter-11: the framework discovers its own topics
rather than having them hand-fed. Hybrid two-pass approach:

  Pass A — cohort-grounded (retrospective).
    Cluster the `s6_topic_label` field on scored_signals.parquet,
    weight each topic by (frequency × mean_strength × recency_decay),
    rank descending. This is the "what does our cohort actually talk
    about" view.

  Pass B — Trends-driven (forward-looking).
    For each top-N cohort topic, query pytrends `related_queries`
    for "rising" terms. These are candidate topics that may not yet
    appear in our cohort signal stream but are gaining search
    momentum — useful for Tier-1 forward-looking detection.

  Merge: the discovered topic list = top cohort topics (Pass A) ∪
  highest-rising Pass-B candidates that don't already appear in A.
  Each topic carries a `source` tag ("cohort" / "trends_rising")
  and a normalised score.

Output:
  - `data/processed/discovered_topics.csv`
  - returned DataFrame for live use by the dashboard

The discovered topics feed `ingestion/trends_collect.py` (for momentum
sweeps) and `analysis/topic_momentum.py` (for downstream metrics).
"""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

logger = logging.getLogger(__name__)

_SCORED_DEFAULT = Path("data/processed/scored_signals.parquet")
_OUT_DEFAULT = Path("data/processed/discovered_topics.csv")


def _recency_decay(timestamp: pd.Timestamp, now: pd.Timestamp, half_life_days: float) -> float:
    age_days = (now - timestamp).total_seconds() / 86400.0
    if age_days <= 0:
        return 1.0
    return float(2 ** (-age_days / half_life_days))


def cohort_topic_ranking(
    scored_path: Path = _SCORED_DEFAULT,
    now: datetime | None = None,
    half_life_days: float = 365.0,
    min_signals: int = 2,
) -> pd.DataFrame:
    """Pass A — rank topics observed in the cohort's scored signals.

    Score per topic = sum_over_signals(strength × recency_decay).
    Topics with fewer than `min_signals` are dropped to denoise.
    """
    if not scored_path.exists():
        return pd.DataFrame(
            columns=["topic", "n_signals", "mean_strength", "raw_score", "norm_score"]
        )
    df = pq.read_table(scored_path).to_pandas()
    if len(df) == 0:
        return pd.DataFrame(
            columns=["topic", "n_signals", "mean_strength", "raw_score", "norm_score"]
        )
    df = df[df["s6_topic_label"].notna() & (df["s6_topic_label"] != "")]
    if len(df) == 0:
        return pd.DataFrame(
            columns=["topic", "n_signals", "mean_strength", "raw_score", "norm_score"]
        )

    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df["strength"] = df["overall_signal_strength"].fillna(0.0)
    now_value = now or datetime.now(UTC)
    now_ts = pd.Timestamp(now_value)
    if now_ts.tzinfo is None:
        now_ts = now_ts.tz_localize("UTC")
    else:
        now_ts = now_ts.tz_convert("UTC")
    df["recency"] = df["timestamp"].apply(
        lambda t: _recency_decay(t, now_ts, half_life_days)
    )
    df["weight"] = df["strength"] * df["recency"]
    df["topic_norm"] = df["s6_topic_label"].str.lower().str.strip()

    grouped = (
        df.groupby("topic_norm")
        .agg(
            n_signals=("signal_id", "count"),
            mean_strength=("strength", "mean"),
            raw_score=("weight", "sum"),
        )
        .reset_index()
        .rename(columns={"topic_norm": "topic"})
    )
    grouped = grouped[grouped["n_signals"] >= min_signals]
    if len(grouped) == 0:
        return grouped.assign(norm_score=[])

    max_score = grouped["raw_score"].max() or 1.0
    grouped["norm_score"] = grouped["raw_score"] / max_score
    return grouped.sort_values("raw_score", ascending=False).reset_index(drop=True)


def trends_related_topics(
    seed_topics: list[str],
    geo: str = "",
    rate_limit_sec: float = 2.0,
    max_per_seed: int = 5,
) -> pd.DataFrame:
    """Pass B — pytrends `related_queries` rising for each seed term.

    Skips seeds that don't return rising terms; failures are logged
    and don't abort the run. Returns a DataFrame with columns
    (topic, seed, rising_score) where rising_score is the pytrends
    "value" (relative search momentum, no fixed scale).
    """
    try:
        from pytrends.request import TrendReq  # noqa: PLC0415
    except ImportError:
        logger.warning("pytrends not installed; Pass B returns empty")
        return pd.DataFrame(columns=["topic", "seed", "rising_score", "source"])

    pytrends = TrendReq()
    rows: list[dict] = []
    for seed in seed_topics:
        try:
            pytrends.build_payload([seed], timeframe="today 12-m", geo=geo)
            related = pytrends.related_queries()
            rising = (related.get(seed) or {}).get("rising")
            if rising is None or len(rising) == 0:
                continue
            for _, r in rising.head(max_per_seed).iterrows():
                rows.append(
                    {
                        "topic": str(r["query"]).lower().strip(),
                        "seed": seed,
                        "rising_score": float(r["value"]),
                        "source": "trends_rising",
                    }
                )
        except Exception as exc:
            logger.warning("trends related_queries failed for %r: %s", seed, exc)
            continue
        time.sleep(rate_limit_sec)
    return pd.DataFrame(rows)


def discover_topics(
    scored_path: Path = _SCORED_DEFAULT,
    out_path: Path = _OUT_DEFAULT,
    top_cohort_n: int = 10,
    trends_max_per_seed: int = 3,
    geo: str = "",
    skip_trends: bool = False,
    now: datetime | None = None,
) -> pd.DataFrame:
    """Run both passes and write the unified ranked list.

    Returns the DataFrame; also writes to `out_path` (CSV).

    The output schema:
        topic                str — lowercase, stripped
        source               str — "cohort" or "trends_rising"
        n_signals            int — Pass A only (NaN for Pass B)
        mean_strength        float — Pass A only
        cohort_score         float — normalised Pass A score (0–1)
        rising_score         float — Pass B raw value (NaN for Pass A)
        rank                 int — final rank in the merged list
    """
    a = cohort_topic_ranking(scored_path=scored_path, now=now)
    a_top = a.head(top_cohort_n).copy()
    a_top["source"] = "cohort"
    a_top = a_top.rename(columns={"norm_score": "cohort_score"})
    a_top["rising_score"] = np.nan

    if skip_trends or len(a_top) == 0:
        b = pd.DataFrame(columns=["topic", "seed", "rising_score", "source"])
    else:
        b = trends_related_topics(
            seed_topics=a_top["topic"].tolist(),
            geo=geo,
            max_per_seed=trends_max_per_seed,
        )

    # Drop trends rows whose topic already appears in cohort.
    if len(b):
        b = b[~b["topic"].isin(set(a_top["topic"]))]
        b["n_signals"] = np.nan
        b["mean_strength"] = np.nan
        b["cohort_score"] = np.nan
        b["raw_score"] = np.nan

    out_cols = [
        "topic", "source", "n_signals", "mean_strength",
        "cohort_score", "rising_score",
    ]
    a_part = a_top[["topic", "source", "n_signals", "mean_strength",
                    "cohort_score", "rising_score"]] if len(a_top) else pd.DataFrame(columns=out_cols)
    b_part = b[["topic", "source", "n_signals", "mean_strength",
                "cohort_score", "rising_score"]] if len(b) else pd.DataFrame(columns=out_cols)

    out = pd.concat([a_part, b_part], ignore_index=True)
    out["rank"] = range(1, len(out) + 1)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(out_path, index=False)
    cohort_n = (out["source"] == "cohort").sum()
    rising_n = (out["source"] == "trends_rising").sum()
    print(
        f"discovered_topics | {len(out)} total | cohort={cohort_n} "
        f"trends_rising={rising_n} | written to {out_path}"
    )
    return out


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    discover_topics()
