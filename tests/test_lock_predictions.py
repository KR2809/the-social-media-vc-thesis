"""Tests for `analysis/lock_predictions.py`."""

from __future__ import annotations

import json
import pickle
from datetime import date
from pathlib import Path

import pandas as pd
import pytest
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from analysis.lock_predictions import lock_predictions


def _train_dummy_pipeline(feature_cols):
    """Train a tiny logistic regression for testing."""
    import numpy as np
    rng = np.random.default_rng(0)
    n = 20
    X = pd.DataFrame(rng.normal(size=(n, len(feature_cols))), columns=feature_cols)
    y = (X[feature_cols[0]] > 0).astype(int).to_numpy()
    pipe = Pipeline([("scale", StandardScaler()), ("clf", LogisticRegression(max_iter=200))])
    pipe.fit(X, y)
    return pipe


def _setup(tmp_path: Path):
    feature_cols = ["n_signals", "mean_signal_strength", "s1_mean"]
    pipe = _train_dummy_pipeline(feature_cols)
    model_path = tmp_path / "kg_aug.pkl"
    with model_path.open("wb") as f:
        pickle.dump({"pipeline": pipe, "feature_cols": feature_cols}, f)

    flat = pd.DataFrame(
        [
            {"person_id": "alice", "n_signals": 30, "mean_signal_strength": 0.7, "s1_mean": 0.5},
            {"person_id": "bob",   "n_signals": 5,  "mean_signal_strength": 0.2, "s1_mean": 0.1},
            {"person_id": "carol", "n_signals": 15, "mean_signal_strength": 0.5, "s1_mean": 0.4},
        ]
    )
    flat_path = tmp_path / "person_features.parquet"
    flat.to_parquet(flat_path, index=False)

    kg = pd.DataFrame(columns=["person_id"])
    kg_path = tmp_path / "kg_features.parquet"
    kg.to_parquet(kg_path, index=False)

    out_dir = tmp_path / "out"
    return model_path, flat_path, kg_path, out_dir


def test_lock_writes_json_and_sha256(tmp_path):
    model, flat, kg, out_dir = _setup(tmp_path)
    json_path = lock_predictions(
        prospective_handles=["alice", "bob", "carol"],
        lock_date=date(2026, 5, 31),
        model_path=model,
        person_features_path=flat,
        kg_features_path=kg,
        out_dir=out_dir,
    )
    assert json_path.exists()
    sha_path = json_path.with_suffix(".sha256")
    assert sha_path.exists()
    sha = sha_path.read_text().strip()
    assert len(sha) == 64  # SHA-256 hex digest


def test_lock_record_has_required_fields(tmp_path):
    model, flat, kg, out_dir = _setup(tmp_path)
    json_path = lock_predictions(
        ["alice"], lock_date=date(2026, 5, 31),
        model_path=model, person_features_path=flat, kg_features_path=kg,
        out_dir=out_dir,
    )
    record = json.loads(json_path.read_text())
    for k in [
        "lock_date", "locked_at", "framework_version", "prompt_version",
        "input_hashes", "n_predictions", "predictions",
    ]:
        assert k in record
    assert record["framework_version"] == "v1.0-thesis-submission"
    assert record["n_predictions"] == 1
    assert record["predictions"][0]["person_id"] == "alice"
    assert "rank" in record["predictions"][0]


def test_lock_refuses_missing_handles(tmp_path):
    model, flat, kg, out_dir = _setup(tmp_path)
    with pytest.raises(ValueError, match="refusing to lock"):
        lock_predictions(
            ["alice", "stranger"], lock_date=date(2026, 5, 31),
            model_path=model, person_features_path=flat, kg_features_path=kg,
            out_dir=out_dir,
        )


def test_lock_refuses_missing_model(tmp_path):
    _, flat, kg, out_dir = _setup(tmp_path)
    with pytest.raises(FileNotFoundError, match="locked model"):
        lock_predictions(
            ["alice"],
            model_path=tmp_path / "no_such.pkl",
            person_features_path=flat,
            kg_features_path=kg,
            out_dir=out_dir,
        )


def test_lock_predictions_sorted_by_probability(tmp_path):
    model, flat, kg, out_dir = _setup(tmp_path)
    json_path = lock_predictions(
        ["alice", "bob", "carol"], lock_date=date(2026, 5, 31),
        model_path=model, person_features_path=flat, kg_features_path=kg,
        out_dir=out_dir,
    )
    record = json.loads(json_path.read_text())
    probs = [r["p_emerge"] for r in record["predictions"]]
    assert probs == sorted(probs, reverse=True)
    assert record["predictions"][0]["rank"] == 1
