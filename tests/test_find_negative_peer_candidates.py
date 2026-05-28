"""Unit tests for scripts.find_negative_peer_candidates.

All network calls are mocked. Coverage:
  1. NICHE_MAP is exhaustive — 15 PH-applicable + 4 research-Substack;
     research-Substack entries are explicitly out-of-scope.
  2. Positives-cohort makers are excluded from candidate lists.
  3. Wayback classification: live / dormant / gone / no_wayback_data.
  4. Outcome-class guess decision tree.
  5. CSV schema integrity — header + dict round-trip.
"""

from __future__ import annotations

import csv
from dataclasses import asdict
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts import find_negative_peer_candidates as fnpc
from scripts.find_negative_peer_candidates import (
    CSV_FIELDS,
    NICHE_MAP,
    CandidateRow,
    _outcome_class_guess,
    _parse_quarter,
    _post_makers_intersect_positives,
    _post_matches_keywords,
    classify_wayback,
    find_candidates_for_niche,
    write_csv,
)

# ---------------------------------------------------------------------------
# 1. Mapping table is exhaustive
# ---------------------------------------------------------------------------

# These are the 15 PH-applicable niches; slug matches `register_negative_peers.py`
# `peer_id` slug (minus the `NEG_` prefix and `_YYYYQX_NN` suffix).
EXPECTED_PH_NICHES = {
    "dev-tooling-boilerplate",
    "image-video-generation-api",
    "notion-adjacent-tooling",
    "twitter-growth-tools",
    "testimonials-social-proof",
    "ai-consumer-cheating-tools",
    "ai-creator-ads-automation",
    "newsletter-vertical-professional",
    "newsletter-niche-professional",
    "newsletter-cohort-writing",
    "creator-economy-education-finance",
    "solo-creator-content-business",
    "community-led-education",
    "mental-models-newsletter",
    "multi-product-indie-twitter-tooling",
}

EXPECTED_RESEARCH_SUBSTACK_NICHES = {
    "research-substack-thematic-equity-macro",
    "research-substack-energy-commodities",
    "research-substack-tech-vc-analyst",
    "research-substack-finance-tech-analyst",
}


def test_niche_map_covers_all_15_ph_niches() -> None:
    ph_slugs = {k for k, v in NICHE_MAP.items() if not v["out_of_scope"]}
    assert ph_slugs == EXPECTED_PH_NICHES, (
        f"missing or extra PH niches:\n"
        f"  missing: {sorted(EXPECTED_PH_NICHES - ph_slugs)}\n"
        f"  extra:   {sorted(ph_slugs - EXPECTED_PH_NICHES)}"
    )


def test_niche_map_marks_research_substack_out_of_scope() -> None:
    oos_slugs = {k for k, v in NICHE_MAP.items() if v["out_of_scope"]}
    assert oos_slugs == EXPECTED_RESEARCH_SUBSTACK_NICHES


def test_niche_map_every_entry_has_required_fields() -> None:
    required = {
        "niche_label",
        "emergence_quarter",
        "ph_topic_slugs",
        "search_keywords",
        "requires_review",
        "rationale",
        "out_of_scope",
    }
    for slug, spec in NICHE_MAP.items():
        assert required.issubset(spec.keys()), f"{slug} missing {required - spec.keys()}"


# ---------------------------------------------------------------------------
# 2. Quarter parsing
# ---------------------------------------------------------------------------


def test_parse_quarter_expands_window_by_2_months() -> None:
    start, end = _parse_quarter("2020-Q3")
    # Q3-2020 = July 1 → Oct 1. ±2 months = May 1 → Dec 1.
    assert start == date(2020, 5, 1)
    assert end == date(2020, 12, 1)


def test_parse_quarter_q4_crosses_year_boundary() -> None:
    start, end = _parse_quarter("2019-Q4")
    # Q4 = Oct 1, 2019 → Jan 1, 2020. ±2 months = Aug 1, 2019 → Mar 1, 2020.
    assert start == date(2019, 8, 1)
    assert end == date(2020, 3, 1)


# ---------------------------------------------------------------------------
# 3. Wayback classification — 4 paths
# ---------------------------------------------------------------------------


def test_classify_wayback_live_when_snapshots_in_window() -> None:
    # Launch Jan 1 2020 → window = July 1 2021 → July 1 2022.
    # Single-query contract: fetcher is called once with (launch, win_end);
    # the function buckets timestamps in-memory.
    def fetcher(url, start, end):
        return ["20200110000000", "20211215000000", "20220601000000"]

    status, last = classify_wayback("https://example.com", date(2020, 1, 1), fetcher=fetcher)
    assert status == "live"
    assert last == "20220601000000"


def test_classify_wayback_dormant_when_snapshots_only_pre_window() -> None:
    def fetcher(url, start, end):
        # Snapshots exist but all before the 18mo-after-launch window.
        return ["20200115000000", "20200601000000"]

    status, last = classify_wayback("https://example.com", date(2020, 1, 1), fetcher=fetcher)
    assert status == "dormant"
    assert last == "20200601000000"


def test_classify_wayback_gone_when_no_snapshots_at_all() -> None:
    def fetcher(url, start, end):
        return []

    status, last = classify_wayback("https://example.com", date(2020, 1, 1), fetcher=fetcher)
    assert status == "gone"
    assert last is None


def test_classify_wayback_no_data_when_url_missing() -> None:
    status, last = classify_wayback(None, date(2020, 1, 1))
    assert status == "no_wayback_data"
    assert last is None

    status, last = classify_wayback("", date(2020, 1, 1))
    assert status == "no_wayback_data"


# ---------------------------------------------------------------------------
# 4. Outcome class guess decision tree
# ---------------------------------------------------------------------------


def test_outcome_class_guess_dormant_to_abandoned() -> None:
    assert _outcome_class_guess("dormant", 5) == "abandoned"
    assert _outcome_class_guess("dormant", 80) == "abandoned"


def test_outcome_class_guess_gone_to_abandoned() -> None:
    assert _outcome_class_guess("gone", 5) == "abandoned"


def test_outcome_class_guess_live_low_upvotes_to_low_traction() -> None:
    assert _outcome_class_guess("live", 5) == "low_traction"
    assert _outcome_class_guess("live", 99) == "low_traction"


def test_outcome_class_guess_no_data_defaults_low_traction() -> None:
    assert _outcome_class_guess("no_wayback_data", 5) == "low_traction"


# ---------------------------------------------------------------------------
# 5. Positives-cohort exclusion
# ---------------------------------------------------------------------------


def test_post_makers_intersect_positives_matches_x_handle() -> None:
    post = {"makers": [{"username": "someone_else", "twitterUsername": "marclou"}]}
    assert _post_makers_intersect_positives(post, {"marclou"}) is True


def test_post_makers_intersect_positives_matches_ph_handle() -> None:
    post = {"makers": [{"username": "marclou", "twitterUsername": ""}]}
    assert _post_makers_intersect_positives(post, {"marclou"}) is True


def test_post_makers_intersect_positives_no_match() -> None:
    post = {"makers": [{"username": "nobody", "twitterUsername": "nobody"}]}
    assert _post_makers_intersect_positives(post, {"marclou", "levelsio"}) is False


def test_post_makers_intersect_positives_handles_at_prefix() -> None:
    post = {"makers": [{"twitterUsername": "@marclou"}]}
    assert _post_makers_intersect_positives(post, {"marclou"}) is True


# ---------------------------------------------------------------------------
# 6. find_candidates_for_niche integration (mocked PH + Wayback)
# ---------------------------------------------------------------------------


def _fake_post(
    pid: str,
    upvotes: int,
    *,
    maker_x: str = "",
    maker_ph: str = "",
    website: str = "https://example.com",
    created_at: str = "2023-08-15T12:00:00Z",
    slug: str | None = None,
) -> dict:
    return {
        "id": pid,
        "slug": slug or f"slug-{pid}",
        "name": f"Post {pid}",
        "tagline": "tagline",
        "createdAt": created_at,
        "votesCount": upvotes,
        "commentsCount": 0,
        "website": website,
        "topics": {"edges": []},
        "makers": [
            {
                "id": "m1",
                "username": maker_ph,
                "twitterUsername": maker_x,
            }
        ],
    }


def test_find_candidates_for_niche_excludes_positives_and_high_upvotes() -> None:
    posts = [
        _fake_post("1", 5, maker_x="newbie_a"),
        _fake_post("2", 12, maker_x="newbie_b"),
        _fake_post("3", 500, maker_x="newbie_c"),  # filtered: too many upvotes
        _fake_post("4", 8, maker_x="marclou"),     # filtered: positive maker
    ]

    with patch.object(fnpc, "_iter_posts_by_topic_cached", return_value=posts), \
         patch.object(fnpc, "_classify_cached", return_value=("live", "20250101000000")):
        rows = find_candidates_for_niche(
            "dev-tooling-boilerplate",
            max_upvotes=100,
            keyword_filter=False,  # this test isolates upvote/positives logic
            token="fake",
            positives={"marclou"},
            wayback_cache={},
            ph_cache={},
        )

    ids = [r.ph_post_id for r in rows]
    assert ids == ["1", "2"]  # ascending by upvotes; 3 and 4 excluded
    # public_signals_available is True when X handle is present.
    assert all(r.public_signals_available for r in rows)
    assert rows[0].candidate_id.startswith("CAND_dev-tooling-boilerplate_2023Q3_")


def test_post_matches_keywords_substring_case_insensitive() -> None:
    post = {"name": "Notion Sites", "tagline": "Turn Notion into a site"}
    assert _post_matches_keywords(post, ["notion"]) is True
    assert _post_matches_keywords(post, ["NOTION"]) is True
    # Multi-word keyword matches as a substring.
    assert _post_matches_keywords(post, ["notion to"]) is False  # not present
    assert _post_matches_keywords(post, ["into a site"]) is True


def test_post_matches_keywords_rejects_unrelated() -> None:
    post = {"name": "Salesforce CRM Plus", "tagline": "Enterprise pipeline tool"}
    assert _post_matches_keywords(post, ["notion", "notion to"]) is False


def test_post_matches_keywords_empty_keywords_matches_all() -> None:
    post = {"name": "Anything", "tagline": "whatever"}
    assert _post_matches_keywords(post, []) is True


def test_post_matches_keywords_missing_fields_rejects() -> None:
    # Stale cache entries (pre-PR8) lack name/tagline. They should be
    # filtered out rather than crash; user re-runs with --refresh-ph.
    post = {"id": "x"}
    assert _post_matches_keywords(post, ["notion"]) is False


def test_find_candidates_for_niche_keyword_filter_narrows_results() -> None:
    posts = [
        _fake_post("1", 5, maker_x="a"),  # name="Post 1", tagline="tagline" — no match
        # Inject a name with the keyword present.
        {**_fake_post("2", 6, maker_x="b"), "name": "Notion Sites", "tagline": "Build with Notion"},
        {**_fake_post("3", 7, maker_x="c"), "name": "TodoApp", "tagline": "use notion-style blocks"},
        {**_fake_post("4", 8, maker_x="d"), "name": "CRM Pro", "tagline": "sales pipelines"},
    ]

    with patch.object(fnpc, "_iter_posts_by_topic_cached", return_value=posts), \
         patch.object(fnpc, "_classify_cached", return_value=("live", "20250101000000")):
        rows = find_candidates_for_niche(
            "notion-adjacent-tooling",
            max_upvotes=100,
            token="fake",
            positives=set(),
            wayback_cache={},
            ph_cache={},
        )

    ids = sorted(r.ph_post_id for r in rows)
    assert ids == ["2", "3"]  # only the two with "notion" in name/tagline


def test_find_candidates_for_niche_no_keyword_filter_keeps_all() -> None:
    posts = [
        _fake_post("1", 5, maker_x="a"),
        {**_fake_post("2", 6, maker_x="b"), "name": "Random", "tagline": "nothing"},
    ]

    with patch.object(fnpc, "_iter_posts_by_topic_cached", return_value=posts), \
         patch.object(fnpc, "_classify_cached", return_value=("live", "20250101000000")):
        rows = find_candidates_for_niche(
            "notion-adjacent-tooling",
            max_upvotes=100,
            keyword_filter=False,
            token="fake",
            positives=set(),
            wayback_cache={},
            ph_cache={},
        )

    assert {r.ph_post_id for r in rows} == {"1", "2"}


def test_find_candidates_for_niche_out_of_scope_returns_empty(caplog) -> None:
    with caplog.at_level("INFO"):
        rows = find_candidates_for_niche(
            "research-substack-tech-vc-analyst",
            token="fake",
            positives=set(),
            wayback_cache={},
            ph_cache={},
        )
    assert rows == []
    assert any("out-of-scope" in rec.message for rec in caplog.records)


def test_max_pages_for_cap_known_values() -> None:
    # (2*N + 49) // 50 floor; bounded to [1, 10].
    assert fnpc._max_pages_for_cap(1) == 1
    assert fnpc._max_pages_for_cap(25) == 1
    assert fnpc._max_pages_for_cap(26) == 2
    assert fnpc._max_pages_for_cap(50) == 2
    assert fnpc._max_pages_for_cap(100) == 4
    assert fnpc._max_pages_for_cap(1000) == 10  # capped


def test_iter_posts_by_topic_respects_max_pages() -> None:
    """Confirms we stop paginating once we've fetched max_pages worth."""
    call_count = {"n": 0}

    def fake_gql(query, variables, token):  # noqa: ARG001
        call_count["n"] += 1
        # Always say there's a next page so we can verify the cap.
        return {
            "posts": {
                "pageInfo": {"hasNextPage": True, "endCursor": f"c{call_count['n']}"},
                "edges": [{"node": {"id": f"p{call_count['n']}", "createdAt": "2023-01-01T00:00:00Z"}}],
            }
        }

    with patch.object(fnpc, "_gql", side_effect=fake_gql):
        posts, complete = fnpc._iter_posts_by_topic(
            "developer-tools", date(2023, 1, 1), date(2023, 6, 1), "tok", max_pages=3
        )

    assert call_count["n"] == 3
    assert len(posts) == 3
    # Reaching max_pages cleanly is a complete fetch (cacheable).
    assert complete is True


def test_find_candidates_for_niche_caps_at_max_candidates() -> None:
    posts = [_fake_post(str(i), upvotes=i, maker_x=f"u{i}") for i in range(50)]
    with patch.object(fnpc, "_iter_posts_by_topic_cached", return_value=posts), \
         patch.object(fnpc, "_classify_cached", return_value=("live", None)):
        rows = find_candidates_for_niche(
            "dev-tooling-boilerplate",
            max_upvotes=1000,
            max_candidates=5,
            keyword_filter=False,  # isolate cap logic from keyword filter
            token="fake",
            positives=set(),
            wayback_cache={},
            ph_cache={},
        )
    assert len(rows) == 5
    # Cap takes the lowest-upvote slice (already sorted ascending).
    assert [r.upvotes for r in rows] == [0, 1, 2, 3, 4]


def test_find_candidates_dedup_across_topics() -> None:
    # Same post id returned by two topic queries → de-duped.
    shared = _fake_post("shared", 10, maker_x="x_user")
    by_topic = {
        "marketing": [shared],
        "social-media-tools": [shared, _fake_post("other", 20, maker_x="other_user")],
    }

    def fake_iter_cached(topic_slug, start, end, token, max_pages, ph_cache, refresh):  # noqa: ARG001
        return by_topic[topic_slug]

    with patch.object(fnpc, "_iter_posts_by_topic_cached", side_effect=fake_iter_cached), \
         patch.object(fnpc, "_classify_cached", return_value=("live", None)):
        rows = find_candidates_for_niche(
            "twitter-growth-tools",
            keyword_filter=False,  # isolate dedup logic from keyword filter
            token="fake",
            positives=set(),
            wayback_cache={},
            ph_cache={},
        )

    ids = sorted(r.ph_post_id for r in rows)
    assert ids == ["other", "shared"]


# ---------------------------------------------------------------------------
# 7. CSV schema integrity
# ---------------------------------------------------------------------------


def test_csv_fields_match_dataclass_keys() -> None:
    row = CandidateRow(
        candidate_id="CAND_x_2020Q1_01",
        ph_post_id="1",
        ph_url="https://www.producthunt.com/posts/x",
        maker_handle_x="foo",
        maker_handle_ph="foo",
        launch_date="2020-01-15",
        niche_slug="dev-tooling-boilerplate",
        matched_emergence_quarter="2023-Q3",
        upvotes=5,
        website_url="https://example.com",
        wayback_status="live",
        last_wayback_capture="20250101000000",
        public_signals_available=True,
        candidate_outcome_class_guess="low_traction",
        notes_for_picker="PH Jan 2020, 5 upvotes, Wayback Jan 2025 = live, X maker @foo",
    )
    # dataclass keys must equal CSV_FIELDS exactly.
    assert list(asdict(row).keys()) == CSV_FIELDS


def test_write_csv_round_trips(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(fnpc, "OUT_DIR", tmp_path)
    row = CandidateRow(
        candidate_id="CAND_x_2020Q1_01",
        ph_post_id="1",
        ph_url="https://www.producthunt.com/posts/x",
        maker_handle_x="foo",
        maker_handle_ph="foo",
        launch_date="2020-01-15",
        niche_slug="dev-tooling-boilerplate",
        matched_emergence_quarter="2023-Q3",
        upvotes=5,
        website_url="https://example.com",
        wayback_status="live",
        last_wayback_capture="20250101000000",
        public_signals_available=True,
        candidate_outcome_class_guess="low_traction",
        notes_for_picker="PH Jan 2020, 5 upvotes, Wayback Jan 2025 = live, X maker @foo",
    )
    path = write_csv("dev-tooling-boilerplate", [row])
    assert path.exists()
    with path.open() as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 1
    assert rows[0]["candidate_id"] == "CAND_x_2020Q1_01"
    assert rows[0]["upvotes"] == "5"
    assert rows[0]["public_signals_available"] == "True"


def test_write_csv_empty_writes_header_only(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(fnpc, "OUT_DIR", tmp_path)
    path = write_csv("dev-tooling-boilerplate", [])
    with path.open() as f:
        content = f.read()
    # Header line present, no data rows.
    assert content.strip().split("\n") == [",".join(CSV_FIELDS)]


# ---------------------------------------------------------------------------
# 8. Notes-for-picker formatting
# ---------------------------------------------------------------------------


def test_notes_for_picker_formats_live_wayback() -> None:
    post = _fake_post("1", 42, maker_x="someone", created_at="2023-08-15T12:00:00Z")
    note = fnpc._make_notes_for_picker(post, "live", "20250215123456", "someone")
    assert "Aug 2023" in note
    assert "42 upvotes" in note
    assert "Feb 2025" in note
    assert "live" in note
    assert "@someone" in note


def test_notes_for_picker_no_x_maker() -> None:
    post = _fake_post("1", 5, maker_x="")
    note = fnpc._make_notes_for_picker(post, "gone", None, "")
    assert "no X maker" in note
    assert "Wayback = gone" in note


# ---------------------------------------------------------------------------
# 9. Idempotency cache
# ---------------------------------------------------------------------------


def test_classify_cached_hits_cache(monkeypatch) -> None:
    cache = {"2020-01-01|https://example.com": ["live", "20250101000000"]}
    called = []

    def explode(*a, **kw):
        called.append(1)
        return "gone", None

    monkeypatch.setattr(fnpc, "classify_wayback", explode)
    status, last = fnpc._classify_cached(
        "https://example.com", date(2020, 1, 1), cache, refresh=False
    )
    assert status == "live"
    assert last == "20250101000000"
    assert called == []  # cache hit, no live lookup


def test_classify_cached_refresh_bypasses_cache(monkeypatch) -> None:
    cache = {"2020-01-01|https://example.com": ["live", "20250101000000"]}

    def refresh_value(*a, **kw):
        return "gone", None

    monkeypatch.setattr(fnpc, "classify_wayback", refresh_value)
    status, last = fnpc._classify_cached(
        "https://example.com", date(2020, 1, 1), cache, refresh=True
    )
    assert status == "gone"
    assert last is None
    # Cache was overwritten.
    assert cache["2020-01-01|https://example.com"] == ["gone", None]


# ---------------------------------------------------------------------------
# 10. Smoke: rejected niche slug
# ---------------------------------------------------------------------------


def test_find_candidates_unknown_niche_raises() -> None:
    with pytest.raises(KeyError):
        find_candidates_for_niche(
            "does-not-exist", token="fake", positives=set(), wayback_cache={}, ph_cache={}
        )


# ---------------------------------------------------------------------------
# 12. PH response cache (Piece 3)
# ---------------------------------------------------------------------------


def test_iter_posts_by_topic_cached_hits_cache() -> None:
    cached_posts = [{"id": "cached_1", "createdAt": "2023-01-01T00:00:00Z"}]
    ph_cache = {
        fnpc._ph_cache_key("developer-tools", date(2023, 5, 1), date(2023, 12, 1)): cached_posts
    }
    called = []

    def explode(*a, **kw):  # noqa: ARG001
        called.append(1)
        return [], True

    with patch.object(fnpc, "_iter_posts_by_topic", side_effect=explode):
        result = fnpc._iter_posts_by_topic_cached(
            "developer-tools",
            date(2023, 5, 1),
            date(2023, 12, 1),
            "tok",
            max_pages=2,
            ph_cache=ph_cache,
            refresh=False,
        )

    assert result == cached_posts
    assert called == []  # cache hit, no live query


def test_iter_posts_by_topic_cached_refresh_bypasses() -> None:
    cached_posts = [{"id": "stale"}]
    fresh_posts = [{"id": "fresh"}]
    key = fnpc._ph_cache_key("developer-tools", date(2023, 5, 1), date(2023, 12, 1))
    ph_cache = {key: cached_posts}

    with patch.object(fnpc, "_iter_posts_by_topic", return_value=(fresh_posts, True)):
        result = fnpc._iter_posts_by_topic_cached(
            "developer-tools",
            date(2023, 5, 1),
            date(2023, 12, 1),
            "tok",
            max_pages=2,
            ph_cache=ph_cache,
            refresh=True,
        )

    assert result == fresh_posts
    # Cache is overwritten with the fresh data.
    assert ph_cache[key] == fresh_posts


def test_iter_posts_by_topic_cached_skips_cache_on_partial_fetch() -> None:
    partial_posts = [{"id": "partial"}]
    ph_cache: dict[str, list[dict]] = {}
    key = fnpc._ph_cache_key("developer-tools", date(2023, 5, 1), date(2023, 12, 1))

    with patch.object(fnpc, "_iter_posts_by_topic", return_value=(partial_posts, False)):
        result = fnpc._iter_posts_by_topic_cached(
            "developer-tools",
            date(2023, 5, 1),
            date(2023, 12, 1),
            "tok",
            max_pages=2,
            ph_cache=ph_cache,
            refresh=False,
        )

    # Caller still gets the partial result for this run.
    assert result == partial_posts
    # But the cache is NOT polluted with it.
    assert key not in ph_cache


def test_iter_posts_by_topic_retries_once_on_429(monkeypatch) -> None:
    """A 429 mid-fetch sleeps once and then succeeds on retry."""
    from ingestion.producthunt_collect import ProductHuntRateLimitedError

    call_count = {"n": 0}
    slept_for: list[float] = []

    def fake_gql(query, variables, token):  # noqa: ARG001
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise ProductHuntRateLimitedError(reset_seconds=3)
        return {
            "posts": {
                "pageInfo": {"hasNextPage": False, "endCursor": None},
                "edges": [{"node": {"id": "p1", "createdAt": "2023-01-01T00:00:00Z"}}],
            }
        }

    monkeypatch.setattr(fnpc, "_gql", fake_gql)
    # Patch the sleep inside the retry path (it's `import time as _t; _t.sleep`).
    import time as _real_time
    monkeypatch.setattr(_real_time, "sleep", lambda s: slept_for.append(s))

    posts, complete = fnpc._iter_posts_by_topic(
        "developer-tools", date(2023, 1, 1), date(2023, 6, 1), "tok", max_pages=3
    )
    assert call_count["n"] == 2  # one 429, one success
    assert slept_for == [3]
    assert [p["id"] for p in posts] == ["p1"]
    assert complete is True  # natural completion via hasNextPage=False


# ---------------------------------------------------------------------------
# 11. PH redirect resolution
# ---------------------------------------------------------------------------


def test_resolve_ph_redirect_passes_through_non_ph_url() -> None:
    # Non-PH URLs are returned unchanged (no HTTP call needed).
    assert fnpc._resolve_ph_redirect("https://example.com") == "https://example.com"


def test_resolve_ph_redirect_returns_none_for_empty() -> None:
    assert fnpc._resolve_ph_redirect("") is None
    assert fnpc._resolve_ph_redirect(None) is None


def test_resolve_ph_redirect_follows_ph_r_link(monkeypatch) -> None:
    class FakeResp:
        url = "https://realsite.com/landing"

    def fake_head(url, allow_redirects, timeout):  # noqa: ARG001
        return FakeResp()

    monkeypatch.setattr(fnpc.requests, "head", fake_head)
    result = fnpc._resolve_ph_redirect(
        "https://www.producthunt.com/r/ABC?utm_source=foo"
    )
    assert result == "https://realsite.com/landing"


def test_resolve_ph_redirect_returns_none_on_loop(monkeypatch) -> None:
    class FakeResp:
        url = "https://www.producthunt.com/r/ABC"  # didn't escape PH

    monkeypatch.setattr(
        fnpc.requests, "head", lambda *a, **kw: FakeResp()
    )
    assert (
        fnpc._resolve_ph_redirect("https://www.producthunt.com/r/ABC") is None
    )
