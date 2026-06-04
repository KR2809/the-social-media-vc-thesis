"""Reddit collector via the UNAUTHENTICATED public-JSON API.

Public entry: `collect_reddit_public(username, start, end, out_dir) -> Path`.

Why this exists: the OAuth/PRAW path (`ingestion/reddit_collect.py`) needs
`REDDIT_CLIENT_ID` / `REDDIT_CLIENT_SECRET`. When those are unavailable we
fall back to Reddit's public JSON endpoints, which require no credentials —
only a descriptive `User-Agent`. This recovers cohort Reddit history at the
cost of a stricter, IP-based rate limit (~60 requests/minute), so we throttle
and paginate conservatively.

Endpoints (no auth):
  https://www.reddit.com/user/<name>/submitted.json?limit=100&after=<fullname>
  https://www.reddit.com/user/<name>/comments.json?limit=100&after=<fullname>

This path is a documented methodological choice: the unauthenticated listing
is subject to the same ~1000-item global ceiling as PRAW, and Reddit may rate
limit aggressively, so a thin result is recorded honestly (empty parquet) for
the cohort balance report rather than retried indefinitely.
"""

from __future__ import annotations

import logging
import os
import time
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

_REDDIT_BASE = "https://www.reddit.com"
_TIMEOUT_SEC = 30
_PAGE_SIZE = 100
_LISTING_CEILING = 1000  # Reddit's global per-listing cap, mirrors PRAW.
_DEFAULT_UA = "thesis-cohort-research/0.1 (unauthenticated public-json)"
_PAGINATE_PAUSE_SEC = 1.2  # stay under the ~60 req/min public limit.


def _user_agent() -> str:
    load_dotenv(override=True)
    return os.environ.get("REDDIT_USER_AGENT") or _DEFAULT_UA


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=20),
    retry=retry_if_exception_type((requests.HTTPError, requests.ConnectionError)),
    reraise=True,
)
def _get_listing_json(url: str, user_agent: str) -> dict | None:
    """GET a Reddit public listing JSON. Archives the raw payload."""
    r = requests.get(url, headers={"User-Agent": user_agent}, timeout=_TIMEOUT_SEC)
    try:
        raw_archive.persist(
            source="reddit",
            url=url,
            response_body=r.content,
            response_status=r.status_code,
            response_headers=dict(r.headers),
            fetch_method="requests-public",
        )
    except Exception as exc:  # archiving must never break ingestion
        logger.warning("raw_archive.persist failed (reddit-public): %s", exc)

    if r.status_code == 404:
        logger.warning("reddit public 404 for %s", url)
        return None
    if r.status_code == 429:
        # Surface as retryable.
        raise requests.HTTPError("429 rate limited", response=r)
    r.raise_for_status()
    return r.json()


def _child_to_event(
    kind: str, data: dict, person_id: str, collected_at: datetime
) -> SignalEvent | None:
    """Map one listing child (t3 submission / t1 comment) to a SignalEvent."""
    created = data.get("created_utc")
    if created is None:
        return None
    ts = datetime.fromtimestamp(float(created), tz=UTC)

    if kind == "t3":  # submission
        title = data.get("title") or ""
        selftext = data.get("selftext") or ""
        raw_text = f"{title}\n\n{selftext}".strip()
        sig_id = f"reddit_sub_{data.get('id')}"
        item_type = "submission"
        replies = data.get("num_comments")
        is_self = data.get("is_self")
        parent_id = None
    elif kind == "t1":  # comment
        raw_text = data.get("body") or ""
        sig_id = f"reddit_comment_{data.get('id')}"
        item_type = "comment"
        replies = None
        is_self = None
        parent_id = data.get("parent_id")
    else:
        return None

    permalink = data.get("permalink")
    return SignalEvent(
        signal_id=sig_id,
        person_id=person_id,
        timestamp=ts,
        platform="reddit",
        raw_text=raw_text,
        engagement={
            "likes": data.get("score"),
            "replies": replies,
            "reposts": None,
            "views": None,
            "quotes": None,
        },
        metadata={
            "type": item_type,
            "subreddit": data.get("subreddit"),
            "url": f"{_REDDIT_BASE}{permalink}" if permalink else None,
            "is_self": is_self,
            "parent_id": parent_id,
        },
        collected_at=collected_at,
        source="reddit-public",
    )


def _collect_endpoint(
    username: str,
    endpoint: str,
    kind: str,
    person_id: str,
    start: date,
    end: date,
    collected_at: datetime,
    user_agent: str,
) -> tuple[list[SignalEvent], bool]:
    """Paginate one public endpoint (submitted/comments). Returns (events, hit_ceiling)."""
    events: list[SignalEvent] = []
    after: str | None = None
    seen = 0
    while seen < _LISTING_CEILING:
        url = f"{_REDDIT_BASE}/user/{username}/{endpoint}.json?limit={_PAGE_SIZE}&raw_json=1"
        if after:
            url += f"&after={after}"
        payload = _get_listing_json(url, user_agent)
        if not payload:
            break
        data = payload.get("data", {})
        children = data.get("children", [])
        if not children:
            break
        for child in children:
            seen += 1
            cdata = child.get("data", {})
            ev = _child_to_event(child.get("kind", kind), cdata, person_id, collected_at)
            if ev is None:
                continue
            if start <= ev.timestamp.date() < end:
                events.append(ev)
        after = data.get("after")
        if not after:
            break
        time.sleep(_PAGINATE_PAUSE_SEC)

    hit_ceiling = seen >= _LISTING_CEILING
    if hit_ceiling:
        logger.warning(
            "reddit-public %s listing hit the %d-item ceiling for %s; "
            "older history may be truncated.",
            endpoint,
            _LISTING_CEILING,
            username,
        )
    return events, hit_ceiling


def collect_reddit_public(
    username: str,
    start: date,
    end: date,
    out_dir: Path = Path("data/raw/reddit"),
    user_agent: str | None = None,
) -> Path:
    """Collect submissions + comments by `username` in [start, end) via public JSON.

    No OAuth required. Writes a parquet (possibly empty) and returns its path.
    """
    person_id = handle_to_person_id(username)
    collected_at = datetime.now(UTC)
    ua = user_agent or _user_agent()

    with raw_archive.handle_scope(username):
        sub_events, sub_trunc = _collect_endpoint(
            username, "submitted", "t3", person_id, start, end, collected_at, ua
        )
        com_events, com_trunc = _collect_endpoint(
            username, "comments", "t1", person_id, start, end, collected_at, ua
        )

    # De-dup defensively on signal_id.
    by_id: dict[str, SignalEvent] = {}
    for e in sub_events + com_events:
        by_id.setdefault(e.signal_id, e)
    events = list(by_id.values())

    out_path = out_dir / f"{person_id}_{start.isoformat()}_{end.isoformat()}.parquet"
    signal_events_to_parquet(events, out_path)

    n_subs = sum(1 for e in events if e.metadata["type"] == "submission")
    n_coms = sum(1 for e in events if e.metadata["type"] == "comment")
    print(
        f"{username} | {len(events)} reddit items (public) | {start} → {end} | "
        f"submissions={n_subs} comments={n_coms} | "
        f"truncated_sub={sub_trunc} truncated_com={com_trunc} | "
        f"written to {out_path}"
    )
    return out_path


@click.command()
@click.option("--username", required=True, help="Reddit username (no /u/).")
@click.option("--start", required=True, type=click.DateTime(formats=["%Y-%m-%d"]))
@click.option("--end", required=True, type=click.DateTime(formats=["%Y-%m-%d"]))
@click.option(
    "--out-dir",
    default="data/raw/reddit",
    type=click.Path(file_okay=False, path_type=Path),
)
def main(username: str, start: datetime, end: datetime, out_dir: Path) -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    collect_reddit_public(
        username=username, start=start.date(), end=end.date(), out_dir=out_dir
    )


if __name__ == "__main__":
    main()
