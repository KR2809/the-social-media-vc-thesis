"""Unified SignalEvent schema.

Every ingestion module (twitter, youtube, reddit, hn, producthunt, github)
writes to this single shape, so downstream scoring / KG / model code only
deals with one row type.

Two rules baked in:

1. Lookahead-bias discipline. Every event carries `timestamp` (when the
   post happened) and `collected_at` (when we scraped). Models that
   predict outcomes at time T may only use events with `observed_at <= T`
   where observed_at = collected_at.
2. Immutability. `SignalEvent` is frozen — once recorded, an event does
   not change. Re-collection produces a new event.

`metadata` is stored as a JSON string in parquet rather than a nested
struct: platforms carry heterogeneous metadata shapes and a union struct
across all platforms would be brittle. JSON-string keeps the parquet
schema stable; downstream code uses pandas.json_normalize.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq
from pydantic import BaseModel, ConfigDict, field_validator

ENGAGEMENT_KEYS = ("likes", "replies", "reposts", "views", "quotes")


class SignalEvent(BaseModel):
    """One observation of a person's public activity on one platform."""

    model_config = ConfigDict(frozen=True)

    signal_id: str
    person_id: str
    timestamp: datetime
    platform: str
    raw_text: str
    engagement: dict[str, int | None]
    metadata: dict[str, Any]
    collected_at: datetime
    source: str

    @field_validator("timestamp", "collected_at")
    @classmethod
    def _require_utc(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("datetimes must be timezone-aware (UTC)")
        return v.astimezone(UTC)

    @field_validator("engagement")
    @classmethod
    def _engagement_has_all_keys(cls, v: dict[str, int | None]) -> dict[str, int | None]:
        missing = set(ENGAGEMENT_KEYS) - set(v.keys())
        if missing:
            raise ValueError(f"engagement missing keys: {sorted(missing)}")
        extra = set(v.keys()) - set(ENGAGEMENT_KEYS)
        if extra:
            raise ValueError(f"engagement has unknown keys: {sorted(extra)}")
        return v


def handle_to_person_id(handle: str) -> str:
    """`@LevelsIO` → `levelsio`. Strip, drop leading @, lowercase.

    Raises ValueError on empty / whitespace-only input — a person_id
    silently becoming the empty string would cause downstream key
    collisions and corrupt the cohort.
    """
    s = handle.strip().lstrip("@").strip().lower()
    if not s:
        raise ValueError(f"handle resolves to empty person_id: {handle!r}")
    return s


_PARQUET_SCHEMA = pa.schema(
    [
        ("signal_id", pa.string()),
        ("person_id", pa.string()),
        ("timestamp", pa.timestamp("us", tz="UTC")),
        ("platform", pa.string()),
        ("raw_text", pa.string()),
        (
            "engagement",
            pa.struct(
                [
                    ("likes", pa.int64()),
                    ("replies", pa.int64()),
                    ("reposts", pa.int64()),
                    ("views", pa.int64()),
                    ("quotes", pa.int64()),
                ]
            ),
        ),
        ("metadata", pa.string()),
        ("collected_at", pa.timestamp("us", tz="UTC")),
        ("source", pa.string()),
    ]
)


def signal_events_to_parquet(events: list[SignalEvent], path: Path) -> None:
    """Write events to parquet with the canonical schema.

    Empty input writes a parquet file with the schema but zero rows —
    downstream code can always rely on the columns existing.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = {
        "signal_id": [e.signal_id for e in events],
        "person_id": [e.person_id for e in events],
        "timestamp": [e.timestamp for e in events],
        "platform": [e.platform for e in events],
        "raw_text": [e.raw_text for e in events],
        "engagement": [{k: e.engagement.get(k) for k in ENGAGEMENT_KEYS} for e in events],
        "metadata": [json.dumps(e.metadata, default=str) for e in events],
        "collected_at": [e.collected_at for e in events],
        "source": [e.source for e in events],
    }
    table = pa.Table.from_pydict(rows, schema=_PARQUET_SCHEMA)
    pq.write_table(table, path)


def parquet_to_signal_events(path: Path) -> list[SignalEvent]:
    """Inverse of `signal_events_to_parquet`. Used by tests for roundtrip."""
    table = pq.read_table(path)
    df = table.to_pylist()
    out: list[SignalEvent] = []
    for r in df:
        out.append(
            SignalEvent(
                signal_id=r["signal_id"],
                person_id=r["person_id"],
                timestamp=r["timestamp"],
                platform=r["platform"],
                raw_text=r["raw_text"],
                engagement=dict(r["engagement"]),
                metadata=json.loads(r["metadata"]),
                collected_at=r["collected_at"],
                source=r["source"],
            )
        )
    return out
