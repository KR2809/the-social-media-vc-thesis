"""Wayback-only Twitter backfill — skips the dead snscrape path entirely.

snscrape's SearchTimeline endpoint has returned HTTP 404 "blocked" since
X's 2023 anti-scraping change (confirmed again 2026-05-29). The existing
`backfill_one_handle.py` tries snscrape first and burns ~30s of retries
per handle before falling back. This script calls `_try_wayback` directly
so each handle goes straight to the Wayback Machine CDX + snapshot parse.

Per-handle snapshot cap + polite pacing keep us within CLAUDE.md §6
(free sources, graceful fallback). Writes one parquet per handle into
data/raw/twitter/, matching the schema the rest of the pipeline expects.

Usage:
    python scripts/backfill_wayback_only.py HANDLE [HANDLE ...] \
        [--start 2016-01-01] [--end 2024-01-01] [--max-snapshots 25]
"""

from __future__ import annotations

import argparse
import logging
from datetime import UTC, date, datetime
from pathlib import Path

from ingestion.schema import handle_to_person_id, signal_events_to_parquet
from ingestion import twitter_collect as tc

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("backfill_wayback")


def backfill(handle: str, start: date, end: date, max_snapshots: int) -> int:
    from bs4 import BeautifulSoup

    collected_at = datetime.now(UTC)
    person_id = handle_to_person_id(handle)
    events = []

    # Walk the CDX index ourselves so we can hard-cap the number of
    # snapshot HTML fetches (the slow part Wayback throttles on). We
    # spread the cap evenly across the available snapshots so the sample
    # covers the whole window, not just the earliest captures.
    try:
        cdx = tc._fetch_cdx_index(handle, start, end)
    except Exception as exc:  # noqa: BLE001
        logger.warning("CDX index failed for %s: %s", handle, exc)
        cdx = []

    if cdx and len(cdx) > max_snapshots:
        step = len(cdx) / max_snapshots
        cdx = [cdx[int(i * step)] for i in range(max_snapshots)]

    for ts in cdx:
        url = tc._WAYBACK_SNAPSHOT_FMT.format(ts=ts, handle=handle.lstrip("@"))
        try:
            r = tc._rate_limited_get(url, timeout=tc._SNAPSHOT_TIMEOUT_SEC)
        except Exception as exc:  # noqa: BLE001
            logger.info("snapshot %s failed: %s", ts, type(exc).__name__)
            continue
        soup = BeautifulSoup(r.text, "lxml")
        events.extend(tc._parse_pre2020_tweets(soup, handle, person_id, collected_at))
        events.extend(tc._parse_post2020_tweets(soup, handle, person_id, collected_at))

    tally = f"{len(cdx)} snapshots"
    # Keep only in-window events + de-dup on signal_id.
    seen: dict[str, object] = {}
    for e in events:
        if start <= e.timestamp.date() < end:
            seen.setdefault(e.signal_id, e)
    events = list(seen.values())
    out = Path("data/raw/twitter") / f"{person_id}_{start.isoformat()}_{end.isoformat()}.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    signal_events_to_parquet(events, out)
    logger.info("RESULT %s -> %d events (tally=%s) -> %s", handle, len(events), tally, out.name)
    return len(events)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("handles", nargs="+")
    ap.add_argument("--start", type=lambda s: date.fromisoformat(s), default=date(2016, 1, 1))
    ap.add_argument("--end", type=lambda s: date.fromisoformat(s), default=date(2024, 1, 1))
    ap.add_argument("--max-snapshots", type=int, default=25)
    args = ap.parse_args()
    total = 0
    for h in args.handles:
        total += backfill(h, args.start, args.end, args.max_snapshots)
    logger.info("DONE — %d total events across %d handles", total, len(args.handles))


if __name__ == "__main__":
    main()
