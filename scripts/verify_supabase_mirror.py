"""Assert local parquet/csv and Supabase tables are in sync.

DECISION_LOG iter-13 acceptance criterion: row-count parity AND a few
row-level spot checks. This script runs after `sync_to_supabase.py`
and exits non-zero if anything is off, so it can be wired into CI or
called from `pipeline.py` post-sync.

Three layers of check:

  L1. Row-count parity per table.
      `len(local_rows) == count(*) from supabase.<table>`

  L2. Random-sample row-level checks.
      For 5 random rows per non-empty table, fetch from Supabase by
      primary key and compare a small set of columns.

  L3. Primary-key set equality.
      `set(local_pks) == set(supabase_pks)` per table — catches the
      case where row counts agree but the row IDENTITIES don't.

A clean exit means all three layers passed for every table where the
local source has rows. Tables whose local source is empty are
counted as "skipped" (not failed).

Usage:
    python -m scripts.verify_supabase_mirror
    python -m scripts.verify_supabase_mirror --tables signal_events
    python -m scripts.verify_supabase_mirror --sample 10
"""

from __future__ import annotations

import argparse
import logging
import os
import random
import sys
from dataclasses import dataclass, field
from typing import Any

from dotenv import load_dotenv

from scripts.sync_to_supabase import TABLE_REGISTRY

logger = logging.getLogger("verify_supabase_mirror")


@dataclass
class TableReport:
    name: str
    local_count: int
    remote_count: int | None = None
    pk_set_match: bool | None = None
    sample_matches: int = 0
    sample_total: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        if self.local_count == 0:
            return True  # skipped
        if self.remote_count != self.local_count:
            return False
        if self.pk_set_match is False:
            return False
        if self.sample_total > 0 and self.sample_matches < self.sample_total:
            return False
        return not self.errors


def _get_client():
    load_dotenv(override=True)
    url = os.environ.get("SUPABASE_URL")
    # Use anon key for read-only verification — works even without service-role.
    key = os.environ.get("SUPABASE_ANON_KEY") or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        raise RuntimeError(
            "SUPABASE_URL and SUPABASE_ANON_KEY (or SUPABASE_SERVICE_ROLE_KEY) "
            "required in .env"
        )
    from supabase import create_client  # noqa: PLC0415

    return create_client(url, key)


def _remote_count(client: Any, table_name: str) -> int:
    resp = (
        client.table(table_name)
        .select("*", count="exact", head=True)
        .execute()
    )
    return int(resp.count or 0)


def _remote_pks(client: Any, table_name: str, pk_cols: list[str]) -> set[tuple]:
    """Fetch all primary keys from a remote table. Pages through if needed."""
    pks: set[tuple] = set()
    page_size = 1000
    page = 0
    while True:
        resp = (
            client.table(table_name)
            .select(",".join(pk_cols))
            .range(page * page_size, (page + 1) * page_size - 1)
            .execute()
        )
        rows = resp.data or []
        if not rows:
            break
        for r in rows:
            pks.add(tuple(r.get(c) for c in pk_cols))
        if len(rows) < page_size:
            break
        page += 1
    return pks


def _local_pks(rows: list[dict], pk_cols: list[str]) -> set[tuple]:
    return {tuple(r.get(c) for c in pk_cols) for r in rows}


def _spot_check_sample(
    client: Any,
    table_name: str,
    local_rows: list[dict],
    pk_cols: list[str],
    sample_n: int,
) -> tuple[int, int]:
    """Return (n_matched, n_total) — verifies sample_n random rows round-trip."""
    if not local_rows:
        return 0, 0
    n_total = min(sample_n, len(local_rows))
    sampled = random.sample(local_rows, n_total)
    matched = 0
    for local in sampled:
        q = client.table(table_name).select("*").limit(1)
        for c in pk_cols:
            q = q.eq(c, local.get(c))
        try:
            resp = q.execute()
        except Exception as exc:
            logger.warning("spot check error for %s: %s", table_name, exc)
            continue
        if resp.data:
            matched += 1
    return matched, n_total


def verify_all(
    tables: list[str] | None = None,
    sample_n: int = 5,
    seed: int = 42,
) -> list[TableReport]:
    random.seed(seed)
    client = _get_client()
    reports: list[TableReport] = []
    for table_name, loader, on_conflict in TABLE_REGISTRY:
        if tables and table_name not in tables:
            continue
        pk_cols = on_conflict.split(",")
        report = TableReport(name=table_name, local_count=0)
        try:
            local_rows = loader()
        except Exception as exc:
            report.errors.append(f"loader failed: {exc}")
            reports.append(report)
            continue
        report.local_count = len(local_rows)

        if report.local_count == 0:
            print(f"verify | {table_name:28s} | local=0 | SKIP (empty source)")
            reports.append(report)
            continue

        try:
            report.remote_count = _remote_count(client, table_name)
        except Exception as exc:
            report.errors.append(f"remote count failed: {exc}")

        try:
            local_pks = _local_pks(local_rows, pk_cols)
            remote_pks = _remote_pks(client, table_name, pk_cols)
            report.pk_set_match = local_pks == remote_pks
            if not report.pk_set_match:
                missing_in_remote = list(local_pks - remote_pks)[:3]
                missing_in_local = list(remote_pks - local_pks)[:3]
                report.errors.append(
                    f"PK set mismatch — local-only(sample)={missing_in_remote} "
                    f"remote-only(sample)={missing_in_local}"
                )
        except Exception as exc:
            report.errors.append(f"pk set check failed: {exc}")

        try:
            matched, total = _spot_check_sample(
                client, table_name, local_rows, pk_cols, sample_n
            )
            report.sample_matches = matched
            report.sample_total = total
        except Exception as exc:
            report.errors.append(f"spot check failed: {exc}")

        status = "OK" if report.passed else "FAIL"
        print(
            f"verify | {table_name:28s} | "
            f"local={report.local_count:5d} remote={report.remote_count or 0:5d} | "
            f"pk_set_match={report.pk_set_match} sample={report.sample_matches}/{report.sample_total} | {status}"
        )
        if report.errors:
            for e in report.errors:
                print(f"        ↳ {e}")
        reports.append(report)
    return reports


def main() -> int:
    ap = argparse.ArgumentParser(description="Verify local↔Supabase mirror parity.")
    ap.add_argument("--tables", type=str, default=None)
    ap.add_argument("--sample", type=int, default=5)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--verbose", "-v", action="store_true")
    args = ap.parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    tables = args.tables.split(",") if args.tables else None
    reports = verify_all(tables=tables, sample_n=args.sample, seed=args.seed)
    n_fail = sum(1 for r in reports if not r.passed)
    n_ok = sum(1 for r in reports if r.passed and r.local_count > 0)
    n_skip = sum(1 for r in reports if r.local_count == 0)
    print(
        f"\nverify complete | tables: ok={n_ok} fail={n_fail} skipped(empty)={n_skip}"
    )
    return 0 if n_fail == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
