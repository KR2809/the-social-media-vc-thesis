"""Tests for `models/allocation_framework/` — combine.py + backtest.py."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from ingestion.trends_collect import _PARQUET_SCHEMA as _TRENDS_SCHEMA
from models.allocation_framework.backtest import _precision_at_k, run_backtest
from models.allocation_framework.combine import (
    TierConfig,
    combined_ranking,
    tier1_topic_score_at,
    tier2_founder_score_at,
)
from scoring.score_signals import _SCORED_SCHEMA


def _make_scored_parquet(path: Path, rows: list[dict]):
    table = pa.Table.from_pylist(rows, schema=_SCORED_SCHEMA)
    pq.write_table(table, path)


def _scored_row(
    sig: str, person: str, platform: str, topic: str, ts: datetime,
    strength: float = 0.6, bip: float = 0.4, goal: float = 0.3,
):
    row = {c: None for c in _SCORED_SCHEMA.names}
    row.update(
        {
            "signal_id": sig,
            "person_id": person,
            "platform": platform,
            "timestamp": ts,
            "prompt_version": "v1",
            "model": "claude-haiku-4-5-20251001",
            "s1_build_in_public": bip,
            "s3_explicit_goal": goal,
            "s3_recurring_theme": 0.2,
            "s6_topic_label": topic,
            "overall_signal_strength": strength,
            "flags": "[]",
            "scored_at": datetime(2024, 6, 1, tzinfo=UTC),
            "raw_response": "{}",
        }
    )
    return row


def _make_trends_parquet(path: Path, series: dict[str, list[int]]):
    from datetime import date, timedelta

    base = date(2023, 1, 2)
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
    table = pa.Table.from_pandas(df, schema=_TRENDS_SCHEMA, preserve_index=False)
    pq.write_table(table, path)


def test_tier2_filters_by_date(tmp_path):
    scored = tmp_path / "scored.parquet"
    _make_scored_parquet(
        scored,
        [
            _scored_row(
                "s1", "alice", "twitter", "saas",
                datetime(2022, 6, 1, tzinfo=UTC), strength=0.8,
            ),
            _scored_row(
                "s2", "bob", "twitter", "saas",
                datetime(2025, 1, 1, tzinfo=UTC), strength=0.9,
            ),
        ],
    )
    # At date 2023-01-01 only alice's signal is observable.
    df = tier2_founder_score_at(datetime(2023, 1, 1), scored_path=scored)
    assert set(df["person_id"]) == {"alice"}


def test_tier1_filters_by_date(tmp_path):
    trends = tmp_path / "trends.parquet"
    _make_trends_parquet(trends, {"indie hacking": list(range(40))})
    # At date 2023-05-01 only ~17 weeks observable.
    df = tier1_topic_score_at(datetime(2023, 5, 1), trends_path=trends)
    assert len(df) == 1 and df.iloc[0]["keyword"] == "indie hacking"


def test_combined_ranking_balances_tiers(tmp_path):
    scored = tmp_path / "scored.parquet"
    _make_scored_parquet(
        scored,
        [
            # Alice: lots of signals, weak topic match
            *[
                _scored_row(
                    f"a{j}", "alice", "twitter", "random thing",
                    datetime(2023, j % 11 + 1, 1, tzinfo=UTC), strength=0.7,
                )
                for j in range(8)
            ],
            # Bob: fewer signals, strong topic match on 'indie hacking'
            _scored_row(
                "b1", "bob", "twitter", "indie hacking",
                datetime(2023, 6, 1, tzinfo=UTC), strength=0.9,
            ),
        ],
    )
    trends = tmp_path / "trends.parquet"
    _make_trends_parquet(trends, {"indie hacking": list(range(30))})

    # alpha=0.0 → only tier-2 matters → Alice should rank high
    cfg_t2 = TierConfig(alpha=0.0, top_k=5)
    df_t2 = combined_ranking(
        datetime(2024, 1, 1), cfg=cfg_t2,
        scored_path=scored, trends_path=trends,
    )
    # alpha=1.0 → only tier-1 matters → Bob's "indie hacking" pair should appear
    cfg_t1 = TierConfig(alpha=1.0, top_k=5)
    df_t1 = combined_ranking(
        datetime(2024, 1, 1), cfg=cfg_t1,
        scored_path=scored, trends_path=trends,
    )
    assert len(df_t2) > 0
    assert len(df_t1) > 0
    # Bob's "indie hacking" pair should have a nonzero tier1 component on t1 path
    bob_row = df_t1[df_t1["person_id"] == "bob"]
    assert len(bob_row) and bob_row.iloc[0]["tier1_score"] > 0


def test_combined_ranking_empty_input_returns_empty(tmp_path):
    scored = tmp_path / "scored.parquet"
    _make_scored_parquet(scored, [])
    df = combined_ranking(
        datetime(2024, 1, 1),
        scored_path=scored,
        trends_path=tmp_path / "no_trends.parquet",
    )
    assert len(df) == 0


def test_precision_at_k():
    assert _precision_at_k(["a", "b", "c"], {"a", "c"}, k=2) == 0.5
    assert _precision_at_k(["x", "y"], {"a"}, k=2) == 0.0
    assert _precision_at_k([], {"a"}, k=5) == 0.0


def test_run_backtest_writes_csv_and_report(tmp_path):
    scored = tmp_path / "scored.parquet"
    _make_scored_parquet(
        scored,
        [
            _scored_row(
                "s1", "alice", "twitter", "saas",
                datetime(2022, 6, 1, tzinfo=UTC), strength=0.9,
            ),
            _scored_row(
                "s2", "bob", "twitter", "ai",
                datetime(2022, 8, 1, tzinfo=UTC), strength=0.5,
            ),
        ],
    )
    labels = tmp_path / "labels.csv"
    pd.DataFrame(
        [
            {"person_id": "alice", "emerged": 1},
            {"person_id": "bob", "emerged": 0},
        ]
    ).to_csv(labels, index=False)
    out_csv = tmp_path / "backtest.csv"
    out_md = tmp_path / "report.md"
    df = run_backtest(
        backtest_dates=[datetime(2023, 1, 1)],
        k_values=(1, 2),
        scored_path=scored,
        trends_path=tmp_path / "no_trends.parquet",
        labels_path=labels,
        out_csv=out_csv,
        out_md=out_md,
    )
    assert out_csv.exists() and out_md.exists()
    assert len(df) == 8  # 1 date × 2 k-values × 4 strategies
    assert set(df["strategy"]) == {"two_tier", "random", "signal_volume", "recency"}
