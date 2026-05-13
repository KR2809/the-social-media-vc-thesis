"""Unit tests for ingestion.youtube_collect.

Stdlib unittest.mock. No live network. Five tests:
1. success path (channels.list → playlistItems.list → videos.list)
2. empty channel (no uploads)
3. duration parser correctness
4. missing API key raises YouTubeAuthError
5. parquet roundtrip preserves YouTube metadata (incl. tags, is_short)
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest

from ingestion import youtube_collect
from ingestion.schema import parquet_to_signal_events
from ingestion.youtube_collect import (
    YouTubeAuthError,
    _parse_iso8601_duration,
    collect_youtube,
)


def test_parse_iso8601_duration_handles_all_combinations() -> None:
    assert _parse_iso8601_duration("PT15S") == 15
    assert _parse_iso8601_duration("PT2M") == 120
    assert _parse_iso8601_duration("PT1H") == 3600
    assert _parse_iso8601_duration("PT15M33S") == 933
    assert _parse_iso8601_duration("PT1H2M3S") == 3723
    assert _parse_iso8601_duration(None) is None
    assert _parse_iso8601_duration("garbage") is None


def test_missing_api_key_raises(tmp_path: Path) -> None:
    with patch.dict("os.environ", {"YOUTUBE_API_KEY": ""}, clear=False):
        with patch.object(youtube_collect, "load_dotenv"):
            with pytest.raises(YouTubeAuthError):
                collect_youtube(
                    channel_id="UC_test",
                    start=date(2024, 1, 1),
                    end=date(2024, 2, 1),
                    out_dir=tmp_path,
                )


def _api_get_side_effect(channels_response, playlist_pages, videos_response):
    """Build a side_effect mimicking the three endpoints we hit."""
    playlist_iter = iter(playlist_pages)

    def _se(path: str, params: dict, api_key: str):
        if path == "channels":
            return channels_response
        if path == "playlistItems":
            return next(playlist_iter)
        if path == "videos":
            return videos_response
        raise AssertionError(f"unexpected path {path!r}")

    return _se


def test_success_path(tmp_path: Path) -> None:
    channels_response = {
        "items": [
            {"id": "UC_test", "contentDetails": {"relatedPlaylists": {"uploads": "UU_test"}}}
        ]
    }
    playlist_pages = [
        {
            "items": [
                {
                    "contentDetails": {
                        "videoId": "vid1",
                        "videoPublishedAt": "2024-01-15T12:00:00Z",
                    }
                },
                {
                    "contentDetails": {
                        "videoId": "vid2",
                        "videoPublishedAt": "2024-01-20T12:00:00Z",
                    }
                },
                {
                    # out-of-window — should be filtered
                    "contentDetails": {
                        "videoId": "vid_old",
                        "videoPublishedAt": "2020-01-01T12:00:00Z",
                    }
                },
            ]
        }
    ]
    videos_response = {
        "items": [
            {
                "id": "vid1",
                "snippet": {
                    "title": "First video",
                    "description": "Long description with link",
                    "publishedAt": "2024-01-15T12:00:00Z",
                    "channelTitle": "Test Channel",
                    "tags": ["startups", "indiehacker"],
                },
                "statistics": {
                    "viewCount": "10000",
                    "likeCount": "500",
                    "commentCount": "42",
                },
                "contentDetails": {"duration": "PT15M33S"},
            },
            {
                "id": "vid2",
                "snippet": {
                    "title": "Short",
                    "description": "",
                    "publishedAt": "2024-01-20T12:00:00Z",
                    "channelTitle": "Test Channel",
                    "tags": [],
                },
                "statistics": {"viewCount": "5", "likeCount": "1"},
                "contentDetails": {"duration": "PT45S"},
            },
        ]
    }

    with patch.object(
        youtube_collect,
        "_api_get",
        side_effect=_api_get_side_effect(channels_response, playlist_pages, videos_response),
    ):
        out = collect_youtube(
            channel_id="UC_test",
            start=date(2024, 1, 1),
            end=date(2024, 2, 1),
            out_dir=tmp_path,
            api_key="fake",
        )

    events = parquet_to_signal_events(out)
    assert len(events) == 2
    by_id = {e.signal_id: e for e in events}

    e1 = by_id["youtube_vid1"]
    assert e1.platform == "youtube"
    assert e1.source == "youtube_api_v3"
    assert e1.engagement["views"] == 10000
    assert e1.engagement["likes"] == 500
    assert e1.engagement["replies"] == 42
    assert e1.metadata["duration_seconds"] == 933
    assert e1.metadata["is_short"] is False
    assert e1.metadata["tags"] == ["startups", "indiehacker"]
    assert "First video" in e1.raw_text
    assert "Long description" in e1.raw_text

    e2 = by_id["youtube_vid2"]
    assert e2.metadata["is_short"] is True
    assert e2.metadata["duration_seconds"] == 45
    # Missing commentCount → engagement.replies is None
    assert e2.engagement["replies"] is None


def test_channel_with_no_uploads_playlist(tmp_path: Path) -> None:
    """Edge case: brand new channel, channels.list has no contentDetails."""
    channels_response: dict = {"items": []}
    with patch.object(
        youtube_collect,
        "_api_get",
        side_effect=_api_get_side_effect(channels_response, [], {"items": []}),
    ):
        out = collect_youtube(
            channel_id="UC_empty",
            start=date(2024, 1, 1),
            end=date(2024, 2, 1),
            out_dir=tmp_path,
            api_key="fake",
        )
    assert parquet_to_signal_events(out) == []


def test_handle_to_channel_id_uses_cache(tmp_path: Path) -> None:
    """If the cache already has the handle, no API call is made."""
    cache_path = tmp_path / "cache.json"
    cache_path.write_text(json.dumps({"levelsio": "UC_levelsio_id"}))
    with patch.object(youtube_collect, "_CACHE_PATH", cache_path), patch.object(
        youtube_collect, "_api_get"
    ) as m_api:
        result = youtube_collect.handle_to_channel_id("@LevelsIO", api_key="fake")
    assert result == "UC_levelsio_id"
    assert m_api.call_count == 0  # cache hit, no API calls


def test_handle_to_channel_id_falls_back_to_search(tmp_path: Path) -> None:
    """forHandle returns nothing → search.list yields the id."""
    cache_path = tmp_path / "cache.json"
    for_handle_response: dict = {"items": []}
    search_response = {"items": [{"snippet": {"channelId": "UC_via_search"}}]}

    def _se(path: str, params: dict, api_key: str):
        if path == "channels":
            return for_handle_response
        if path == "search":
            return search_response
        raise AssertionError(f"unexpected path {path}")

    with patch.object(youtube_collect, "_CACHE_PATH", cache_path), patch.object(
        youtube_collect, "_api_get", side_effect=_se
    ):
        result = youtube_collect.handle_to_channel_id("@unknown", api_key="fake")
    assert result == "UC_via_search"
    # And it should now be cached on disk.
    assert json.loads(cache_path.read_text())["unknown"] == "UC_via_search"
