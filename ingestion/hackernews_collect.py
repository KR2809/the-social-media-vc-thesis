"""Hacker News collector via the Firebase API.

Public entry: `collect_hackernews(username, start, end, out_dir) -> Path`.

The HN Firebase API is unauthenticated and lenient. We fetch the user's
flat list of submitted item IDs (`/v0/user/<u>.json`), then resolve each
item in parallel with a ThreadPoolExecutor (max 10 workers).

Items come in three flavours (`story`, `comment`, `poll`); for our
purposes we keep stories and comments. Stories carry `score` and
`descendants` (= reply count); comments do not.
"""

from __future__ import annotations

import contextvars
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, date, datetime
from pathlib import Path

import click
import requests
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

_HN_BASE = "https://hacker-news.firebaseio.com/v0"
_HN_TIMEOUT_SEC = 30
_MAX_WORKERS = 10


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type((requests.HTTPError, requests.ConnectionError)),
    reraise=True,
)
def _get_json(url: str) -> dict | list | None:
    r = requests.get(url, timeout=_HN_TIMEOUT_SEC)
    try:
        raw_archive.persist(
            source="hn",
            url=url,
            response_body=r.content,
            response_status=r.status_code,
            response_headers=dict(r.headers),
            fetch_method="requests",
        )
    except Exception as exc:
        logger.warning("raw_archive.persist failed (hn): %s", exc)
    r.raise_for_status()
    return r.json()


def _fetch_user_submitted(username: str) -> list[int]:
    """Return the user's flat list of submitted item IDs (or [] if not found)."""
    try:
        data = _get_json(f"{_HN_BASE}/user/{username}.json")
    except requests.RequestException as exc:
        logger.warning("HN user fetch failed for %s: %s", username, exc)
        return []
    if data is None:
        # HN returns `null` for unknown users.
        logger.warning("HN user %s not found (null response)", username)
        return []
    return list(data.get("submitted") or [])


def _fetch_item(item_id: int) -> dict | None:
    """Resolve one item id. Returns None on error or deleted/dead items."""
    try:
        item = _get_json(f"{_HN_BASE}/item/{item_id}.json")
    except requests.RequestException as exc:
        logger.warning("HN item %d fetch failed: %s", item_id, exc)
        return None
    if not isinstance(item, dict):
        return None
    if item.get("deleted") or item.get("dead"):
        return None
    return item


def _item_to_event(
    item: dict, username: str, person_id: str, collected_at: datetime
) -> SignalEvent | None:
    """Map an HN item dict → SignalEvent. Returns None for unsupported types."""
    item_type = item.get("type")
    if item_type not in {"story", "comment", "poll"}:
        return None

    ts_epoch = item.get("time")
    if not isinstance(ts_epoch, int):
        return None
    ts = datetime.fromtimestamp(ts_epoch, tz=UTC)

    if item_type == "comment":
        raw_text = item.get("text", "") or ""
        likes = None
        replies = None
    else:
        # story or poll
        title = item.get("title", "") or ""
        text = item.get("text", "") or ""
        raw_text = f"{title}\n\n{text}".strip()
        likes = item.get("score")
        replies = item.get("descendants")

    title_lc = (item.get("title") or "").lower()
    metadata = {
        "type": item_type,
        "url": item.get("url"),
        "parent": item.get("parent"),
        "is_show_hn": title_lc.startswith("show hn"),
        "is_ask_hn": title_lc.startswith("ask hn"),
        "hn_url": f"https://news.ycombinator.com/item?id={item['id']}",
    }
    return SignalEvent(
        signal_id=f"hn_{item['id']}",
        person_id=person_id,
        timestamp=ts,
        platform="hackernews",
        raw_text=raw_text,
        engagement={
            "likes": likes,
            "replies": replies,
            "reposts": None,
            "views": None,
            "quotes": None,
        },
        metadata=metadata,
        collected_at=collected_at,
        source="hn_firebase",
    )


def collect_hackernews(
    username: str,
    start: date,
    end: date,
    out_dir: Path = Path("data/raw/hackernews"),
    max_items: int | None = None,
) -> Path:
    """Collect a user's HN stories + comments in [start, end). Returns path.

    The user endpoint returns ALL submitted IDs (HN returns them
    newest-first). We resolve them in parallel and client-side-filter by
    the in-window date.

    `max_items` caps how many of the (newest-first) submitted IDs are
    resolved. This bounds the fetch for power-users with tens of thousands
    of items (e.g. prolific HN commenters harvested as negatives), which
    would otherwise trigger ~50k item fetches. None = no cap (default).
    """
    person_id = handle_to_person_id(username)
    collected_at = datetime.now(UTC)

    with raw_archive.handle_scope(username):
        return _collect_hackernews_inner(
            username, person_id, start, end, collected_at, out_dir, max_items
        )


def _collect_hackernews_inner(
    username: str,
    person_id: str,
    start: date,
    end: date,
    collected_at: datetime,
    out_dir: Path,
    max_items: int | None = None,
) -> Path:
    submitted = _fetch_user_submitted(username)
    if max_items is not None and len(submitted) > max_items:
        logger.info(
            "HN user %s: capping %d submitted items to newest %d",
            username, len(submitted), max_items,
        )
        submitted = submitted[:max_items]
    logger.info("HN user %s: %d submitted items", username, len(submitted))

    # contextvars do not propagate to ThreadPoolExecutor workers by
    # default. For each submission we copy the parent's context (cheap —
    # it's a snapshot, not a deep copy) and run the worker inside it, so
    # the raw_archive handle scope is visible inside _fetch_item. A
    # fresh copy per task is required because Context.run() rejects
    # concurrent re-entry.
    items: list[dict] = []
    with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as pool:
        futures = {
            pool.submit(contextvars.copy_context().run, _fetch_item, iid): iid
            for iid in submitted
        }
        for fut in as_completed(futures):
            item = fut.result()
            if item is not None:
                items.append(item)

    events: list[SignalEvent] = []
    for item in items:
        ev = _item_to_event(item, username, person_id, collected_at)
        if ev is None:
            continue
        if start <= ev.timestamp.date() < end:
            events.append(ev)

    # De-dup by signal_id (HN's user.submitted shouldn't repeat, but be safe).
    by_id: dict[str, SignalEvent] = {}
    for e in events:
        by_id.setdefault(e.signal_id, e)
    events = list(by_id.values())

    out_path = out_dir / f"{person_id}_{start.isoformat()}_{end.isoformat()}.parquet"
    signal_events_to_parquet(events, out_path)

    n_stories = sum(1 for e in events if e.metadata.get("type") == "story")
    n_comments = sum(1 for e in events if e.metadata.get("type") == "comment")
    n_polls = sum(1 for e in events if e.metadata.get("type") == "poll")
    print(
        f"{username} | {len(events)} HN items | {start} → {end} | "
        f"stories={n_stories} comments={n_comments} polls={n_polls} | "
        f"written to {out_path}"
    )
    return out_path


@click.command()
@click.option("--username", required=True, help="HN username.")
@click.option(
    "--start",
    required=True,
    type=click.DateTime(formats=["%Y-%m-%d"]),
    help="Inclusive start date (UTC).",
)
@click.option(
    "--end",
    required=True,
    type=click.DateTime(formats=["%Y-%m-%d"]),
    help="Exclusive end date (UTC).",
)
@click.option(
    "--out-dir",
    default="data/raw/hackernews",
    type=click.Path(file_okay=False, path_type=Path),
)
def main(username: str, start: datetime, end: datetime, out_dir: Path) -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    collect_hackernews(
        username=username, start=start.date(), end=end.date(), out_dir=out_dir
    )


if __name__ == "__main__":
    main()
