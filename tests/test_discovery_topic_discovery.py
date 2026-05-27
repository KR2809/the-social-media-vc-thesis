"""Tests for `discovery.topic_discovery` (LLM clustering + candidate harvest).

All network + LLM paths go through indirection seams that we monkeypatch.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq
import pytest

from discovery import topic_discovery as td

# ---------------------------------------------------------------------------
# Cluster JSON parsing
# ---------------------------------------------------------------------------


def test_parse_cluster_json_plain():
    text = '[{"cluster_id":"a","representative_label":"A","member_topics":["x"],"rationale":"r"}]'
    parsed = td._parse_cluster_json(text)
    assert len(parsed) == 1
    assert parsed[0]["cluster_id"] == "a"


def test_parse_cluster_json_strips_code_fence():
    text = '```json\n[{"cluster_id":"a","representative_label":"A","member_topics":[],"rationale":"r"}]\n```'
    parsed = td._parse_cluster_json(text)
    assert parsed[0]["cluster_id"] == "a"


def test_parse_cluster_json_rejects_non_list():
    with pytest.raises(ValueError, match="not a list"):
        td._parse_cluster_json('{"oops": true}')


# ---------------------------------------------------------------------------
# cluster_topics — uses CLUSTER_CALL_FN seam, no real Anthropic
# ---------------------------------------------------------------------------


_FAKE_CLUSTERS = [
    {
        "cluster_id": "ai-agents",
        "representative_label": "AI agents",
        "member_topics": ["ai sdr", "ai workflows", "agent tools"],
        "rationale": "AI-agent themes.",
        "momentum_signal_strength": 0.8,
        "suggested_subreddits": ["entrepreneur", "saas"],
    },
    {
        "cluster_id": "creator-tools",
        "representative_label": "creator tools",
        "member_topics": ["newsletter", "membership", "video editing"],
        "rationale": "creator-economy tooling.",
        "momentum_signal_strength": 0.6,
        "suggested_subreddits": ["sideproject"],
    },
    {
        "cluster_id": "b2b-saas",
        "representative_label": "B2B SaaS plumbing",
        "member_topics": ["pricing", "onboarding", "churn"],
        "rationale": "saas mechanics.",
        "momentum_signal_strength": 0.5,
        "suggested_subreddits": ["saas"],
    },
    {
        "cluster_id": "ai-infra",
        "representative_label": "AI infra",
        "member_topics": ["vector dbs", "embedding"],
        "rationale": "infra layer.",
        "momentum_signal_strength": 0.7,
        "suggested_subreddits": ["machinelearning"],
    },
    {
        "cluster_id": "devtools",
        "representative_label": "developer tools",
        "member_topics": ["cli ux", "build perf"],
        "rationale": "devtools.",
        "momentum_signal_strength": 0.55,
        "suggested_subreddits": ["programming"],
    },
]


def _fake_cluster_call(system_prompt, user_payload, model):
    # Returns 5 clusters → satisfies min_clusters=5.
    return (json.dumps(_FAKE_CLUSTERS), 500, 200)


def test_cluster_count_reasonable(monkeypatch, tmp_path):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake")
    monkeypatch.setattr(td, "CLUSTER_CALL_FN", _fake_cluster_call)
    # Redirect cost log to tmp.
    monkeypatch.setattr(td.ranking_cfg, "LLM_LOG_PATH", tmp_path / "log.jsonl")

    seeds = [f"topic_{i}" for i in range(50)]
    clusters = td.cluster_topics(seeds)
    assert td.DEFAULT_MIN_CLUSTERS <= len(clusters) <= td.DEFAULT_MAX_CLUSTERS
    assert all(isinstance(c, td.ClusterRow) for c in clusters)
    assert clusters[0].cluster_id == "ai-agents"

    # Cost ledger was appended.
    log_lines = (tmp_path / "log.jsonl").read_text().splitlines()
    assert len(log_lines) == 1
    entry = json.loads(log_lines[0])
    assert entry["purpose"] == "cluster_topics"
    assert entry["n_seeds"] == 50
    assert entry["n_clusters"] == 5


def test_cluster_topics_retries_once_on_bad_json(monkeypatch, tmp_path):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake")
    monkeypatch.setattr(td.ranking_cfg, "LLM_LOG_PATH", tmp_path / "log.jsonl")
    attempts = {"n": 0}

    def flaky(system_prompt, user_payload, model):
        attempts["n"] += 1
        if attempts["n"] == 1:
            return ("not valid json at all", 100, 30)
        return (json.dumps(_FAKE_CLUSTERS), 500, 200)

    monkeypatch.setattr(td, "CLUSTER_CALL_FN", flaky)
    clusters = td.cluster_topics(["a", "b"])
    assert attempts["n"] == 2
    assert len(clusters) == 5


def test_cluster_topics_fallback_when_no_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(td, "CLUSTER_CALL_FN", None)
    seeds = ["a", "b", "c"]
    clusters = td.cluster_topics(seeds)
    assert len(clusters) == 1
    assert clusters[0].cluster_id == "fallback-all"
    assert clusters[0].member_topics == seeds


def test_cluster_topics_empty_seeds():
    assert td.cluster_topics([]) == []


# ---------------------------------------------------------------------------
# Candidate harvest with mocked Reddit + HN
# ---------------------------------------------------------------------------


def _fake_reddit(sub, query, since_epoch):
    # Each call yields 2 authors, with some overlap to test dedup.
    return [
        {"author": f"{sub}-author-1", "platform": "reddit", "subreddit": sub,
         "permalink": "/r/x/1", "created_utc": since_epoch + 100, "title": query},
        {"author": f"{sub}-author-2", "platform": "reddit", "subreddit": sub,
         "permalink": "/r/x/2", "created_utc": since_epoch + 200, "title": query},
        # A repeated author to test aggregation:
        {"author": f"{sub}-author-1", "platform": "reddit", "subreddit": sub,
         "permalink": "/r/x/3", "created_utc": since_epoch + 300, "title": query},
    ]


def _fake_hn(query, since_epoch):
    return [
        {"author": "shared-handle", "platform": "hackernews", "story_id": "1",
         "created_at": "2026-01-01T00:00:00Z", "title": query},
        {"author": "hn-only-author", "platform": "hackernews", "story_id": "2",
         "created_at": "2026-01-02T00:00:00Z", "title": query},
    ]


def _fake_reddit_with_cross_platform(sub, query, since_epoch):
    """One author also appears on HN — should get the cross-platform bonus."""
    return [
        {"author": "shared-handle", "platform": "reddit", "subreddit": sub,
         "permalink": "/r/x/1", "created_utc": since_epoch + 100, "title": query},
    ]


def test_pytrends_smoke_uses_cohort_topic_ranking(monkeypatch):
    """Confirms _seeds_from_cohort delegates to analysis.topic_discovery."""
    from analysis import topic_discovery as atd

    fake_df = pd.DataFrame({"topic": [f"t{i}" for i in range(10)]})
    monkeypatch.setattr(atd, "cohort_topic_ranking", lambda **kwargs: fake_df)
    seeds = td._seeds_from_cohort(max_seeds=5)
    assert seeds == ["t0", "t1", "t2", "t3", "t4"]


def test_reddit_harvest_dedup(monkeypatch, tmp_path):
    monkeypatch.setattr(td, "REDDIT_FETCH_FN", _fake_reddit)
    monkeypatch.setattr(td, "HN_FETCH_FN", _fake_hn)

    cluster = td.ClusterRow(
        cluster_id="ai-agents",
        representative_label="AI agents",
        member_topics=["x"],
        rationale="r",
        momentum_signal_strength=0.7,
        suggested_subreddits=["entrepreneur"],
    )
    raw = td.harvest_candidates([cluster], since_days=90, max_workers=1)
    # 3 reddit rows + 2 hn rows = 5
    assert len(raw) == 5

    ranked = td._rank_candidates(raw, [cluster])
    # Distinct authors: entrepreneur-author-1 (2 reddit), entrepreneur-author-2 (1 reddit),
    #                   shared-handle (1 hn), hn-only-author (1 hn) = 4
    assert len(ranked) == 4
    # author-1 should have n_appearances=2, n_platforms=1.
    a1 = ranked[ranked["handle"] == "entrepreneur-author-1"].iloc[0]
    assert a1["n_appearances"] == 2
    assert a1["n_platforms"] == 1
    assert a1["discovery_strength"] == 2.0  # 2 * (1 + 0.5*0)


def test_cross_platform_bonus(monkeypatch):
    monkeypatch.setattr(td, "REDDIT_FETCH_FN", _fake_reddit_with_cross_platform)
    monkeypatch.setattr(td, "HN_FETCH_FN", _fake_hn)

    cluster = td.ClusterRow(
        cluster_id="c1",
        representative_label="q",
        member_topics=[],
        rationale="",
        momentum_signal_strength=0.5,
        suggested_subreddits=["entrepreneur"],
    )
    raw = td.harvest_candidates([cluster], since_days=90, max_workers=1)
    ranked = td._rank_candidates(raw, [cluster])
    shared = ranked[ranked["handle"] == "shared-handle"].iloc[0]
    # n_appearances=2 (1 reddit + 1 hn), n_platforms=2 → strength = 2 * 1.5 = 3.0
    assert shared["n_platforms"] == 2
    assert shared["discovery_strength"] == 3.0
    assert sorted(shared["source_platforms"]) == ["hackernews", "reddit"]


# ---------------------------------------------------------------------------
# Parquet schema
# ---------------------------------------------------------------------------


def test_candidate_schema(tmp_path, monkeypatch):
    monkeypatch.setattr(td, "REDDIT_FETCH_FN", _fake_reddit)
    monkeypatch.setattr(td, "HN_FETCH_FN", _fake_hn)

    cluster = td.ClusterRow(
        cluster_id="c1",
        representative_label="q",
        member_topics=[],
        rationale="",
        momentum_signal_strength=0.5,
        suggested_subreddits=["entrepreneur"],
    )
    raw = td.harvest_candidates([cluster], since_days=90, max_workers=1)
    ranked = td._rank_candidates(raw, [cluster])

    out = tmp_path / "candidates.parquet"
    td.write_candidates(ranked, out_path=out)
    table = pq.read_table(out)
    expected = {
        "cluster_id", "cluster_label", "handle", "source_platforms",
        "n_appearances", "n_platforms", "discovery_strength",
        "suggested_for_ranking", "degraded_mode",
    }
    assert set(table.column_names) == expected
    import pyarrow as pa
    assert table.schema.field("n_appearances").type == pa.int32()
    assert table.schema.field("suggested_for_ranking").type == pa.bool_()
    assert table.schema.field("degraded_mode").type == pa.bool_()
    # Non-degraded clusters → degraded_mode False on every row.
    assert not table.column("degraded_mode").to_pylist()[0]

    # Empty write also works.
    td.write_candidates(pd.DataFrame(), out_path=tmp_path / "empty.parquet")
    empty = pq.read_table(tmp_path / "empty.parquet")
    assert set(empty.column_names) == expected


def test_degraded_mode_propagates_from_fallback_cluster(monkeypatch):
    """Fallback cluster (no API key) → degraded_mode=True on all candidates."""
    monkeypatch.setattr(td, "REDDIT_FETCH_FN", _fake_reddit)
    monkeypatch.setattr(td, "HN_FETCH_FN", _fake_hn)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(td, "CLUSTER_CALL_FN", None)

    clusters = td.cluster_topics(["seed1", "seed2"])
    assert len(clusters) == 1
    assert clusters[0].degraded is True

    raw = td.harvest_candidates(clusters, since_days=90, max_workers=1)
    ranked = td._rank_candidates(raw, clusters)
    assert len(ranked) > 0
    assert ranked["degraded_mode"].all()


# ---------------------------------------------------------------------------
# End-to-end (mocked) discover()
# ---------------------------------------------------------------------------


def test_discover_end_to_end(monkeypatch, tmp_path):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake")
    monkeypatch.setattr(td, "CLUSTER_CALL_FN", _fake_cluster_call)
    monkeypatch.setattr(td, "REDDIT_FETCH_FN", _fake_reddit)
    monkeypatch.setattr(td, "HN_FETCH_FN", _fake_hn)
    monkeypatch.setattr(td.ranking_cfg, "LLM_LOG_PATH", tmp_path / "log.jsonl")
    monkeypatch.setattr(td, "DISCOVERED_TOPICS_PATH", tmp_path / "topics.csv")

    seeds = [f"topic_{i}" for i in range(20)]
    clusters, candidates = td.discover(seeds=seeds, from_cohort=False)
    assert len(clusters) == 5
    # Each of the 5 clusters runs reddit + hn → at least 5 distinct authors total.
    assert len(candidates) >= 5
    # Topics CSV got written.
    assert (tmp_path / "topics.csv").exists()
    csv = pd.read_csv(tmp_path / "topics.csv")
    assert len(csv) == 5
    assert "rationale" in csv.columns


def test_no_paid_apis_used_in_test_path(monkeypatch):
    """Sanity: with all seams mocked, no real outbound HTTP happens.

    We patch `requests.get` to raise — if anything in the pipeline forgets
    to use the indirection seam and falls through to real HTTP, this catches it.
    """
    import requests

    def explode(*args, **kwargs):  # pragma: no cover — only fires on regression
        raise AssertionError(
            f"unexpected real HTTP call: {args=} {kwargs=}; "
            "all network paths must go through REDDIT_FETCH_FN / HN_FETCH_FN"
        )

    monkeypatch.setattr(requests, "get", explode)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake")
    monkeypatch.setattr(td, "CLUSTER_CALL_FN", _fake_cluster_call)
    monkeypatch.setattr(td, "REDDIT_FETCH_FN", _fake_reddit)
    monkeypatch.setattr(td, "HN_FETCH_FN", _fake_hn)
    monkeypatch.setattr(td.ranking_cfg, "LLM_LOG_PATH", Path("/tmp/test_log.jsonl"))

    clusters, candidates = td.discover(
        seeds=["a", "b"], from_cohort=False, write_clusters_csv=False,
    )
    assert len(clusters) == 5
    assert len(candidates) > 0
