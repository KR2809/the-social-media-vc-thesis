"""Ingest signal-bearing negatives from the discovery harvest.

The B2.b zero-feature negatives are trivially separable from positives
(eval ROC AUC = 1.000) because abandoned PH projects leave no founder
signal trail. This script builds *real* negatives instead: people who
posted publicly in creator-economy niches (harvested by the discovery
pipeline) but did NOT cross the §4.1 emergence threshold.

Source: `data/processed/discovered_candidates.parquet` (HN handles only —
HN's API is auth-free, in-policy per CLAUDE.md §6; Reddit needs PRAW creds
we don't have).

Integrity guards:
  - We label these negative ONLY because they're drawn from the broad
    in-niche posting population whose base rate of emergence is ~0. Any
    handle that looks emerged (very high signal volume + strength) is
    flagged for manual review rather than auto-labelled.
  - Per-handle signal cap keeps LLM scoring cost bounded and the class
    balanced against the 9 ingested positives.
  - Idempotent: re-running skips handles already in outcome_labels.csv.

Flow (mirrors the positive cohort exactly):
    discovered_candidates → collect_hackernews → data/raw/
        → clean → signal_events → score → scored_signals
        → person_features → outcome_labels (emerged=0)

Then re-run `python pipeline.py eval backtest allocate`.
"""
from __future__ import annotations

import argparse
import logging
from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd

from ingestion.hackernews_collect import collect_hackernews
from ingestion.schema import handle_to_person_id

logger = logging.getLogger(__name__)

_DISCOVERED = Path("data/processed/discovered_candidates.parquet")
# clean.py consolidates from per-platform subdirs (data/raw/<platform>/),
# so HN parquets must land in data/raw/hackernews/ to be picked up.
_RAW_DIR = Path("data/raw/hackernews")
_LABELS = Path("data/processed/outcome_labels.csv")

# Defaults tuned for cost + class balance.
DEFAULT_N_HANDLES = 15
DEFAULT_MAX_SIGNALS_PER_HANDLE = 40
DEFAULT_START = date(2015, 1, 1)
# Emergence-review heuristic: a handle with this many high-strength signals
# is suspiciously founder-like and should be eyeballed, not auto-negatived.
EMERGENCE_REVIEW_SIGNAL_FLOOR = 200


def select_hn_handles(
    discovered_path: Path = _DISCOVERED,
    n: int = DEFAULT_N_HANDLES,
) -> list[str]:
    """Pick the top-N HackerNews handles from the discovery harvest.

    Sorted by discovery_strength desc so we ingest the handles with the
    most in-niche public activity — the strongest 'tried publicly' signal,
    which makes them the most informative negatives.
    """
    df = pd.read_parquet(discovered_path)
    hn = df[df["source_platforms"].apply(lambda ps: "hackernews" in list(ps))]
    hn = hn.sort_values("discovery_strength", ascending=False)
    return hn["handle"].head(n).tolist()


def _canonical_hn_schema() -> "object | None":
    """The schema of an existing HN raw parquet, so new files match it.

    pandas→parquet emits `large_string` by default on newer pyarrow, but
    the cohort positives were written with `string`. clean.py's
    pa.concat_tables fails on the mismatch, so we cast new files to the
    canonical schema. Returns None if no reference file exists.
    """
    import glob  # noqa: PLC0415

    import pyarrow.parquet as pq  # noqa: PLC0415

    refs = sorted(glob.glob(str(_RAW_DIR / "*.parquet")))
    for r in refs:
        s = pq.read_schema(r)
        if s.field("signal_id").type == __import__("pyarrow").string():
            return s
    return None


def trim_parquet_to_cap(path: Path, cap: int) -> int:
    """Keep the `cap` most-recent signals; normalise schema. Returns kept count."""
    import pyarrow as pa  # noqa: PLC0415
    import pyarrow.parquet as pq  # noqa: PLC0415

    df = pd.read_parquet(path)
    if len(df) > cap:
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
        df = df.sort_values("timestamp", ascending=False).head(cap)

    # Cast to the canonical (string, not large_string) schema so clean.py's
    # concat_tables succeeds. Falls back to a plain write if no reference.
    canonical = _canonical_hn_schema()
    if canonical is not None:
        try:
            table = pa.Table.from_pandas(df, preserve_index=False).cast(canonical)
            pq.write_table(table, path)
            return len(df)
        except Exception:  # pragma: no cover — cast best-effort
            logger.warning("schema cast failed for %s; writing as-is", path.name)
    df.to_parquet(path, index=False)
    return len(df)


def ingest_negatives(
    n_handles: int = DEFAULT_N_HANDLES,
    max_signals: int = DEFAULT_MAX_SIGNALS_PER_HANDLE,
    start: date = DEFAULT_START,
    end: date | None = None,
    raw_dir: Path = _RAW_DIR,
    labels_path: Path = _LABELS,
) -> dict[str, int]:
    """Ingest + cap HN signals for selected negative handles.

    Returns {handle: kept_signal_count}. Does NOT score or label — that's
    done by the caller (so the cost-bearing LLM step stays explicit).
    """
    end = end or datetime.now(UTC).date()
    raw_dir.mkdir(parents=True, exist_ok=True)

    already: set[str] = set()
    if labels_path.exists():
        existing = pd.read_csv(labels_path)
        already = set(existing["person_id"].astype(str))

    handles = select_hn_handles(n=n_handles)
    result: dict[str, int] = {}
    flagged: list[str] = []

    for h in handles:
        pid = handle_to_person_id(h)
        if pid in already:
            logger.info("skip %s (%s already labelled)", h, pid)
            continue
        try:
            path = collect_hackernews(
                username=h, start=start, end=end, out_dir=raw_dir
            )
        except Exception:
            logger.exception("HN collect failed for %s — skipping", h)
            continue

        full = len(pd.read_parquet(path))
        if full >= EMERGENCE_REVIEW_SIGNAL_FLOOR:
            flagged.append(f"{h} ({full} signals)")
        kept = trim_parquet_to_cap(path, max_signals)
        result[h] = kept
        logger.info("%s → %d signals kept (of %d)", h, kept, full)

    if flagged:
        logger.warning(
            "EMERGENCE REVIEW: %d handle(s) have >=%d signals and may be "
            "real emerged founders — verify before labelling negative: %s",
            len(flagged), EMERGENCE_REVIEW_SIGNAL_FLOOR, ", ".join(flagged),
        )
    return result


def label_negatives(
    handles: list[str], labels_path: Path = _LABELS
) -> Path:
    """Append emerged=0 rows for the ingested handles. Idempotent."""
    if labels_path.exists():
        existing = pd.read_csv(labels_path)
    else:
        existing = pd.DataFrame(columns=["person_id", "emerged", "source"])

    have = set(existing["person_id"].astype(str))
    new = [
        {"person_id": handle_to_person_id(h), "emerged": 0,
         "source": "signal_bearing_negative_hn_discovery"}
        for h in handles
        if handle_to_person_id(h) not in have
    ]
    if not new:
        print("label | nothing to add")
        return labels_path
    out = pd.concat([existing, pd.DataFrame(new)], ignore_index=True)
    out.to_csv(labels_path, index=False)
    print(
        f"label | +{len(new)} negatives | "
        f"pos={int((out['emerged']==1).sum())} neg={int((out['emerged']==0).sum())}"
    )
    return labels_path


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--n-handles", type=int, default=DEFAULT_N_HANDLES)
    p.add_argument("--max-signals", type=int, default=DEFAULT_MAX_SIGNALS_PER_HANDLE)
    p.add_argument("--label", action="store_true",
                   help="After ingesting, append emerged=0 rows to outcome_labels.csv.")
    p.add_argument("--log-level", default="INFO")
    args = p.parse_args(argv)

    logging.basicConfig(level=args.log_level, format="%(levelname)s %(name)s: %(message)s")

    ingested = ingest_negatives(n_handles=args.n_handles, max_signals=args.max_signals)
    print(f"\ningested {len(ingested)} negative handles:")
    for h, n in ingested.items():
        print(f"  {h:<28s} {n} signals")

    if args.label:
        label_negatives(list(ingested.keys()))

    print(
        "\nNext: python pipeline.py clean score person graph kg-features "
        "&& python pipeline.py eval backtest allocate"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
