"""YouTube collector via the Data API v3 (REST, no SDK).

Public entry: `collect_youtube(channel_id, start, end, out_dir) -> Path`.

Auth: `YOUTUBE_API_KEY` env var (loaded from `.env`).

Quota-cheap pattern:
  1. channels.list                  — 1 unit — get the uploads playlist id
  2. playlistItems.list (paginate)  — 1 unit / page of 50 — enumerate uploads
  3. videos.list (batch up to 50)   — 1 unit / call — fetch statistics + duration

`search.list` (100 units/call) is avoided for video discovery. It IS the
only way to resolve a handle to a channel id when `forHandle` is not
supported — that path is in `handle_to_channel_id` and the result is
cached on disk.
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import UTC, date, datetime
from pathlib import Path

import click
import requests
from dotenv import load_dotenv
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from ingestion import raw_archive
from ingestion.schema import (
    SignalEvent,
    handle_to_person_id,
    signal_events_to_parquet,
)

logger = logging.getLogger(__name__)

_API_BASE = "https://www.googleapis.com/youtube/v3"
_TIMEOUT_SEC = 30
_CACHE_PATH = Path("data/interim/youtube_channel_id_cache.json")

# ISO 8601 duration parser — videos.list returns e.g. "PT15M33S" or "PT1H2M3S".
_DUR_RE = re.compile(
    r"PT"
    r"(?:(?P<hours>\d+)H)?"
    r"(?:(?P<minutes>\d+)M)?"
    r"(?:(?P<seconds>\d+)S)?"
)


class YouTubeAuthError(RuntimeError):
    """YOUTUBE_API_KEY missing or rejected."""


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type((requests.HTTPError, requests.ConnectionError)),
    reraise=True,
)
def _api_get(path: str, params: dict, api_key: str) -> dict:
    full_params = {**params, "key": api_key}
    r = requests.get(f"{_API_BASE}/{path}", params=full_params, timeout=_TIMEOUT_SEC)
    # NB: archive the URL WITHOUT the api_key query param, so the persisted
    # index is safe to share. requests builds the final URL with the key in
    # the querystring; we reconstruct a redacted version here.
    redacted_url = f"{_API_BASE}/{path}"
    if params:
        from urllib.parse import urlencode
        redacted_url = f"{redacted_url}?{urlencode(params)}"
    try:
        raw_archive.persist(
            source="youtube",
            url=redacted_url,
            response_body=r.content,
            response_status=r.status_code,
            response_headers=dict(r.headers),
            fetch_method="requests",
        )
    except Exception as exc:
        logger.warning("raw_archive.persist failed (youtube): %s", exc)
    if r.status_code in (401, 403):
        raise YouTubeAuthError(f"{path} rejected: {r.status_code} {r.text[:200]}")
    r.raise_for_status()
    return r.json()


def _require_api_key() -> str:
    # override=True so that `.env` wins over an empty value injected by the
    # parent shell (e.g. some IDE/agent harnesses pre-set blank API keys for
    # safety, which would otherwise mask our real value).
    load_dotenv(override=True)
    key = os.environ.get("YOUTUBE_API_KEY")
    if not key:
        raise YouTubeAuthError(
            "YOUTUBE_API_KEY missing — populate .env from .env.example and re-run."
        )
    return key


def _parse_iso8601_duration(s: str | None) -> int | None:
    if not s:
        return None
    m = _DUR_RE.fullmatch(s)
    if not m:
        return None
    h = int(m.group("hours") or 0)
    mi = int(m.group("minutes") or 0)
    sec = int(m.group("seconds") or 0)
    return h * 3600 + mi * 60 + sec


def _load_channel_id_cache() -> dict[str, str]:
    if not _CACHE_PATH.exists():
        return {}
    try:
        return json.loads(_CACHE_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        logger.warning("channel-id cache at %s unreadable; ignoring", _CACHE_PATH)
        return {}


def _save_channel_id_cache(cache: dict[str, str]) -> None:
    _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _CACHE_PATH.write_text(json.dumps(cache, indent=2, sort_keys=True))


def handle_to_channel_id(handle: str, api_key: str | None = None) -> str | None:
    """Resolve a YouTube handle (`@levelsio`) to a channel id (`UC...`).

    Caches results in data/interim/youtube_channel_id_cache.json. Prefers
    the cheap `forHandle` path (1 unit) and falls back to `search.list`
    (100 units) only if that fails. Both are tried via channels.list first.
    """
    norm = handle.lstrip("@").strip().lower()
    cache = _load_channel_id_cache()
    if norm in cache:
        return cache[norm]

    if api_key is None:
        api_key = _require_api_key()

    # Try the cheap `forHandle` path first.
    try:
        data = _api_get(
            "channels", {"part": "id", "forHandle": f"@{norm}"}, api_key
        )
        items = data.get("items") or []
        if items:
            channel_id = items[0]["id"]
            cache[norm] = channel_id
            _save_channel_id_cache(cache)
            return channel_id
    except (requests.HTTPError, YouTubeAuthError):
        logger.warning("channels.forHandle failed for %s; falling back to search", norm)

    # Fallback: search.list (100 units — expensive).
    try:
        data = _api_get(
            "search",
            {"part": "snippet", "q": handle, "type": "channel", "maxResults": 1},
            api_key,
        )
        items = data.get("items") or []
        if items:
            channel_id = items[0]["snippet"]["channelId"]
            cache[norm] = channel_id
            _save_channel_id_cache(cache)
            return channel_id
    except (requests.HTTPError, YouTubeAuthError) as exc:
        logger.warning("search.list failed for %s: %s", norm, exc)

    return None


def _get_uploads_playlist_id(channel_id: str, api_key: str) -> str | None:
    data = _api_get(
        "channels", {"part": "contentDetails", "id": channel_id}, api_key
    )
    items = data.get("items") or []
    if not items:
        return None
    return items[0]["contentDetails"]["relatedPlaylists"]["uploads"]


def _iter_uploads_video_ids(playlist_id: str, api_key: str) -> list[tuple[str, datetime]]:
    """Walk the uploads playlist; return (video_id, publishedAt) pairs.

    Note: YouTube returns playlist items newest-first. We don't truncate
    here — date-filtering happens after we've fetched statistics.
    """
    out: list[tuple[str, datetime]] = []
    page_token: str | None = None
    while True:
        params: dict = {
            "part": "contentDetails",
            "playlistId": playlist_id,
            "maxResults": 50,
        }
        if page_token:
            params["pageToken"] = page_token
        data = _api_get("playlistItems", params, api_key)
        for item in data.get("items", []):
            details = item.get("contentDetails", {})
            video_id = details.get("videoId")
            published = details.get("videoPublishedAt")
            if not video_id or not published:
                continue
            try:
                ts = datetime.fromisoformat(published.replace("Z", "+00:00")).astimezone(UTC)
            except ValueError:
                continue
            out.append((video_id, ts))
        page_token = data.get("nextPageToken")
        if not page_token:
            break
    return out


def _fetch_videos(video_ids: list[str], api_key: str) -> dict[str, dict]:
    """Batch videos.list (50 ids per call). Returns id → item dict."""
    out: dict[str, dict] = {}
    for i in range(0, len(video_ids), 50):
        batch = video_ids[i : i + 50]
        data = _api_get(
            "videos",
            {"part": "snippet,statistics,contentDetails", "id": ",".join(batch)},
            api_key,
        )
        for item in data.get("items", []):
            out[item["id"]] = item
    return out


def _video_to_event(
    video: dict, channel_id: str, person_id: str, collected_at: datetime
) -> SignalEvent | None:
    vid = video.get("id")
    snippet = video.get("snippet") or {}
    stats = video.get("statistics") or {}
    details = video.get("contentDetails") or {}

    published_iso = snippet.get("publishedAt")
    if not vid or not published_iso:
        return None
    try:
        ts = datetime.fromisoformat(published_iso.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None

    title = snippet.get("title", "") or ""
    description = snippet.get("description", "") or ""
    raw_text = f"{title}\n\n{description}".strip()

    duration_s = _parse_iso8601_duration(details.get("duration"))

    # YouTube exposes statistics as strings.
    def _as_int(key: str) -> int | None:
        v = stats.get(key)
        if v is None:
            return None
        try:
            return int(v)
        except (TypeError, ValueError):
            return None

    metadata = {
        "video_id": vid,
        "duration_seconds": duration_s,
        "tags": snippet.get("tags") or [],
        "url": f"https://www.youtube.com/watch?v={vid}",
        "is_short": duration_s is not None and duration_s <= 60,
        "channel_id": channel_id,
        "channel_title": snippet.get("channelTitle"),
    }
    return SignalEvent(
        signal_id=f"youtube_{vid}",
        person_id=person_id,
        timestamp=ts,
        platform="youtube",
        raw_text=raw_text,
        # Canonical engagement keys are fixed by the SignalEvent schema:
        # likes, replies, reposts, views, quotes. For YouTube we map
        # viewCount → views, likeCount → likes, commentCount → replies
        # (treating comment count as the conversation size).
        engagement={
            "likes": _as_int("likeCount"),
            "replies": _as_int("commentCount"),
            "reposts": None,
            "views": _as_int("viewCount"),
            "quotes": None,
        },
        metadata=metadata,
        collected_at=collected_at,
        source="youtube_api_v3",
    )


def collect_youtube(
    channel_id: str,
    start: date,
    end: date,
    out_dir: Path = Path("data/raw/youtube"),
    api_key: str | None = None,
) -> Path:
    """Fetch all videos by `channel_id` published in [start, end). Returns path.

    Quota usage: ~1 + ceil(N/50) + ceil(N/50) units where N is the total
    uploads on the channel.
    """
    person_id = handle_to_person_id(channel_id)
    collected_at = datetime.now(UTC)
    if api_key is None:
        api_key = _require_api_key()

    with raw_archive.handle_scope(channel_id):
        return _collect_youtube_inner(
            channel_id, person_id, start, end, collected_at, out_dir, api_key
        )


def _collect_youtube_inner(
    channel_id: str,
    person_id: str,
    start: date,
    end: date,
    collected_at: datetime,
    out_dir: Path,
    api_key: str,
) -> Path:
    uploads_pl = _get_uploads_playlist_id(channel_id, api_key)
    if uploads_pl is None:
        logger.warning("channel %s has no uploads playlist", channel_id)
        out_path = out_dir / f"{person_id}_{start.isoformat()}_{end.isoformat()}.parquet"
        signal_events_to_parquet([], out_path)
        print(f"{channel_id} | 0 videos | {start} → {end} | source: youtube_api_v3 | "
              f"written to {out_path}")
        return out_path

    pairs = _iter_uploads_video_ids(uploads_pl, api_key)
    in_window_ids = [vid for (vid, ts) in pairs if start <= ts.date() < end]
    videos = _fetch_videos(in_window_ids, api_key)

    events: list[SignalEvent] = []
    for vid in in_window_ids:
        item = videos.get(vid)
        if item is None:
            continue
        ev = _video_to_event(item, channel_id, person_id, collected_at)
        if ev is None:
            continue
        if start <= ev.timestamp.date() < end:
            events.append(ev)

    out_path = out_dir / f"{person_id}_{start.isoformat()}_{end.isoformat()}.parquet"
    signal_events_to_parquet(events, out_path)
    print(
        f"{channel_id} | {len(events)} videos | {start} → {end} | "
        f"source: youtube_api_v3 | written to {out_path}"
    )
    return out_path


@click.command()
@click.option("--channel-id", required=True, help="YouTube channel id (e.g. UCX6OQ...).")
@click.option(
    "--start",
    required=True,
    type=click.DateTime(formats=["%Y-%m-%d"]),
)
@click.option(
    "--end",
    required=True,
    type=click.DateTime(formats=["%Y-%m-%d"]),
)
@click.option(
    "--out-dir",
    default="data/raw/youtube",
    type=click.Path(file_okay=False, path_type=Path),
)
def main(channel_id: str, start: datetime, end: datetime, out_dir: Path) -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    collect_youtube(
        channel_id=channel_id, start=start.date(), end=end.date(), out_dir=out_dir
    )


if __name__ == "__main__":
    main()
