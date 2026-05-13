"""Reddit collector via PRAW (read-only OAuth).

Public entry: `collect_reddit(username, start, end, out_dir) -> Path`.

Auth: `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`, `REDDIT_USER_AGENT` env
vars (loaded from `.env`). Read-only mode; no user login required.

PRAW does not support server-side date filtering on `Redditor.submissions`
or `Redditor.comments`. We iterate `limit=None` and filter in-window
client-side. Reddit caps user listings at ~1000 items globally; if we
hit that ceiling we log a warning so the cohort balance report can flag
potentially-truncated users.

PRAW handles rate-limiting and retries automatically; we don't add
extra throttling.
"""

from __future__ import annotations

import logging
import os
from datetime import UTC, date, datetime
from pathlib import Path

import click
import praw
from dotenv import load_dotenv
from prawcore.exceptions import NotFound, PrawcoreException

from ingestion.schema import (
    SignalEvent,
    handle_to_person_id,
    signal_events_to_parquet,
)

logger = logging.getLogger(__name__)

# Reddit's hard per-listing ceiling. PRAW will fetch up to this many items
# before the API stops paginating. Cohort members above this lose history.
_REDDIT_LISTING_CEILING = 1000


class RedditAuthError(RuntimeError):
    """REDDIT_CLIENT_ID/SECRET/USER_AGENT missing."""


def _require_reddit_client() -> praw.Reddit:
    load_dotenv()
    cid = os.environ.get("REDDIT_CLIENT_ID")
    csec = os.environ.get("REDDIT_CLIENT_SECRET")
    uagent = os.environ.get("REDDIT_USER_AGENT")
    missing = [
        k
        for k, v in {
            "REDDIT_CLIENT_ID": cid,
            "REDDIT_CLIENT_SECRET": csec,
            "REDDIT_USER_AGENT": uagent,
        }.items()
        if not v
    ]
    if missing:
        raise RedditAuthError(
            f"Missing env vars: {', '.join(missing)}. Populate .env from .env.example."
        )
    return praw.Reddit(
        client_id=cid,
        client_secret=csec,
        user_agent=uagent,
        check_for_async=False,
    )


def _submission_to_event(
    sub, person_id: str, collected_at: datetime
) -> SignalEvent:
    title = getattr(sub, "title", "") or ""
    selftext = getattr(sub, "selftext", "") or ""
    raw_text = f"{title}\n\n{selftext}".strip()
    return SignalEvent(
        signal_id=f"reddit_sub_{sub.id}",
        person_id=person_id,
        timestamp=datetime.fromtimestamp(sub.created_utc, tz=UTC),
        platform="reddit",
        raw_text=raw_text,
        engagement={
            "likes": getattr(sub, "score", None),
            "replies": getattr(sub, "num_comments", None),
            "reposts": None,
            "views": None,
            "quotes": None,
        },
        metadata={
            "type": "submission",
            "subreddit": str(getattr(sub.subreddit, "display_name", "")) if getattr(sub, "subreddit", None) else None,
            "url": f"https://www.reddit.com{sub.permalink}" if getattr(sub, "permalink", None) else None,
            "is_self": getattr(sub, "is_self", None),
            "parent_id": None,
        },
        collected_at=collected_at,
        source="praw",
    )


def _comment_to_event(
    comment, person_id: str, collected_at: datetime
) -> SignalEvent:
    raw_text = getattr(comment, "body", "") or ""
    return SignalEvent(
        signal_id=f"reddit_comment_{comment.id}",
        person_id=person_id,
        timestamp=datetime.fromtimestamp(comment.created_utc, tz=UTC),
        platform="reddit",
        raw_text=raw_text,
        engagement={
            "likes": getattr(comment, "score", None),
            "replies": None,  # not available on comments via the listing
            "reposts": None,
            "views": None,
            "quotes": None,
        },
        metadata={
            "type": "comment",
            "subreddit": str(getattr(comment.subreddit, "display_name", "")) if getattr(comment, "subreddit", None) else None,
            "url": f"https://www.reddit.com{comment.permalink}" if getattr(comment, "permalink", None) else None,
            "is_self": None,
            "parent_id": getattr(comment, "parent_id", None),
        },
        collected_at=collected_at,
        source="praw",
    )


def _collect_listing(
    listing_iter, kind: str, person_id: str, start: date, end: date, collected_at: datetime
) -> tuple[list[SignalEvent], bool]:
    """Walk a PRAW listing and map to events. Returns (events, hit_ceiling)."""
    events: list[SignalEvent] = []
    seen = 0
    try:
        for item in listing_iter:
            seen += 1
            ts = datetime.fromtimestamp(item.created_utc, tz=UTC)
            if not (start <= ts.date() < end):
                # We do NOT break: PRAW listings are returned in `.new` order
                # by default; older items may interleave with re-orderings,
                # and the caller can specify other sorts. Keep iterating up
                # to the listing ceiling.
                continue
            if kind == "submission":
                events.append(_submission_to_event(item, person_id, collected_at))
            else:
                events.append(_comment_to_event(item, person_id, collected_at))
    except NotFound:
        logger.warning("PRAW reported user/listing not found for kind=%s", kind)
        return [], False
    except PrawcoreException as exc:
        logger.warning("PRAW error during %s listing: %s", kind, exc)
        return events, False

    hit_ceiling = seen >= _REDDIT_LISTING_CEILING
    if hit_ceiling:
        logger.warning(
            "Reddit %s listing hit the %d-item ceiling for this user; "
            "older history may be truncated.",
            kind,
            _REDDIT_LISTING_CEILING,
        )
    return events, hit_ceiling


def collect_reddit(
    username: str,
    start: date,
    end: date,
    out_dir: Path = Path("data/raw/reddit"),
    reddit_client: praw.Reddit | None = None,
) -> Path:
    """Collect submissions + comments by `username` in [start, end). Returns path."""
    person_id = handle_to_person_id(username)
    collected_at = datetime.now(UTC)
    if reddit_client is None:
        reddit_client = _require_reddit_client()

    redditor = reddit_client.redditor(username)

    sub_events, sub_truncated = _collect_listing(
        redditor.submissions.new(limit=None),
        "submission",
        person_id,
        start,
        end,
        collected_at,
    )
    com_events, com_truncated = _collect_listing(
        redditor.comments.new(limit=None),
        "comment",
        person_id,
        start,
        end,
        collected_at,
    )

    events = sub_events + com_events
    # De-dup defensively on signal_id (shouldn't happen but be safe).
    by_id: dict[str, SignalEvent] = {}
    for e in events:
        by_id.setdefault(e.signal_id, e)
    events = list(by_id.values())

    out_path = out_dir / f"{person_id}_{start.isoformat()}_{end.isoformat()}.parquet"
    signal_events_to_parquet(events, out_path)

    n_subs = sum(1 for e in events if e.metadata["type"] == "submission")
    n_coms = sum(1 for e in events if e.metadata["type"] == "comment")
    print(
        f"{username} | {len(events)} reddit items | {start} → {end} | "
        f"submissions={n_subs} comments={n_coms} | "
        f"truncated_sub={sub_truncated} truncated_com={com_truncated} | "
        f"written to {out_path}"
    )
    return out_path


@click.command()
@click.option("--username", required=True, help="Reddit username (no /u/).")
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
    default="data/raw/reddit",
    type=click.Path(file_okay=False, path_type=Path),
)
def main(username: str, start: datetime, end: datetime, out_dir: Path) -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    collect_reddit(
        username=username, start=start.date(), end=end.date(), out_dir=out_dir
    )


if __name__ == "__main__":
    main()
