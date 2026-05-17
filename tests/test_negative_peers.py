"""Tests for `ingestion/negative_peers.py`."""

from __future__ import annotations

import pandas as pd

from ingestion.negative_peers import (
    NegativePeer,
    load_negative_peers,
    materialise_for_outcome_labels,
    register_peer,
    write_protocol_summary,
)


def test_register_and_load_peer(tmp_path):
    registry = tmp_path / "registry.csv"
    register_peer(
        NegativePeer(
            peer_id="peer_1",
            matched_positive_niche="SaaS/CE",
            matched_emergence_quarter="2020-Q3",
            public_signals_available=True,
            outcome_class="low_traction",
        ),
        registry_path=registry,
    )
    df = load_negative_peers(registry)
    assert len(df) == 1
    assert df.iloc[0]["peer_id"] == "peer_1"


def test_register_overwrites_duplicate_peer_id(tmp_path):
    registry = tmp_path / "registry.csv"
    register_peer(
        NegativePeer("peer_1", "SaaS/CE", "2020-Q3", True, "low_traction"),
        registry_path=registry,
    )
    register_peer(
        NegativePeer("peer_1", "SaaS/CE", "2020-Q3", True, "abandoned"),
        registry_path=registry,
    )
    df = load_negative_peers(registry)
    assert len(df) == 1
    assert df.iloc[0]["outcome_class"] == "abandoned"


def test_materialise_appends_to_labels(tmp_path):
    registry = tmp_path / "registry.csv"
    labels = tmp_path / "labels.csv"
    pd.DataFrame(
        [{"person_id": "alice", "emerged": 1, "source": "cohort"}]
    ).to_csv(labels, index=False)
    register_peer(
        NegativePeer("peer_1", "SaaS/CE", "2020-Q3", True, "low_traction"),
        registry_path=registry,
    )
    register_peer(
        NegativePeer("peer_2", "SaaS/CE", "2020-Q3", False, "no_launch"),
        registry_path=registry,
    )
    materialise_for_outcome_labels(registry_path=registry, labels_path=labels)
    df = pd.read_csv(labels)
    assert (df["emerged"] == 0).sum() == 2
    assert (df["emerged"] == 1).sum() == 1
    assert set(df["person_id"]) == {"alice", "peer_1", "peer_2"}


def test_materialise_idempotent(tmp_path):
    registry = tmp_path / "registry.csv"
    labels = tmp_path / "labels.csv"
    register_peer(
        NegativePeer("peer_1", "SaaS/CE", "2020-Q3", True, "low_traction"),
        registry_path=registry,
    )
    materialise_for_outcome_labels(registry_path=registry, labels_path=labels)
    materialise_for_outcome_labels(registry_path=registry, labels_path=labels)
    df = pd.read_csv(labels)
    assert len(df[df["person_id"] == "peer_1"]) == 1


def test_summary_handles_empty_registry(tmp_path):
    registry = tmp_path / "registry.csv"
    out = tmp_path / "summary.md"
    write_protocol_summary(registry_path=registry, out_path=out)
    assert out.exists()
    assert "No peers registered yet" in out.read_text()


def test_summary_lists_counts(tmp_path):
    registry = tmp_path / "registry.csv"
    out = tmp_path / "summary.md"
    register_peer(
        NegativePeer("peer_1", "SaaS/CE", "2020-Q3", True, "low_traction"),
        registry_path=registry,
    )
    register_peer(
        NegativePeer("peer_2", "Research/Substack", "2022-Q1", False, "no_launch"),
        registry_path=registry,
    )
    write_protocol_summary(registry_path=registry, out_path=out)
    text = out.read_text()
    assert "n = 2" in text
    assert "low_traction" in text
    assert "SaaS/CE" in text
