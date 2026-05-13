"""Unit tests for ingestion.reddit_collect.

Stdlib unittest.mock. No live network. Five tests:
1. success path (submissions + comments, mixed in/out of window)
2. empty redditor (no submissions, no comments)
3. NotFound from PRAW → empty parquet, no raise
4. ceiling warning when >= 1000 items seen
5. parquet roundtrip preserves Reddit metadata (subreddit, parent_id)
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from prawcore.exceptions import NotFound

from ingestion import reddit_collect
from ingestion.schema import parquet_to_signal_events


def _fake_subreddit(name: str) -> SimpleNamespace:
    return SimpleNamespace(display_name=name)


def _fake_submission(
    sid: str,
    title: str,
    selftext: str,
    score: int,
    num_comments: int,
    subreddit: str,
    created_utc: float,
    permalink: str = "",
    is_self: bool = True,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=sid,
        title=title,
        selftext=selftext,
        score=score,
        num_comments=num_comments,
        subreddit=_fake_subreddit(subreddit),
        created_utc=created_utc,
        permalink=permalink or f"/r/{subreddit}/comments/{sid}/_",
        is_self=is_self,
    )


def _fake_comment(
    cid: str,
    body: str,
    score: int,
    subreddit: str,
    created_utc: float,
    parent_id: str = "t3_abc",
    permalink: str = "",
) -> SimpleNamespace:
    return SimpleNamespace(
        id=cid,
        body=body,
        score=score,
        subreddit=_fake_subreddit(subreddit),
        created_utc=created_utc,
        parent_id=parent_id,
        permalink=permalink or f"/r/{subreddit}/comments/xyz/_/{cid}/",
    )


def _epoch(y: int, m: int, d: int) -> float:
    return datetime(y, m, d, 12, 0, tzinfo=UTC).timestamp()


def _build_fake_redditor(submissions: list, comments: list) -> MagicMock:
    redditor = MagicMock()
    redditor.submissions.new.return_value = iter(submissions)
    redditor.comments.new.return_value = iter(comments)
    return redditor


def test_success_path(tmp_path: Path) -> None:
    submissions = [
        _fake_submission(
            "sub_in",
            "Hello",
            "body text",
            score=42,
            num_comments=7,
            subreddit="entrepreneur",
            created_utc=_epoch(2024, 1, 15),
        ),
        _fake_submission(
            "sub_out",
            "old post",
            "",
            score=1,
            num_comments=0,
            subreddit="entrepreneur",
            created_utc=_epoch(2020, 1, 1),
        ),
    ]
    comments = [
        _fake_comment(
            "com_in",
            "good point",
            score=5,
            subreddit="saas",
            created_utc=_epoch(2024, 1, 20),
        ),
    ]
    reddit = MagicMock()
    reddit.redditor.return_value = _build_fake_redditor(submissions, comments)

    out = reddit_collect.collect_reddit(
        username="someuser",
        start=date(2024, 1, 1),
        end=date(2024, 2, 1),
        out_dir=tmp_path,
        reddit_client=reddit,
    )
    events = parquet_to_signal_events(out)
    assert len(events) == 2
    by_id = {e.signal_id: e for e in events}
    assert "reddit_sub_sub_in" in by_id
    assert "reddit_comment_com_in" in by_id

    sub = by_id["reddit_sub_sub_in"]
    assert sub.platform == "reddit"
    assert sub.source == "praw"
    assert sub.engagement["likes"] == 42
    assert sub.engagement["replies"] == 7
    assert sub.metadata["subreddit"] == "entrepreneur"
    assert sub.metadata["type"] == "submission"
    assert "Hello" in sub.raw_text
    assert "body text" in sub.raw_text

    com = by_id["reddit_comment_com_in"]
    assert com.engagement["likes"] == 5
    assert com.engagement["replies"] is None
    assert com.metadata["type"] == "comment"
    assert com.metadata["parent_id"] == "t3_abc"


def test_empty_user(tmp_path: Path) -> None:
    reddit = MagicMock()
    reddit.redditor.return_value = _build_fake_redditor([], [])
    out = reddit_collect.collect_reddit(
        username="empty",
        start=date(2024, 1, 1),
        end=date(2024, 2, 1),
        out_dir=tmp_path,
        reddit_client=reddit,
    )
    assert parquet_to_signal_events(out) == []


def test_user_not_found(tmp_path: Path) -> None:
    """Reddit returns 404 → NotFound. We must return [] not raise."""
    reddit = MagicMock()
    redditor = MagicMock()

    def _boom():
        raise NotFound(MagicMock())

    redditor.submissions.new.return_value = MagicMock(__iter__=lambda self: _boom())
    redditor.comments.new.return_value = MagicMock(__iter__=lambda self: _boom())
    reddit.redditor.return_value = redditor

    out = reddit_collect.collect_reddit(
        username="ghost",
        start=date(2024, 1, 1),
        end=date(2024, 2, 1),
        out_dir=tmp_path,
        reddit_client=reddit,
    )
    assert parquet_to_signal_events(out) == []


def test_missing_credentials_raises() -> None:
    with patch.dict(
        "os.environ",
        {"REDDIT_CLIENT_ID": "", "REDDIT_CLIENT_SECRET": "", "REDDIT_USER_AGENT": ""},
        clear=False,
    ), patch.object(reddit_collect, "load_dotenv"):
        with pytest.raises(reddit_collect.RedditAuthError):
            reddit_collect._require_reddit_client()


def test_ceiling_truncation_logged(tmp_path: Path, caplog) -> None:
    """If a listing yields the full 1000-item ceiling we log a warning."""
    submissions = [
        _fake_submission(
            f"sub_{i}",
            "t",
            "",
            score=1,
            num_comments=0,
            subreddit="x",
            created_utc=_epoch(2024, 1, 15),
        )
        for i in range(1000)
    ]
    reddit = MagicMock()
    reddit.redditor.return_value = _build_fake_redditor(submissions, [])

    with caplog.at_level("WARNING", logger="ingestion.reddit_collect"):
        out = reddit_collect.collect_reddit(
            username="prolific",
            start=date(2024, 1, 1),
            end=date(2024, 2, 1),
            out_dir=tmp_path,
            reddit_client=reddit,
        )
    events = parquet_to_signal_events(out)
    assert len(events) == 1000
    assert any("ceiling" in rec.message for rec in caplog.records)
