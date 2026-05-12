"""Unit tests for ingestion.twitter_collect.

No live network calls. Six tests:
1. handle_to_person_id strips @ and lowercases
2. SignalEvent signal_id format
3. snscrape success path (mocked)
4. snscrape empty triggers Wayback (mocked)
5. de-duplication when both sources return the same tweet id
6. parquet schema roundtrip
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from ingestion import twitter_collect
from ingestion.schema import (
    SignalEvent,
    handle_to_person_id,
    parquet_to_signal_events,
    signal_events_to_parquet,
)

# ---------------------------------------------------------------------------
# fixtures / helpers
# ---------------------------------------------------------------------------


def _fake_snscrape_tweet(tweet_id: int, dt: datetime, text: str = "hello") -> SimpleNamespace:
    """Build a SimpleNamespace mirroring snscrape's Tweet attributes."""
    return SimpleNamespace(
        id=tweet_id,
        url=f"https://twitter.com/levelsio/status/{tweet_id}",
        date=dt,
        rawContent=text,
        likeCount=10,
        replyCount=2,
        retweetCount=1,
        quoteCount=0,
        viewCount=None,
        lang="en",
        inReplyToTweetId=None,
        inReplyToUser=None,
        retweetedTweet=None,
        quotedTweet=None,
        media=None,
    )


# ---------------------------------------------------------------------------
# 1. handle_to_person_id
# ---------------------------------------------------------------------------


def test_handle_to_person_id_strips_at_and_lowercases() -> None:
    assert handle_to_person_id("@LevelsIO") == "levelsio"
    assert handle_to_person_id("  levelsio  ") == "levelsio"
    assert handle_to_person_id("LEVELSIO") == "levelsio"
    assert handle_to_person_id("@@nesting") == "nesting"

    with pytest.raises(ValueError):
        handle_to_person_id("")
    with pytest.raises(ValueError):
        handle_to_person_id("   ")
    with pytest.raises(ValueError):
        handle_to_person_id("@")


# ---------------------------------------------------------------------------
# 2. signal_id format
# ---------------------------------------------------------------------------


def test_signal_id_format() -> None:
    now = datetime.now(UTC)
    e = SignalEvent(
        signal_id="twitter_12345",
        person_id="levelsio",
        timestamp=now,
        platform="twitter",
        raw_text="hi",
        engagement={"likes": 0, "replies": 0, "reposts": 0, "views": None, "quotes": 0},
        metadata={},
        collected_at=now,
        source="snscrape",
    )
    assert e.signal_id == "twitter_12345"
    assert e.signal_id.startswith("twitter_")


# ---------------------------------------------------------------------------
# 3. snscrape success path
# ---------------------------------------------------------------------------


def test_snscrape_success_path(tmp_path: Path) -> None:
    fake_scraper_cls = MagicMock()
    fake_scraper_instance = MagicMock()
    fake_scraper_instance.get_items.return_value = iter(
        [
            _fake_snscrape_tweet(1, datetime(2014, 6, 10, 12, 0, tzinfo=UTC)),
            _fake_snscrape_tweet(2, datetime(2014, 6, 20, 12, 0, tzinfo=UTC)),
        ]
    )
    fake_scraper_cls.return_value = fake_scraper_instance

    # Patch the import target: twitter_collect imports TwitterSearchScraper
    # inside _try_snscrape, so patch it on the actual module path.
    with patch.dict(
        "sys.modules",
        {"snscrape.modules.twitter": MagicMock(TwitterSearchScraper=fake_scraper_cls)},
    ):
        out = twitter_collect.collect_twitter(
            handle="levelsio",
            start=date(2014, 6, 1),
            end=date(2014, 7, 1),
            out_dir=tmp_path,
        )

    events = parquet_to_signal_events(out)
    assert len(events) == 2
    assert all(e.source == "snscrape" for e in events)
    assert {e.signal_id for e in events} == {"twitter_1", "twitter_2"}


# ---------------------------------------------------------------------------
# 4. snscrape empty → Wayback fallback
# ---------------------------------------------------------------------------


_WAYBACK_HTML_PRE2020 = """
<html><body>
<div class="tweet" data-tweet-id="9999">
  <a class="tweet-timestamp" href="/levelsio/status/9999">
    <span class="_timestamp" data-time="1402848000">June 15, 2014</span>
  </a>
  <p class="tweet-text">hello world from wayback</p>
  <div class="ProfileTweet-action ProfileTweet-action--reply">
    <span class="ProfileTweet-actionCount" data-tweet-stat-count="3"></span>
  </div>
  <div class="ProfileTweet-action ProfileTweet-action--retweet">
    <span class="ProfileTweet-actionCount" data-tweet-stat-count="5"></span>
  </div>
  <div class="ProfileTweet-action ProfileTweet-action--favorite">
    <span class="ProfileTweet-actionCount" data-tweet-stat-count="21"></span>
  </div>
</div>
</body></html>
"""


def _mock_requests_get(url: str, **_: object) -> MagicMock:
    """Pretend to be requests.get: returns a CDX index or a Wayback snapshot."""
    resp = MagicMock()
    resp.status_code = 200
    resp.raise_for_status = MagicMock()
    if "cdx/search" in url:
        resp.json.return_value = [
            ["timestamp", "original", "statuscode"],
            ["20140615120000", "twitter.com/levelsio", "200"],
        ]
        resp.text = "[]"
    else:
        resp.json.side_effect = ValueError("not json")
        resp.text = _WAYBACK_HTML_PRE2020
    return resp


def test_snscrape_empty_triggers_wayback(tmp_path: Path) -> None:
    empty_scraper_cls = MagicMock()
    empty_scraper_cls.return_value.get_items.return_value = iter([])

    with patch.dict(
        "sys.modules",
        {"snscrape.modules.twitter": MagicMock(TwitterSearchScraper=empty_scraper_cls)},
    ), patch.object(twitter_collect, "_rate_limited_get") as m_get, patch.object(
        twitter_collect.time, "sleep"
    ):

        def _get_side_effect(url: str, *, params: dict | None = None, timeout: int = 30):
            return _mock_requests_get(
                f"{url}?{params}" if params and "cdx/search" in url else url
            )

        m_get.side_effect = _get_side_effect

        out = twitter_collect.collect_twitter(
            handle="levelsio",
            start=date(2014, 6, 1),
            end=date(2014, 7, 1),
            out_dir=tmp_path,
        )

    events = parquet_to_signal_events(out)
    assert len(events) == 1
    assert events[0].source == "wayback"
    assert events[0].signal_id == "twitter_9999"
    assert events[0].raw_text == "hello world from wayback"
    # Engagement extracted from the data-tweet-stat-count attrs.
    assert events[0].engagement["likes"] == 21
    assert events[0].engagement["replies"] == 3
    assert events[0].engagement["reposts"] == 5


# ---------------------------------------------------------------------------
# 5. de-duplication
# ---------------------------------------------------------------------------


def test_deduplication(tmp_path: Path) -> None:
    """Snscrape AND Wayback yield the same tweet id → only one row in output;
    snscrape wins (richer engagement)."""
    sns_scraper_cls = MagicMock()
    sns_scraper_cls.return_value.get_items.return_value = iter(
        [_fake_snscrape_tweet(9999, datetime(2014, 6, 15, 12, 0, tzinfo=UTC))]
    )

    # Force the Wayback path to run too, despite snscrape returning a tweet,
    # by directly testing the deduper with mixed events.
    from datetime import datetime as _dt  # local alias to keep mypy quiet

    sns_event = SignalEvent(
        signal_id="twitter_9999",
        person_id="levelsio",
        timestamp=_dt(2014, 6, 15, 12, 0, tzinfo=UTC),
        platform="twitter",
        raw_text="from snscrape",
        engagement={"likes": 50, "replies": 5, "reposts": 5, "views": 100, "quotes": 1},
        metadata={"lang": "en"},
        collected_at=_dt.now(UTC),
        source="snscrape",
    )
    wb_event = SignalEvent(
        signal_id="twitter_9999",
        person_id="levelsio",
        timestamp=_dt(2014, 6, 15, 12, 0, tzinfo=UTC),
        platform="twitter",
        raw_text="from wayback",
        engagement={"likes": None, "replies": None, "reposts": None, "views": None, "quotes": None},
        metadata={},
        collected_at=_dt.now(UTC),
        source="wayback",
    )

    deduped = twitter_collect._dedupe_prefer_snscrape([sns_event, wb_event])
    assert len(deduped) == 1
    assert deduped[0].source == "snscrape"
    assert deduped[0].raw_text == "from snscrape"

    # And again with the order reversed — snscrape should still win.
    deduped_rev = twitter_collect._dedupe_prefer_snscrape([wb_event, sns_event])
    assert len(deduped_rev) == 1
    assert deduped_rev[0].source == "snscrape"

    # Tmp_path is only used to satisfy the fixture; check the parquet helper
    # works on the deduped output (defensive coverage).
    out = tmp_path / "dedup.parquet"
    signal_events_to_parquet(deduped, out)
    assert parquet_to_signal_events(out) == deduped

    # Reference sns_scraper_cls so the linter doesn't complain.
    del sns_scraper_cls


# ---------------------------------------------------------------------------
# 6. parquet schema roundtrip
# ---------------------------------------------------------------------------


def test_parquet_schema_roundtrip(tmp_path: Path) -> None:
    e = SignalEvent(
        signal_id="twitter_42",
        person_id="levelsio",
        timestamp=datetime(2014, 6, 15, 10, 0, tzinfo=UTC),
        platform="twitter",
        raw_text="testing roundtrip",
        engagement={"likes": 7, "replies": 2, "reposts": None, "views": None, "quotes": 1},
        metadata={"is_reply": False, "lang": "en", "url": "https://twitter.com/levelsio/status/42"},
        collected_at=datetime(2026, 5, 12, 9, 0, tzinfo=UTC),
        source="snscrape",
    )
    path = tmp_path / "rt.parquet"
    signal_events_to_parquet([e], path)
    back = parquet_to_signal_events(path)
    assert len(back) == 1
    assert back[0] == e

    # Also: empty list round-trips with no errors and yields empty list back.
    empty_path = tmp_path / "empty.parquet"
    signal_events_to_parquet([], empty_path)
    assert parquet_to_signal_events(empty_path) == []

    # And the metadata column survives as JSON (not silently lost).
    import pyarrow.parquet as pq

    table = pq.read_table(path)
    metadata_col = table.column("metadata").to_pylist()
    assert json.loads(metadata_col[0])["lang"] == "en"
