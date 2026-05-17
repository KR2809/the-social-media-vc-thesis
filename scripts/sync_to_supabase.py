"""Mirror local data/processed/* (and selected data/interim/* files) into
Supabase Postgres. DECISION_LOG iter-13.

Idempotent: every table sync is an UPSERT keyed on the table's natural
primary key (see `supabase/migrations/20260514_initial_schema.sql`).
Re-running this script after a pipeline re-run pushes only the rows
that have new content; rows whose PKs already exist get their non-PK
columns overwritten.

Empty source files produce zero writes (the parquet schema is enough
to know the destination table is correct; we just upsert nothing).

Per iter-13 §3 of `DECISION_LOG`, the service-role key is required
because RLS is enabled with anon-read-only policies. The service-role
key MUST live in `.env` and never be committed. The script refuses to
run if the key is missing.

Usage:
    # From repo root, with .env populated (SUPABASE_URL +
    # SUPABASE_SERVICE_ROLE_KEY at minimum):
    python -m scripts.sync_to_supabase
    python -m scripts.sync_to_supabase --tables signal_events,scored_signals
    python -m scripts.sync_to_supabase --dry-run
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable

import pandas as pd
import pyarrow.parquet as pq
from dotenv import load_dotenv

logger = logging.getLogger("sync_to_supabase")

CHUNK_SIZE = 200  # Supabase's PostgREST has request-size limits; 200 is well within.

_REPO_ROOT = Path(__file__).resolve().parents[1]
_PROCESSED = _REPO_ROOT / "data" / "processed"
_INTERIM = _REPO_ROOT / "data" / "interim"


# ---------------------------------------------------------------------------
# Per-row preparation: parquet/csv shapes → Supabase-friendly JSON
# ---------------------------------------------------------------------------


def _to_iso(value: Any) -> Any:
    """Convert datetime / pd.Timestamp / date to ISO-8601 string; pass through otherwise."""
    if value is None:
        return None
    if isinstance(value, pd.Timestamp):
        if pd.isna(value):
            return None
        return value.isoformat()
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return value


def _clean_row(row: dict[str, Any]) -> dict[str, Any]:
    """Replace NaN/NaT with None, ISO-format datetimes, leave other types alone.

    PostgREST will reject NaN; pandas defaults are full of them.
    """
    out: dict[str, Any] = {}
    for k, v in row.items():
        # Drop the auto-managed mirror_synced_at column (DB sets default).
        if k == "mirror_synced_at":
            continue
        if v is None:
            out[k] = None
            continue
        # pd.isna trips on lists/dicts; protect with a try.
        try:
            if pd.isna(v):
                out[k] = None
                continue
        except (TypeError, ValueError):
            pass
        out[k] = _to_iso(v)
    return out


def _engagement_to_jsonb(val: Any) -> Any:
    """signal_events.engagement comes in as a dict / struct — pass through."""
    if val is None:
        return None
    if isinstance(val, dict):
        return val
    return val


def _metadata_to_jsonb(val: Any) -> Any:
    """signal_events.metadata is stored as a JSON STRING in parquet; parse it."""
    if val is None or val == "":
        return None
    if isinstance(val, str):
        try:
            return json.loads(val)
        except json.JSONDecodeError:
            logger.warning("could not parse metadata JSON: %r", val[:80])
            return None
    return val


# ---------------------------------------------------------------------------
# Per-table sync functions
# ---------------------------------------------------------------------------


def _load_parquet_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        logger.warning("source missing: %s — skipping", path)
        return []
    df = pq.read_table(path).to_pandas()
    if len(df) == 0:
        return []
    return df.to_dict(orient="records")


def _load_csv_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        logger.warning("source missing: %s — skipping", path)
        return []
    df = pd.read_csv(path)
    if len(df) == 0:
        return []
    return df.to_dict(orient="records")


def _prepare_signal_events(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        c = _clean_row(r)
        # engagement was a pyarrow struct → pandas dict; metadata was JSON string.
        c["engagement"] = _engagement_to_jsonb(c.get("engagement"))
        c["metadata"] = _metadata_to_jsonb(c.get("metadata"))
        out.append(c)
    return out


def _prepare_scored_signals(rows: list[dict]) -> list[dict]:
    return [_clean_row(r) for r in rows]


def _prepare_person_features(rows: list[dict]) -> list[dict]:
    return [_clean_row(r) for r in rows]


def _prepare_kg_features(rows: list[dict]) -> list[dict]:
    return [_clean_row(r) for r in rows]


def _prepare_outcome_labels(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        c = _clean_row(r)
        if c.get("emerged") is not None:
            c["emerged"] = int(c["emerged"])
        out.append(c)
    return out


def _prepare_negative_peers(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        c = _clean_row(r)
        if "public_signals_available" in c and c["public_signals_available"] is not None:
            # CSV stores bools as "True"/"False" sometimes; coerce.
            val = c["public_signals_available"]
            c["public_signals_available"] = bool(val) if not isinstance(val, str) else (
                val.strip().lower() == "true"
            )
        out.append(c)
    return out


def _prepare_eval_metrics(rows: list[dict]) -> list[dict]:
    return [_clean_row(r) for r in rows]


def _prepare_backtest_results(rows: list[dict]) -> list[dict]:
    return [_clean_row(r) for r in rows]


def _prepare_allocation(rows: list[dict]) -> list[dict]:
    return [_clean_row(r) for r in rows]


def _prepare_topic_momentum_metrics(rows: list[dict]) -> list[dict]:
    return [_clean_row(r) for r in rows]


def _prepare_discovered_topics(rows: list[dict]) -> list[dict]:
    return [_clean_row(r) for r in rows]


def _prepare_locked_predictions(json_paths: list[Path]) -> list[dict]:
    """Each prospective_predictions_*.json file becomes one row."""
    import hashlib

    out = []
    for p in json_paths:
        if not p.exists():
            continue
        text = p.read_text()
        record = json.loads(text)
        out.append(
            {
                "lock_date": record["lock_date"],
                "framework_version": record["framework_version"],
                "git_commit": record.get("git_commit"),
                "n_predictions": record.get("n_predictions"),
                "record": record,
                "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                "locked_at": record["locked_at"],
            }
        )
    return out


# ---------------------------------------------------------------------------
# Table registry — (table_name, source_loader, on_conflict_columns)
# ---------------------------------------------------------------------------


def _signal_events_source() -> list[dict]:
    return _prepare_signal_events(_load_parquet_rows(_INTERIM / "signal_events.parquet"))


def _scored_signals_source() -> list[dict]:
    return _prepare_scored_signals(_load_parquet_rows(_PROCESSED / "scored_signals.parquet"))


def _person_features_source() -> list[dict]:
    return _prepare_person_features(_load_parquet_rows(_PROCESSED / "person_features.parquet"))


def _kg_features_source() -> list[dict]:
    return _prepare_kg_features(_load_parquet_rows(_PROCESSED / "kg_features.parquet"))


def _outcome_labels_source() -> list[dict]:
    return _prepare_outcome_labels(_load_csv_rows(_PROCESSED / "outcome_labels.csv"))


def _negative_peers_source() -> list[dict]:
    return _prepare_negative_peers(_load_csv_rows(_PROCESSED / "negative_peers_registry.csv"))


def _eval_metrics_source() -> list[dict]:
    return _prepare_eval_metrics(_load_csv_rows(_PROCESSED / "eval_metrics.csv"))


def _backtest_source() -> list[dict]:
    return _prepare_backtest_results(_load_csv_rows(_PROCESSED / "backtest_results.csv"))


def _allocation_source() -> list[dict]:
    return _prepare_allocation(_load_csv_rows(_PROCESSED / "allocation.csv"))


def _topic_momentum_metrics_source() -> list[dict]:
    return _prepare_topic_momentum_metrics(
        _load_parquet_rows(_PROCESSED / "topic_momentum_metrics.parquet")
    )


def _discovered_topics_source() -> list[dict]:
    return _prepare_discovered_topics(_load_csv_rows(_PROCESSED / "discovered_topics.csv"))


def _locked_predictions_source() -> list[dict]:
    workspace = Path(
        "/Users/k.ratkov/Documents/Claude/Projects/Thesis/04_RETROSPECTIVE_CASES"
    )
    candidates = sorted(workspace.glob("prospective_predictions_*.json"))
    return _prepare_locked_predictions(candidates)


TABLE_REGISTRY: list[tuple[str, Callable[[], list[dict]], str]] = [
    ("signal_events",          _signal_events_source,          "signal_id"),
    ("scored_signals",         _scored_signals_source,         "signal_id"),
    ("person_features",        _person_features_source,        "person_id"),
    ("kg_features",            _kg_features_source,            "person_id"),
    ("outcome_labels",         _outcome_labels_source,         "person_id"),
    ("negative_peers_registry", _negative_peers_source,        "peer_id"),
    ("eval_metrics",           _eval_metrics_source,           "name"),
    ("backtest_results",       _backtest_source,               "backtest_date,strategy,k"),
    ("allocation",             _allocation_source,             "person_id"),
    ("topic_momentum_metrics", _topic_momentum_metrics_source, "keyword,geo"),
    ("discovered_topics",      _discovered_topics_source,      "topic,source"),
    ("locked_predictions",     _locked_predictions_source,     "lock_date"),
]


# ---------------------------------------------------------------------------
# Sync engine
# ---------------------------------------------------------------------------


def _get_client():
    """Build a Supabase client using the service-role key. Raises if missing."""
    load_dotenv(override=True)
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url:
        raise RuntimeError("SUPABASE_URL not set in .env")
    if not key:
        raise RuntimeError(
            "SUPABASE_SERVICE_ROLE_KEY not set in .env — required for writes. "
            "Grab it from supabase.com/dashboard/project/<your_project>/settings/api"
        )
    from supabase import create_client  # noqa: PLC0415

    return create_client(url, key)


def _chunks(xs: list[dict], n: int):
    for i in range(0, len(xs), n):
        yield xs[i : i + n]


def sync_table(
    client: Any,
    table_name: str,
    rows: list[dict],
    on_conflict: str,
    dry_run: bool = False,
) -> dict[str, int]:
    """Upsert rows for one table. Returns counts."""
    n_in = len(rows)
    if n_in == 0:
        print(f"sync | {table_name:28s} | 0 rows | nothing to do")
        return {"in": 0, "upserted": 0, "errors": 0}
    if dry_run:
        print(f"sync | {table_name:28s} | {n_in} rows | DRY RUN (no writes)")
        return {"in": n_in, "upserted": 0, "errors": 0}

    upserted = 0
    errors = 0
    for batch in _chunks(rows, CHUNK_SIZE):
        try:
            client.table(table_name).upsert(batch, on_conflict=on_conflict).execute()
            upserted += len(batch)
        except Exception as exc:
            errors += len(batch)
            logger.warning("upsert failed for %s batch: %s", table_name, exc)
    print(
        f"sync | {table_name:28s} | in={n_in:5d} upserted={upserted:5d} errors={errors}"
    )
    return {"in": n_in, "upserted": upserted, "errors": errors}


def sync_all(
    tables: list[str] | None = None,
    dry_run: bool = False,
) -> dict[str, dict[str, int]]:
    """Run the full sync. Returns per-table counts."""
    client = None if dry_run else _get_client()
    out: dict[str, dict[str, int]] = {}
    for table_name, loader, on_conflict in TABLE_REGISTRY:
        if tables and table_name not in tables:
            continue
        try:
            rows = loader()
        except Exception as exc:
            logger.error("loader failed for %s: %s", table_name, exc)
            out[table_name] = {"in": 0, "upserted": 0, "errors": -1}
            continue
        out[table_name] = sync_table(client, table_name, rows, on_conflict, dry_run=dry_run)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Sync local parquet/csv to Supabase Postgres.")
    ap.add_argument(
        "--tables",
        type=str,
        default=None,
        help="Comma-separated subset of table names to sync. Default: all.",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Load + count rows but do not write to Supabase.",
    )
    ap.add_argument("--verbose", "-v", action="store_true")
    args = ap.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    tables = args.tables.split(",") if args.tables else None
    results = sync_all(tables=tables, dry_run=args.dry_run)
    total_in = sum(r["in"] for r in results.values())
    total_up = sum(r["upserted"] for r in results.values())
    total_err = sum(max(0, r["errors"]) for r in results.values())
    print(f"\nsync complete | total: in={total_in} upserted={total_up} errors={total_err}")
    return 0 if total_err == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
