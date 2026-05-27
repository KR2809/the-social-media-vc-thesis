"""Verbatim HTTP payload archive.

Every collector that fetches over the network calls :func:`persist` once
per HTTP round-trip. The payload bytes are stored gzipped on disk under a
SHA-256-addressed path, and one row per fetch is appended to a parquet
index. This is what the thesis reproducibility appendix points at.

Storage layout::

    data/raw_archive/
    ├── <source>/                 # 'wayback' | 'reddit' | 'youtube' | 'hn' | 'ph'
    │   └── <YYYY-MM>/
    │       └── <sha[:2]>/
    │           └── <sha>.json.gz
    └── _index.parquet

The gz file holds a small JSON envelope with the base64-encoded body plus
provenance metadata (URL, fetch method, status code, fetched_at, the
handle the fetch belongs to). Base64 means the envelope is fully
human-readable when unzipped — convenient for the appendix.

Idempotence: writing the same body twice yields a single gz file but two
index rows. The duplicate index row preserves the fetched_at timestamp,
so re-fetch events are traceable.

Concurrency: the index parquet is read-modify-write under an ``flock``
on a sidecar lock file. Volume is small (~hundreds of rows per cohort
run) so the round-trip cost is fine. If this ever bottlenecks, swap to
a JSONL append + roll-up to parquet at end-of-run.

Handle plumbing: rather than thread a ``handle`` argument through every
internal call site of every collector, each ``collect_*()`` entry point
sets :data:`current_handle` (a :class:`contextvars.ContextVar`) on entry
and resets it on exit. ``persist()`` reads it as a fallback when the
caller doesn't pass ``handle=`` explicitly.
"""

from __future__ import annotations

import base64
import contextlib
import contextvars
import gzip
import hashlib
import json
import logging
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterator

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from ingestion import config

logger = logging.getLogger(__name__)


# Headers we keep on every persisted payload. Everything else is dropped —
# we don't want auth tokens, cookies, internal request IDs etc. landing
# in a checked-in (well, gitignored, but visible) reproducibility appendix.
_ALLOWED_HEADERS = frozenset({"content-type", "etag", "last-modified"})


# ---------------------------------------------------------------------------
# Handle context
# ---------------------------------------------------------------------------

current_handle: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "raw_archive_current_handle", default=None
)


@contextlib.contextmanager
def handle_scope(handle: str | None) -> Iterator[None]:
    """Bind ``current_handle`` for the duration of a ``with`` block.

    Usage::

        with raw_archive.handle_scope(handle):
            ... do all fetches for this handle ...
    """
    token = current_handle.set(handle)
    try:
        yield
    finally:
        current_handle.reset(token)


# ---------------------------------------------------------------------------
# Index parquet
# ---------------------------------------------------------------------------

_INDEX_COLUMNS = [
    "sha256",
    "source",
    "url",
    "response_status",
    "fetch_method",
    "handle",
    "fetched_at",
    "size_bytes",
    "content_type",
    "path",
]


def _index_path() -> Path:
    return config.RAW_ARCHIVE_DIR / "_index.parquet"


def _lock_path() -> Path:
    return config.RAW_ARCHIVE_DIR / "_index.lock"


@contextlib.contextmanager
def _index_lock() -> Iterator[None]:
    """Cross-process advisory lock around the index parquet."""
    import fcntl  # POSIX-only; the project targets macOS/Linux

    config.RAW_ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    lock = _lock_path()
    with open(lock, "w") as fh:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


def _append_index_row(row: dict) -> None:
    """Append one row to the index parquet, creating it if missing.

    Read-modify-write inside the file lock. Volume is small enough that
    we don't need a streaming writer; correctness on parallel runs is
    worth the cost.
    """
    with _index_lock():
        path = _index_path()
        # Coerce row keys to the canonical column order; missing keys → None.
        ordered = {col: row.get(col) for col in _INDEX_COLUMNS}
        new_df = pd.DataFrame([ordered])
        if path.exists():
            try:
                existing = pq.read_table(path).to_pandas()
                combined = pd.concat([existing, new_df], ignore_index=True)
            except Exception as exc:  # pragma: no cover — corrupt index recovery
                logger.warning(
                    "raw_archive index unreadable (%s); rewriting from scratch",
                    exc,
                )
                combined = new_df
        else:
            combined = new_df
        # Stable string dtype for the parquet schema; pyarrow infers
        # otherwise but mixed-None columns can flip dtypes between writes.
        for col in ("sha256", "source", "url", "fetch_method", "handle",
                    "content_type", "path"):
            if col in combined.columns:
                combined[col] = combined[col].astype("string")
        # Status + size as nullable Int64.
        for col in ("response_status", "size_bytes"):
            if col in combined.columns:
                combined[col] = combined[col].astype("Int64")
        # Timestamp normalised to ISO 8601 UTC.
        combined["fetched_at"] = combined["fetched_at"].astype("string")

        path.parent.mkdir(parents=True, exist_ok=True)
        pq.write_table(pa.Table.from_pandas(combined, preserve_index=False), path)


# ---------------------------------------------------------------------------
# Persist
# ---------------------------------------------------------------------------


def _filter_headers(headers: dict | None) -> dict[str, str]:
    if not headers:
        return {}
    out: dict[str, str] = {}
    for k, v in headers.items():
        if not isinstance(k, str):
            continue
        if k.lower() in _ALLOWED_HEADERS:
            out[k.lower()] = str(v)
    return out


def _payload_path(source: str, sha: str, fetched_at: datetime) -> Path:
    return (
        config.RAW_ARCHIVE_DIR
        / source
        / fetched_at.strftime("%Y-%m")
        / sha[:2]
        / f"{sha}.json.gz"
    )


def persist(
    *,
    source: str,
    url: str,
    response_body: bytes,
    response_status: int,
    response_headers: dict | None = None,
    fetch_method: str,
    handle: str | None = None,
    extra_metadata: dict | None = None,
) -> str:
    """Persist one HTTP fetch.

    Returns the SHA-256 of the response body. Callers are free to ignore
    the return value — it's exposed for diagnostics and tests.

    When ``config.RAW_ARCHIVE_ENABLED`` is false the SHA is still computed
    and returned, but no files are written. This lets the existing
    collector tests run without polluting the test environment with
    archive files.

    Idempotence: if a payload with this SHA already exists on disk, the
    gz file is left alone but a new index row is still appended (so
    re-fetch counts stay accurate).

    Oversize: bodies larger than ``config.RAW_ARCHIVE_MAX_BYTES`` are
    skipped — index row written with ``path=None``, body dropped, warning
    logged.

    ``extra_metadata`` lets a caller add a few extra fields to the JSON
    envelope (used by ``producthunt_collect`` to record the GraphQL
    request body alongside the response). It does NOT affect the index.
    """
    if not isinstance(response_body, (bytes, bytearray)):
        raise TypeError(
            f"response_body must be bytes, got {type(response_body).__name__}"
        )
    response_body = bytes(response_body)
    sha = hashlib.sha256(response_body).hexdigest()

    if not config.RAW_ARCHIVE_ENABLED:
        return sha

    if handle is None:
        handle = current_handle.get()

    fetched_at = datetime.now(UTC)
    size = len(response_body)
    filtered_headers = _filter_headers(response_headers)
    content_type = filtered_headers.get("content-type")

    payload_path = _payload_path(source, sha, fetched_at)
    rel_path: str | None = str(payload_path.relative_to(config.RAW_ARCHIVE_DIR))

    if size > config.RAW_ARCHIVE_MAX_BYTES:
        logger.warning(
            "raw_archive: payload too large (%d bytes > %d); skipping body "
            "but recording index row [source=%s sha=%s url=%s]",
            size, config.RAW_ARCHIVE_MAX_BYTES, source, sha[:12], url,
        )
        rel_path = None
    else:
        payload_path.parent.mkdir(parents=True, exist_ok=True)
        if payload_path.exists():
            # Idempotent — body already on disk, just count the re-fetch.
            logger.debug(
                "raw_archive: payload exists, skipping write [sha=%s url=%s]",
                sha[:12], url,
            )
        else:
            envelope: dict = {
                "sha256": sha,
                "source": source,
                "url": url,
                "response_status": response_status,
                "response_headers": filtered_headers,
                "fetch_method": fetch_method,
                "handle": handle,
                "fetched_at": fetched_at.isoformat(),
                "size_bytes": size,
                "content_type": content_type,
                "body_b64": base64.b64encode(response_body).decode("ascii"),
            }
            if extra_metadata:
                envelope["extra"] = extra_metadata
            # tmp + rename for crash safety; otherwise a SIGKILL mid-write
            # leaves a half-written gz that re-runs can't detect.
            tmp = payload_path.with_suffix(payload_path.suffix + ".tmp")
            with gzip.open(tmp, "wb") as gz:
                gz.write(json.dumps(envelope).encode("utf-8"))
            os.replace(tmp, payload_path)

    _append_index_row(
        {
            "sha256": sha,
            "source": source,
            "url": url,
            "response_status": response_status,
            "fetch_method": fetch_method,
            "handle": handle,
            "fetched_at": fetched_at.isoformat(),
            "size_bytes": size,
            "content_type": content_type,
            "path": rel_path,
        }
    )
    return sha


# ---------------------------------------------------------------------------
# Reporting helpers (used by scripts/raw_archive_report.py)
# ---------------------------------------------------------------------------


def read_index() -> pd.DataFrame:
    """Return the index as a DataFrame, or an empty one if no index exists."""
    path = _index_path()
    if not path.exists():
        return pd.DataFrame(columns=_INDEX_COLUMNS)
    return pq.read_table(path).to_pandas()


def summarise(df: pd.DataFrame) -> dict:
    """Compute the aggregates that the report script renders to Markdown."""
    if df.empty:
        return {
            "total_fetches": 0,
            "unique_sha": 0,
            "dedupe_rate": 0.0,
            "total_bytes": 0,
            "per_source": [],
            "per_handle": [],
        }
    total_fetches = int(len(df))
    unique_sha = int(df["sha256"].nunique())
    dedupe_rate = (
        (total_fetches - unique_sha) / total_fetches if total_fetches else 0.0
    )

    # `size_bytes` is per-fetch; for dedupe-aware bytes we sum once per SHA.
    bytes_per_sha = df.drop_duplicates("sha256")["size_bytes"].fillna(0)
    total_bytes = int(bytes_per_sha.sum())

    per_source = (
        df.groupby("source", dropna=False)
        .agg(
            fetches=("sha256", "count"),
            unique_sha=("sha256", "nunique"),
        )
        .reset_index()
        .sort_values("fetches", ascending=False)
        .to_dict("records")
    )
    # bytes per source — sum unique SHA per source so dupes don't double-count.
    bytes_per_source = (
        df.drop_duplicates(["source", "sha256"])
        .groupby("source", dropna=False)["size_bytes"]
        .sum()
        .fillna(0)
        .astype(int)
        .to_dict()
    )
    for row in per_source:
        row["bytes"] = int(bytes_per_source.get(row["source"], 0))

    per_handle = (
        df.groupby("handle", dropna=False)
        .agg(
            fetches=("sha256", "count"),
            unique_sha=("sha256", "nunique"),
        )
        .reset_index()
        .sort_values("fetches", ascending=False)
        .to_dict("records")
    )

    return {
        "total_fetches": total_fetches,
        "unique_sha": unique_sha,
        "dedupe_rate": float(dedupe_rate),
        "total_bytes": total_bytes,
        "per_source": per_source,
        "per_handle": per_handle,
    }
