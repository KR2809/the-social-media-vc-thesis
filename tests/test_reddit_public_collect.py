"""Unit tests for ingestion.reddit_public_collect (unauthenticated path).

No live network: the module-level `_get_listing_json` is patched to return
canned Reddit public-JSON listing payloads. Covers:
1. success path — submission + comment in-window, one out-of-window dropped
2. empty listing → empty parquet, no raise
3. 404/None payload → empty parquet, no raise
4. pagination stops when `after` is null
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path
from unittest.mock import patch

from ingestion import reddit_public_collect
from ingestion.schema import parquet_to_signal_events


def _epoch(y: int, m: int, d: int) -> float:
    return datetime(y, m, d, 12, 0, tzinfo=UTC).timestamp()


def _listing(children: list[dict], after: str | None = None) -> dict:
    return {"data": {"after": after, "children": children}}


def _sub(id_: str, created: float, title: str = "hi") -> dict:
    return {
        "kind": "t3",
        "data": {
            "id": id_,
            "created_utc": created,
            "title": title,
            "selftext": "body",
            "score": 12,
            "num_comments": 3,
            "subreddit": "SaaS",
            "permalink": f"/r/SaaS/comments/{id_}/",
            "is_self": True,
        },
    }


def _com(id_: str, created: float, body: str = "a comment") -> dict:
    return {
        "kind": "t1",
        "data": {
            "id": id_,
            "created_utc": created,
            "body": body,
            "score": 5,
            "subreddit": "indiehackers",
            "permalink": f"/r/indiehackers/comments/x/{id_}/",
            "parent_id": "t3_abc",
        },
    }


def test_success_path_submission_and_comment(tmp_path: Path) -> None:
    start, end = date(2022, 1, 1), date(2023, 1, 1)

    def fake_get(url: str, ua: str):
        if "submitted" in url:
            return _listing(
                [
                    _sub("s1", _epoch(2022, 6, 1)),  # in window
                    _sub("s2", _epoch(2019, 1, 1)),  # out of window → dropped
                ],
                after=None,
            )
        if "comments" in url:
            return _listing([_com("c1", _epoch(2022, 7, 1))], after=None)
        return None

    with patch.object(reddit_public_collect, "_get_listing_json", side_effect=fake_get):
        out = reddit_public_collect.collect_reddit_public(
            "someuser", start, end, out_dir=tmp_path, user_agent="test-ua"
        )

    events = parquet_to_signal_events(Path(out))
    ids = sorted(e.signal_id for e in events)
    assert ids == ["reddit_comment_c1", "reddit_sub_s1"]
    sub = next(e for e in events if e.signal_id == "reddit_sub_s1")
    assert sub.platform == "reddit"
    assert sub.source == "reddit-public"
    assert sub.metadata["type"] == "submission"
    assert sub.metadata["subreddit"] == "SaaS"
    assert sub.engagement["likes"] == 12
    assert sub.engagement["replies"] == 3


def test_empty_listing_writes_empty_parquet(tmp_path: Path) -> None:
    with patch.object(
        reddit_public_collect, "_get_listing_json", return_value=_listing([], after=None)
    ):
        out = reddit_public_collect.collect_reddit_public(
            "ghost", date(2022, 1, 1), date(2023, 1, 1), out_dir=tmp_path, user_agent="ua"
        )
    assert Path(out).exists()
    assert parquet_to_signal_events(Path(out)) == []


def test_none_payload_writes_empty_parquet(tmp_path: Path) -> None:
    # Simulates a 404 (helper returns None) — must not raise.
    with patch.object(reddit_public_collect, "_get_listing_json", return_value=None):
        out = reddit_public_collect.collect_reddit_public(
            "deleted", date(2022, 1, 1), date(2023, 1, 1), out_dir=tmp_path, user_agent="ua"
        )
    assert Path(out).exists()
    assert parquet_to_signal_events(Path(out)) == []


def test_pagination_follows_after_then_stops(tmp_path: Path) -> None:
    start, end = date(2022, 1, 1), date(2023, 1, 1)
    calls: list[str] = []

    def fake_get(url: str, ua: str):
        calls.append(url)
        if "submitted" in url and "after=" not in url:
            return _listing([_sub("s1", _epoch(2022, 2, 1))], after="t3_s1")
        if "submitted" in url and "after=t3_s1" in url:
            return _listing([_sub("s2", _epoch(2022, 3, 1))], after=None)
        # comments endpoint empty
        return _listing([], after=None)

    with patch.object(reddit_public_collect, "_get_listing_json", side_effect=fake_get):
        # Patch the inter-page sleep so the test is fast.
        with patch.object(reddit_public_collect.time, "sleep", return_value=None):
            out = reddit_public_collect.collect_reddit_public(
                "pager", start, end, out_dir=tmp_path, user_agent="ua"
            )

    events = parquet_to_signal_events(Path(out))
    assert sorted(e.signal_id for e in events) == ["reddit_sub_s1", "reddit_sub_s2"]
    # Followed exactly one `after` page on submitted (2 submitted calls) + 1 comments call.
    assert sum(1 for c in calls if "submitted" in c) == 2
