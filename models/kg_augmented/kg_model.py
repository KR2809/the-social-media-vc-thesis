"""KG-augmented logistic regression model.

Same algorithm + same baseline features as `models/baselines/baseline_model.py`,
plus the KG-derived per-person features from
`data/processed/kg_features.parquet`. The evaluation harness compares
this model head-to-head with the baseline; the delta is the empirical
KG contribution per `COMPREHENSIVE_PLAN.md §4.5`.

Saves the fitted sklearn `Pipeline` to
`data/processed/models/kg_augmented.pkl`.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from models.baselines.baseline_model import (
    BASELINE_FEATURE_COLS,
    TrainResult,
    train_baseline,
)

logger = logging.getLogger(__name__)

KG_FEATURE_COLS = [
    "degree_centrality",
    "clustering_coeff",
    "topic_diversity",
    "n_topics",
    "n_platforms",  # NOTE: also in baseline; intentional — same column appears in both
                    # frames after the merge; we drop the duplicate before fitting.
    "bip_triad",
]

_FEATURES_DEFAULT = Path("data/processed/person_features.parquet")
_KG_FEATURES_DEFAULT = Path("data/processed/kg_features.parquet")
_LABELS_DEFAULT = Path("data/processed/outcome_labels.csv")
_MODEL_DEFAULT = Path("data/processed/models/kg_augmented.pkl")


def merge_features(
    flat_path: Path = _FEATURES_DEFAULT,
    kg_path: Path = _KG_FEATURES_DEFAULT,
) -> pd.DataFrame:
    flat = pd.read_parquet(flat_path)
    kg = pd.read_parquet(kg_path)
    # Drop overlapping cols (n_platforms appears in both) keeping the flat version.
    overlap = set(flat.columns) & set(kg.columns) - {"person_id"}
    kg = kg.drop(columns=list(overlap), errors="ignore")
    return flat.merge(kg, on="person_id", how="left")


def train_kg_augmented(
    flat_path: Path = _FEATURES_DEFAULT,
    kg_path: Path = _KG_FEATURES_DEFAULT,
    labels_path: Path = _LABELS_DEFAULT,
    out_path: Path = _MODEL_DEFAULT,
) -> TrainResult:
    merged = merge_features(flat_path, kg_path)
    # Write the merged features to a temp parquet so train_baseline can reuse logic.
    tmp = out_path.parent / "_merged_features.parquet"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    merged.to_parquet(tmp, index=False)
    feature_cols = list(
        dict.fromkeys(
            [*BASELINE_FEATURE_COLS, *[c for c in KG_FEATURE_COLS if c in merged.columns]]
        )
    )
    return train_baseline(
        features_path=tmp,
        labels_path=labels_path,
        out_path=out_path,
        feature_cols=feature_cols,
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    train_kg_augmented()
