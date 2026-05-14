"""Baseline flat-feature model (Arroyo-style logistic regression).

Trains a logistic-regression classifier on the per-person flat features
from `analysis/person_features.py`. The KG-augmented model in
`models/kg_augmented/` extends this with the KG features and is
evaluated against this baseline (the empirical contribution of the
thesis per `COMPREHENSIVE_PLAN.md §4.5`).

Outcome labels: a CSV at `data/processed/outcome_labels.csv` with
columns `(person_id, emerged)`. The cohort (n=20 verified) is positive
by construction; negatives come from the negative-peer protocol
(separate ingest, not in this artefact tonight). When negatives are
absent the trainer raises with a clear error so we don't silently
fit on a single-class dataset.

Saves the fitted sklearn `Pipeline` to
`data/processed/models/baseline.pkl`.
"""

from __future__ import annotations

import logging
import pickle
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

logger = logging.getLogger(__name__)

_FEATURES_DEFAULT = Path("data/processed/person_features.parquet")
_LABELS_DEFAULT = Path("data/processed/outcome_labels.csv")
_MODEL_DEFAULT = Path("data/processed/models/baseline.pkl")

BASELINE_FEATURE_COLS = [
    "n_signals", "n_platforms", "active_days",
    "mean_signal_strength", "max_signal_strength",
    "s1_mean", "s2_mean", "s3_mean", "s4_mean",
    "bip_signals", "explicit_goal_signals", "recruitment_signals",
]


@dataclass
class TrainResult:
    pipeline: Pipeline
    feature_cols: list[str]
    n_train: int
    n_pos: int
    n_neg: int


def load_labels(labels_path: Path = _LABELS_DEFAULT) -> pd.DataFrame:
    if not labels_path.exists():
        raise FileNotFoundError(
            f"no outcome labels at {labels_path}. "
            "Create a CSV with columns (person_id, emerged). "
            "Cohort positives are in 04_RETROSPECTIVE_CASES/cohort_verified.md."
        )
    df = pd.read_csv(labels_path)
    if not {"person_id", "emerged"}.issubset(df.columns):
        raise ValueError(f"labels file missing required columns: {df.columns.tolist()}")
    df["emerged"] = df["emerged"].astype(int)
    return df


def make_pipeline(feature_cols: list[str]) -> Pipeline:
    return Pipeline(
        [
            ("impute", SimpleImputer(strategy="median")),
            ("scale", StandardScaler()),
            ("clf", LogisticRegression(max_iter=1000, class_weight="balanced")),
        ]
    )


def assemble_xy(
    features: pd.DataFrame,
    labels: pd.DataFrame,
    feature_cols: list[str],
) -> tuple[pd.DataFrame, np.ndarray]:
    """Inner join features with labels; return (X, y) keyed on person_id."""
    df = features.merge(labels, on="person_id", how="inner")
    if len(df) == 0:
        raise ValueError("no overlap between features and labels — check person_id keys.")
    X = df[feature_cols].copy()
    y = df["emerged"].to_numpy()
    return X, y


def train_baseline(
    features_path: Path = _FEATURES_DEFAULT,
    labels_path: Path = _LABELS_DEFAULT,
    out_path: Path = _MODEL_DEFAULT,
    feature_cols: list[str] | None = None,
) -> TrainResult:
    features = pd.read_parquet(features_path)
    labels = load_labels(labels_path)
    cols = feature_cols or BASELINE_FEATURE_COLS
    X, y = assemble_xy(features, labels, cols)
    n_pos = int((y == 1).sum())
    n_neg = int((y == 0).sum())
    if n_pos == 0 or n_neg == 0:
        raise ValueError(
            f"single-class dataset (pos={n_pos}, neg={n_neg}); cannot fit. "
            "Add negative examples to outcome_labels.csv."
        )
    pipe = make_pipeline(cols)
    pipe.fit(X, y)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("wb") as f:
        pickle.dump({"pipeline": pipe, "feature_cols": cols}, f)
    print(
        f"baseline | trained on n={len(y)} (pos={n_pos}, neg={n_neg}) | "
        f"written to {out_path}"
    )
    return TrainResult(pipeline=pipe, feature_cols=cols, n_train=len(y), n_pos=n_pos, n_neg=n_neg)


def predict(
    pipeline: Pipeline,
    features: pd.DataFrame,
    feature_cols: list[str],
) -> pd.DataFrame:
    X = features[feature_cols].copy()
    p = pipeline.predict_proba(X)[:, 1]
    return pd.DataFrame({"person_id": features["person_id"], "p_emerge": p})


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    train_baseline()
