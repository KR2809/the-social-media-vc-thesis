"""Product Hunt collector via the GraphQL v2 API.

Public entry: `collect_producthunt(username, start, end, out_dir) -> Path`.

Auth: `PRODUCTHUNT_DEV_TOKEN` env var (developer token from
https://api.producthunt.com/v2/oauth/applications).

Queries:
  - `user(username: "...")` → `madePosts` and `madeComments` connections.
  - Both connections paginate via `pageInfo.hasNextPage` + `endCursor`.

Date filtering is client-side. ProductHunt's GraphQL does not expose a
`createdAt` predicate on `madePosts` / `madeComments` connections.
"""

from __future__ import annotations

import logging
import os
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

from ingestion.schema import (
    SignalEvent,
    handle_to_person_id,
    signal_events_to_parquet,
)

logger = logging.getLogger(__name__)

_GQL_ENDPOINT = "https://api.producthunt.com/v2/api/graphql"
_TIMEOUT_SEC = 30
_PAGE_SIZE = 50


class ProductHuntAuthError(RuntimeError):
    """PRODUCTHUNT_DEV_TOKEN missing or rejected."""


_MADE_POSTS_QUERY = """
query MadePosts($username: String!, $after: String) {
  user(username: $username) {
    madePosts(first: 50, after: $after) {
      pageInfo { hasNextPage endCursor }
      edges {
        node {
          id
          slug
          name
          tagline
          description
          createdAt
          votesCount
          commentsCount
          thumbnail { url }
          topics(first: 10) {
            edges { node { name } }
          }
        }
      }
    }
  }
}
"""

_MADE_COMMENTS_QUERY = """
query MadeComments($username: String!, $after: String) {
  user(username: $username) {
    madeComments(first: 50, after: $after) {
      pageInfo { hasNextPage endCursor }
      edges {
        node {
          id
          body
          createdAt
          post {
            id
            slug
            name
          }
        }
      }
    }
  }
}
"""


def _require_token() -> str:
    # override=True: see note in youtube_collect._require_api_key.
    load_dotenv(override=True)
    tok = os.environ.get("PRODUCTHUNT_DEV_TOKEN")
    if not tok:
        raise ProductHuntAuthError(
            "PRODUCTHUNT_DEV_TOKEN missing — populate .env from .env.example."
        )
    return tok


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type((requests.HTTPError, requests.ConnectionError)),
    reraise=True,
)
def _gql(query: str, variables: dict, token: str) -> dict:
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    r = requests.post(
        _GQL_ENDPOINT,
        json={"query": query, "variables": variables},
        headers=headers,
        timeout=_TIMEOUT_SEC,
    )
    if r.status_code in (401, 403):
        raise ProductHuntAuthError(f"GraphQL rejected: {r.status_code} {r.text[:200]}")
    r.raise_for_status()
    payload = r.json()
    if payload.get("errors"):
        raise RuntimeError(f"GraphQL errors: {payload['errors']}")
    return payload["data"]


def _iter_made_posts(username: str, token: str):
    cursor: str | None = None
    while True:
        data = _gql(_MADE_POSTS_QUERY, {"username": username, "after": cursor}, token)
        user = data.get("user")
        if not user:
            return
        conn = user.get("madePosts") or {}
        for edge in conn.get("edges", []):
            yield edge["node"]
        page_info = conn.get("pageInfo") or {}
        if not page_info.get("hasNextPage"):
            return
        cursor = page_info.get("endCursor")
        if not cursor:
            return


def _iter_made_comments(username: str, token: str):
    cursor: str | None = None
    while True:
        data = _gql(
            _MADE_COMMENTS_QUERY, {"username": username, "after": cursor}, token
        )
        user = data.get("user")
        if not user:
            return
        conn = user.get("madeComments") or {}
        for edge in conn.get("edges", []):
            yield edge["node"]
        page_info = conn.get("pageInfo") or {}
        if not page_info.get("hasNextPage"):
            return
        cursor = page_info.get("endCursor")
        if not cursor:
            return


def _parse_ts(iso: str | None) -> datetime | None:
    if not iso:
        return None
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None


def _post_to_event(post: dict, person_id: str, collected_at: datetime) -> SignalEvent | None:
    ts = _parse_ts(post.get("createdAt"))
    if ts is None or not post.get("id"):
        return None
    tagline = post.get("tagline", "") or ""
    description = post.get("description", "") or ""
    raw_text = f"{tagline}\n\n{description}".strip()

    topics: list[str] = []
    topics_conn = post.get("topics") or {}
    for edge in topics_conn.get("edges", []) or []:
        name = (edge.get("node") or {}).get("name")
        if name:
            topics.append(name)
    slug = post.get("slug")
    return SignalEvent(
        signal_id=f"ph_post_{post['id']}",
        person_id=person_id,
        timestamp=ts,
        platform="producthunt",
        raw_text=raw_text,
        engagement={
            "likes": post.get("votesCount"),
            "replies": post.get("commentsCount"),
            "reposts": None,
            "views": None,
            "quotes": None,
        },
        metadata={
            "type": "post",
            "post_url": f"https://www.producthunt.com/posts/{slug}" if slug else None,
            "topics": topics,
            "thumbnail_url": (post.get("thumbnail") or {}).get("url"),
            "name": post.get("name"),
        },
        collected_at=collected_at,
        source="producthunt_graphql",
    )


def _comment_to_event(
    comment: dict, person_id: str, collected_at: datetime
) -> SignalEvent | None:
    ts = _parse_ts(comment.get("createdAt"))
    if ts is None or not comment.get("id"):
        return None
    post = comment.get("post") or {}
    slug = post.get("slug")
    return SignalEvent(
        signal_id=f"ph_comment_{comment['id']}",
        person_id=person_id,
        timestamp=ts,
        platform="producthunt",
        raw_text=comment.get("body", "") or "",
        engagement={
            "likes": None,
            "replies": None,
            "reposts": None,
            "views": None,
            "quotes": None,
        },
        metadata={
            "type": "comment",
            "post_url": f"https://www.producthunt.com/posts/{slug}" if slug else None,
            "post_id": post.get("id"),
            "post_name": post.get("name"),
            "topics": [],
            "thumbnail_url": None,
        },
        collected_at=collected_at,
        source="producthunt_graphql",
    )


def collect_producthunt(
    username: str,
    start: date,
    end: date,
    out_dir: Path = Path("data/raw/producthunt"),
    token: str | None = None,
) -> Path:
    """Collect a user's PH posts + comments in [start, end). Returns path."""
    person_id = handle_to_person_id(username)
    collected_at = datetime.now(UTC)
    if token is None:
        token = _require_token()

    events: list[SignalEvent] = []
    n_posts_seen = 0
    n_comments_seen = 0

    try:
        for post in _iter_made_posts(username, token):
            n_posts_seen += 1
            ev = _post_to_event(post, person_id, collected_at)
            if ev is None:
                continue
            if start <= ev.timestamp.date() < end:
                events.append(ev)
    except requests.RequestException as exc:
        logger.warning("PH madePosts iteration failed: %s", exc)

    try:
        for comment in _iter_made_comments(username, token):
            n_comments_seen += 1
            ev = _comment_to_event(comment, person_id, collected_at)
            if ev is None:
                continue
            if start <= ev.timestamp.date() < end:
                events.append(ev)
    except requests.RequestException as exc:
        logger.warning("PH madeComments iteration failed: %s", exc)

    # De-dup defensively on signal_id.
    by_id: dict[str, SignalEvent] = {}
    for e in events:
        by_id.setdefault(e.signal_id, e)
    events = list(by_id.values())

    out_path = out_dir / f"{person_id}_{start.isoformat()}_{end.isoformat()}.parquet"
    signal_events_to_parquet(events, out_path)
    n_posts = sum(1 for e in events if e.metadata["type"] == "post")
    n_coms = sum(1 for e in events if e.metadata["type"] == "comment")
    print(
        f"{username} | {len(events)} PH items | {start} → {end} | "
        f"posts={n_posts} comments={n_coms} | seen posts={n_posts_seen} comments={n_comments_seen} | "
        f"written to {out_path}"
    )
    return out_path


@click.command()
@click.option("--username", required=True, help="Product Hunt username.")
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
    default="data/raw/producthunt",
    type=click.Path(file_okay=False, path_type=Path),
)
def main(username: str, start: datetime, end: datetime, out_dir: Path) -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    collect_producthunt(
        username=username, start=start.date(), end=end.date(), out_dir=out_dir
    )


if __name__ == "__main__":
    main()
