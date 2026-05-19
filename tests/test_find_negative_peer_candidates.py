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

    with patch.object(fnpc, "_iter_posts_by_topic", return_value=posts), \
         patch.object(fnpc, "_classify_cached", return_value=("live", "20250101000000")):
        rows = find_candidates_for_niche(
            "dev-tooling-boilerplate",
            max_upvotes=100,
            token="fake",
            positives={"marclou"},
            wayback_cache={},
        )

    ids = [r.ph_post_id for r in rows]
    assert ids == ["1", "2"]  # ascending by upvotes; 3 and 4 excluded
    # public_signals_available is True when X handle is present.
    assert all(r.public_signals_available for r in rows)
    assert rows[0].candidate_id.startswith("CAND_dev-tooling-boilerplate_2023Q3_")


def test_find_candidates_for_niche_out_of_scope_returns_empty(caplog) -> None:
    with caplog.at_level("INFO"):
        rows = find_candidates_for_niche(
            "research-substack-tech-vc-analyst",
            token="fake",
            positives=set(),
            wayback_cache={},
        )
    assert rows == []
    assert any("out-of-scope" in rec.message for rec in caplog.records)


def test_find_candidates_for_niche_caps_at_max_candidates() -> None:
    posts = [_fake_post(str(i), upvotes=i, maker_x=f"u{i}") for i in range(50)]
    with patch.object(fnpc, "_iter_posts_by_topic", return_value=posts), \
         patch.object(fnpc, "_classify_cached", return_value=("live", None)):
        rows = find_candidates_for_niche(
            "dev-tooling-boilerplate",
            max_upvotes=1000,
            max_candidates=5,
            token="fake",
            positives=set(),
            wayback_cache={},
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

    def fake_iter(topic_slug, start, end, token):
        return by_topic[topic_slug]

    with patch.object(fnpc, "_iter_posts_by_topic", side_effect=fake_iter), \
         patch.object(fnpc, "_classify_cached", return_value=("live", None)):
        rows = find_candidates_for_niche(
            "twitter-growth-tools",
            token="fake",
            positives=set(),
            wayback_cache={},
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
        find_candidates_for_niche("does-not-exist", token="fake", positives=set(), wayback_cache={})


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
