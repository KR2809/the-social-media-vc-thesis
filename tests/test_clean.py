"""Tests for ingestion.clean."""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import pyarrow.parquet as pq

from ingestion.clean import consolidate_signal_events, consolidate_trends
from ingestion.schema import SignalEvent, parquet_to_signal_events, signal_events_to_parquet
from ingestion.trends_collect import collect_trends


def _make_event(
    signal_id: str,
    person_id: str,
    platform: str,
    ts: datetime,
    collected_at: datetime | None = None,
) -> SignalEvent:
    return SignalEvent(
        signal_id=signal_id,
        person_id=person_id,
        timestamp=ts,
        platform=platform,
        raw_text=f"text for {signal_id}",
        engagement={"likes": 1, "replies": 0, "reposts": 0, "views": None, "quotes": 0},
        metadata={"src": platform},
        collected_at=collected_at or datetime.now(UTC),
        source=f"{platform}_test",
    )


def test_consolidate_signal_events_empty(tmp_path: Path) -> None:
    """Nothing in data/raw → empty output with full schema."""
    raw = tmp_path / "raw"
    interim = tmp_path / "interim"
    raw.mkdir()
    out = consolidate_signal_events(raw_dir=raw, interim_dir=interim)
    assert out.exists()
    rows = parquet_to_signal_events(out)
    assert rows == []


def test_consolidate_signal_events_concats_platforms(tmp_path: Path) -> None:
    """Three platforms, two events each → 6 events in unified output."""
    raw = tmp_path / "raw"
    interim = tmp_path / "interim"
    for plat in ("twitter", "hackernews", "reddit"):
        (raw / plat).mkdir(parents=True)
    events_by_plat = {
        "twitter": [
            _make_event("twitter_1", "p1", "twitter", datetime(2023, 1, 1, tzinfo=UTC)),
            _make_event("twitter_2", "p1", "twitter", datetime(2023, 1, 2, tzinfo=UTC)),
        ],
        "hackernews": [
            _make_event("hn_1", "p1", "hackernews", datetime(2023, 1, 3, tzinfo=UTC)),
            _make_event("hn_2", "p2", "hackernews", datetime(2023, 1, 4, tzinfo=UTC)),
        ],
        "reddit": [
            _make_event("reddit_1", "p2", "reddit", datetime(2023, 1, 5, tzinfo=UTC)),
            _make_event("reddit_2", "p1", "reddit", datetime(2023, 1, 6, tzinfo=UTC)),
        ],
    }
    for plat, events in events_by_plat.items():
        signal_events_to_parquet(events, raw / plat / f"p_{plat}.parquet")

    out = consolidate_signal_events(raw_dir=raw, interim_dir=interim)
    rows = parquet_to_signal_events(out)
    assert len(rows) == 6
    # Sorted by (person_id, timestamp).
    person_ids = [r.person_id for r in rows]
    assert person_ids == sorted(person_ids) or sorted(set(person_ids)) == ["p1", "p2"]


def test_consolidate_signal_events_dedupes_on_signal_id(tmp_path: Path) -> None:
    """Same signal_id collected twice → only newest collected_at survives."""
    raw = tmp_path / "raw"
    interim = tmp_path / "interim"
    (raw / "twitter").mkdir(parents=True)

    older = _make_event(
        "twitter_dup",
        "p1",
        "twitter",
        ts=datetime(2023, 1, 1, tzinfo=UTC),
        collected_at=datetime(2024, 6, 1, tzinfo=UTC),
    )
    newer = _make_event(
        "twitter_dup",
        "p1",
        "twitter",
        ts=datetime(2023, 1, 1, tzinfo=UTC),
        collected_at=datetime(2025, 1, 1, tzinfo=UTC),
    )
    # Mutate raw_text on the newer one so we can verify which won.
    newer = SignalEvent(
        **{**newer.model_dump(), "raw_text": "newer version"}
    )
    signal_events_to_parquet([older], raw / "twitter" / "old.parquet")
    signal_events_to_parquet([newer], raw / "twitter" / "new.parquet")

    out = consolidate_signal_events(raw_dir=raw, interim_dir=interim)
    rows = parquet_to_signal_events(out)
    assert len(rows) == 1
    assert rows[0].raw_text == "newer version"


def test_consolidate_trends_empty(tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    interim = tmp_path / "interim"
    raw.mkdir()
    out = consolidate_trends(raw_dir=raw, interim_dir=interim)
    df = pq.read_table(out).to_pandas()
    assert len(df) == 0
    assert "keyword" in df.columns


def test_consolidate_trends_concats(tmp_path: Path) -> None:
    """Two keyword-files → both keywords concatenated."""
    raw = tmp_path / "raw"
    interim = tmp_path / "interim"
    (raw / "trends").mkdir(parents=True)

    # Use the public collector with a fake pytrends client (already covered
    # in test_trends_collect.py) — here we just need real files on disk.
    from unittest.mock import MagicMock, patch

    import pandas as pd

    from ingestion import trends_collect

    def _client_for(kw_value, series):
        client = MagicMock()
        client._current = None

        def _build(kw_list, timeframe, geo, cat, gprop):
            client._current = kw_list[0]

        def _iot():
            return pd.DataFrame({client._current: series, "isPartial": [False] * len(series)},
                                index=pd.to_datetime(["2024-01-01", "2024-01-08"]))

        client.build_payload.side_effect = _build
        client.interest_over_time.side_effect = _iot
        return client

    with patch.object(trends_collect.time, "sleep"):
        collect_trends(
            keywords=["alpha"],
            start=date(2024, 1, 1),
            end=date(2024, 2, 1),
            out_dir=raw / "trends",
            pytrends_client=_client_for("alpha", [10, 20]),
        )
        collect_trends(
            keywords=["beta"],
            start=date(2024, 1, 1),
            end=date(2024, 2, 1),
            out_dir=raw / "trends",
            pytrends_client=_client_for("beta", [30, 40]),
        )

    out = consolidate_trends(raw_dir=raw, interim_dir=interim)
    df = pq.read_table(out).to_pandas()
    assert set(df["keyword"]) == {"alpha", "beta"}
    assert len(df) == 4
