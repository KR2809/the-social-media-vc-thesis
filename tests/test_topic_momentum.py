"""Tests for `analysis/topic_momentum.py`."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from analysis import topic_momentum as tm
from ingestion.trends_collect import _PARQUET_SCHEMA


def _make_trends_parquet(path: Path, series: dict[str, list[float]]):
    """series: {keyword: [weekly values]}. Dates start 2024-01-01 (Mon)."""
    base = date(2024, 1, 1)
    rows = []
    for kw, vals in series.items():
        for i, v in enumerate(vals):
            rows.append(
                {
                    "keyword": kw,
                    "date": base + timedelta(weeks=i),
                    "interest": int(v),
                    "geo": "",
                    "collected_at": datetime.now(UTC),
                }
            )
    df = pd.DataFrame(rows)
    table = pa.Table.from_pandas(df, schema=_PARQUET_SCHEMA, preserve_index=False)
    pq.write_table(table, path)


def test_ols_slope_known_value():
    # y = 2x + 5, slope = 2
    y = np.array([5.0, 7.0, 9.0, 11.0, 13.0])
    assert abs(tm._ols_slope(y) - 2.0) < 1e-9


def test_ols_slope_flat_returns_zero():
    assert tm._ols_slope(np.array([3.0, 3.0, 3.0])) == 0.0


def test_compute_keyword_metrics_increasing_series():
    # 12 weeks of strictly increasing interest.
    df = pd.DataFrame({"interest": np.arange(0, 12, dtype=float)})
    m = tm.compute_keyword_metrics(df)
    assert m["slope_4w"] > 0
    assert m["slope_12w"] > 0
    assert m["delta_4w"] > 0
    assert m["latest"] == 11.0
    assert m["peak"] == 11.0
    assert m["n_weeks"] == 12


def test_compute_keyword_metrics_handles_short_series():
    df = pd.DataFrame({"interest": [10.0]})
    m = tm.compute_keyword_metrics(df)
    assert m["n_weeks"] == 1
    assert m["latest"] == 10.0
    assert m["slope_4w"] == 0.0


def test_compute_all_metrics_writes_one_row_per_keyword(tmp_path):
    inp = tmp_path / "topic_momentum.parquet"
    out = tmp_path / "metrics.parquet"
    # Accelerating curve: x^2 over 30 weeks so the 4w slope at the end
    # is steeper than the 12w slope.
    accel = [float(i * i) / 5.0 for i in range(30)]
    _make_trends_parquet(
        inp,
        {
            "indie hacking": accel,
            "side hustle": [50.0] * 30,
        },
    )
    tm.compute_all_metrics(input_path=inp, output_path=out)
    df = pd.read_parquet(out)
    assert len(df) == 2
    rising = df[df["keyword"] == "indie hacking"].iloc[0]
    flat = df[df["keyword"] == "side hustle"].iloc[0]
    assert rising["slope_12w"] > 0
    assert flat["slope_12w"] == 0.0
    # On an accelerating curve, the most recent 4w slope > the 12w slope.
    assert rising["acceleration"] > 0


def test_compute_all_metrics_handles_missing_input(tmp_path):
    out = tmp_path / "metrics.parquet"
    tm.compute_all_metrics(input_path=tmp_path / "nonexistent.parquet", output_path=out)
    assert out.exists()
    df = pd.read_parquet(out)
    assert len(df) == 0
