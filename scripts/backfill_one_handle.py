"""Backfill ONE positive handle via Wayback, in an isolated process.

Wayback throttles per-client after the first handle in a batch loop
(confirmed: handle #1 works, handle #2 wedges at 0% CPU). The reliable
mode is one fresh process per handle so no throttle/connection state
carries over. This script is that single unit; `backfill_positives.sh`
drives it sequentially with a per-process timeout.

Usage:
    python scripts/backfill_one_handle.py <handle> [--max-signals N]
        [--start YYYY-MM-DD] [--end YYYY-MM-DD] [--wayback-rate-sec S]

Exit 0 on success (even 0 events — that's a real "no Wayback data"
answer); prints a single RESULT line for the driver to parse.
"""
from __future__ import annotations

import argparse
import logging
from datetime import date
from pathlib import Path

import pandas as pd

from ingestion import twitter_collect
from ingestion.twitter_collect import collect_twitter

logger = logging.getLogger(__name__)

_RAW_TWITTER = Path("data/raw/twitter")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("handle")
    p.add_argument("--max-signals", type=int, default=120)
    p.add_argument("--start", type=lambda s: date.fromisoformat(s), default=date(2018, 1, 1))
    p.add_argument("--end", type=lambda s: date.fromisoformat(s), default=date(2024, 1, 1))
    p.add_argument("--wayback-rate-sec", type=float, default=3.0)
    # Tighten snapshot timeout so a hung connection fails fast instead of
    # burning 60s × retries and wedging the process.
    p.add_argument("--snapshot-timeout", type=int, default=20)
    # Wayback snapshot HTML fetches are slow (10s+ each) and hang under load.
    # Cap how many we fetch per handle so a run completes in bounded time.
    p.add_argument("--max-snapshots", type=int, default=25)
    p.add_argument("--log-level", default="INFO")
    args = p.parse_args(argv)

    logging.basicConfig(level=args.log_level, format="%(levelname)s %(name)s: %(message)s")

    twitter_collect._WAYBACK_RATE_LIMIT_SEC = args.wayback_rate_sec
    twitter_collect._SNAPSHOT_TIMEOUT_SEC = args.snapshot_timeout
    twitter_collect._CDX_TIMEOUT_SEC = max(args.snapshot_timeout, 30)

    # Cap snapshots/handle: wrap the CDX index fn to truncate its output.
    # The index returns newest-first within the window; take the first N.
    _orig_cdx = twitter_collect._fetch_cdx_index

    def _capped_cdx(handle, start, end, _cap=args.max_snapshots, _fn=_orig_cdx):
        ts = _fn(handle, start, end)
        if len(ts) > _cap:
            logger.info("capping %s: %d → %d snapshots", handle, len(ts), _cap)
            return ts[:_cap]
        return ts

    twitter_collect._fetch_cdx_index = _capped_cdx

    _RAW_TWITTER.mkdir(parents=True, exist_ok=True)
    handle = args.handle

    try:
        path = collect_twitter(
            handle=handle, start=args.start, end=args.end, out_dir=_RAW_TWITTER
        )
    except Exception as exc:  # noqa: BLE001
        import traceback  # noqa: PLC0415
        traceback.print_exc()
        print(f"RESULT {handle} ERROR {type(exc).__name__}: {exc}")
        return 0  # don't fail the driver; report and move on

    n = len(pd.read_parquet(path))
    if n > args.max_signals:
        df = pd.read_parquet(path)
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
        df = df.sort_values("timestamp", ascending=False).head(args.max_signals)
        # Normalise to canonical string schema for clean.py concat.
        import glob  # noqa: PLC0415

        import pyarrow as pa  # noqa: PLC0415
        import pyarrow.parquet as pq  # noqa: PLC0415

        canonical = None
        for r in sorted(glob.glob(str(_RAW_TWITTER / "*.parquet"))):
            s = pq.read_schema(r)
            if s.field("signal_id").type == pa.string():
                canonical = s
                break
        if canonical is not None:
            try:
                pq.write_table(
                    pa.Table.from_pandas(df, preserve_index=False).cast(canonical), path
                )
            except Exception:  # noqa: BLE001
                df.to_parquet(path, index=False)
        else:
            df.to_parquet(path, index=False)
        n = len(df)

    print(f"RESULT {handle} OK {n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
