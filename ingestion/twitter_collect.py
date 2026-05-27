"""Twitter collector — snscrape primary, Wayback Machine fallback.

Public entry: `collect_twitter(handle, start, end, out_dir)` → Path.

snscrape is the gray-area-but-free option (CLAUDE.md §3.6). When it
returns nothing or raises, fall back to Wayback Machine CDX snapshots
of the user's profile page and parse tweets out of the HTML.

The Wayback parser targets two Twitter eras:
- pre-2020:  `div.tweet` desktop layout (stable, well-documented).
- 2020+:     `article[data-testid="tweet"]` React layout (brittle on
             Wayback because content often renders client-side; we try
             and log misses).
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path

import click
import requests
from bs4 import BeautifulSoup
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

# Wayback's CDX index endpoint and snapshot template.
_CDX_ENDPOINT = "https://web.archive.org/cdx/search/cdx"
_WAYBACK_SNAPSHOT_FMT = "https://web.archive.org/web/{ts}/https://twitter.com/{handle}"

# Be polite to Wayback. 1 req/sec is well below their published limit.
_WAYBACK_RATE_LIMIT_SEC = 1.0

# CDX index queries are slow (often 30–60s for popular handles). Snapshot
# fetches are usually fast but a few are large enough to need headroom.
_CDX_TIMEOUT_SEC = 120
_SNAPSHOT_TIMEOUT_SEC = 60


@dataclass
class _WaybackTally:
    snapshots_seen: int = 0
    parsed_pre2020: int = 0
    parsed_post2020: int = 0
    snapshots_unparseable: int = 0
    errors: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# snscrape path
# ---------------------------------------------------------------------------


def _snscrape_tweet_to_event(tweet, person_id: str, collected_at: datetime) -> SignalEvent:
    """Map a snscrape Tweet → SignalEvent."""
    reply_to = None
    if getattr(tweet, "inReplyToUser", None) is not None:
        reply_to = getattr(tweet.inReplyToUser, "username", None)

    media_count = len(tweet.media) if getattr(tweet, "media", None) else 0

    return SignalEvent(
        signal_id=f"twitter_{tweet.id}",
        person_id=person_id,
        timestamp=tweet.date,
        platform="twitter",
        raw_text=tweet.rawContent,
        engagement={
            "likes": tweet.likeCount,
            "replies": tweet.replyCount,
            "reposts": tweet.retweetCount,
            "views": tweet.viewCount,
            "quotes": tweet.quoteCount,
        },
        metadata={
            "is_reply": tweet.inReplyToTweetId is not None,
            "is_retweet": tweet.retweetedTweet is not None,
            "is_quote": tweet.quotedTweet is not None,
            "reply_to_handle": reply_to,
            "lang": tweet.lang,
            "url": tweet.url,
            "media_count": media_count,
        },
        collected_at=collected_at,
        source="snscrape",
    )


def _try_snscrape(
    handle: str, start: date, end: date, collected_at: datetime
) -> tuple[list[SignalEvent], bool]:
    """Try snscrape's search scraper. Returns (events, ok).

    `ok` is True when snscrape completed without raising. An empty list
    with ok=True is suspicious (no tweets in window) and triggers the
    Wayback fallback; ok=False also triggers it.

    `TwitterSearchScraper` is used instead of `TwitterUserScraper` because
    the search scraper accepts a `since`/`until` date filter inline,
    saving full-timeline traversal.
    """
    person_id = handle_to_person_id(handle)
    query = f"from:{handle.lstrip('@')} since:{start.isoformat()} until:{end.isoformat()}"

    try:
        # Imported here so a missing/broken snscrape only kills this path,
        # not the whole module import.
        from snscrape.modules.twitter import TwitterSearchScraper

        events: list[SignalEvent] = []
        for tweet in TwitterSearchScraper(query).get_items():
            events.append(_snscrape_tweet_to_event(tweet, person_id, collected_at))

        if not events:
            logger.warning("snscrape returned 0 tweets for query %r", query)
        return events, True
    except Exception as exc:  # snscrape's exception hierarchy is unstable
        logger.warning("snscrape failed for %s (%s): %s", handle, type(exc).__name__, exc)
        return [], False


# ---------------------------------------------------------------------------
# Wayback path
# ---------------------------------------------------------------------------


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    retry=retry_if_exception_type((requests.HTTPError, requests.ConnectionError)),
    reraise=True,
)
def _rate_limited_get(url: str, *, params: dict | None = None, timeout: int = 30) -> requests.Response:
    """GET with polite rate-limit + exponential backoff on 429/5xx.

    Sleep BEFORE the call so multiple back-to-back calls never burst.
    """
    time.sleep(_WAYBACK_RATE_LIMIT_SEC)
    r = requests.get(url, params=params, timeout=timeout)
    # Persist the verbatim response BEFORE raise_for_status: even 404/500
    # bodies are reproducibility evidence (they tell us *what* Wayback
    # served for a given URL at a given moment).
    try:
        raw_archive.persist(
            source="wayback",
            url=r.url,  # final URL after redirects + query string
            response_body=r.content,
            response_status=r.status_code,
            response_headers=dict(r.headers),
            fetch_method="requests",
        )
    except Exception as exc:  # never let archiving break the collector
        logger.warning("raw_archive.persist failed (wayback): %s", exc)
    r.raise_for_status()
    return r


def _fetch_cdx_index(handle: str, start: date, end: date) -> list[str]:
    """Return list of Wayback snapshot timestamps (yyyyMMddHHmmss) for the handle in [start, end)."""
    params = {
        "url": f"twitter.com/{handle.lstrip('@')}",
        "from": start.strftime("%Y%m%d"),
        "to": end.strftime("%Y%m%d"),
        "output": "json",
        "limit": "200",
        "filter": "statuscode:200",
    }
    try:
        r = _rate_limited_get(_CDX_ENDPOINT, params=params, timeout=_CDX_TIMEOUT_SEC)
    except requests.RequestException as exc:
        logger.warning("CDX index request failed for %s: %s", handle, exc)
        return []
    try:
        rows = r.json()
    except json.JSONDecodeError:
        logger.warning("CDX index returned non-JSON for %s", handle)
        return []
    if not rows or len(rows) < 2:
        return []
    header, *data_rows = rows
    try:
        ts_idx = header.index("timestamp")
    except ValueError:
        logger.warning("CDX header missing 'timestamp' column: %r", header)
        return []
    return [row[ts_idx] for row in data_rows]


def _parse_tweet_id_from_url(url: str | None) -> str | None:
    """Extract a numeric tweet id from a status URL fragment."""
    if not url:
        return None
    parts = url.split("/status/")
    if len(parts) < 2:
        return None
    tail = parts[1].split("?")[0].split("/")[0]
    return tail if tail.isdigit() else None


def _pre2020_stat(div, action: str) -> int | None:
    el = div.select_one(f".ProfileTweet-action--{action} .ProfileTweet-actionCount")
    if el is None:
        return None
    raw = el.get("data-tweet-stat-count")
    if raw is None or not str(raw).isdigit():
        return None
    return int(raw)


def _parse_pre2020_tweets(
    soup: BeautifulSoup, handle: str, person_id: str, collected_at: datetime
) -> list[SignalEvent]:
    """Parse the pre-2020 desktop layout.

    The 2014–2019 profile pages used multiple class names for tweet
    containers (`div.tweet`, `div.js-tweet`, `div.js-stream-tweet`), but
    every one of them carried a `data-tweet-id` attribute. We target
    that attribute directly — it's the most stable selector across the
    era.
    """
    events: list[SignalEvent] = []
    for div in soup.select("div[data-tweet-id]"):
        tweet_id = div.get("data-tweet-id") or div.get("data-item-id")
        if not tweet_id or not str(tweet_id).isdigit():
            continue

        text_el = div.select_one(".tweet-text") or div.select_one(".js-tweet-text")
        if text_el is None:
            continue
        text = text_el.get_text(separator=" ", strip=True)

        # Timestamp: 2014-era pages use `span[data-time]` (class
        # `js-short-timestamp`) with a unix-seconds value. Older `span._timestamp`
        # also matches `span[data-time]` so this is the broader form.
        ts_el = div.select_one("span[data-time]")
        if ts_el is not None and ts_el.get("data-time", "").isdigit():
            tweet_dt = datetime.fromtimestamp(int(ts_el["data-time"]), tz=UTC)
        else:
            # Fallback: `a.tweet-timestamp time[datetime]` (later 2010s).
            time_el = div.select_one("a.tweet-timestamp time")
            iso = time_el.get("datetime") if time_el else None
            if not iso:
                continue
            try:
                tweet_dt = datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(UTC)
            except ValueError:
                continue

        events.append(
            SignalEvent(
                signal_id=f"twitter_{tweet_id}",
                person_id=person_id,
                timestamp=tweet_dt,
                platform="twitter",
                raw_text=text,
                engagement={
                    "likes": _pre2020_stat(div, "favorite"),
                    "replies": _pre2020_stat(div, "reply"),
                    "reposts": _pre2020_stat(div, "retweet"),
                    "views": None,
                    "quotes": None,
                },
                metadata={
                    "is_reply": False,
                    "is_retweet": False,
                    "is_quote": False,
                    "reply_to_handle": None,
                    "lang": None,
                    "url": f"https://twitter.com/{handle.lstrip('@')}/status/{tweet_id}",
                    "media_count": None,
                },
                collected_at=collected_at,
                source="wayback",
            )
        )
    return events


def _parse_post2020_tweets(
    soup: BeautifulSoup, handle: str, person_id: str, collected_at: datetime
) -> list[SignalEvent]:
    """Parse the post-2020 React layout (`article[data-testid="tweet"]`).

    React renders tweets client-side, so Wayback often only has the
    empty shell. We try anyway; failures are counted by the caller.
    """
    events: list[SignalEvent] = []
    for art in soup.select('article[data-testid="tweet"]'):
        # Find the status URL inside the article (link with /status/<id>).
        status_link = None
        for a in art.find_all("a", href=True):
            if "/status/" in a["href"]:
                status_link = a["href"]
                break
        tweet_id = _parse_tweet_id_from_url(status_link)
        if tweet_id is None:
            continue

        # Tweet text: data-testid="tweetText" container.
        text_el = art.select_one('[data-testid="tweetText"]')
        if text_el is None:
            continue
        text = text_el.get_text(separator=" ", strip=True)

        # Timestamp: <time datetime="...">.
        time_el = art.select_one("time")
        iso = time_el.get("datetime") if time_el else None
        if not iso:
            continue
        try:
            tweet_dt = datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(UTC)
        except ValueError:
            continue

        events.append(
            SignalEvent(
                signal_id=f"twitter_{tweet_id}",
                person_id=person_id,
                timestamp=tweet_dt,
                platform="twitter",
                raw_text=text,
                engagement={
                    "likes": None,
                    "replies": None,
                    "reposts": None,
                    "views": None,
                    "quotes": None,
                },
                metadata={
                    "is_reply": False,
                    "is_retweet": False,
                    "is_quote": False,
                    "reply_to_handle": None,
                    "lang": None,
                    "url": f"https://twitter.com/{handle.lstrip('@')}/status/{tweet_id}",
                    "media_count": None,
                },
                collected_at=collected_at,
                source="wayback",
            )
        )
    return events


def _try_wayback(
    handle: str, start: date, end: date, collected_at: datetime
) -> tuple[list[SignalEvent], _WaybackTally]:
    """Fetch + parse Wayback snapshots in [start, end). Returns (events, tally)."""
    person_id = handle_to_person_id(handle)
    tally = _WaybackTally()
    snapshot_timestamps = _fetch_cdx_index(handle, start, end)
    if not snapshot_timestamps:
        return [], tally

    events: list[SignalEvent] = []
    for ts in snapshot_timestamps:
        tally.snapshots_seen += 1
        url = _WAYBACK_SNAPSHOT_FMT.format(ts=ts, handle=handle.lstrip("@"))
        try:
            r = _rate_limited_get(url, timeout=_SNAPSHOT_TIMEOUT_SEC)
        except requests.RequestException as exc:
            tally.errors.append(f"{ts}: {type(exc).__name__}")
            continue

        soup = BeautifulSoup(r.text, "lxml")

        pre = _parse_pre2020_tweets(soup, handle, person_id, collected_at)
        post = _parse_post2020_tweets(soup, handle, person_id, collected_at)
        tally.parsed_pre2020 += len(pre)
        tally.parsed_post2020 += len(post)

        if not pre and not post:
            tally.snapshots_unparseable += 1
            logger.info("Wayback snapshot %s yielded no parseable tweets", ts)

        events.extend(pre + post)

    return events, tally


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def _dedupe_prefer_snscrape(events: list[SignalEvent]) -> list[SignalEvent]:
    """De-dupe by signal_id; when both sources have the same id, keep snscrape."""
    out: dict[str, SignalEvent] = {}
    for e in events:
        existing = out.get(e.signal_id)
        if existing is None:
            out[e.signal_id] = e
        elif existing.source == "snscrape":
            continue
        else:
            out[e.signal_id] = e
    return list(out.values())


def collect_twitter(
    handle: str,
    start: date,
    end: date,
    out_dir: Path = Path("data/raw/twitter"),
) -> Path:
    """Collect tweets for `handle` in [start, end) and write a parquet file.

    Returns the path written. Schema: see ingestion.schema.SignalEvent.

    Lookahead-bias: every event records BOTH `timestamp` (when posted)
    and `collected_at` (one moment, when this function was called).
    """
    person_id = handle_to_person_id(handle)
    collected_at = datetime.now(UTC)

    with raw_archive.handle_scope(handle.lstrip("@")):
        sns_events, sns_ok = _try_snscrape(handle, start, end, collected_at)

        if not sns_ok or len(sns_events) == 0:
            wb_events, wb_tally = _try_wayback(handle, start, end, collected_at)
        else:
            wb_events, wb_tally = [], _WaybackTally()

    combined = _dedupe_prefer_snscrape(sns_events + wb_events)
    # Date-window filter — defensive; snscrape and Wayback can both leak
    # adjacent days.
    in_window = [e for e in combined if start <= e.timestamp.date() < end]

    out_path = out_dir / f"{person_id}_{start.isoformat()}_{end.isoformat()}.parquet"
    signal_events_to_parquet(in_window, out_path)

    n_sns = sum(1 for e in in_window if e.source == "snscrape")
    n_wb = sum(1 for e in in_window if e.source == "wayback")
    summary = (
        f"{handle} | {len(in_window)} tweets | {start} → {end} | "
        f"source: snscrape ({n_sns}) + wayback ({n_wb}) | written to {out_path}"
    )
    print(summary)
    if wb_tally.snapshots_seen:
        print(
            f"  wayback detail: {wb_tally.snapshots_seen} snapshots, "
            f"pre2020={wb_tally.parsed_pre2020} post2020={wb_tally.parsed_post2020} "
            f"unparseable={wb_tally.snapshots_unparseable} errors={len(wb_tally.errors)}"
        )

    return out_path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


@click.command()
@click.option("--handle", required=True, help="X/Twitter handle, with or without @.")
@click.option(
    "--start",
    required=True,
    type=click.DateTime(formats=["%Y-%m-%d"]),
    help="Inclusive start date (UTC), YYYY-MM-DD.",
)
@click.option(
    "--end",
    required=True,
    type=click.DateTime(formats=["%Y-%m-%d"]),
    help="Exclusive end date (UTC), YYYY-MM-DD.",
)
@click.option(
    "--out-dir",
    default="data/raw/twitter",
    type=click.Path(file_okay=False, path_type=Path),
    help="Output directory for the parquet file.",
)
def main(handle: str, start: datetime, end: datetime, out_dir: Path) -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    collect_twitter(handle=handle, start=start.date(), end=end.date(), out_dir=out_dir)


if __name__ == "__main__":
    main()
