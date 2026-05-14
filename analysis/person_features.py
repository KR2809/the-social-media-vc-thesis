"""Per-person flat feature builder from scored signals.

This is the input to the BASELINE model (Arroyo-style flat features).
The KG-augmented model layers `kg_features.parquet` on top of this.

Per `signal_taxonomy_v1.md §3.5`, per-person rollups happen at the
analysis layer, not at scoring time. This module is that layer.

For each person we compute:
  - n_signals
  - n_platforms (distinct)
  - first_signal_date / last_signal_date / active_days
  - mean & max overall_signal_strength
  - per-category means (s1_mean, s2_mean, s3_mean, s4_mean) over each
    person's signals — averaging the sub-signal scores within a category
  - sum of build-in-public, explicit-goal, and recruitment signals
    (S1.3, S3.1, S3.5 — the most theory-loaded per-signal markers)

Writes `data/processed/person_features.parquet`.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

logger = logging.getLogger(__name__)

_SCORED_DEFAULT = Path("data/processed/scored_signals.parquet")
_OUT_DEFAULT = Path("data/processed/person_features.parquet")

_S1_COLS = [
    "s1_output_cadence", "s1_format_diversity", "s1_build_in_public",
    "s1_domain_coherence", "s1_original_synthesis", "s1_production_quality",
]
_S2_COLS = [
    "s2_reading_list_breadth", "s2_specialist_vs_generalist",
    "s2_highbrow_mix", "s2_cross_domain", "s2_tool_fascination",
]
_S3_COLS = [
    "s3_explicit_goal", "s3_frustration_to_idea", "s3_public_commitment",
    "s3_recurring_theme", "s3_recruitment", "s3_counterfactual_future_self",
]
_S4_COLS = [
    "s4_operator_proximity", "s4_mentor_engagement", "s4_reciprocity",
    "s4_community_embedding", "s4_sustained_relationship",
]


def build_person_features(scored_path: Path = _SCORED_DEFAULT) -> pd.DataFrame:
    if not scored_path.exists():
        logger.warning("no scored signals at %s — returning empty frame", scored_path)
        return pd.DataFrame()

    df = pq.read_table(scored_path).to_pandas()
    if len(df) == 0:
        return pd.DataFrame()

    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df["s1_mean"] = df[_S1_COLS].mean(axis=1)
    df["s2_mean"] = df[_S2_COLS].mean(axis=1)
    df["s3_mean"] = df[_S3_COLS].mean(axis=1)
    df["s4_mean"] = df[_S4_COLS].mean(axis=1)

    groups = df.groupby("person_id")
    out = pd.DataFrame()
    out["n_signals"] = groups.size()
    out["n_platforms"] = groups["platform"].nunique()
    out["first_signal_date"] = groups["timestamp"].min()
    out["last_signal_date"] = groups["timestamp"].max()
    out["active_days"] = (
        (out["last_signal_date"] - out["first_signal_date"]).dt.total_seconds() / 86400.0
    ).fillna(0)
    out["mean_signal_strength"] = groups["overall_signal_strength"].mean().fillna(0)
    out["max_signal_strength"] = groups["overall_signal_strength"].max().fillna(0)
    out["s1_mean"] = groups["s1_mean"].mean().fillna(0)
    out["s2_mean"] = groups["s2_mean"].mean().fillna(0)
    out["s3_mean"] = groups["s3_mean"].mean().fillna(0)
    out["s4_mean"] = groups["s4_mean"].mean().fillna(0)
    out["bip_signals"] = groups["s1_build_in_public"].apply(lambda s: float((s > 0.3).sum()))
    out["explicit_goal_signals"] = groups["s3_explicit_goal"].apply(
        lambda s: float((s > 0.3).sum())
    )
    out["recruitment_signals"] = groups["s3_recruitment"].apply(
        lambda s: float((s > 0.3).sum())
    )

    out = out.reset_index()
    return out


def build_and_save(
    scored_path: Path = _SCORED_DEFAULT,
    out_path: Path = _OUT_DEFAULT,
) -> Path:
    df = build_person_features(scored_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out_path, index=False)
    print(f"person_features | {len(df)} persons | written to {out_path}")
    return out_path


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    build_and_save()
