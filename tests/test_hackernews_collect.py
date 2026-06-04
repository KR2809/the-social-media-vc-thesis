"""Unit tests for ingestion.hackernews_collect.

Stdlib unittest.mock. No live network. Five tests:
1. success path (story + comment, mixed in window and out-of-window)
2. empty submitted list
3. network error on user endpoint → empty parquet, no raise
4. type filter (poll kept, unknown type dropped)
5. parquet roundtrip preserves HN-specific metadata
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from ingestion import hackernews_collect
from ingestion.schema import parquet_to_signal_events


def _epoch(y: int, m: int, d: int) -> int:
    return int(datetime(y, m, d, 12, 0, tzinfo=UTC).timestamp())


def test_success_path_stories_and_comments(tmp_path: Path) -> None:
    submitted = [1, 2, 3, 99]
    items_by_id = {
        1: {
            "id": 1,
            "type": "story",
            "by": "pg",
            "title": "How to do startup",
            "text": "with hard work",
            "time": _epoch(2014, 6, 15),
            "score": 200,
            "descendants": 42,
            "url": "https://paulgraham.com/ds.html",
        },
        2: {
            "id": 2,
            "type": "comment",
            "by": "pg",
            "text": "this is a comment",
            "time": _epoch(2014, 6, 20),
            "parent": 1,
        },
        3: {
            # Out of window — should be dropped by client-side date filter.
            "id": 3,
            "type": "story",
            "by": "pg",
            "title": "Old post",
            "time": _epoch(2013, 1, 1),
            "score": 10,
            "descendants": 0,
        },
        99: {
            # Deleted item — must be filtered.
            "id": 99,
            "type": "story",
            "deleted": True,
            "time": _epoch(2014, 6, 10),
        },
    }

    with patch.object(
        hackernews_collect, "_fetch_user_submitted", return_value=submitted
    ), patch.object(
        hackernews_collect, "_fetch_item", side_effect=lambda iid: items_by_id.get(iid)
    ):
        # _fetch_item normally drops deleted/dead inside itself; emulate that.
        def real_fetch_item(iid: int):
            item = items_by_id.get(iid)
            if item is None or item.get("deleted") or item.get("dead"):
                return None
            return item

        with patch.object(hackernews_collect, "_fetch_item", side_effect=real_fetch_item):
            out = hackernews_collect.collect_hackernews(
                username="pg",
                start=date(2014, 6, 1),
                end=date(2014, 7, 1),
                out_dir=tmp_path,
            )

    events = parquet_to_signal_events(out)
    assert len(events) == 2
    by_id = {e.signal_id: e for e in events}
    assert "hn_1" in by_id
    assert "hn_2" in by_id

    story = by_id["hn_1"]
    assert story.platform == "hackernews"
    assert story.source == "hn_firebase"
    assert story.engagement["likes"] == 200
    assert story.engagement["replies"] == 42
    assert story.metadata["type"] == "story"
    assert story.metadata["url"] == "https://paulgraham.com/ds.html"
    assert "How to do startup" in story.raw_text
    assert "with hard work" in story.raw_text

    comment = by_id["hn_2"]
    assert comment.metadata["type"] == "comment"
    assert comment.engagement["likes"] is None
    assert comment.engagement["replies"] is None
    assert comment.metadata["parent"] == 1


def test_empty_submitted_list(tmp_path: Path) -> None:
    with patch.object(hackernews_collect, "_fetch_user_submitted", return_value=[]):
        out = hackernews_collect.collect_hackernews(
            username="ghost",
            start=date(2020, 1, 1),
            end=date(2021, 1, 1),
            out_dir=tmp_path,
        )
    assert parquet_to_signal_events(out) == []


def test_network_error_on_user_endpoint(tmp_path: Path) -> None:
    """Real-world: HN may 500 or time out. We must return [] not raise."""
    import requests

    def _boom(url: str):
        raise requests.ConnectionError("simulated network down")

    with patch.object(hackernews_collect, "_get_json", side_effect=_boom):
        out = hackernews_collect.collect_hackernews(
            username="anyone",
            start=date(2020, 1, 1),
            end=date(2021, 1, 1),
            out_dir=tmp_path,
        )
    assert parquet_to_signal_events(out) == []


def test_type_filter_keeps_poll_drops_unknown(tmp_path: Path) -> None:
    submitted = [10, 11, 12]
    items_by_id = {
        10: {
            "id": 10,
            "type": "poll",
            "by": "pg",
            "title": "Which lang",
            "time": _epoch(2014, 6, 15),
            "score": 5,
            "descendants": 3,
        },
        11: {
            "id": 11,
            "type": "pollopt",  # unsupported type
            "by": "pg",
            "time": _epoch(2014, 6, 15),
        },
        12: {
            "id": 12,
            "type": "job",  # also unsupported
            "by": "pg",
            "time": _epoch(2014, 6, 15),
        },
    }
    with patch.object(
        hackernews_collect, "_fetch_user_submitted", return_value=submitted
    ), patch.object(
        hackernews_collect, "_fetch_item", side_effect=lambda iid: items_by_id.get(iid)
    ):
        out = hackernews_collect.collect_hackernews(
            username="pg",
            start=date(2014, 6, 1),
            end=date(2014, 7, 1),
            out_dir=tmp_path,
        )
    events = parquet_to_signal_events(out)
    assert len(events) == 1
    assert events[0].signal_id == "hn_10"
    assert events[0].metadata["type"] == "poll"


def test_show_hn_and_ask_hn_flags(tmp_path: Path) -> None:
    submitted = [100, 101, 102]
    items = [
        {
            "id": 100,
            "type": "story",
            "by": "x",
            "title": "Show HN: my new tool",
            "time": _epoch(2014, 6, 15),
            "score": 1,
            "descendants": 0,
        },
        {
            "id": 101,
            "type": "story",
            "by": "x",
            "title": "Ask HN: what's the best DB?",
            "time": _epoch(2014, 6, 15),
            "score": 1,
            "descendants": 0,
        },
        {
            "id": 102,
            "type": "story",
            "by": "x",
            "title": "Just a regular story",
            "time": _epoch(2014, 6, 15),
            "score": 1,
            "descendants": 0,
        },
    ]
    items_by_id = {it["id"]: it for it in items}
    with patch.object(
        hackernews_collect, "_fetch_user_submitted", return_value=submitted
    ), patch.object(
        hackernews_collect, "_fetch_item", side_effect=lambda iid: items_by_id.get(iid)
    ):
        out = hackernews_collect.collect_hackernews(
            username="x",
            start=date(2014, 6, 1),
            end=date(2014, 7, 1),
            out_dir=tmp_path,
        )
    events = {e.signal_id: e for e in parquet_to_signal_events(out)}
    assert events["hn_100"].metadata["is_show_hn"] is True
    assert events["hn_100"].metadata["is_ask_hn"] is False
    assert events["hn_101"].metadata["is_show_hn"] is False
    assert events["hn_101"].metadata["is_ask_hn"] is True
    assert events["hn_102"].metadata["is_show_hn"] is False
    assert events["hn_102"].metadata["is_ask_hn"] is False


# Reference pytest so importing it doesn't get flagged as unused — required
# implicitly by pytest collection but ruff sees it as dead.
_ = pytest


def test_max_items_caps_submitted_ids(tmp_path: Path) -> None:
    """max_items resolves only the newest-N submitted IDs (HN returns newest-first)."""
    # 1000 submitted IDs; only the first 5 should be fetched when capped.
    submitted = list(range(1000))
    fetched: list[int] = []

    def fake_fetch_item(iid: int):
        fetched.append(iid)
        return {
            "id": iid,
            "type": "story",
            "by": "power",
            "title": f"post {iid}",
            "time": _epoch(2022, 6, 15),
            "score": 1,
            "descendants": 0,
        }

    with patch.object(
        hackernews_collect, "_fetch_user_submitted", return_value=submitted
    ), patch.object(hackernews_collect, "_fetch_item", side_effect=fake_fetch_item):
        hackernews_collect.collect_hackernews(
            username="power",
            start=date(2022, 1, 1),
            end=date(2023, 1, 1),
            out_dir=tmp_path,
            max_items=5,
        )

    assert len(fetched) == 5
    assert set(fetched) == set(range(5))
