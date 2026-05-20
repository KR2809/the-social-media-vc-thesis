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
import time
from dataclasses import dataclass
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

# PH dev tokens get 6,250 complexity points per 15-minute window. When the
# remaining budget falls below this threshold, gate the next call until the
# window resets — self-throttling so we never actually hit 429.
_RATE_LIMIT_FLOOR = 200
# Headers returned on every PH GraphQL response.
_HEADER_LIMIT = "X-Rate-Limit-Limit"
_HEADER_REMAINING = "X-Rate-Limit-Remaining"
_HEADER_RESET = "X-Rate-Limit-Reset"


class ProductHuntAuthError(RuntimeError):
    """PRODUCTHUNT_DEV_TOKEN missing or rejected."""


class ProductHuntRateLimitedError(RuntimeError):
    """PH returned 429. The `reset_seconds` attribute carries the retry-after.

    Deliberately NOT a subclass of HTTPError — that's what tenacity retries on,
    and retrying a 429 burns more budget for nothing. Callers should catch this
    explicitly, sleep, and try again from the top.
    """

    def __init__(self, reset_seconds: int) -> None:
        self.reset_seconds = max(reset_seconds, 1)
        super().__init__(
            f"PH GraphQL rate-limited; reset in ~{self.reset_seconds}s"
        )


@dataclass
class _RateLimitState:
    """Latest rate-limit headers parsed from a PH response, per token."""

    limit: int = 6250
    remaining: int = 6250
    reset_at_epoch: float = 0.0
    last_seen_epoch: float = 0.0

    def parse_response(self, resp: requests.Response, now: float) -> None:
        try:
            self.limit = int(resp.headers.get(_HEADER_LIMIT, self.limit))
            self.remaining = int(resp.headers.get(_HEADER_REMAINING, self.remaining))
            reset_in = int(resp.headers.get(_HEADER_RESET, 0))
            if reset_in > 0:
                self.reset_at_epoch = now + reset_in
        except (TypeError, ValueError):
            # Headers absent or malformed — leave state as-is.
            pass
        self.last_seen_epoch = now

    def seconds_until_reset(self, now: float) -> int:
        return max(int(self.reset_at_epoch - now), 0)


# Module-level rate-limit state keyed by token string. Per-token, so the dual-
# token round-robin can pick whichever has more headroom.
_RATE_LIMIT_BY_TOKEN: dict[str, _RateLimitState] = {}


def rate_limit_state(token: str) -> _RateLimitState:
    """Public accessor — used by tests + observability prints in CLIs."""
    return _RATE_LIMIT_BY_TOKEN.setdefault(token, _RateLimitState())


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


def _require_tokens() -> list[str]:
    """Return all configured PH dev tokens (primary + optional secondary).

    Reads `PRODUCTHUNT_DEV_TOKEN` (required) and `PRODUCTHUNT_DEV_TOKEN_2`
    (optional). A second token doubles the per-15-minute complexity budget
    when the candidate-longlist tool round-robins between them.
    """
    # override=True: see note in youtube_collect._require_api_key.
    load_dotenv(override=True)
    primary = os.environ.get("PRODUCTHUNT_DEV_TOKEN")
    if not primary:
        raise ProductHuntAuthError(
            "PRODUCTHUNT_DEV_TOKEN missing — populate .env from .env.example."
        )
    tokens = [primary]
    secondary = os.environ.get("PRODUCTHUNT_DEV_TOKEN_2")
    if secondary:
        tokens.append(secondary)
    return tokens


def _require_token() -> str:
    """Back-compat shim for callers that don't care about the second token."""
    return _require_tokens()[0]


def _pick_token(tokens: list[str], now: float | None = None) -> str:
    """Pick the token with the most remaining budget.

    Ties broken in favour of the first token (primary), so single-token
    callers behave identically to before.
    """
    if len(tokens) == 1:
        return tokens[0]
    now = now if now is not None else time.time()
    return max(
        tokens,
        key=lambda t: rate_limit_state(t).remaining
        if rate_limit_state(t).last_seen_epoch > 0
        else 10**9,  # untouched tokens look "fresh" — try them first
    )


def _gate_before_call(token: str) -> None:
    """If the token's remaining budget is below floor, sleep until reset.

    Self-throttle so we never actually hit 429.
    """
    state = rate_limit_state(token)
    now = time.time()
    if state.last_seen_epoch == 0:
        # Never made a call on this token — let it rip; we'll learn the
        # window from the first response.
        return
    if state.remaining >= _RATE_LIMIT_FLOOR:
        return
    wait = state.seconds_until_reset(now) + 1
    if wait <= 0:
        return
    logger.warning(
        "PH dev token near quota (remaining=%d, floor=%d); sleeping %ds until reset",
        state.remaining, _RATE_LIMIT_FLOOR, wait,
    )
    time.sleep(wait)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    # IMPORTANT: ProductHuntRateLimitedError is NOT in this list — retrying a 429
    # burns more quota. Caller decides whether to sleep + retry.
    retry=retry_if_exception_type((requests.ConnectionError, requests.Timeout)),
    reraise=True,
)
def _gql(query: str, variables: dict, token: str) -> dict:
    _gate_before_call(token)
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
    # Parse rate-limit headers BEFORE handling status, so the governor learns
    # the window state even on errors.
    rate_limit_state(token).parse_response(r, time.time())
    if r.status_code == 429:
        # PH sometimes returns Retry-After; fall back to the window reset.
        retry_after = r.headers.get("Retry-After")
        try:
            reset_seconds = int(retry_after) if retry_after else rate_limit_state(token).seconds_until_reset(time.time())
        except ValueError:
            reset_seconds = 60
        raise ProductHuntRateLimitedError(reset_seconds)
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
