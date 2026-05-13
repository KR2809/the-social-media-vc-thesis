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
