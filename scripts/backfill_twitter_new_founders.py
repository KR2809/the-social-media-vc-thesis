"""Low-concurrency Wayback Twitter backfill for the iter-15 new founders.

Phase B of the expanded backtest run. The cohort sweep skips Twitter (the
Wayback CDX path throttles hard). This script attempts Wayback for the new /
zero-Twitter founders ONE AT A TIME (no concurrency) and records the realised
snapshot density per handle to `data/interim/wayback_density.csv`.

No paid X API is used. Handles that Wayback cannot recover are recorded with
their (empty) result honestly — never synthesised.

Usage: python -m scripts.backfill_twitter_new_founders
"""

from __future__ import annotations

import csv
import logging
from datetime import date, datetime
from pathlib import Path

from ingestion.cohort import load_cohort
from ingestion.schema import parquet_to_signal_events
from ingestion.twitter_collect import collect_twitter

logger = logging.getLogger(__name__)

# New founders (iter-15) + any pre-existing founder with no Twitter file yet.
_WINDOW_START = date(2014, 1, 1)
_WINDOW_END = date(2026, 6, 1)
_DENSITY_CSV = Path("data/interim/wayback_density.csv")
_TWITTER_DIR = Path("data/raw/twitter")


def _already_has_twitter(person_id: str) -> bool:
    return any(_TWITTER_DIR.glob(f"{person_id}_*.parquet"))


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    cohort = load_cohort()
    targets = [m for m in cohort if not _already_has_twitter(m.person_id)]
    logger.info("Wayback backfill targets (no existing twitter file): %d", len(targets))

    _DENSITY_CSV.parent.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    for m in targets:
        logger.info("Wayback: @%s (#%d %s)", m.x_handle, m.number, m.founder_name)
        n_events = 0
        status = "ok"
        try:
            out = collect_twitter(
                handle=m.x_handle, start=_WINDOW_START, end=_WINDOW_END,
                out_dir=_TWITTER_DIR,
            )
            n_events = len(parquet_to_signal_events(Path(out)))
        except Exception as exc:  # noqa: BLE001
            status = f"error:{type(exc).__name__}"
            logger.warning("  @%s failed: %s", m.x_handle, exc)
        rows.append(
            {
                "person_id": m.person_id,
                "handle": m.x_handle,
                "n_tweets_recovered": n_events,
                "status": status,
                "collected_at": datetime.now().isoformat(timespec="seconds"),
            }
        )

    with _DENSITY_CSV.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["person_id", "handle", "n_tweets_recovered", "status", "collected_at"],
        )
        w.writeheader()
        w.writerows(rows)

    recovered = sum(1 for r in rows if r["n_tweets_recovered"] > 0)
    total = sum(r["n_tweets_recovered"] for r in rows)
    print(
        f"wayback backfill complete | handles={len(rows)} | "
        f"recovered>=1: {recovered} | total tweets: {total} | density → {_DENSITY_CSV}"
    )


if __name__ == "__main__":
    main()
