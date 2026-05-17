"""Tests for `analysis/topic_discovery.py`."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from analysis import topic_discovery as td
from scoring.score_signals import _SCORED_SCHEMA


def _scored_row(sig: str, person: str, topic: str, strength: float, ts: datetime):
    row = {c: None for c in _SCORED_SCHEMA.names}
    row.update(
        {
            "signal_id": sig,
            "person_id": person,
            "platform": "twitter",
            "timestamp": ts,
            "prompt_version": "v1",
            "model": "claude-haiku-4-5-20251001",
            "s6_topic_label": topic,
            "overall_signal_strength": strength,
            "flags": "[]",
            "scored_at": datetime(2024, 6, 1, tzinfo=UTC),
            "raw_response": "{}",
        }
    )
    return row


def _make_parquet(path: Path, rows: list[dict]):
    table = pa.Table.from_pylist(rows, schema=_SCORED_SCHEMA)
    pq.write_table(table, path)


def test_cohort_topic_ranking_orders_by_weighted_score(tmp_path):
    scored = tmp_path / "scored.parquet"
    now = datetime(2024, 6, 1, tzinfo=UTC)
    _make_parquet(
        scored,
        [
            # Strong + recent + frequent: "saas"
            _scored_row("a1", "alice", "saas", 0.8, now - timedelta(days=30)),
            _scored_row("a2", "alice", "saas", 0.9, now - timedelta(days=60)),
            _scored_row("b1", "bob", "saas", 0.7, now - timedelta(days=10)),
            # Weak + old: "blockchain"
            _scored_row("c1", "carol", "blockchain", 0.1, now - timedelta(days=900)),
            _scored_row("c2", "carol", "blockchain", 0.2, now - timedelta(days=800)),
            # Below min_signals (only 1): "fintech"
            _scored_row("d1", "dave", "fintech", 0.9, now - timedelta(days=10)),
        ],
    )
    df = td.cohort_topic_ranking(scored, now=now, min_signals=2)
    assert "fintech" not in set(df["topic"])
    assert df.iloc[0]["topic"] == "saas"
    assert df["norm_score"].iloc[0] == 1.0


def test_cohort_topic_ranking_empty_input(tmp_path):
    scored = tmp_path / "scored.parquet"
    _make_parquet(scored, [])
    df = td.cohort_topic_ranking(scored)
    assert len(df) == 0


def test_cohort_topic_ranking_ignores_null_topic(tmp_path):
    scored = tmp_path / "scored.parquet"
    now = datetime(2024, 6, 1, tzinfo=UTC)
    _make_parquet(
        scored,
        [
            _scored_row("a1", "alice", "", 0.8, now),
            _scored_row("a2", "alice", "saas", 0.7, now),
            _scored_row("a3", "alice", "saas", 0.8, now),
        ],
    )
    df = td.cohort_topic_ranking(scored, now=now, min_signals=2)
    assert set(df["topic"]) == {"saas"}


def test_discover_topics_skip_trends_returns_cohort_only(tmp_path):
    scored = tmp_path / "scored.parquet"
    out = tmp_path / "discovered.csv"
    now = datetime(2024, 6, 1, tzinfo=UTC)
    _make_parquet(
        scored,
        [
            _scored_row("a1", "alice", "saas", 0.8, now),
            _scored_row("a2", "alice", "saas", 0.9, now),
        ],
    )
    df = td.discover_topics(
        scored_path=scored, out_path=out, skip_trends=True, now=now,
    )
    assert (df["source"] == "cohort").all()
    assert out.exists()
    csv = pd.read_csv(out)
    assert "saas" in set(csv["topic"])


def test_discover_topics_merges_trends_results(tmp_path, monkeypatch):
    """Mock trends_related_topics to inject a synthetic rising candidate."""
    scored = tmp_path / "scored.parquet"
    out = tmp_path / "discovered.csv"
    now = datetime(2024, 6, 1, tzinfo=UTC)
    _make_parquet(
        scored,
        [
            _scored_row("a1", "alice", "saas", 0.8, now),
            _scored_row("a2", "alice", "saas", 0.9, now),
        ],
    )
    fake = pd.DataFrame(
        [
            {"topic": "ai saas", "seed": "saas", "rising_score": 250, "source": "trends_rising"},
            # This one should be filtered out because "saas" is already in cohort.
            {"topic": "saas", "seed": "saas", "rising_score": 500, "source": "trends_rising"},
        ]
    )
    monkeypatch.setattr(td, "trends_related_topics", lambda **kwargs: fake)
    df = td.discover_topics(scored_path=scored, out_path=out, now=now)
    assert "ai saas" in set(df["topic"])
    # The duplicate "saas" rising row should NOT add a second saas entry.
    assert (df["topic"] == "saas").sum() == 1


def test_recency_decay_decreases_with_age():
    now = pd.Timestamp(datetime(2024, 6, 1, tzinfo=UTC))
    recent = pd.Timestamp(datetime(2024, 5, 1, tzinfo=UTC))
    old = pd.Timestamp(datetime(2020, 6, 1, tzinfo=UTC))
    r1 = td._recency_decay(recent, now, 365)
    r2 = td._recency_decay(old, now, 365)
    assert r1 > r2 > 0
