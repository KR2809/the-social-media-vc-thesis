"""Forward-looking topic + candidate discovery (Tier-1 → Tier-2 bridge).

This module wraps `analysis.topic_discovery` and produces a ranked slate of
candidate handles per topic cluster, harvested from public Reddit + HN
searches. It does NOT auto-trigger `ranking.rank_handles` — the frontend's
"discover → review → rank" UX decides which candidates to push through.

Pipeline:

    seed topics
        ├── --from-cohort → analysis.topic_discovery.cohort_topic_ranking
        └── --seed-topics → CLI verbatim
              │
              ▼
    LLM clustering (Haiku) → 5–15 clusters with suggested_subreddits
              │
              ▼
    Cross-platform candidate harvest (per cluster, ThreadPoolExecutor):
        ├── Reddit JSON listing API (no auth, public posts)
        └── Hacker News Algolia search (no auth, free)
              │
              ▼
    Aggregate + rank (cross-platform bonus + frequency)
              │
              ▼
    data/processed/discovered_candidates.parquet

All network calls go through indirection seams that tests monkeypatch.

Public API:
    discover(seeds, date=None, max_topics=50) -> pd.DataFrame
    cluster_topics(seeds, model=RATIONALE_MODEL) -> list[ClusterRow]
    harvest_candidates(clusters, *, since_days=90) -> pd.DataFrame

Used by api.main `/api/discover/topics` and `/api/discover/candidates/{cluster_id}`.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from ranking import config as ranking_cfg

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


DISCOVERED_CANDIDATES_PATH: Path = Path("data/processed/discovered_candidates.parquet")
DISCOVERED_TOPICS_PATH: Path = Path("data/processed/discovered_topics.csv")
CLUSTER_PROMPT_PATH: Path = Path("discovery/prompts/v1/cluster_topics.md")
CLUSTER_PROMPT_VERSION: str = "v1"
CLUSTER_MAX_TOKENS: int = 2048
DEFAULT_MAX_SEEDS: int = 50
DEFAULT_HARVEST_SINCE_DAYS: int = 90
DEFAULT_MIN_CLUSTERS: int = 5
DEFAULT_MAX_CLUSTERS: int = 15
DEFAULT_REDDIT_FALLBACK_SUBS = ("entrepreneur", "saas")
DEFAULT_RANK_THRESHOLD: float = 3.0
DEFAULT_PER_CLUSTER_TOP_PCT: float = 0.20


# ---------------------------------------------------------------------------
# Indirection seams — tests monkeypatch these
# ---------------------------------------------------------------------------


# (system_prompt, user_payload, model) -> (text, in_tokens, out_tokens)
CLUSTER_CALL_FN = None
# (subreddit, query, since_epoch_seconds) -> list[{"author": str, "platform": "reddit"}]
REDDIT_FETCH_FN = None
# (query, since_epoch_seconds) -> list[{"author": str, "platform": "hackernews"}]
HN_FETCH_FN = None


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class ClusterRow:
    cluster_id: str
    representative_label: str
    member_topics: list[str]
    rationale: str
    momentum_signal_strength: float
    suggested_subreddits: list[str]


# ---------------------------------------------------------------------------
# Seed collection
# ---------------------------------------------------------------------------


def _seeds_from_cohort(
    date: datetime | None = None,
    max_seeds: int = DEFAULT_MAX_SEEDS,
) -> list[str]:
    """Pass A seeds from scored_signals via analysis.topic_discovery.

    Re-uses `cohort_topic_ranking` which already weights topics by
    strength × recency. Replay-safe: pass `date` to enforce
    observed_at <= date filtering at the source.
    """
    from analysis import topic_discovery as atd  # noqa: PLC0415

    ranked = atd.cohort_topic_ranking(now=date)
    if len(ranked) == 0:
        return []
    return ranked["topic"].head(max_seeds).tolist()


def _seeds_from_cli(raw: str) -> list[str]:
    return [s.lower().strip() for s in raw.split(",") if s.strip()]


# ---------------------------------------------------------------------------
# LLM clustering
# ---------------------------------------------------------------------------


def _call_haiku_for_clustering(
    system_prompt: str, user_payload: str, model: str,
) -> tuple[str, int, int]:
    """Wraps scoring.score_signals._call_anthropic so we share SDK + pricing."""
    from scoring.score_signals import _call_anthropic  # noqa: PLC0415

    return _call_anthropic(
        system_prompt=system_prompt,
        user_payload=user_payload,
        model=model,
        max_tokens=CLUSTER_MAX_TOKENS,
    )


def _parse_cluster_json(text: str) -> list[dict[str, Any]]:
    """Strip optional code-fence and parse the JSON array."""
    s = text.strip()
    if s.startswith("```"):
        # Drop leading ```json or ``` and trailing ```
        s = s.split("\n", 1)[1] if "\n" in s else ""
        if s.endswith("```"):
            s = s[: -3]
        s = s.strip()
    parsed = json.loads(s)
    if not isinstance(parsed, list):
        raise ValueError(f"clustering response was not a list: {type(parsed)}")
    return parsed


def _validate_cluster(c: dict[str, Any]) -> ClusterRow:
    required = ("cluster_id", "representative_label", "member_topics", "rationale")
    for k in required:
        if k not in c:
            raise ValueError(f"cluster missing field {k!r}: {c}")
    return ClusterRow(
        cluster_id=str(c["cluster_id"]),
        representative_label=str(c["representative_label"]),
        member_topics=list(c["member_topics"]),
        rationale=str(c["rationale"]),
        momentum_signal_strength=float(c.get("momentum_signal_strength", 0.5)),
        suggested_subreddits=[
            str(s).lstrip("r/").lower()
            for s in c.get("suggested_subreddits") or []
        ],
    )


def cluster_topics(
    seeds: list[str],
    model: str = ranking_cfg.RATIONALE_MODEL,
    min_clusters: int = DEFAULT_MIN_CLUSTERS,
    max_clusters: int = DEFAULT_MAX_CLUSTERS,
) -> list[ClusterRow]:
    """LLM-cluster seed topics into 5-15 coherent groups.

    Best-effort with one retry on validation error; raises on the second
    failure so the caller can surface a clear blocker (no silent fallback
    to a hand-coded clustering). All token + cost data is appended to the
    LLM run log per CLAUDE.md §3.

    If `ANTHROPIC_API_KEY` is not set, returns a single-cluster fallback
    that lumps everything together — non-zero output so the rest of the
    pipeline can be exercised in CI / offline tests, but obviously degraded.
    """
    if not seeds:
        return []

    if not os.environ.get("ANTHROPIC_API_KEY") and CLUSTER_CALL_FN is None:
        logger.warning(
            "ANTHROPIC_API_KEY unset and no CLUSTER_CALL_FN override; emitting "
            "single-cluster fallback (degraded)."
        )
        return [
            ClusterRow(
                cluster_id="fallback-all",
                representative_label="all seeds",
                member_topics=seeds,
                rationale="LLM clustering unavailable; all seeds lumped together.",
                momentum_signal_strength=0.5,
                suggested_subreddits=list(DEFAULT_REDDIT_FALLBACK_SUBS),
            )
        ]

    if not CLUSTER_PROMPT_PATH.exists():
        raise FileNotFoundError(f"clustering prompt missing at {CLUSTER_PROMPT_PATH}")
    system_prompt = CLUSTER_PROMPT_PATH.read_text()
    payload = (
        f"# Topics to cluster (n={len(seeds)})\n\n"
        + "\n".join(f"- {s}" for s in seeds)
        + f"\n\nProduce between {min_clusters} and {max_clusters} clusters."
    )

    fn = CLUSTER_CALL_FN or _call_haiku_for_clustering

    for attempt in (1, 2):
        try:
            text, in_tok, out_tok = fn(system_prompt, payload, model)
            parsed = _parse_cluster_json(text)
            clusters = [_validate_cluster(c) for c in parsed]
            break
        except Exception as exc:
            if attempt == 2:
                raise
            logger.warning(
                "clustering attempt %d failed (%s); retrying once", attempt, exc
            )

    # Log cost.
    try:
        from scoring.score_signals import (  # noqa: PLC0415
            append_run_log,
            estimate_cost,
        )

        cost = estimate_cost(model, in_tok, out_tok)
        append_run_log(
            {
                "purpose": "cluster_topics",
                "n_seeds": len(seeds),
                "n_clusters": len(clusters),
                "model": model,
                "prompt_version": CLUSTER_PROMPT_VERSION,
                "input_tokens": in_tok,
                "output_tokens": out_tok,
                "cost_usd": cost,
                "timestamp": datetime.now(UTC).isoformat(),
            },
            log_path=ranking_cfg.LLM_LOG_PATH,
        )
    except Exception:  # pragma: no cover — log failure shouldn't abort
        logger.exception("could not append cluster cost to run log")

    if not (min_clusters <= len(clusters) <= max_clusters):
        logger.warning(
            "got %d clusters, expected %d-%d — proceeding anyway",
            len(clusters), min_clusters, max_clusters,
        )
    return clusters


# ---------------------------------------------------------------------------
# Candidate harvest — Reddit + HN
# ---------------------------------------------------------------------------


def _reddit_fetch(subreddit: str, query: str, since_epoch: int) -> list[dict[str, Any]]:
    """Public Reddit JSON listing for posts matching `query` in `subreddit`.

    No auth, no praw — keeps the dependency surface minimal and the rate
    behaviour easy to reason about. Returns a list of {author, platform,
    permalink, created_utc, title}.
    """
    import requests  # noqa: PLC0415

    url = f"https://www.reddit.com/r/{subreddit}/search.json"
    params = {
        "q": query,
        "restrict_sr": "true",
        "sort": "relevance",
        "t": "year",
        "limit": 50,
    }
    headers = {"User-Agent": "vc-thesis-discovery/0.1 (by /u/thesis-bot)"}
    try:
        resp = requests.get(url, params=params, headers=headers, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        logger.warning("reddit fetch failed for r/%s '%s': %s", subreddit, query, exc)
        return []

    out: list[dict[str, Any]] = []
    for child in (data.get("data", {}) or {}).get("children", []) or []:
        post = child.get("data", {}) or {}
        if int(post.get("created_utc", 0)) < since_epoch:
            continue
        author = post.get("author")
        if not author or author in {"[deleted]", "AutoModerator"}:
            continue
        out.append(
            {
                "author": author,
                "platform": "reddit",
                "subreddit": subreddit,
                "permalink": f"https://www.reddit.com{post.get('permalink', '')}",
                "created_utc": int(post.get("created_utc", 0)),
                "title": post.get("title", ""),
            }
        )
    return out


def _hn_fetch(query: str, since_epoch: int) -> list[dict[str, Any]]:
    """Hacker News Algolia search — free, no auth.

    Pulls stories + comments matching the query in the last 90d, returns
    list of {author, platform, story_id, created_at}.
    """
    import requests  # noqa: PLC0415

    url = "https://hn.algolia.com/api/v1/search_by_date"
    params = {
        "query": query,
        "tags": "story",
        "numericFilters": f"created_at_i>{since_epoch}",
        "hitsPerPage": 50,
    }
    try:
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        logger.warning("hn fetch failed for '%s': %s", query, exc)
        return []

    out: list[dict[str, Any]] = []
    for hit in data.get("hits", []) or []:
        author = hit.get("author")
        if not author:
            continue
        out.append(
            {
                "author": author,
                "platform": "hackernews",
                "story_id": hit.get("objectID"),
                "created_at": hit.get("created_at"),
                "title": hit.get("title", ""),
            }
        )
    return out


def _harvest_one_cluster(
    cluster: ClusterRow,
    since_epoch: int,
) -> list[dict[str, Any]]:
    """Run Reddit + HN harvest for one cluster. Returns raw author rows."""
    rows: list[dict[str, Any]] = []

    reddit_fn = REDDIT_FETCH_FN or _reddit_fetch
    hn_fn = HN_FETCH_FN or _hn_fetch

    subs = cluster.suggested_subreddits or list(DEFAULT_REDDIT_FALLBACK_SUBS)
    for sub in subs:
        for row in reddit_fn(sub, cluster.representative_label, since_epoch):
            row["cluster_id"] = cluster.cluster_id
            rows.append(row)
        time.sleep(0.5)  # gentle pacing to Reddit's anonymous JSON endpoint

    for row in hn_fn(cluster.representative_label, since_epoch):
        row["cluster_id"] = cluster.cluster_id
        rows.append(row)

    return rows


def harvest_candidates(
    clusters: list[ClusterRow],
    *,
    since_days: int = DEFAULT_HARVEST_SINCE_DAYS,
    max_workers: int = 4,
    now: datetime | None = None,
) -> pd.DataFrame:
    """Harvest candidate handles per cluster in parallel.

    Returns a long-form DataFrame (one row per (cluster, author, platform)
    occurrence). Aggregation + ranking happens in `_rank_candidates`.
    """
    if not clusters:
        return pd.DataFrame()
    now_ts = now or datetime.now(UTC)
    since_epoch = int((now_ts - timedelta(days=since_days)).timestamp())

    all_rows: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(_harvest_one_cluster, c, since_epoch): c for c in clusters}
        for fut in as_completed(futures):
            cluster = futures[fut]
            try:
                all_rows.extend(fut.result())
            except Exception:
                logger.exception("harvest failed for cluster %s", cluster.cluster_id)
    return pd.DataFrame(all_rows)


# ---------------------------------------------------------------------------
# Aggregate + rank
# ---------------------------------------------------------------------------


def _rank_candidates(
    raw: pd.DataFrame,
    clusters: list[ClusterRow],
    *,
    per_cluster_top_pct: float = DEFAULT_PER_CLUSTER_TOP_PCT,
    rank_threshold: float = DEFAULT_RANK_THRESHOLD,
) -> pd.DataFrame:
    """Aggregate raw author rows into one row per (cluster_id, handle) with
    discovery_strength = n_appearances × (1 + 0.5 * (n_platforms - 1)).
    """
    cluster_label_by_id = {c.cluster_id: c.representative_label for c in clusters}
    if len(raw) == 0:
        return pd.DataFrame(
            columns=[
                "cluster_id", "cluster_label", "handle", "source_platforms",
                "n_appearances", "n_platforms", "discovery_strength",
                "suggested_for_ranking",
            ]
        )

    grouped = (
        raw.groupby(["cluster_id", "author"])
        .agg(
            n_appearances=("platform", "size"),
            source_platforms=("platform", lambda s: sorted(set(s))),
        )
        .reset_index()
    )
    grouped["n_platforms"] = grouped["source_platforms"].apply(len)
    grouped["cross_platform_bonus"] = 1.0 + 0.5 * (grouped["n_platforms"] - 1)
    grouped["discovery_strength"] = (
        grouped["n_appearances"] * grouped["cross_platform_bonus"]
    )
    grouped = grouped.rename(columns={"author": "handle"})
    grouped["cluster_label"] = grouped["cluster_id"].map(cluster_label_by_id)

    # Per-cluster top-N% qualifies, OR discovery_strength >= rank_threshold.
    grouped = grouped.sort_values(
        ["cluster_id", "discovery_strength"], ascending=[True, False]
    )
    grouped["suggested_for_ranking"] = False
    for _cluster_id, sub in grouped.groupby("cluster_id"):
        cutoff_n = max(1, int(len(sub) * per_cluster_top_pct))
        top_idx = sub.head(cutoff_n).index
        grouped.loc[top_idx, "suggested_for_ranking"] = True
        threshold_idx = sub[sub["discovery_strength"] >= rank_threshold].index
        grouped.loc[threshold_idx, "suggested_for_ranking"] = True

    return grouped[
        [
            "cluster_id", "cluster_label", "handle", "source_platforms",
            "n_appearances", "n_platforms", "discovery_strength",
            "suggested_for_ranking",
        ]
    ].reset_index(drop=True)


# ---------------------------------------------------------------------------
# Output schema
# ---------------------------------------------------------------------------


_CANDIDATES_SCHEMA = pa.schema(
    [
        ("cluster_id", pa.string()),
        ("cluster_label", pa.string()),
        ("handle", pa.string()),
        ("source_platforms", pa.list_(pa.string())),
        ("n_appearances", pa.int32()),
        ("n_platforms", pa.int32()),
        ("discovery_strength", pa.float64()),
        ("suggested_for_ranking", pa.bool_()),
    ]
)


def write_candidates(df: pd.DataFrame, out_path: Path = DISCOVERED_CANDIDATES_PATH) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if len(df) == 0:
        table = _CANDIDATES_SCHEMA.empty_table()
    else:
        df = df.copy()
        df["n_appearances"] = df["n_appearances"].astype("int32")
        df["n_platforms"] = df["n_platforms"].astype("int32")
        df["suggested_for_ranking"] = df["suggested_for_ranking"].astype(bool)
        table = pa.Table.from_pandas(df, schema=_CANDIDATES_SCHEMA, preserve_index=False)
    pq.write_table(table, out_path)
    logger.info("wrote %d candidates to %s", len(df), out_path)
    return out_path


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------


def discover(
    seeds: list[str] | None = None,
    date: datetime | None = None,
    from_cohort: bool = False,
    max_topics: int = DEFAULT_MAX_SEEDS,
    *,
    write_clusters_csv: bool = True,
) -> tuple[list[ClusterRow], pd.DataFrame]:
    """Run the full discovery pipeline. Returns (clusters, candidates_df)."""
    if from_cohort and (seeds is None or not seeds):
        seeds = _seeds_from_cohort(date=date, max_seeds=max_topics)
    if not seeds:
        raise ValueError("no seeds available — pass --from-cohort or --seed-topics")

    logger.info("clustering %d seed topics", len(seeds))
    clusters = cluster_topics(seeds)
    logger.info("got %d clusters", len(clusters))

    if write_clusters_csv:
        _write_topics_csv(clusters, seeds)

    raw = harvest_candidates(clusters, now=date)
    logger.info("harvested %d raw author rows", len(raw))
    ranked = _rank_candidates(raw, clusters)
    logger.info(
        "ranked candidates: %d total, %d suggested",
        len(ranked), int(ranked["suggested_for_ranking"].sum()) if len(ranked) else 0,
    )
    return clusters, ranked


def _write_topics_csv(clusters: list[ClusterRow], seeds: list[str]) -> None:
    """Companion CSV with one row per cluster. Useful for the dashboard."""
    rows = [
        {
            "cluster_id": c.cluster_id,
            "representative_label": c.representative_label,
            "n_member_topics": len(c.member_topics),
            "momentum_signal_strength": c.momentum_signal_strength,
            "suggested_subreddits": "|".join(c.suggested_subreddits),
            "rationale": c.rationale,
        }
        for c in clusters
    ]
    df = pd.DataFrame(rows)
    DISCOVERED_TOPICS_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(DISCOVERED_TOPICS_PATH, index=False)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m discovery.topic_discovery",
        description="LLM-clustered topic discovery + cross-platform candidate harvest.",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--from-cohort", action="store_true",
                       help="Seed from scored_signals.parquet's s6_topic_label column.")
    group.add_argument("--seed-topics", type=str,
                       help="Comma-separated topic list (e.g. 'AI agents,creator tools').")
    parser.add_argument("--date", type=str, default=None,
                        help="ISO date for replay mode (default: today). Filters signals "
                             "to observed_at <= date for lookahead-bias discipline.")
    parser.add_argument("--max-topics", type=int, default=DEFAULT_MAX_SEEDS)
    parser.add_argument("--out", type=Path, default=DISCOVERED_CANDIDATES_PATH)
    parser.add_argument("--log-level", default="INFO",
                        choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=args.log_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    date = None
    if args.date:
        date = datetime.fromisoformat(args.date).replace(tzinfo=UTC)

    seeds = _seeds_from_cli(args.seed_topics) if args.seed_topics else None

    clusters, candidates = discover(
        seeds=seeds,
        date=date,
        from_cohort=args.from_cohort,
        max_topics=args.max_topics,
    )
    write_candidates(candidates, out_path=args.out)

    print(f"\nclusters: {len(clusters)}")
    for c in clusters[:10]:
        print(f"  {c.cluster_id:<25s} {c.representative_label}")

    if len(candidates):
        per_cluster = (
            candidates.groupby("cluster_id")
            .agg(n=("handle", "count"), suggested=("suggested_for_ranking", "sum"))
        )
        print("\ncandidates per cluster:")
        print(per_cluster.to_string())
    else:
        print("\nno candidates harvested (network issue? empty clusters?)")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
