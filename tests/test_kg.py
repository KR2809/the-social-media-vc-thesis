"""Tests for `analysis/build_graph.py` and `analysis/kg_features.py`."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from analysis import build_graph as bg
from analysis import kg_features as kf
from scoring.score_signals import _SCORED_SCHEMA


def _scored_row(
    signal_id: str,
    person_id: str,
    platform: str,
    topic: str,
    strength: float = 0.5,
):
    row = {c: None for c in _SCORED_SCHEMA.names}
    row.update(
        {
            "signal_id": signal_id,
            "person_id": person_id,
            "platform": platform,
            "timestamp": datetime(2024, 1, 1, tzinfo=UTC),
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


def _make_scored_parquet(path: Path, rows: list[dict]):
    table = pa.Table.from_pylist(rows, schema=_SCORED_SCHEMA)
    pq.write_table(table, path)


def test_build_graph_creates_expected_node_types(tmp_path):
    scored = tmp_path / "scored.parquet"
    _make_scored_parquet(
        scored,
        [
            _scored_row("s1", "alice", "twitter", "indie hacking"),
            _scored_row("s2", "alice", "twitter", "saas"),
            _scored_row("s3", "bob", "hackernews", "indie hacking"),
        ],
    )
    g = bg.build_graph(scored)
    kinds = {n: d["kind"] for n, d in g.nodes(data=True)}
    assert "Person:alice" in g and kinds["Person:alice"] == "Person"
    assert "Person:bob" in g
    assert "SignalEvent:s1" in g
    assert "Topic:indie hacking" in g
    assert "Platform:twitter" in g
    # Person -> Signal edge
    assert g.has_edge("Person:alice", "SignalEvent:s1")
    # Signal -> Topic edge
    assert g.has_edge("SignalEvent:s1", "Topic:indie hacking")
    # Signal -> Platform edge
    assert g.has_edge("SignalEvent:s1", "Platform:twitter")


def test_build_graph_topic_cooccurrence(tmp_path):
    """Two topics expressed by the same person should co-occur."""
    scored = tmp_path / "scored.parquet"
    _make_scored_parquet(
        scored,
        [
            _scored_row("s1", "alice", "twitter", "indie hacking"),
            _scored_row("s2", "alice", "twitter", "saas"),
        ],
    )
    g = bg.build_graph(scored)
    # CO_OCCURS_WITH is directional in the build (sorted pair).
    assert g.has_edge("Topic:indie hacking", "Topic:saas") or g.has_edge(
        "Topic:saas", "Topic:indie hacking"
    )


def test_build_graph_empty_input(tmp_path):
    scored = tmp_path / "scored.parquet"
    _make_scored_parquet(scored, [])
    g = bg.build_graph(scored)
    assert g.number_of_nodes() == 0


def test_save_and_load_roundtrip(tmp_path):
    scored = tmp_path / "scored.parquet"
    _make_scored_parquet(scored, [_scored_row("s1", "alice", "twitter", "topic")])
    g = bg.build_graph(scored)
    gpath, ppath = bg.save_graph(g, tmp_path / "g.graphml", tmp_path / "g.pkl")
    assert gpath.exists() and ppath.exists()
    g2 = bg.load_graph(ppath)
    assert g2.number_of_nodes() == g.number_of_nodes()
    assert g2.has_node("Person:alice")


def test_kg_features_counts(tmp_path):
    scored = tmp_path / "scored.parquet"
    _make_scored_parquet(
        scored,
        [
            _scored_row("s1", "alice", "twitter", "indie hacking", 0.6),
            _scored_row("s2", "alice", "youtube", "saas", 0.4),
            _scored_row("s3", "bob", "twitter", "indie hacking", 0.5),
        ],
    )
    g = bg.build_graph(scored)
    df = kf.compute_person_features(g)
    assert set(df["person_id"]) == {"alice", "bob"}
    alice = df[df["person_id"] == "alice"].iloc[0]
    bob = df[df["person_id"] == "bob"].iloc[0]
    assert alice["n_signals"] == 2
    assert alice["n_topics"] == 2
    assert alice["n_platforms"] == 2
    assert bob["n_signals"] == 1
    assert bob["n_topics"] == 1
    assert bob["n_platforms"] == 1
    # alice's mean strength = (0.6+0.4)/2 = 0.5
    assert abs(alice["mean_signal_strength"] - 0.5) < 1e-9
    # bip triad: indie hacking is shared between alice and bob, so each gets ≥1
    assert alice["bip_triad"] >= 1
    assert bob["bip_triad"] >= 1


def test_shannon_entropy_two_equal_topics():
    h = kf._shannon_entropy([5, 5])
    assert abs(h - 1.0) < 1e-9  # entropy of fair binary = 1 bit


def test_shannon_entropy_single_topic_zero():
    assert kf._shannon_entropy([10]) == 0.0
