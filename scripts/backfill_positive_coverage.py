"""Backfill ingested signals for the X-native positive cohort.

13 of the 20 cohort positives have 0 ingested signals: they are
X/Twitter-native creators (levelsio, yongfook, damengchen, ...) with
~0 HackerNews activity, so the HN ingestion that covered the other 7
positives can't reach them. snscrape is dead (CLAUDE.md), but Wayback
CDX has rich snapshots for them, and `ingestion.twitter_collect`'s
Wayback path parses those into tweet SignalEvents.

This script:
  - Targets only positives currently lacking scored signals.
  - Calls collect_twitter() per handle (snscrape attempt → Wayback
    fallback) with retry on transient CDX/connection failures.
  - Caps signals/handle to bound LLM scoring cost + keep the class
    from being dominated by the heaviest tweeters.
  - Reports which handles closed vs stayed thin (Wayback is rate-limit
    prone; thin handles are acceptable degradation, not a blocker).

After running:
    python pipeline.py clean score person graph kg-features
    python pipeline.py eval backtest allocate
"""
from __future__ import annotations

import argparse
import logging
import time
from datetime import date
from pathlib import Path

import pandas as pd

from ingestion import twitter_collect
from ingestion.cohort import load_cohort
from ingestion.schema import handle_to_person_id
from ingestion.twitter_collect import collect_twitter

logger = logging.getLogger(__name__)

_SCORED = Path("data/processed/scored_signals.parquet")
_RAW_TWITTER = Path("data/raw/twitter")

DEFAULT_START = date(2018, 1, 1)
DEFAULT_END = date(2024, 1, 1)
DEFAULT_MAX_SIGNALS_PER_HANDLE = 120
DEFAULT_RETRIES = 3
# Wayback throttles sustained snapshot fetching (Connection refused after a
# burst). These pacing knobs respect that: a slow per-request rate plus a
# cooldown between handles lets the throttle window reset. Slower wall-clock,
# but it actually completes where a tight loop wedges.
DEFAULT_WAYBACK_RATE_SEC = 4.0   # was 1.0 in the module; override at runtime
DEFAULT_HANDLE_COOLDOWN_SEC = 20.0
DEFAULT_HANDLE_RETRY_COOLDOWN_SEC = 60.0  # longer rest after a throttle hit


def positives_missing_signals(scored_path: Path = _SCORED) -> list[str]:
    """X handles of positives that currently have 0 scored signals."""
    cohort = load_cohort()
    positives = [m for m in cohort if getattr(m, "emerged", True)]

    scored_ids: set[str] = set()
    if scored_path.exists():
        df = pd.read_parquet(scored_path)
        scored_ids = set(df["person_id"].astype(str))

    missing: list[str] = []
    for m in positives:
        handle = getattr(m, "x_handle", None)
        if not handle:
            continue
        pid = handle_to_person_id(handle)
        if pid not in scored_ids:
            missing.append(handle)
    return missing


def _collect_with_retry(
    handle: str,
    start: date,
    end: date,
    retries: int,
    retry_cooldown: float = DEFAULT_HANDLE_RETRY_COOLDOWN_SEC,
) -> int:
    """collect_twitter with retry + long cooldown on throttle. Returns event count."""
    last_n = 0
    for attempt in range(1, retries + 1):
        try:
            path = collect_twitter(
                handle=handle, start=start, end=end, out_dir=_RAW_TWITTER
            )
            last_n = len(pd.read_parquet(path))
            if last_n > 0:
                return last_n
            # 0 events: either genuinely no Wayback tweets, or a throttle
            # blip. Rest a full window before retrying so the connection
            # limit resets.
            logger.info(
                "%s: 0 events on attempt %d — cooling down %.0fs",
                handle, attempt, retry_cooldown,
            )
        except Exception as exc:
            logger.warning(
                "%s: collect failed attempt %d (%s) — cooling down %.0fs",
                handle, attempt, exc, retry_cooldown,
            )
        if attempt < retries:
            time.sleep(retry_cooldown)
    return last_n


def trim_parquet_to_cap(path: Path, cap: int) -> int:
    """Keep the `cap` most-recent signals; normalise to canonical string schema."""
    import pyarrow as pa  # noqa: PLC0415
    import pyarrow.parquet as pq  # noqa: PLC0415

    df = pd.read_parquet(path)
    if len(df) > cap:
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
        df = df.sort_values("timestamp", ascending=False).head(cap)

    # Match the canonical (string, not large_string) schema used by the
    # cohort positives so clean.py's concat_tables succeeds.
    import glob  # noqa: PLC0415

    canonical = None
    for r in sorted(glob.glob(str(_RAW_TWITTER / "*.parquet"))):
        s = pq.read_schema(r)
        if s.field("signal_id").type == pa.string():
            canonical = s
            break
    if canonical is not None:
        try:
            table = pa.Table.from_pandas(df, preserve_index=False).cast(canonical)
            pq.write_table(table, path)
            return len(df)
        except Exception:  # pragma: no cover
            logger.warning("schema cast failed for %s; writing as-is", path.name)
    df.to_parquet(path, index=False)
    return len(df)


def backfill(
    start: date = DEFAULT_START,
    end: date = DEFAULT_END,
    max_signals: int = DEFAULT_MAX_SIGNALS_PER_HANDLE,
    retries: int = DEFAULT_RETRIES,
    wayback_rate_sec: float = DEFAULT_WAYBACK_RATE_SEC,
    handle_cooldown: float = DEFAULT_HANDLE_COOLDOWN_SEC,
) -> dict[str, int]:
    """Ingest Wayback signals for positives missing them. Returns {handle: kept}.

    Paces requests to respect Wayback throttling: slows the module's
    per-request rate limit and rests between handles. Checkpoints after each
    handle (the raw parquet is written immediately), so a mid-run failure
    keeps completed handles.
    """
    _RAW_TWITTER.mkdir(parents=True, exist_ok=True)

    # Slow the shared collector's rate limit for this run only.
    original_rate = twitter_collect._WAYBACK_RATE_LIMIT_SEC
    twitter_collect._WAYBACK_RATE_LIMIT_SEC = wayback_rate_sec
    logger.info(
        "wayback rate limit %.1fs → %.1fs for this run",
        original_rate, wayback_rate_sec,
    )

    targets = positives_missing_signals()
    logger.info("positives missing signals: %d → %s", len(targets), targets)

    result: dict[str, int] = {}
    try:
        for i, handle in enumerate(targets, start=1):
            logger.info("[%d/%d] backfilling %s", i, len(targets), handle)
            n = _collect_with_retry(handle, start, end, retries)
            if n == 0:
                logger.warning(
                    "%s: stayed thin (0 events after %d tries)", handle, retries
                )
                result[handle] = 0
            else:
                pid = handle_to_person_id(handle)
                path = _RAW_TWITTER / f"{pid}_{start.isoformat()}_{end.isoformat()}.parquet"
                kept = trim_parquet_to_cap(path, max_signals) if path.exists() else n
                result[handle] = kept
                logger.info("%s → %d signals kept (of %d)", handle, kept, n)
            # Cooldown between handles so we don't trip the throttle.
            if i < len(targets):
                time.sleep(handle_cooldown)
    finally:
        twitter_collect._WAYBACK_RATE_LIMIT_SEC = original_rate
    return result


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--start", type=lambda s: date.fromisoformat(s), default=DEFAULT_START)
    p.add_argument("--end", type=lambda s: date.fromisoformat(s), default=DEFAULT_END)
    p.add_argument("--max-signals", type=int, default=DEFAULT_MAX_SIGNALS_PER_HANDLE)
    p.add_argument("--retries", type=int, default=DEFAULT_RETRIES)
    p.add_argument("--wayback-rate-sec", type=float, default=DEFAULT_WAYBACK_RATE_SEC)
    p.add_argument("--handle-cooldown", type=float, default=DEFAULT_HANDLE_COOLDOWN_SEC)
    p.add_argument("--log-level", default="INFO")
    args = p.parse_args(argv)

    logging.basicConfig(level=args.log_level, format="%(levelname)s %(name)s: %(message)s")

    res = backfill(
        start=args.start, end=args.end,
        max_signals=args.max_signals, retries=args.retries,
        wayback_rate_sec=args.wayback_rate_sec,
        handle_cooldown=args.handle_cooldown,
    )
    closed = {h: n for h, n in res.items() if n > 0}
    thin = [h for h, n in res.items() if n == 0]
    print(f"\nbackfill complete | closed {len(closed)} / {len(res)} handles")
    for h, n in closed.items():
        print(f"  {h:<18s} {n} signals")
    if thin:
        print(f"\nstayed thin (Wayback unavailable): {', '.join(thin)}")
    print(
        "\nNext: python pipeline.py clean score person graph kg-features "
        "&& python pipeline.py eval backtest allocate"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
