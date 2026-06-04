"""Two-tier framework: Tier-1 topic momentum × Tier-2 founder emergence.

Iter-4 (`DECISION_LOG.md`) locked the two-tier framework:

    Tier 1: topic-trend detection → analysis/topic_momentum.py
    Tier 2: founder-emergence prediction → models/baselines + kg_augmented
    Integration: ranked allocation conditioned on Tier-1 × Tier-2

Public entry point:

    combined_ranking(date_T, top_k=20, alpha=0.5) -> DataFrame

Returns a ranked DataFrame of (person_id, topic, combined_score)
where combined_score = alpha * tier_1_score + (1 - alpha) * tier_2_score.
`alpha` is a single knob VCs can twist: 0.0 = pure founder-emergence
(Tier-2 only); 1.0 = pure topic-momentum (Tier-1 only). 0.5 = balanced.

Lookahead-bias discipline. Per `CLAUDE.md §3.5`, ranking at time T
may only use signals with `observed_at <= T`. The function applies
this filter to BOTH tiers — scored signals are filtered on
`timestamp`, topic-momentum rows on `date`. The retrospective
backtest in `backtest.py` is the primary consumer of this guard.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

logger = logging.getLogger(__name__)

_SCORED_DEFAULT = Path("data/processed/scored_signals.parquet")
_TOPIC_METRICS_DEFAULT = Path("data/processed/topic_momentum_metrics.parquet")
_TRENDS_DEFAULT = Path("data/interim/topic_momentum.parquet")
_PERSON_FEATURES_DEFAULT = Path("data/processed/person_features.parquet")


@dataclass
class TierConfig:
    """Knobs for the combined ranking."""

    alpha: float = 0.5  # weight on Tier-1 (topic momentum). 1-alpha goes to Tier-2.
    top_k: int = 20
    horizon_signal_strength: float = 0.4  # minimum signal strength to count


# ---------------------------------------------------------------------------
# Tier 1 — topic momentum score per topic
# ---------------------------------------------------------------------------


def tier1_topic_score_at(
    date_t: datetime,
    trends_path: Path = _TRENDS_DEFAULT,
) -> pd.DataFrame:
    """Per-keyword momentum score at time `date_t`, using only data <= date_t.

    Returns DataFrame with columns (keyword, slope_4w, slope_12w,
    delta_4w, acceleration, score) where `score` is a normalised 0–1
    composite of the four metrics.
    """
    trends_path = Path(trends_path)
    if not trends_path.exists():
        return pd.DataFrame(
            columns=[
                "keyword", "geo", "slope_4w", "slope_12w", "delta_4w",
                "acceleration", "score",
            ]
        )

    df = pq.read_table(trends_path).to_pandas()
    if len(df) == 0:
        return pd.DataFrame()
    df["date"] = pd.to_datetime(df["date"])
    df = df[df["date"] <= pd.Timestamp(date_t)]
    if len(df) == 0:
        return pd.DataFrame()

    # Re-compute metrics at this horizon. We import lazily because the analysis
    # module also reads from this same path in offline mode.
    from analysis.topic_momentum import compute_keyword_metrics

    rows = []
    for (kw, geo), grp in df.sort_values(["keyword", "geo", "date"]).groupby(
        ["keyword", "geo"]
    ):
        m = compute_keyword_metrics(grp)
        m["keyword"] = kw
        m["geo"] = geo
        rows.append(m)
    out = pd.DataFrame(rows)
    if len(out) == 0:
        return out

    # Composite Tier-1 score: equal-weight rank-normalised slope_4w +
    # acceleration + delta_4w. (slope_12w stays available but is a slower
    # signal — kept in the DataFrame for inspection.)
    # Fallback when only one keyword (or all identical): use a tanh squash
    # of the raw metric so a single-keyword sweep still produces a
    # meaningful score rather than collapsing to zero.
    for col in ["slope_4w", "acceleration", "delta_4w"]:
        rng = out[col].max() - out[col].min()
        if rng > 0:
            out[f"_{col}_norm"] = (out[col] - out[col].min()) / rng
        else:
            out[f"_{col}_norm"] = (np.tanh(out[col] / 10.0) + 1) / 2.0
    out["score"] = (
        out["_slope_4w_norm"] + out["_acceleration_norm"] + out["_delta_4w_norm"]
    ) / 3.0
    return out.drop(columns=[c for c in out.columns if c.startswith("_")])


# ---------------------------------------------------------------------------
# Tier 2 — founder emergence score per person
# ---------------------------------------------------------------------------


def tier2_founder_score_at(
    date_t: datetime,
    scored_path: Path = _SCORED_DEFAULT,
    cfg: TierConfig | None = None,
) -> pd.DataFrame:
    """Per-person emergence score at time `date_t`, using only signals <= date_t.

    The score is a simple per-person rollup of scored-signal strengths
    over the window. The KG-augmented logistic model is the proper
    predictor; we use the rollup here to keep the backtest's
    lookahead-bias guard auditable (no model fit happens at backtest
    time — only re-aggregation of already-scored signals).
    """
    cfg = cfg or TierConfig()
    scored_path = Path(scored_path)
    if not scored_path.exists():
        return pd.DataFrame(columns=["person_id", "score"])

    df = pq.read_table(scored_path).to_pandas()
    if len(df) == 0:
        return pd.DataFrame(columns=["person_id", "score"])
    # Defensive dedup: a duplicated signal_id would double-count a person's
    # strength in the rollup. Keep the last (newest) scored copy.
    if "signal_id" in df.columns:
        df = df.drop_duplicates(subset=["signal_id"], keep="last")
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df[df["timestamp"] <= pd.Timestamp(date_t, tz="UTC")]
    if len(df) == 0:
        return pd.DataFrame(columns=["person_id", "score"])

    # Strength-weighted aggregate of build-in-public, explicit-goal,
    # recurring-theme + overall_signal_strength.
    grouped = df.groupby("person_id").agg(
        mean_strength=("overall_signal_strength", "mean"),
        max_strength=("overall_signal_strength", "max"),
        n_signals=("signal_id", "count"),
        bip_mean=("s1_build_in_public", "mean"),
        explicit_goal_mean=("s3_explicit_goal", "mean"),
        recurring_theme_mean=("s3_recurring_theme", "mean"),
    ).reset_index()
    # Normalise n_signals (log-scaled).
    grouped["n_signals_norm"] = np.log1p(grouped["n_signals"]) / np.log1p(
        grouped["n_signals"].max() or 1
    )
    grouped["score"] = (
        0.4 * grouped["mean_strength"].fillna(0)
        + 0.15 * grouped["bip_mean"].fillna(0)
        + 0.15 * grouped["explicit_goal_mean"].fillna(0)
        + 0.1 * grouped["recurring_theme_mean"].fillna(0)
        + 0.2 * grouped["n_signals_norm"].fillna(0)
    )
    return grouped[["person_id", "score", "n_signals"]]


# ---------------------------------------------------------------------------
# Tier-1 × Tier-2 integration
# ---------------------------------------------------------------------------


def _person_topic_pairs(
    date_t: datetime,
    scored_path: Path,
) -> pd.DataFrame:
    """For each (person, topic), the per-pair signal strength at time T."""
    scored_path = Path(scored_path)
    if not scored_path.exists():
        return pd.DataFrame(columns=["person_id", "topic", "pair_strength"])
    df = pq.read_table(scored_path).to_pandas()
    if len(df) == 0:
        return pd.DataFrame(columns=["person_id", "topic", "pair_strength"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df[df["timestamp"] <= pd.Timestamp(date_t, tz="UTC")]
    df = df[df["s6_topic_label"].notna() & (df["s6_topic_label"] != "")]
    grp = df.groupby(["person_id", "s6_topic_label"]).agg(
        pair_strength=("overall_signal_strength", "mean"),
        pair_count=("signal_id", "count"),
    ).reset_index().rename(columns={"s6_topic_label": "topic"})
    return grp


def combined_ranking(
    date_t: datetime,
    cfg: TierConfig | None = None,
    scored_path: Path = _SCORED_DEFAULT,
    trends_path: Path = _TRENDS_DEFAULT,
) -> pd.DataFrame:
    """Ranked (person, topic) pairs at time T under the two-tier framework.

    Returns DataFrame with columns (person_id, topic, tier1_score,
    tier2_score, combined_score, pair_strength, n_signals) sorted by
    combined_score descending, truncated at cfg.top_k.

    combined_score = alpha * tier1_score + (1 - alpha) * tier2_score.

    Lookahead-bias guard: both tiers filter to data with timestamp <= T.
    """
    cfg = cfg or TierConfig()

    t1 = tier1_topic_score_at(date_t, trends_path=trends_path)
    t2 = tier2_founder_score_at(date_t, scored_path=scored_path, cfg=cfg)
    pairs = _person_topic_pairs(date_t, scored_path)

    if len(pairs) == 0:
        return pd.DataFrame(
            columns=[
                "person_id", "topic", "tier1_score", "tier2_score",
                "combined_score", "pair_strength", "n_signals",
            ]
        )

    # Merge person-side score.
    pairs = pairs.merge(
        t2.rename(columns={"score": "tier2_score"}),
        on="person_id",
        how="left",
    )
    pairs["tier2_score"] = pairs["tier2_score"].fillna(0.0)
    # Merge topic-side score; topic match is case-insensitive substring on keyword.
    if len(t1):
        t1_lite = t1[["keyword", "score"]].rename(columns={"score": "tier1_score"})
        t1_lite["keyword_lower"] = t1_lite["keyword"].str.lower()
        pairs["topic_lower"] = pairs["topic"].str.lower()
        # Substring match: topic_lower contains keyword_lower (loose semantic).
        merged = []
        for _, row in pairs.iterrows():
            tl = row["topic_lower"]
            matches = t1_lite[
                t1_lite["keyword_lower"].apply(lambda k, tl=tl: k in tl)
            ]
            tier1 = float(matches["tier1_score"].max()) if len(matches) else 0.0
            merged.append(tier1)
        pairs["tier1_score"] = merged
        pairs = pairs.drop(columns=["topic_lower"])
    else:
        pairs["tier1_score"] = 0.0

    pairs["combined_score"] = (
        cfg.alpha * pairs["tier1_score"] + (1 - cfg.alpha) * pairs["tier2_score"]
    )
    out = pairs.sort_values("combined_score", ascending=False).head(cfg.top_k)
    return out[
        [
            "person_id", "topic", "tier1_score", "tier2_score",
            "combined_score", "pair_strength", "pair_count",
        ]
    ].rename(columns={"pair_count": "n_signals"}).reset_index(drop=True)
