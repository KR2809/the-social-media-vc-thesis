"""Data source abstraction for the FastAPI layer.

Two implementations:
  - LocalSource — reads from `data/processed/*.parquet` directly via pyarrow
  - SupabaseSource — reads from Supabase tables via the supabase-py client

Selected at process start via the `DATA_SOURCE` env var (default: "local").
The same query interface lets the FastAPI endpoints not care which is wired.

The Supabase implementation only requires the anon key (read-only).
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Protocol

import pandas as pd
import pyarrow.parquet as pq

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[1]
_PROCESSED = _REPO_ROOT / "data" / "processed"
_INTERIM = _REPO_ROOT / "data" / "interim"


class DataSource(Protocol):
    name: str

    def read_signal_events(
        self, person_id: str | None = None, until: datetime | None = None
    ) -> pd.DataFrame: ...
    def read_scored_signals(
        self, person_id: str | None = None, until: datetime | None = None
    ) -> pd.DataFrame: ...
    def read_person_features(self) -> pd.DataFrame: ...
    def read_kg_features(self) -> pd.DataFrame: ...
    def read_outcome_labels(self) -> pd.DataFrame: ...
    def read_eval_metrics(self) -> pd.DataFrame: ...
    def read_backtest_results(self) -> pd.DataFrame: ...
    def read_allocation(self) -> pd.DataFrame: ...
    def read_topic_momentum_metrics(self) -> pd.DataFrame: ...
    def read_discovered_topics(self) -> pd.DataFrame: ...


# ---------------------------------------------------------------------------
# Local parquet/csv source
# ---------------------------------------------------------------------------


def _read_parquet_safe(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    try:
        return pq.read_table(path).to_pandas()
    except Exception as exc:
        logger.warning("read failed for %s: %s", path, exc)
        return pd.DataFrame()


def _read_csv_safe(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except Exception as exc:
        logger.warning("read failed for %s: %s", path, exc)
        return pd.DataFrame()


class LocalSource:
    name = "local"

    def read_signal_events(self, person_id=None, until=None) -> pd.DataFrame:
        df = _read_parquet_safe(_INTERIM / "signal_events.parquet")
        return _filter(df, person_id=person_id, until=until)

    def read_scored_signals(self, person_id=None, until=None) -> pd.DataFrame:
        df = _read_parquet_safe(_PROCESSED / "scored_signals.parquet")
        return _filter(df, person_id=person_id, until=until)

    def read_person_features(self) -> pd.DataFrame:
        return _read_parquet_safe(_PROCESSED / "person_features.parquet")

    def read_kg_features(self) -> pd.DataFrame:
        return _read_parquet_safe(_PROCESSED / "kg_features.parquet")

    def read_outcome_labels(self) -> pd.DataFrame:
        return _read_csv_safe(_PROCESSED / "outcome_labels.csv")

    def read_eval_metrics(self) -> pd.DataFrame:
        return _read_csv_safe(_PROCESSED / "eval_metrics.csv")

    def read_backtest_results(self) -> pd.DataFrame:
        return _read_csv_safe(_PROCESSED / "backtest_results.csv")

    def read_allocation(self) -> pd.DataFrame:
        return _read_csv_safe(_PROCESSED / "allocation.csv")

    def read_topic_momentum_metrics(self) -> pd.DataFrame:
        return _read_parquet_safe(_PROCESSED / "topic_momentum_metrics.parquet")

    def read_discovered_topics(self) -> pd.DataFrame:
        return _read_csv_safe(_PROCESSED / "discovered_topics.csv")


def _filter(df: pd.DataFrame, person_id=None, until=None) -> pd.DataFrame:
    if len(df) == 0:
        return df
    out = df
    if person_id is not None and "person_id" in out.columns:
        out = out[out["person_id"] == person_id]
    if until is not None and "timestamp" in out.columns:
        ts = pd.to_datetime(out["timestamp"], utc=True)
        until_ts = pd.Timestamp(until)
        if until_ts.tzinfo is None:
            until_ts = until_ts.tz_localize("UTC")
        out = out[ts <= until_ts]
    return out


# ---------------------------------------------------------------------------
# Supabase source
# ---------------------------------------------------------------------------


class SupabaseSource:
    name = "supabase"

    def __init__(self, url: str, anon_key: str):
        from supabase import create_client  # noqa: PLC0415

        self.client = create_client(url, anon_key)

    def _fetch_all(self, table: str, until_col: str | None = None, until=None,
                   person_id: str | None = None) -> pd.DataFrame:
        q = self.client.table(table).select("*")
        if person_id is not None:
            q = q.eq("person_id", person_id)
        if until is not None and until_col is not None:
            q = q.lte(until_col, pd.Timestamp(until).isoformat())
        # Page through results.
        all_rows: list[dict] = []
        page = 0
        page_size = 1000
        while True:
            resp = q.range(page * page_size, (page + 1) * page_size - 1).execute()
            rows = resp.data or []
            if not rows:
                break
            all_rows.extend(rows)
            if len(rows) < page_size:
                break
            page += 1
        return pd.DataFrame(all_rows)

    def read_signal_events(self, person_id=None, until=None) -> pd.DataFrame:
        return self._fetch_all("signal_events", "timestamp", until, person_id)

    def read_scored_signals(self, person_id=None, until=None) -> pd.DataFrame:
        return self._fetch_all("scored_signals", "timestamp", until, person_id)

    def read_person_features(self) -> pd.DataFrame:
        return self._fetch_all("person_features")

    def read_kg_features(self) -> pd.DataFrame:
        return self._fetch_all("kg_features")

    def read_outcome_labels(self) -> pd.DataFrame:
        return self._fetch_all("outcome_labels")

    def read_eval_metrics(self) -> pd.DataFrame:
        return self._fetch_all("eval_metrics")

    def read_backtest_results(self) -> pd.DataFrame:
        return self._fetch_all("backtest_results")

    def read_allocation(self) -> pd.DataFrame:
        return self._fetch_all("allocation")

    def read_topic_momentum_metrics(self) -> pd.DataFrame:
        return self._fetch_all("topic_momentum_metrics")

    def read_discovered_topics(self) -> pd.DataFrame:
        return self._fetch_all("discovered_topics")


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def get_source() -> DataSource:
    """Return the configured DataSource. Env-controlled via DATA_SOURCE."""
    kind = (os.environ.get("DATA_SOURCE") or "local").strip().lower()
    if kind == "local":
        return LocalSource()
    if kind == "supabase":
        url = os.environ.get("SUPABASE_URL")
        key = os.environ.get("SUPABASE_ANON_KEY")
        if not url or not key:
            logger.warning("Supabase env missing — falling back to local")
            return LocalSource()
        return SupabaseSource(url, key)
    logger.warning("unknown DATA_SOURCE=%r — defaulting to local", kind)
    return LocalSource()
