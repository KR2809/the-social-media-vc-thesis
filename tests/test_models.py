"""Tests for the model layer: person_features, baseline, KG-augmented, eval."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from analysis import build_graph as bg
from analysis import kg_features as kf
from analysis import person_features as pf
from models.baselines.baseline_model import (
    BASELINE_FEATURE_COLS,
    train_baseline,
)
from models.evaluation.eval import evaluate_model, run_full_eval
from models.kg_augmented.kg_model import KG_FEATURE_COLS, train_kg_augmented
from scoring.score_signals import _SCORED_SCHEMA

# ---------------------------------------------------------------------------
# Fixtures: synthetic scored signals for 6 people (3 positives, 3 negatives).
# Positives have higher signal strengths to give the classifier a learnable
# structure.
# ---------------------------------------------------------------------------


def _row(
    sig: str, person: str, platform: str, topic: str,
    strength: float, ts: datetime, s3_explicit: float = 0.0, s1_bip: float = 0.0,
):
    row = {c: None for c in _SCORED_SCHEMA.names}
    # Fill ALL sub-signal floats with the strength as a baseline.
    for c in _SCORED_SCHEMA.names:
        if c.startswith(("s1_", "s2_", "s3_", "s4_", "s5_", "s6_")) and c != "s6_topic_label":
            row[c] = strength
    row.update(
        {
            "signal_id": sig,
            "person_id": person,
            "platform": platform,
            "timestamp": ts,
            "prompt_version": "v1",
            "model": "claude-haiku-4-5-20251001",
            "s3_explicit_goal": s3_explicit,
            "s1_build_in_public": s1_bip,
            "s3_recruitment": s3_explicit,  # piggyback
            "s6_topic_label": topic,
            "overall_signal_strength": strength,
            "flags": "[]",
            "scored_at": datetime(2024, 6, 1, tzinfo=UTC),
            "raw_response": "{}",
        }
    )
    return row


def _make_synthetic_dataset(tmp_path: Path):
    scored_rows = []
    base_t = datetime(2024, 1, 1, tzinfo=UTC)
    # 3 positives: high strength, multiple platforms, many signals, BIP+explicit goals.
    for i in range(3):
        person = f"pos_{i}"
        for j in range(8):
            scored_rows.append(
                _row(
                    f"{person}_s{j}", person,
                    "twitter" if j % 2 == 0 else "hackernews",
                    "indie hacking" if j % 3 == 0 else "saas",
                    strength=0.7 + 0.02 * j,
                    ts=base_t + timedelta(days=j * 30),
                    s3_explicit=0.7,
                    s1_bip=0.6,
                )
            )
    # 3 negatives: low strength, fewer signals, single platform, no explicit goals.
    for i in range(3):
        person = f"neg_{i}"
        for j in range(3):
            scored_rows.append(
                _row(
                    f"{person}_s{j}", person, "twitter", "random topic",
                    strength=0.1 + 0.02 * j,
                    ts=base_t + timedelta(days=j * 30),
                    s3_explicit=0.0,
                    s1_bip=0.0,
                )
            )

    scored_path = tmp_path / "scored.parquet"
    table = pa.Table.from_pylist(scored_rows, schema=_SCORED_SCHEMA)
    pq.write_table(table, scored_path)

    # Labels.
    labels = pd.DataFrame(
        [{"person_id": f"pos_{i}", "emerged": 1} for i in range(3)]
        + [{"person_id": f"neg_{i}", "emerged": 0} for i in range(3)]
    )
    labels_path = tmp_path / "outcome_labels.csv"
    labels.to_csv(labels_path, index=False)

    # Build flat + KG features.
    flat_path = tmp_path / "person_features.parquet"
    flat = pf.build_person_features(scored_path)
    flat.to_parquet(flat_path, index=False)

    g = bg.build_graph(scored_path)
    kg_path = tmp_path / "kg_features.parquet"
    kg_df = kf.compute_person_features(g)
    kg_df.to_parquet(kg_path, index=False)

    return scored_path, flat_path, kg_path, labels_path


def test_person_features_per_person_rollup(tmp_path):
    scored, flat_path, _, _ = _make_synthetic_dataset(tmp_path)
    flat = pd.read_parquet(flat_path)
    assert set(flat["person_id"]) == {"pos_0", "pos_1", "pos_2", "neg_0", "neg_1", "neg_2"}
    pos0 = flat[flat["person_id"] == "pos_0"].iloc[0]
    neg0 = flat[flat["person_id"] == "neg_0"].iloc[0]
    assert pos0["n_signals"] == 8
    assert neg0["n_signals"] == 3
    assert pos0["mean_signal_strength"] > neg0["mean_signal_strength"]


def test_baseline_train_and_predict(tmp_path):
    _, flat_path, _, labels_path = _make_synthetic_dataset(tmp_path)
    model_path = tmp_path / "baseline.pkl"
    result = train_baseline(
        features_path=flat_path,
        labels_path=labels_path,
        out_path=model_path,
    )
    assert result.n_train == 6
    assert result.n_pos == 3 and result.n_neg == 3
    assert model_path.exists()


def test_baseline_refuses_single_class(tmp_path):
    _, flat_path, _, labels_path = _make_synthetic_dataset(tmp_path)
    # Overwrite labels to be all-positive.
    pd.DataFrame(
        [{"person_id": f"pos_{i}", "emerged": 1} for i in range(3)]
        + [{"person_id": f"neg_{i}", "emerged": 1} for i in range(3)]
    ).to_csv(labels_path, index=False)
    model_path = tmp_path / "baseline.pkl"
    try:
        train_baseline(
            features_path=flat_path,
            labels_path=labels_path,
            out_path=model_path,
        )
    except ValueError as exc:
        assert "single-class" in str(exc)
    else:
        raise AssertionError("expected ValueError on single-class labels")


def test_kg_augmented_train_includes_kg_cols(tmp_path):
    _, flat_path, kg_path, labels_path = _make_synthetic_dataset(tmp_path)
    model_path = tmp_path / "kg.pkl"
    result = train_kg_augmented(
        flat_path=flat_path,
        kg_path=kg_path,
        labels_path=labels_path,
        out_path=model_path,
    )
    assert any(c in result.feature_cols for c in KG_FEATURE_COLS)
    assert "n_signals" in result.feature_cols  # baseline cols preserved
    assert model_path.exists()


def test_eval_baseline_separates_synthetic_classes(tmp_path):
    _, flat_path, kg_path, labels_path = _make_synthetic_dataset(tmp_path)
    flat = pd.read_parquet(flat_path)
    from models.baselines.baseline_model import load_labels
    labels = load_labels(labels_path)
    m = evaluate_model("baseline", flat, BASELINE_FEATURE_COLS, labels)
    # Synthetic data is highly separable; AUC should be very high.
    assert m.roc_auc > 0.8, f"baseline AUC unexpectedly low: {m.roc_auc}"
    assert m.n == 6 and m.n_pos == 3


def test_run_full_eval_writes_report(tmp_path):
    _, flat_path, kg_path, labels_path = _make_synthetic_dataset(tmp_path)
    report = tmp_path / "report.md"
    baseline, kg_aug = run_full_eval(
        flat_path=flat_path,
        kg_path=kg_path,
        labels_path=labels_path,
        report_out=report,
    )
    assert report.exists()
    text = report.read_text()
    assert "ROC AUC" in text and "KG-augmented" in text
    # eval_metrics.csv is written to the default data path; that's OK for the test
    # since it's overwritten on the next run.
