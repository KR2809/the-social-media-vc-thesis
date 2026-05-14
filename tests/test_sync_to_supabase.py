"""Tests for `scripts/sync_to_supabase.py`. Supabase client is mocked
so no network calls happen.
"""

from __future__ import annotations

import json

import pandas as pd

from scripts import sync_to_supabase as sync


class MockSupabaseClient:
    """In-memory recorder for Supabase upserts."""

    def __init__(self):
        self.upserts: dict[str, list[dict]] = {}
        self._current_table: str | None = None

    def table(self, name: str):
        self._current_table = name
        return self

    def upsert(self, rows, on_conflict=None):
        assert self._current_table is not None
        self.upserts.setdefault(self._current_table, []).extend(rows)
        return self

    def execute(self):
        return self


def test_clean_row_strips_nans_and_iso_formats():
    row = {
        "signal_id": "abc",
        "timestamp": pd.Timestamp("2024-01-01", tz="UTC"),
        "engagement": {"likes": 5},
        "metadata": '{"x": 1}',
        "mirror_synced_at": pd.Timestamp("2024-06-01", tz="UTC"),
        "nan_value": pd.NA,
    }
    cleaned = sync._clean_row(row)
    assert "mirror_synced_at" not in cleaned  # auto-managed, dropped
    assert cleaned["signal_id"] == "abc"
    assert cleaned["timestamp"].startswith("2024-01-01")
    assert cleaned["nan_value"] is None


def test_metadata_jsonb_parses_string():
    out = sync._metadata_to_jsonb('{"a": 1}')
    assert out == {"a": 1}
    assert sync._metadata_to_jsonb(None) is None
    assert sync._metadata_to_jsonb("") is None
    # malformed JSON returns None with a warning
    assert sync._metadata_to_jsonb("{not json") is None


def test_engagement_jsonb_passthrough():
    eng = {"likes": 10, "views": None}
    assert sync._engagement_to_jsonb(eng) == eng
    assert sync._engagement_to_jsonb(None) is None


def test_sync_table_empty_rows_no_op(monkeypatch):
    client = MockSupabaseClient()
    result = sync.sync_table(client, "signal_events", [], "signal_id")
    assert result == {"in": 0, "upserted": 0, "errors": 0}
    assert client.upserts == {}


def test_sync_table_chunks_large_input(monkeypatch):
    client = MockSupabaseClient()
    rows = [{"signal_id": f"sig-{i}", "person_id": "p"} for i in range(450)]
    result = sync.sync_table(client, "signal_events", rows, "signal_id")
    assert result["in"] == 450
    assert result["upserted"] == 450
    assert result["errors"] == 0
    assert len(client.upserts["signal_events"]) == 450


def test_sync_table_handles_partial_failure(monkeypatch):
    class FailingClient(MockSupabaseClient):
        def __init__(self):
            super().__init__()
            self._calls = 0

        def execute(self):
            self._calls += 1
            if self._calls == 2:
                raise RuntimeError("simulated network error")
            return self

    client = FailingClient()
    rows = [{"signal_id": f"sig-{i}"} for i in range(300)]
    result = sync.sync_table(client, "signal_events", rows, "signal_id")
    # 200-row batch succeeded; 100-row batch failed (2nd call raises)
    assert result["in"] == 300
    assert result["upserted"] == 200
    assert result["errors"] == 100


def test_load_parquet_rows_missing_file_returns_empty(tmp_path):
    rows = sync._load_parquet_rows(tmp_path / "nonexistent.parquet")
    assert rows == []


def test_load_parquet_rows_reads_real_file(tmp_path):
    # Build a small parquet manually.
    df = pd.DataFrame([{"a": 1, "b": "hi"}, {"a": 2, "b": "lo"}])
    p = tmp_path / "t.parquet"
    df.to_parquet(p, index=False)
    rows = sync._load_parquet_rows(p)
    assert len(rows) == 2
    assert rows[0]["a"] == 1


def test_outcome_labels_loader_coerces_emerged(tmp_path, monkeypatch):
    """outcome_labels CSV → emerged field becomes int."""
    df = pd.DataFrame(
        [
            {"person_id": "alice", "emerged": "1", "source": "cohort"},
            {"person_id": "bob", "emerged": "0", "source": "negative_peer"},
            {"person_id": "kris", "emerged": "-1", "source": "self_case"},
        ]
    )
    p = tmp_path / "outcome_labels.csv"
    df.to_csv(p, index=False)
    monkeypatch.setattr(sync, "_PROCESSED", tmp_path)
    rows = sync._outcome_labels_source()
    by_pid = {r["person_id"]: r["emerged"] for r in rows}
    assert by_pid == {"alice": 1, "bob": 0, "kris": -1}


def test_locked_predictions_loader_computes_sha256(tmp_path, monkeypatch):
    workspace = tmp_path / "ws"
    workspace.mkdir()
    record = {
        "lock_date": "2026-05-31",
        "framework_version": "v1.0-thesis-submission",
        "git_commit": "abc1234",
        "n_predictions": 2,
        "locked_at": "2026-05-31T12:00:00+00:00",
        "predictions": [
            {"person_id": "x", "p_emerge": 0.8, "rank": 1},
        ],
    }
    p = workspace / "prospective_predictions_2026-05-31.json"
    p.write_text(json.dumps(record))
    # Build the loader directly so we can pass a custom workspace.
    rows = sync._prepare_locked_predictions([p])
    assert len(rows) == 1
    r = rows[0]
    assert r["lock_date"] == "2026-05-31"
    assert r["framework_version"] == "v1.0-thesis-submission"
    assert len(r["sha256"]) == 64
    assert r["record"]["n_predictions"] == 2


def test_negative_peers_loader_coerces_bool(tmp_path, monkeypatch):
    df = pd.DataFrame(
        [
            {
                "peer_id": "peer_1",
                "matched_positive_niche": "saas",
                "matched_emergence_quarter": "2022-Q3",
                "public_signals_available": "True",
                "outcome_class": "low_traction",
                "notes": "",
                "registered_at": "2026-05-14T00:00:00+00:00",
            }
        ]
    )
    p = tmp_path / "negative_peers_registry.csv"
    df.to_csv(p, index=False)
    monkeypatch.setattr(sync, "_PROCESSED", tmp_path)
    rows = sync._negative_peers_source()
    assert rows[0]["public_signals_available"] is True


def test_sync_all_end_to_end_with_mock_client(tmp_path, monkeypatch):
    # Stand up a minimal fake source tree.
    processed = tmp_path / "processed"
    processed.mkdir()
    pd.DataFrame(
        [{"person_id": "alice", "emerged": 1, "source": "cohort"}]
    ).to_csv(processed / "outcome_labels.csv", index=False)
    monkeypatch.setattr(sync, "_PROCESSED", processed)
    monkeypatch.setattr(sync, "_INTERIM", tmp_path / "interim_does_not_exist")

    client = MockSupabaseClient()
    monkeypatch.setattr(sync, "_get_client", lambda: client)
    results = sync.sync_all(tables=["outcome_labels"])
    assert results["outcome_labels"]["upserted"] == 1
    assert client.upserts["outcome_labels"][0]["person_id"] == "alice"
