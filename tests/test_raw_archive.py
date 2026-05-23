"""Tests for ingestion.raw_archive."""

from __future__ import annotations

import base64
import gzip
import importlib
import json
import os
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq
import pytest


# ---------------------------------------------------------------------------
# Fixture: redirect raw_archive into a tmp dir and force-enable it.
#
# `raw_archive` reads RAW_ARCHIVE_DIR / RAW_ARCHIVE_ENABLED from
# `ingestion.config` at call time (not import time, after this module's
# module-level lookups), so monkeypatching the config module is enough.
# ---------------------------------------------------------------------------


@pytest.fixture
def archive_env(tmp_path: Path, monkeypatch):
    from ingestion import config, raw_archive

    monkeypatch.setattr(config, "RAW_ARCHIVE_DIR", tmp_path / "raw_archive")
    monkeypatch.setattr(config, "RAW_ARCHIVE_ENABLED", True)
    monkeypatch.setattr(config, "RAW_ARCHIVE_MAX_BYTES", 10_000_000)

    # The contextvar default is None; ensure we don't leak handle state
    # across tests.
    token = raw_archive.current_handle.set(None)
    yield {"config": config, "raw_archive": raw_archive, "tmp_path": tmp_path}
    raw_archive.current_handle.reset(token)


def _read_index(config_mod) -> pd.DataFrame:
    path = config_mod.RAW_ARCHIVE_DIR / "_index.parquet"
    if not path.exists():
        return pd.DataFrame()
    return pq.read_table(path).to_pandas()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_persist_writes_gz_and_index(archive_env):
    raw_archive = archive_env["raw_archive"]
    cfg = archive_env["config"]

    body = b"hello world"
    sha = raw_archive.persist(
        source="wayback",
        url="https://example.test/x",
        response_body=body,
        response_status=200,
        response_headers={"Content-Type": "text/html", "X-Secret": "nope"},
        fetch_method="requests",
        handle="dvassallo",
    )

    # sha is hex of sha256(body)
    import hashlib
    assert sha == hashlib.sha256(body).hexdigest()

    # Exactly one gz file under data/raw_archive/wayback/<YYYY-MM>/<sha[:2]>/
    gz_files = list(cfg.RAW_ARCHIVE_DIR.rglob("*.json.gz"))
    assert len(gz_files) == 1, f"expected 1 gz file, got {gz_files}"
    gz = gz_files[0]
    assert gz.name == f"{sha}.json.gz"
    assert gz.parent.name == sha[:2]
    assert gz.parent.parent.parent.name == "wayback"

    # Envelope content
    with gzip.open(gz, "rb") as fh:
        envelope = json.loads(fh.read().decode("utf-8"))
    assert envelope["sha256"] == sha
    assert envelope["source"] == "wayback"
    assert envelope["url"] == "https://example.test/x"
    assert envelope["response_status"] == 200
    assert envelope["fetch_method"] == "requests"
    assert envelope["handle"] == "dvassallo"
    assert envelope["size_bytes"] == len(body)
    assert envelope["content_type"] == "text/html"
    assert base64.b64decode(envelope["body_b64"]) == body
    # Header filter removed the secret
    assert "x-secret" not in envelope["response_headers"]
    assert envelope["response_headers"]["content-type"] == "text/html"

    # Index has one row with expected fields
    idx = _read_index(cfg)
    assert len(idx) == 1
    row = idx.iloc[0]
    assert row["sha256"] == sha
    assert row["source"] == "wayback"
    assert row["url"] == "https://example.test/x"
    assert int(row["response_status"]) == 200
    assert row["fetch_method"] == "requests"
    assert row["handle"] == "dvassallo"
    assert int(row["size_bytes"]) == len(body)
    assert row["content_type"] == "text/html"
    assert row["path"] is not None and row["path"].endswith(f"{sha}.json.gz")


def test_persist_idempotent_on_same_sha(archive_env):
    raw_archive = archive_env["raw_archive"]
    cfg = archive_env["config"]

    body = b"same payload twice"
    sha1 = raw_archive.persist(
        source="hn", url="https://h.test/1", response_body=body,
        response_status=200, fetch_method="requests", handle="alice",
    )
    sha2 = raw_archive.persist(
        source="hn", url="https://h.test/1", response_body=body,
        response_status=200, fetch_method="requests", handle="alice",
    )
    assert sha1 == sha2

    # Only one gz on disk
    gz_files = list(cfg.RAW_ARCHIVE_DIR.rglob("*.json.gz"))
    assert len(gz_files) == 1

    # But two index rows
    idx = _read_index(cfg)
    assert len(idx) == 2
    assert (idx["sha256"] == sha1).all()


def test_persist_handles_max_bytes_skip(archive_env, monkeypatch):
    raw_archive = archive_env["raw_archive"]
    cfg = archive_env["config"]

    monkeypatch.setattr(cfg, "RAW_ARCHIVE_MAX_BYTES", 100)

    body = b"x" * 200  # > 100-byte cap
    sha = raw_archive.persist(
        source="youtube", url="https://yt.test/big", response_body=body,
        response_status=200, fetch_method="requests", handle="bob",
    )

    # No gz file written
    gz_files = list(cfg.RAW_ARCHIVE_DIR.rglob("*.json.gz"))
    assert len(gz_files) == 0

    # Index row exists, with path=None and size_bytes=200
    idx = _read_index(cfg)
    assert len(idx) == 1
    row = idx.iloc[0]
    assert row["sha256"] == sha
    assert int(row["size_bytes"]) == 200
    # path is None (pandas string dtype stores it as <NA>)
    assert pd.isna(row["path"])


def test_persist_filters_headers(archive_env):
    """Only content-type, etag, last-modified survive — every other header
    is stripped, lowercased, and absent from the envelope on disk."""
    raw_archive = archive_env["raw_archive"]
    cfg = archive_env["config"]

    raw_archive.persist(
        source="ph", url="https://ph.test/q", response_body=b"{}",
        response_status=200,
        response_headers={
            "Content-Type": "application/json",
            "ETag": "abc123",
            "Last-Modified": "Wed, 01 Jan 2025 00:00:00 GMT",
            "Authorization": "Bearer SECRET_TOKEN",
            "Set-Cookie": "session=leak",
            "X-Internal-Trace-Id": "trace-leak",
        },
        fetch_method="gql", handle="carol",
    )
    gz_files = list(cfg.RAW_ARCHIVE_DIR.rglob("*.json.gz"))
    assert len(gz_files) == 1
    with gzip.open(gz_files[0], "rb") as fh:
        envelope = json.loads(fh.read().decode("utf-8"))
    headers = envelope["response_headers"]
    assert set(headers.keys()) == {"content-type", "etag", "last-modified"}
    assert headers["content-type"] == "application/json"
    assert headers["etag"] == "abc123"


def test_persist_disabled(archive_env, monkeypatch):
    """RAW_ARCHIVE_ENABLED=False → SHA returned but nothing written."""
    raw_archive = archive_env["raw_archive"]
    cfg = archive_env["config"]
    monkeypatch.setattr(cfg, "RAW_ARCHIVE_ENABLED", False)

    sha = raw_archive.persist(
        source="reddit", url="https://r.test/p", response_body=b"abc",
        response_status=200, fetch_method="praw", handle="dave",
    )
    import hashlib
    assert sha == hashlib.sha256(b"abc").hexdigest()

    # Nothing on disk
    assert not (cfg.RAW_ARCHIVE_DIR / "_index.parquet").exists()
    assert list(cfg.RAW_ARCHIVE_DIR.rglob("*.json.gz")) == []


def test_handle_scope_sets_contextvar(archive_env):
    """handle_scope() provides the handle to persist() without an explicit kwarg."""
    raw_archive = archive_env["raw_archive"]
    cfg = archive_env["config"]

    with raw_archive.handle_scope("scoped_handle"):
        raw_archive.persist(
            source="wayback", url="https://w.test/s", response_body=b"x",
            response_status=200, fetch_method="requests",
        )
    # And outside the scope, the default reverts
    raw_archive.persist(
        source="wayback", url="https://w.test/t", response_body=b"y",
        response_status=200, fetch_method="requests",
    )

    idx = _read_index(cfg).sort_values("url").reset_index(drop=True)
    assert idx.loc[idx["url"] == "https://w.test/s", "handle"].iloc[0] == "scoped_handle"
    # The second row's handle is NaN (no scope, no kwarg)
    assert pd.isna(idx.loc[idx["url"] == "https://w.test/t", "handle"].iloc[0])


def test_summarise_aggregates_correctly(archive_env):
    """summarise() rolls up totals, per-source, per-handle."""
    raw_archive = archive_env["raw_archive"]

    raw_archive.persist(
        source="hn", url="u1", response_body=b"a", response_status=200,
        fetch_method="requests", handle="alice",
    )
    raw_archive.persist(
        source="hn", url="u2", response_body=b"bb", response_status=200,
        fetch_method="requests", handle="alice",
    )
    # Same body again — counts as a re-fetch (dedupe)
    raw_archive.persist(
        source="hn", url="u1", response_body=b"a", response_status=200,
        fetch_method="requests", handle="alice",
    )
    raw_archive.persist(
        source="wayback", url="u3", response_body=b"ccc", response_status=200,
        fetch_method="requests", handle="bob",
    )

    df = raw_archive.read_index()
    summary = raw_archive.summarise(df)

    assert summary["total_fetches"] == 4
    assert summary["unique_sha"] == 3  # 'a' deduped
    assert 0.24 < summary["dedupe_rate"] < 0.26  # 1/4 == 0.25
    # Total bytes counts each unique SHA once: 1 + 2 + 3 = 6
    assert summary["total_bytes"] == 6

    # per-source rollup
    by_source = {r["source"]: r for r in summary["per_source"]}
    assert by_source["hn"]["fetches"] == 3
    assert by_source["hn"]["unique_sha"] == 2
    assert by_source["wayback"]["fetches"] == 1
    assert by_source["wayback"]["unique_sha"] == 1

    by_handle = {r["handle"]: r for r in summary["per_handle"]}
    assert by_handle["alice"]["fetches"] == 3
    assert by_handle["bob"]["fetches"] == 1
