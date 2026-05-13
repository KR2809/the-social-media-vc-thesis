"""Unified signal-events cleaner (task 2.9).

Walks `data/raw/{twitter,youtube,reddit,hackernews,producthunt}/` and
concatenates every parquet into ONE file at
`data/interim/signal_events.parquet`. This is the single source of
truth that the scoring (W3) and KG (W3) layers consume.

Trends parquets live under `data/raw/trends/` — they have a DIFFERENT
schema (topic time-series, not SignalEvents) and are handled by a
separate function `consolidate_trends()` that writes
`data/interim/topic_momentum.parquet`.

Cleaning rules:
  - Drop rows with missing signal_id, person_id, timestamp.
  - De-dup on signal_id, preferring the most recent collected_at when
    duplicates exist across re-runs.
  - Sort by (person_id, timestamp) ascending.
  - Empty input directories are skipped without error.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

logger = logging.getLogger(__name__)

_SIGNAL_PLATFORMS = ("twitter", "youtube", "reddit", "hackernews", "producthunt")

_RAW_DIR_DEFAULT = Path("data/raw")
_INTERIM_DIR_DEFAULT = Path("data/interim")


def _read_signal_parquets(raw_dir: Path, platform: str) -> pa.Table | None:
    """Read and concat all parquets for one platform. Returns None if empty."""
    pdir = raw_dir / platform
    if not pdir.exists():
        return None
    files = sorted(pdir.glob("*.parquet"))
    if not files:
        return None
    tables: list[pa.Table] = []
    for f in files:
        try:
            t = pq.read_table(f)
        except Exception as exc:
            logger.warning("failed to read %s: %s", f, exc)
            continue
        if t.num_rows == 0:
            continue
        tables.append(t)
    if not tables:
        return None
    return pa.concat_tables(tables, promote_options="default")


def consolidate_signal_events(
    raw_dir: Path = _RAW_DIR_DEFAULT,
    interim_dir: Path = _INTERIM_DIR_DEFAULT,
) -> Path:
    """Merge per-platform raw parquets into one signal_events.parquet.

    Returns the output path. Writes an empty parquet (with schema) if
    nothing is found, so downstream code can rely on the file existing.
    """
    per_platform_tables: list[pa.Table] = []
    counts: dict[str, int] = {}
    for platform in _SIGNAL_PLATFORMS:
        t = _read_signal_parquets(raw_dir, platform)
        if t is None:
            counts[platform] = 0
            continue
        per_platform_tables.append(t)
        counts[platform] = t.num_rows

    interim_dir.mkdir(parents=True, exist_ok=True)
    out_path = interim_dir / "signal_events.parquet"

    if not per_platform_tables:
        # Write empty parquet with the canonical schema from schema module.
        from ingestion.schema import signal_events_to_parquet

        signal_events_to_parquet([], out_path)
        print(f"clean | 0 events total | written to {out_path}")
        return out_path

    table = pa.concat_tables(per_platform_tables, promote_options="default")

    # De-dup on signal_id, preferring most recent collected_at.
    df = table.to_pandas()
    before = len(df)
    df = df.sort_values("collected_at", ascending=False).drop_duplicates(
        subset=["signal_id"], keep="first"
    )
    deduped = before - len(df)

    # Drop rows with missing critical fields.
    null_mask = df["signal_id"].isna() | df["person_id"].isna() | df["timestamp"].isna()
    dropped_null = int(null_mask.sum())
    df = df[~null_mask]

    # Sort canonical (person_id, timestamp).
    df = df.sort_values(["person_id", "timestamp"]).reset_index(drop=True)

    # Write back preserving the original schema.
    out_table = pa.Table.from_pandas(df, schema=table.schema, preserve_index=False)
    pq.write_table(out_table, out_path)

    parts = [f"{k}={v}" for k, v in counts.items() if v]
    print(
        f"clean | {out_table.num_rows} events total | "
        f"{' '.join(parts)} | deduped={deduped} dropped_null={dropped_null} | "
        f"written to {out_path}"
    )
    return out_path


def consolidate_trends(
    raw_dir: Path = _RAW_DIR_DEFAULT,
    interim_dir: Path = _INTERIM_DIR_DEFAULT,
) -> Path:
    """Merge per-keyword trends parquets into one topic_momentum.parquet."""
    pdir = raw_dir / "trends"
    interim_dir.mkdir(parents=True, exist_ok=True)
    out_path = interim_dir / "topic_momentum.parquet"

    files = sorted(pdir.glob("*.parquet")) if pdir.exists() else []
    if not files:
        # Write an empty parquet with the trends schema.
        from ingestion.trends_collect import _PARQUET_SCHEMA  # noqa: PLC0415

        pq.write_table(pa.Table.from_pylist([], schema=_PARQUET_SCHEMA), out_path)
        print(f"trends clean | 0 rows | written to {out_path}")
        return out_path

    tables = [pq.read_table(f) for f in files if pq.read_table(f).num_rows > 0]
    if not tables:
        from ingestion.trends_collect import _PARQUET_SCHEMA  # noqa: PLC0415

        pq.write_table(pa.Table.from_pylist([], schema=_PARQUET_SCHEMA), out_path)
        print(f"trends clean | 0 rows | written to {out_path}")
        return out_path

    table = pa.concat_tables(tables, promote_options="default")
    df = table.to_pandas()
    # De-dup on (keyword, date, geo) — re-runs of the same keyword/window
    # should not double up. Keep most-recent collected_at.
    df = df.sort_values("collected_at", ascending=False).drop_duplicates(
        subset=["keyword", "date", "geo"], keep="first"
    )
    df = df.sort_values(["keyword", "date"]).reset_index(drop=True)
    out_table = pa.Table.from_pandas(df, schema=table.schema, preserve_index=False)
    pq.write_table(out_table, out_path)

    print(
        f"trends clean | {out_table.num_rows} rows | "
        f"keywords={df['keyword'].nunique()} | written to {out_path}"
    )
    return out_path


if __name__ == "__main__":
    import logging as _l

    _l.basicConfig(level=_l.INFO, format="%(levelname)s %(name)s: %(message)s")
    consolidate_signal_events()
    consolidate_trends()
