"""Tests for `analysis/seed_labels.py`."""

from __future__ import annotations

import pandas as pd

from analysis.seed_labels import seed_positives
from ingestion.cohort import load_cohort


def test_seed_positives_writes_one_row_per_cohort_member(tmp_path):
    out = tmp_path / "labels.csv"
    seed_positives(out_path=out)
    df = pd.read_csv(out)
    # One positive row per verified cohort member (size-agnostic).
    n_cohort = len(load_cohort())
    assert len(df) == n_cohort
    assert (df["emerged"] == 1).all()
    assert set(df.columns) >= {"person_id", "emerged", "source"}


def test_seed_positives_idempotent(tmp_path):
    out = tmp_path / "labels.csv"
    seed_positives(out_path=out)
    n_cohort = len(load_cohort())
    # Add a negative manually.
    df = pd.read_csv(out)
    df = pd.concat(
        [df, pd.DataFrame([{"person_id": "fake_negative", "emerged": 0, "source": "manual"}])]
    )
    df.to_csv(out, index=False)
    # Re-seed should preserve the negative.
    seed_positives(out_path=out)
    df2 = pd.read_csv(out)
    assert (df2["person_id"] == "fake_negative").any()
    assert len(df2) == n_cohort + 1
