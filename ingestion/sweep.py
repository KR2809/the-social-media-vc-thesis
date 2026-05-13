"""Cohort-wide ingestion sweep orchestrator (task 2.5).

Walks the verified cohort and calls each available platform collector
for a chosen date window. Skips platforms whose credentials are not
present in `.env`. Twitter is attempted via the existing Wayback path
(snscrape is dead per Phase 1.2 finding); Trends is NOT a per-person
platform and is handled separately.

Output: per-(founder, platform) parquets land under
`data/raw/<platform>/<person_id>_<start>_<end>.parquet`. Missing
accounts produce empty parquets — the balance report surfaces these
honestly so the gap-fill step (task 2.7) can target them.

This script is deliberately tolerant of platform-level failures: one
404 on Reddit does not abort the sweep.
"""

from __future__ import annotations

import logging
import os
import time
from datetime import UTC, date, datetime
from pathlib import Path

import click
from dotenv import load_dotenv

from ingestion.cohort import CohortMember, load_cohort

logger = logging.getLogger(__name__)

# Default sweep window. Covers most cohort emergence dates (2018–2025)
# plus pre-emergence activity. Per-founder windows derived from
# `emergence_quarter` are a future improvement once we add an ISO date
# field to the override file.
_DEFAULT_START = date(2020, 1, 1)
_DEFAULT_END = date(2025, 1, 1)


def _has(*vars: str) -> bool:
    return all(os.environ.get(v) for v in vars)


def _platforms_available() -> dict[str, bool]:
    """Return which platform collectors can run right now."""
    load_dotenv(override=True)
    return {
        "twitter": True,  # Wayback path needs no credentials
        "hackernews": True,  # no auth
        "youtube": _has("YOUTUBE_API_KEY"),
        "reddit": _has("REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET", "REDDIT_USER_AGENT"),
        "producthunt": _has("PRODUCTHUNT_DEV_TOKEN"),
    }


def _safe_collect(label: str, fn, *args, **kwargs) -> Path | None:
    """Run a collector with a try/except wrapper so one failure doesn't
    abort the sweep. Returns the output path on success, None on failure."""
    try:
        return fn(*args, **kwargs)
    except Exception as exc:
        logger.warning(
            "[%s] collector raised %s: %s", label, type(exc).__name__, exc
        )
        return None


def sweep_member(
    member: CohortMember,
    start: date,
    end: date,
    platforms: dict[str, bool],
    *,
    skip_twitter: bool = False,
) -> dict[str, Path | None]:
    """Run all available platform collectors for one cohort member."""
    results: dict[str, Path | None] = {}

    logger.info(
        "sweeping #%d %s (@%s)", member.number, member.founder_name, member.x_handle
    )

    # HackerNews — always runs.
    if platforms.get("hackernews"):
        from ingestion.hackernews_collect import collect_hackernews

        results["hackernews"] = _safe_collect(
            f"hn:{member.hn_username}",
            collect_hackernews,
            username=member.hn_username,
            start=start,
            end=end,
        )

    # Reddit
    if platforms.get("reddit"):
        from ingestion.reddit_collect import collect_reddit

        results["reddit"] = _safe_collect(
            f"reddit:{member.reddit_username}",
            collect_reddit,
            username=member.reddit_username,
            start=start,
            end=end,
        )
    else:
        results["reddit"] = None

    # ProductHunt
    if platforms.get("producthunt"):
        from ingestion.producthunt_collect import collect_producthunt

        results["producthunt"] = _safe_collect(
            f"ph:{member.producthunt_username}",
            collect_producthunt,
            username=member.producthunt_username,
            start=start,
            end=end,
        )
    else:
        results["producthunt"] = None

    # YouTube — needs a channel ID, which we only have if it was set in the
    # overrides file. We don't resolve handle→channel_id here because that
    # burns search.list quota; handle that in a separate fill-channel-ids step.
    if platforms.get("youtube") and member.youtube_channel_id:
        from ingestion.youtube_collect import collect_youtube

        results["youtube"] = _safe_collect(
            f"yt:{member.youtube_channel_id}",
            collect_youtube,
            channel_id=member.youtube_channel_id,
            start=start,
            end=end,
        )
    else:
        results["youtube"] = None

    # Twitter — Wayback fallback (snscrape is dead but the module gracefully
    # handles that). Optional skip flag because Wayback CDX is slow and we
    # might want to defer it.
    if platforms.get("twitter") and not skip_twitter:
        from ingestion.twitter_collect import collect_twitter

        results["twitter"] = _safe_collect(
            f"tw:{member.x_handle}",
            collect_twitter,
            handle=member.x_handle,
            start=start,
            end=end,
        )
    else:
        results["twitter"] = None

    return results


def sweep(
    start: date = _DEFAULT_START,
    end: date = _DEFAULT_END,
    *,
    limit: int | None = None,
    skip_twitter: bool = False,
    pause_between_members_sec: float = 1.0,
) -> list[tuple[CohortMember, dict[str, Path | None]]]:
    """Run the full cohort sweep. Returns list of (member, results) pairs."""
    cohort = load_cohort()
    if limit is not None:
        cohort = cohort[:limit]

    platforms = _platforms_available()
    skipped = [p for p, ok in platforms.items() if not ok]
    if skipped:
        logger.warning(
            "platforms skipped (credentials missing): %s", ", ".join(skipped)
        )

    started_at = datetime.now(UTC)
    out: list[tuple[CohortMember, dict[str, Path | None]]] = []
    for member in cohort:
        results = sweep_member(member, start, end, platforms, skip_twitter=skip_twitter)
        out.append((member, results))
        if pause_between_members_sec > 0:
            time.sleep(pause_between_members_sec)

    elapsed = datetime.now(UTC) - started_at
    print(
        f"sweep complete | members={len(out)} | window={start}→{end} | "
        f"elapsed={elapsed.total_seconds():.0f}s"
    )
    return out


@click.command()
@click.option(
    "--start",
    default=_DEFAULT_START.isoformat(),
    type=click.DateTime(formats=["%Y-%m-%d"]),
)
@click.option(
    "--end",
    default=_DEFAULT_END.isoformat(),
    type=click.DateTime(formats=["%Y-%m-%d"]),
)
@click.option("--limit", default=None, type=int, help="Cohort prefix size for testing.")
@click.option("--skip-twitter", is_flag=True, help="Skip the slow Wayback path.")
def main(start: datetime, end: datetime, limit: int | None, skip_twitter: bool) -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    sweep(start=start.date(), end=end.date(), limit=limit, skip_twitter=skip_twitter)


if __name__ == "__main__":
    main()
