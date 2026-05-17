"""Tests for `analysis/self_case.py`."""

from __future__ import annotations

import pickle

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from analysis.self_case import SELF_HANDLE, register_self_case, self_case_view


def test_register_self_case_writes_unknown_label(tmp_path):
    labels = tmp_path / "labels.csv"
    register_self_case(labels_path=labels)
    df = pd.read_csv(labels)
    assert len(df) == 1
    assert df.iloc[0]["person_id"] == SELF_HANDLE
    assert df.iloc[0]["emerged"] == -1
    assert df.iloc[0]["source"] == "self_case"


def test_register_self_case_idempotent(tmp_path):
    labels = tmp_path / "labels.csv"
    register_self_case(labels_path=labels)
    register_self_case(labels_path=labels)  # no duplicate
    df = pd.read_csv(labels)
    assert len(df) == 1


def test_register_self_case_appends_to_existing_labels(tmp_path):
    labels = tmp_path / "labels.csv"
    pd.DataFrame(
        [
            {"person_id": "alice", "emerged": 1, "source": "cohort"},
            {"person_id": "peer_1", "emerged": 0, "source": "negative_peer"},
        ]
    ).to_csv(labels, index=False)
    register_self_case(labels_path=labels)
    df = pd.read_csv(labels)
    assert set(df["person_id"]) == {"alice", "peer_1", SELF_HANDLE}
    assert (df["emerged"] == -1).sum() == 1


def test_self_case_view_missing_features(tmp_path):
    view = self_case_view(
        features_path=tmp_path / "no.parquet",
        kg_features_path=tmp_path / "no_kg.parquet",
        model_path=tmp_path / "no_model.pkl",
    )
    assert view.handle == SELF_HANDLE
    assert not view.has_features
    assert view.p_emerge is None
    assert "missing" in view.note.lower() or "no feature row" in view.note.lower()


def test_self_case_view_with_features_and_model(tmp_path):
    cols = ["n_signals", "mean_signal_strength", "s1_mean"]
    rng = np.random.default_rng(0)
    n = 20
    X = pd.DataFrame(rng.normal(size=(n, len(cols))), columns=cols)
    y = (X[cols[0]] > 0).astype(int).to_numpy()
    pipe = Pipeline([("scale", StandardScaler()), ("clf", LogisticRegression(max_iter=200))])
    pipe.fit(X, y)
    model_path = tmp_path / "kg_aug.pkl"
    with model_path.open("wb") as f:
        pickle.dump({"pipeline": pipe, "feature_cols": cols}, f)

    flat = pd.DataFrame(
        [
            {"person_id": SELF_HANDLE, "n_signals": 25, "mean_signal_strength": 0.6, "s1_mean": 0.5},
            {"person_id": "alice", "n_signals": 30, "mean_signal_strength": 0.7, "s1_mean": 0.5},
            {"person_id": "bob",   "n_signals": 5,  "mean_signal_strength": 0.2, "s1_mean": 0.1},
        ]
    )
    flat_path = tmp_path / "person_features.parquet"
    flat.to_parquet(flat_path, index=False)
    kg = pd.DataFrame(columns=["person_id"])
    kg_path = tmp_path / "kg_features.parquet"
    kg.to_parquet(kg_path, index=False)

    view = self_case_view(
        features_path=flat_path, kg_features_path=kg_path, model_path=model_path,
    )
    assert view.has_features
    assert view.has_model
    assert view.p_emerge is not None and 0.0 <= view.p_emerge <= 1.0
    assert view.cohort_percentile is not None
