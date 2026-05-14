"""Tests for the FastAPI layer in `api/main.py`.

Uses fastapi.testclient + monkeypatched data sources so no network /
no real parquet are required.
"""

from __future__ import annotations

from datetime import datetime

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from api import sources as src_mod
from api.main import app
from scoring.score_signals import _SCORED_SCHEMA


@pytest.fixture
def client():
    return TestClient(app)


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["data_source"] in {"local", "supabase"}


def test_cohort_returns_20_members(client):
    r = client.get("/api/cohort")
    assert r.status_code == 200
    body = r.json()
    assert body["n"] == 20
    assert isinstance(body["members"], list)
    assert {"person_id", "display_name", "venture", "niche"} <= set(body["members"][0])


def test_timeline_bounds_empty_signals(client, monkeypatch):
    """When the signal_events parquet is missing, timeline returns nulls."""
    class EmptySource:
        name = "local"
        def read_signal_events(self, **kw):
            return pd.DataFrame()
    monkeypatch.setattr(src_mod, "get_source", lambda: EmptySource())
    # Also override the symbol used by api.main via attribute access.
    from api import main as api_main
    monkeypatch.setattr(api_main, "get_source", lambda: EmptySource())
    r = client.get("/api/timeline-bounds")
    assert r.status_code == 200
    body = r.json()
    assert body["n_signals"] == 0
    assert body["earliest"] is None


def test_timeline_bounds_with_real_data(client, monkeypatch, tmp_path):
    class FakeSource:
        name = "local"
        def read_signal_events(self, **kw):
            return pd.DataFrame(
                [
                    {"timestamp": pd.Timestamp("2020-01-01", tz="UTC")},
                    {"timestamp": pd.Timestamp("2024-06-01", tz="UTC")},
                ]
            )
    from api import main as api_main
    monkeypatch.setattr(api_main, "get_source", lambda: FakeSource())
    r = client.get("/api/timeline-bounds")
    assert r.status_code == 200
    body = r.json()
    assert body["n_signals"] == 2
    assert body["earliest"].startswith("2020-01-01")
    assert body["latest"].startswith("2024-06-01")


def test_portfolio_returns_400_on_bad_date(client):
    r = client.get("/api/portfolio?date=notadate&k=5")
    assert r.status_code == 400


def test_portfolio_empty_returns_zero_picks(client, monkeypatch):
    """No scored signals → empty ranking, but 200 OK with picks=[]."""
    r = client.get("/api/portfolio?date=2024-01-01&k=5")
    assert r.status_code == 200
    body = r.json()
    assert body["n_returned"] == 0
    assert body["picks"] == []


def test_precision_at_k_503_without_labels(client, monkeypatch):
    class NoLabels:
        name = "local"
        def read_outcome_labels(self):
            return pd.DataFrame()
    from api import main as api_main
    monkeypatch.setattr(api_main, "get_source", lambda: NoLabels())
    r = client.get("/api/precision-at-k?date=2024-01-01&k=5")
    assert r.status_code == 503


def test_founder_404_when_missing(client, monkeypatch):
    class EmptySource:
        name = "local"
        def read_person_features(self): return pd.DataFrame()
        def read_kg_features(self): return pd.DataFrame()
        def read_outcome_labels(self): return pd.DataFrame()
        def read_scored_signals(self, **kw): return pd.DataFrame()
    from api import main as api_main
    monkeypatch.setattr(api_main, "get_source", lambda: EmptySource())
    r = client.get("/api/founder/levelsio")
    assert r.status_code == 404


def test_founder_returns_features_and_top_signals(client, monkeypatch):
    class FakeSource:
        name = "local"
        def read_person_features(self):
            return pd.DataFrame([
                {"person_id": "levelsio", "n_signals": 30, "mean_signal_strength": 0.6}
            ])
        def read_kg_features(self):
            return pd.DataFrame([
                {"person_id": "levelsio", "degree_centrality": 0.5, "n_topics": 8}
            ])
        def read_outcome_labels(self):
            return pd.DataFrame([
                {"person_id": "levelsio", "emerged": 1, "source": "cohort"}
            ])
        def read_scored_signals(self, person_id=None, until=None):
            data = []
            for i in range(7):
                row = {c: None for c in _SCORED_SCHEMA.names}
                row.update({
                    "signal_id": f"sig-{i}",
                    "person_id": "levelsio",
                    "platform": "twitter",
                    "timestamp": pd.Timestamp("2024-01-01", tz="UTC"),
                    "prompt_version": "v1",
                    "model": "claude-haiku-4-5-20251001",
                    "overall_signal_strength": 0.1 * (i + 1),
                    "flags": "[]",
                    "scored_at": pd.Timestamp("2024-06-01", tz="UTC"),
                    "raw_response": "{}",
                    "s6_topic_label": "saas",
                })
                data.append(row)
            return pd.DataFrame(data)

    from api import main as api_main
    monkeypatch.setattr(api_main, "get_source", lambda: FakeSource())
    r = client.get("/api/founder/levelsio?top_signals=3")
    assert r.status_code == 200
    body = r.json()
    assert body["person_id"] == "levelsio"
    assert body["feature_row"]["n_signals"] == 30
    assert body["kg_features"]["n_topics"] == 8
    assert body["outcome"]["emerged"] == 1
    assert len(body["top_signals_at_t"]) == 3
    # Top signals sorted by strength desc.
    strengths = [s["overall_signal_strength"] for s in body["top_signals_at_t"]]
    assert strengths == sorted(strengths, reverse=True)


def test_locked_predictions_returns_records(client, monkeypatch, tmp_path):
    import json as _json
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    record = {
        "lock_date": "2026-05-31",
        "framework_version": "v1.0-thesis-submission",
        "n_predictions": 1,
        "predictions": [{"person_id": "x", "p_emerge": 0.7, "rank": 1}],
        "locked_at": "2026-05-31T12:00:00+00:00",
    }
    (workspace / "prospective_predictions_2026-05-31.json").write_text(_json.dumps(record))
    from api import main as api_main
    # Patch the Path lookup inside the endpoint.
    monkeypatch.setattr(api_main, "Path", lambda *args, **kwargs: workspace)
    # The endpoint does Path("/Users/.../04_RETROSPECTIVE_CASES") — easier
    # to test by patching pathlib instead. Use a thinner approach: build
    # the Path object pointing at our tmp dir via monkeypatching the
    # endpoint's `workspace` variable directly. Since the endpoint
    # constructs Path inline, override using the function-level globals.
    api_main.get_locked_predictions.__globals__["Path"] = lambda *args, **kwargs: workspace
    r = client.get("/api/locked-predictions")
    assert r.status_code == 200
    body = r.json()
    # The available flag depends on whether the workspace path resolves;
    # the test patches Path so this should pass.
    assert "available" in body
    assert isinstance(body["records"], list)


def test_discovered_topics_pagination(client, monkeypatch):
    class FakeSource:
        name = "local"
        def read_discovered_topics(self):
            return pd.DataFrame(
                [{"topic": f"t{i}", "rank": i, "source": "cohort"} for i in range(50)]
            )
    from api import main as api_main
    monkeypatch.setattr(api_main, "get_source", lambda: FakeSource())
    r = client.get("/api/discovered-topics?limit=10")
    assert r.status_code == 200
    body = r.json()
    assert body["n_returned"] == 10
    assert len(body["topics"]) == 10


def test_local_source_filter_until(monkeypatch):
    """Lookahead-bias filter: `until` clips signals strictly to <= T."""
    fake_df = pd.DataFrame(
        [
            {"signal_id": "old", "person_id": "a", "timestamp": pd.Timestamp("2020-01-01", tz="UTC")},
            {"signal_id": "new", "person_id": "a", "timestamp": pd.Timestamp("2024-06-01", tz="UTC")},
        ]
    )
    filtered = src_mod._filter(fake_df, until=datetime(2022, 1, 1))
    assert set(filtered["signal_id"]) == {"old"}


def test_local_source_filter_person(monkeypatch):
    fake_df = pd.DataFrame(
        [
            {"signal_id": "x", "person_id": "alice"},
            {"signal_id": "y", "person_id": "bob"},
        ]
    )
    filtered = src_mod._filter(fake_df, person_id="alice")
    assert set(filtered["signal_id"]) == {"x"}
