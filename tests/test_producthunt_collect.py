"""Unit tests for ingestion.producthunt_collect.

Stdlib unittest.mock. No live network. Five tests:
1. success path (posts + comments, mixed in/out of window)
2. empty user (GraphQL returns user: null)
3. missing token raises ProductHuntAuthError
4. graphql errors surface as exception (not silent zero)
5. pagination across multiple pages of madePosts
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest

from ingestion import producthunt_collect
from ingestion.producthunt_collect import (
    ProductHuntAuthError,
    collect_producthunt,
)
from ingestion.schema import parquet_to_signal_events


def _posts_response(posts: list[dict], has_next: bool = False, end_cursor: str | None = None) -> dict:
    return {
        "user": {
            "madePosts": {
                "pageInfo": {"hasNextPage": has_next, "endCursor": end_cursor},
                "edges": [{"node": p} for p in posts],
            }
        }
    }


def _comments_response(comments: list[dict], has_next: bool = False, end_cursor: str | None = None) -> dict:
    return {
        "user": {
            "madeComments": {
                "pageInfo": {"hasNextPage": has_next, "endCursor": end_cursor},
                "edges": [{"node": c} for c in comments],
            }
        }
    }


def test_missing_token_raises() -> None:
    with patch.dict("os.environ", {"PRODUCTHUNT_DEV_TOKEN": ""}, clear=False):
        with patch.object(producthunt_collect, "load_dotenv"):
            with pytest.raises(ProductHuntAuthError):
                producthunt_collect._require_token()


def test_success_path(tmp_path: Path) -> None:
    posts = [
        {
            "id": "p1",
            "slug": "remoteok",
            "name": "RemoteOK",
            "tagline": "Find a remote job",
            "description": "The biggest remote-job board",
            "createdAt": "2014-06-15T12:00:00Z",
            "votesCount": 1200,
            "commentsCount": 80,
            "thumbnail": {"url": "https://ph-files/p1.png"},
            "topics": {"edges": [{"node": {"name": "Remote Work"}}, {"node": {"name": "Jobs"}}]},
        },
        {
            # out of window — should be dropped
            "id": "p2",
            "slug": "old",
            "name": "Old launch",
            "tagline": "old",
            "description": "",
            "createdAt": "2010-01-01T00:00:00Z",
            "votesCount": 1,
            "commentsCount": 0,
            "thumbnail": None,
            "topics": {"edges": []},
        },
    ]
    comments = [
        {
            "id": "c1",
            "body": "great launch",
            "createdAt": "2014-06-20T08:00:00Z",
            "post": {"id": "p_other", "slug": "another", "name": "Another"},
        }
    ]

    def _gql_side_effect(query: str, variables: dict, token: str):
        if "madePosts" in query:
            return _posts_response(posts, has_next=False)
        if "madeComments" in query:
            return _comments_response(comments, has_next=False)
        raise AssertionError(f"unexpected query: {query[:30]}")

    with patch.object(producthunt_collect, "_gql", side_effect=_gql_side_effect):
        out = collect_producthunt(
            username="pieter-levels",
            start=date(2014, 6, 1),
            end=date(2014, 7, 1),
            out_dir=tmp_path,
            token="fake_token",
        )

    events = parquet_to_signal_events(out)
    assert len(events) == 2
    by_id = {e.signal_id: e for e in events}

    post = by_id["ph_post_p1"]
    assert post.platform == "producthunt"
    assert post.source == "producthunt_graphql"
    assert post.engagement["likes"] == 1200
    assert post.engagement["replies"] == 80
    assert post.metadata["type"] == "post"
    assert post.metadata["topics"] == ["Remote Work", "Jobs"]
    assert post.metadata["post_url"] == "https://www.producthunt.com/posts/remoteok"
    assert "Find a remote job" in post.raw_text
    assert "biggest remote-job board" in post.raw_text

    com = by_id["ph_comment_c1"]
    assert com.metadata["type"] == "comment"
    assert com.engagement["likes"] is None
    assert com.metadata["post_url"] == "https://www.producthunt.com/posts/another"
    assert com.raw_text == "great launch"


def test_empty_user_returns_empty_parquet(tmp_path: Path) -> None:
    """When PH says `user: null`, write empty parquet with no errors."""

    def _gql_side_effect(query: str, variables: dict, token: str):
        return {"user": None}

    with patch.object(producthunt_collect, "_gql", side_effect=_gql_side_effect):
        out = collect_producthunt(
            username="nobody",
            start=date(2024, 1, 1),
            end=date(2024, 2, 1),
            out_dir=tmp_path,
            token="fake",
        )
    assert parquet_to_signal_events(out) == []


def test_graphql_errors_surface_when_iterating() -> None:
    """If PH returns `errors:` payload, our _gql should raise."""
    import requests

    fake_resp = requests.models.Response()
    fake_resp.status_code = 200
    fake_resp._content = b'{"errors": [{"message": "bad query"}]}'

    with patch.object(producthunt_collect.requests, "post", return_value=fake_resp):
        with pytest.raises(RuntimeError, match="GraphQL errors"):
            producthunt_collect._gql("query {}", {}, "fake_token")


def test_pagination_across_multiple_pages(tmp_path: Path) -> None:
    """Two pages of posts, no comments. We should see all four posts in window."""
    page1_posts = [
        {
            "id": f"p{i}",
            "slug": f"p{i}",
            "name": f"P{i}",
            "tagline": "t",
            "description": "",
            "createdAt": "2014-06-15T12:00:00Z",
            "votesCount": i,
            "commentsCount": 0,
            "thumbnail": None,
            "topics": {"edges": []},
        }
        for i in range(1, 3)
    ]
    page2_posts = [
        {
            "id": f"p{i}",
            "slug": f"p{i}",
            "name": f"P{i}",
            "tagline": "t",
            "description": "",
            "createdAt": "2014-06-20T12:00:00Z",
            "votesCount": i,
            "commentsCount": 0,
            "thumbnail": None,
            "topics": {"edges": []},
        }
        for i in range(3, 5)
    ]

    call_count = {"posts": 0, "comments": 0}

    def _gql_side_effect(query: str, variables: dict, token: str):
        if "madePosts" in query:
            call_count["posts"] += 1
            if call_count["posts"] == 1:
                return _posts_response(page1_posts, has_next=True, end_cursor="cursor1")
            return _posts_response(page2_posts, has_next=False)
        if "madeComments" in query:
            call_count["comments"] += 1
            return _comments_response([])
        raise AssertionError("unexpected")

    with patch.object(producthunt_collect, "_gql", side_effect=_gql_side_effect):
        out = collect_producthunt(
            username="u",
            start=date(2014, 6, 1),
            end=date(2014, 7, 1),
            out_dir=tmp_path,
            token="fake",
        )

    events = parquet_to_signal_events(out)
    assert len(events) == 4
    assert {e.signal_id for e in events} == {"ph_post_p1", "ph_post_p2", "ph_post_p3", "ph_post_p4"}
    assert call_count["posts"] == 2  # exactly two pages walked


# ---------------------------------------------------------------------------
# Rate-limit governor (Piece 1) + dual-token round-robin (Piece 4)
# ---------------------------------------------------------------------------


class _FakeResponse:
    """Minimal stand-in for requests.Response that _gql touches."""

    def __init__(
        self,
        status_code: int = 200,
        headers: dict[str, str] | None = None,
        json_payload: dict | None = None,
    ) -> None:
        self.status_code = status_code
        self.headers = headers or {}
        self._json = json_payload or {"data": {"ok": True}}

    def json(self) -> dict:
        return self._json

    def raise_for_status(self) -> None:
        import requests as _r
        if self.status_code >= 400:
            raise _r.HTTPError(f"{self.status_code}")


def _reset_rate_limit_state() -> None:
    producthunt_collect._RATE_LIMIT_BY_TOKEN.clear()


def test_gql_parses_rate_limit_headers() -> None:
    _reset_rate_limit_state()
    fake = _FakeResponse(
        headers={
            "X-Rate-Limit-Limit": "6250",
            "X-Rate-Limit-Remaining": "5800",
            "X-Rate-Limit-Reset": "830",
        }
    )
    with patch.object(producthunt_collect.requests, "post", return_value=fake):
        producthunt_collect._gql("query {}", {}, "tok-A")

    state = producthunt_collect.rate_limit_state("tok-A")
    assert state.limit == 6250
    assert state.remaining == 5800
    assert state.last_seen_epoch > 0
    # reset_at_epoch is now + 830s — give it generous tolerance.
    import time
    assert state.reset_at_epoch > time.time()
    assert state.reset_at_epoch <= time.time() + 831


def test_gql_429_raises_non_retryable_rate_limited() -> None:
    _reset_rate_limit_state()
    fake = _FakeResponse(
        status_code=429,
        headers={"Retry-After": "42"},
        json_payload={"errors": ["rate-limited"]},
    )
    with patch.object(producthunt_collect.requests, "post", return_value=fake):
        with pytest.raises(producthunt_collect.ProductHuntRateLimitedError) as exc:
            producthunt_collect._gql("query {}", {}, "tok-B")
    assert exc.value.reset_seconds == 42


def test_gate_before_call_sleeps_when_under_floor() -> None:
    _reset_rate_limit_state()
    # Prime the state: pretend we made a call that drained the budget.
    state = producthunt_collect.rate_limit_state("tok-C")
    import time
    state.limit = 6250
    state.remaining = 10  # well under the 200 floor
    state.reset_at_epoch = time.time() + 5  # resets in 5s
    state.last_seen_epoch = time.time()

    slept_for: list[float] = []

    def _fake_sleep(s: float) -> None:
        slept_for.append(s)

    with patch.object(producthunt_collect.time, "sleep", side_effect=_fake_sleep):
        producthunt_collect._gate_before_call("tok-C")

    assert len(slept_for) == 1
    # Should sleep at least until reset (5s) + 1s buffer.
    assert slept_for[0] >= 5


def test_gate_before_call_no_sleep_when_above_floor() -> None:
    _reset_rate_limit_state()
    state = producthunt_collect.rate_limit_state("tok-D")
    state.remaining = 5000
    state.last_seen_epoch = 1.0  # touched

    slept_for: list[float] = []
    with patch.object(producthunt_collect.time, "sleep", side_effect=lambda s: slept_for.append(s)):
        producthunt_collect._gate_before_call("tok-D")
    assert slept_for == []


def test_gate_before_call_no_sleep_on_untouched_token() -> None:
    """First-ever call on a token shouldn't gate — we don't know the window yet."""
    _reset_rate_limit_state()
    slept_for: list[float] = []
    with patch.object(producthunt_collect.time, "sleep", side_effect=lambda s: slept_for.append(s)):
        producthunt_collect._gate_before_call("tok-untouched")
    assert slept_for == []


def test_require_tokens_returns_single_when_no_secondary() -> None:
    with patch.dict(
        "os.environ",
        {"PRODUCTHUNT_DEV_TOKEN": "primary", "PRODUCTHUNT_DEV_TOKEN_2": ""},
        clear=False,
    ):
        with patch.object(producthunt_collect, "load_dotenv"):
            assert producthunt_collect._require_tokens() == ["primary"]


def test_require_tokens_returns_both_when_secondary_set() -> None:
    with patch.dict(
        "os.environ",
        {"PRODUCTHUNT_DEV_TOKEN": "primary", "PRODUCTHUNT_DEV_TOKEN_2": "secondary"},
        clear=False,
    ):
        with patch.object(producthunt_collect, "load_dotenv"):
            assert producthunt_collect._require_tokens() == ["primary", "secondary"]


def test_pick_token_prefers_higher_remaining() -> None:
    _reset_rate_limit_state()
    # tok-A has been touched and is nearly exhausted.
    a = producthunt_collect.rate_limit_state("tok-A")
    a.remaining = 50
    a.last_seen_epoch = 1.0
    # tok-B has been touched and has more headroom.
    b = producthunt_collect.rate_limit_state("tok-B")
    b.remaining = 3000
    b.last_seen_epoch = 1.0
    assert producthunt_collect._pick_token(["tok-A", "tok-B"]) == "tok-B"


def test_pick_token_single_token_passthrough() -> None:
    _reset_rate_limit_state()
    assert producthunt_collect._pick_token(["only-token"]) == "only-token"


def test_pick_token_prefers_untouched_token() -> None:
    """An untouched token has unknown budget — preferred over a drained one."""
    _reset_rate_limit_state()
    drained = producthunt_collect.rate_limit_state("drained")
    drained.remaining = 5
    drained.last_seen_epoch = 1.0
    # untouched has no entry in the table yet; _pick_token should still prefer it.
    assert producthunt_collect._pick_token(["drained", "untouched"]) == "untouched"
