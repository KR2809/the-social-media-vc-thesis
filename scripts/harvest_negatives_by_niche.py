"""Phase C — harvest a large in-niche negative candidate pool (LLM-free).

The `discovery.topic_discovery` LLM clustering step is bypassed here: instead of
asking Haiku to cluster cohort topics, we hand-build one `ClusterRow` per
positive-cohort niche (the same niches enumerated in `cohort_verified.md`) with
several HN-Algolia query terms each. This recovers a niche-diverse candidate
pool from Hacker News (free, no auth) WITHOUT spending LLM budget and WITHOUT
depending on Reddit (whose unauthenticated JSON is now edge-blocked).

These candidates are the raw material for `scripts/ingest_signal_bearing_negatives.py`,
which ingests their HN history and labels them emerged=0 (in-niche posters whose
base rate of emergence is ~0). Nothing is synthesised: a query that returns no
authors contributes nothing.

Usage:
    python -m scripts.harvest_negatives_by_niche --since-days 3650
"""

from __future__ import annotations

import argparse
import logging
from datetime import UTC, datetime, timedelta

import pandas as pd

from discovery.topic_discovery import (
    ClusterRow,
    _hn_fetch,
    _rank_candidates,
    write_candidates,
)

logger = logging.getLogger(__name__)

# One cluster per positive-cohort niche. `representative_label` is the primary
# HN-Algolia query; `member_topics` are extra query terms harvested into the
# same cluster to widen yield. Subreddits are advisory only (Reddit is blocked).
_NICHE_CLUSTERS: list[tuple[str, str, list[str]]] = [
    # (cluster_id, primary query, extra queries)
    ("saas_boilerplate", "SaaS boilerplate", ["Next.js boilerplate", "starter kit SaaS", "indie hacker boilerplate"]),
    ("image_video_api", "image generation API", ["banner generation API", "video generation API", "screenshot API"]),
    ("notion_tools", "Notion tool", ["Notion template", "Notion to website", "Notion API app"]),
    ("twitter_growth_tools", "Twitter growth tool", ["tweet scheduling tool", "X growth SaaS", "Twitter analytics tool"]),
    ("testimonials_socialproof", "testimonial tool", ["social proof widget", "review collection SaaS", "customer testimonials app"]),
    ("ai_productivity", "AI productivity tool", ["AI writing assistant", "AI chat app", "ChatGPT wrapper SaaS"]),
    ("newsletter_creator", "newsletter business", ["paid newsletter", "Substack creator", "email newsletter SaaS"]),
    ("writing_cohort_edu", "writing cohort course", ["online course creator", "cohort based course", "digital writing course"]),
    ("indie_saas_general", "indie SaaS launch", ["bootstrapped SaaS", "build in public SaaS", "solo founder SaaS"]),
    ("community_products", "paid community", ["membership community app", "community platform SaaS", "creator community"]),
    ("ai_image_tools", "AI headshot", ["AI avatar generator", "AI photo app", "AI image SaaS"]),
    ("dev_tools_indie", "developer tool indie", ["CLI tool launch", "open source SaaS", "API developer tool"]),
]


def build_clusters() -> list[ClusterRow]:
    clusters: list[ClusterRow] = []
    for cid, primary, extras in _NICHE_CLUSTERS:
        clusters.append(
            ClusterRow(
                cluster_id=cid,
                representative_label=primary,
                member_topics=[primary, *extras],
                rationale="hand-built niche cluster (Phase C, LLM-free)",
                momentum_signal_strength=0.5,
                suggested_subreddits=[],  # Reddit blocked; HN only
                degraded=False,
            )
        )
    return clusters


def harvest_hn_only(clusters: list[ClusterRow], since_days: int) -> pd.DataFrame:
    """HN-only harvest across every query term of every cluster."""
    since_epoch = int((datetime.now(UTC) - timedelta(days=since_days)).timestamp())
    rows: list[dict] = []
    for c in clusters:
        for query in c.member_topics:
            hits = _hn_fetch(query, since_epoch)
            for h in hits:
                h["cluster_id"] = c.cluster_id
                rows.append(h)
            logger.info("cluster=%s query=%r -> %d authors", c.cluster_id, query, len(hits))
    return pd.DataFrame(rows)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--since-days", type=int, default=3650, help="HN lookback window (days).")
    args = ap.parse_args(argv)

    clusters = build_clusters()
    raw = harvest_hn_only(clusters, args.since_days)
    if len(raw) == 0:
        logger.warning("no candidates harvested — HN Algolia returned nothing.")
        write_candidates(pd.DataFrame())
        return 1

    ranked = _rank_candidates(raw, clusters)
    out = write_candidates(ranked)

    n_unique = ranked["handle"].nunique()
    print(
        f"harvest complete | raw rows={len(raw)} | unique handles={n_unique} | "
        f"clusters={ranked['cluster_id'].nunique()} | written to {out}"
    )
    # Per-cluster balance.
    bal = ranked.groupby("cluster_id")["handle"].nunique().sort_values(ascending=False)
    print("per-cluster unique handles:")
    print(bal.to_string())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
