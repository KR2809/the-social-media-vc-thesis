"""Pre-compute every frontend view payload and write it to Supabase
`view_cache` as JSON, so the deployed frontend reads real data directly
from Supabase — no always-on API server, no re-implementing Python view
logic in TypeScript (single source of truth).

It calls the SAME functions the FastAPI endpoints call, so cached payloads
are byte-identical to what `uvicorn api.main` would serve.

Keys mirror the API routes:
  cohort
  timeline-bounds
  kg/cohort
  kg/ego/<person_id>           (one per cohort founder)
  founder/<person_id>          (one per cohort founder)
  yc-overlap/<YYYY-MM-DD>      (a representative set of slider dates)
  baselines/<YYYY-MM-DD>/<k>   (the real backtest dates × K in {5,10,20})

Writes via psql using $SUPABASE_DB_URL (same as load_supabase_sql.sh).

Usage:
    export SUPABASE_DB_URL='postgresql://postgres:...@db...supabase.co:5432/postgres'
    python scripts/materialise_view_cache.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime

# Reuse the EXACT functions the API endpoints use.
from analysis.kg_views import cohort_graph, ego_graph
from analysis.yc_overlap import yc_overlap
from ingestion.cohort import load_cohort

DB_URL = os.environ.get("SUPABASE_DB_URL")
K_VALUES = [5, 10, 20]
# Quarterly across the meaningful emergence window so the slider produces a
# smooth backtest readout everywhere (the frontend snaps to the nearest of
# these). run_backtest is lookahead-safe at each date.
BACKTEST_DATES = [
    f"{y}-{m:02d}-01"
    for y in range(2019, 2025)
    for m in (1, 4, 7, 10)
]
# Representative slider dates for YC overlap (pre/post Cluely X25 = 2025-04).
YC_DATES = ["2022-01-01", "2023-01-01", "2024-01-01", "2025-06-01", "2026-05-01"]


def _payloads() -> dict[str, dict]:
    """Compute every payload, keyed by the API route it mirrors."""
    out: dict[str, dict] = {}

    # --- cohort (mirror of api.main.get_cohort) ---
    members = load_cohort()
    import pandas as pd  # noqa: PLC0415

    se_path = "data/interim/signal_events.parquet"
    first_at: dict[str, str] = {}
    try:
        se = pd.read_parquet(se_path)
        g = se.groupby("person_id")["timestamp"].min()
        first_at = {k: str(v) for k, v in g.items()}
    except Exception:  # noqa: BLE001
        pass
    rows = []
    for m in members:
        pid = m.x_handle.lower()
        rows.append({
            "person_id": pid,
            "display_name": m.founder_name,
            "venture": m.venture,
            "niche": m.niche,
            "emergence_quarter": m.emergence_quarter,
            "data_score": m.data_score,
            "first_signal_at": first_at.get(pid),
        })
    out["cohort"] = {"n": len(rows), "members": rows}

    # --- timeline-bounds ---
    try:
        se = pd.read_parquet(se_path)
        ts = pd.to_datetime(se["timestamp"], utc=True)
        out["timeline-bounds"] = {
            "earliest": ts.min().isoformat(),
            "latest": ts.max().isoformat(),
            "n_signals": int(len(se)),
        }
    except Exception:  # noqa: BLE001
        out["timeline-bounds"] = {"earliest": None, "latest": None, "n_signals": 0}

    # --- kg/cohort ---
    out["kg/cohort"] = cohort_graph()

    # --- kg/ego/<id> + founder/<id> per cohort member ---
    # get_founder is the exact API handler (reads local parquet via get_source).
    from api.main import get_founder  # noqa: PLC0415

    for m in members:
        pid = m.x_handle.lower()
        out[f"kg/ego/{pid}"] = ego_graph(pid, top_signals=14)
        try:
            out[f"founder/{pid}"] = get_founder(pid, date=None, top_signals=20)
        except Exception as e:  # noqa: BLE001
            print(f"  founder {pid} failed: {e}", file=sys.stderr)

    # --- yc-overlap at representative dates ---
    for d in YC_DATES:
        out[f"yc-overlap/{d}"] = yc_overlap(as_of=d)

    # --- baselines at the real backtest dates × K ---
    from models.allocation_framework.backtest import run_backtest  # noqa: PLC0415

    for d in BACKTEST_DATES:
        try:
            df = run_backtest(backtest_dates=[datetime.fromisoformat(d)], k_values=tuple(K_VALUES))
            for k in K_VALUES:
                sub = df[df["k"] == k]
                out[f"baselines/{d}/{k}"] = {"date": d, "k": k, "rows": sub.to_dict(orient="records")}
        except Exception as e:  # noqa: BLE001
            print(f"  backtest {d} failed: {e}", file=sys.stderr)

    return out


def _sql_escape(s: str) -> str:
    return s.replace("'", "''")


def _clean(obj):
    """Recursively replace NaN/Infinity with None — Postgres JSON rejects them."""
    import math

    if isinstance(obj, float):
        return None if (math.isnan(obj) or math.isinf(obj)) else obj
    if isinstance(obj, dict):
        return {k: _clean(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_clean(v) for v in obj]
    return obj


def main() -> None:
    if not DB_URL:
        print("set SUPABASE_DB_URL", file=sys.stderr)
        sys.exit(1)
    payloads = _payloads()
    # Build one multi-row UPSERT.
    values = []
    for key, payload in payloads.items():
        j = _sql_escape(json.dumps(_clean(payload), default=str, allow_nan=False))
        values.append(f"('{_sql_escape(key)}', '{j}'::jsonb, now())")
    stmt = (
        "INSERT INTO view_cache (key, payload, computed_at) VALUES\n"
        + ",\n".join(values)
        + "\nON CONFLICT (key) DO UPDATE SET payload = EXCLUDED.payload, computed_at = EXCLUDED.computed_at;"
    )
    # Write to a temp file + psql -f (the combined SQL exceeds the OS
    # arg-length limit for -c once founder payloads with raw_text are added).
    import tempfile  # noqa: PLC0415

    with tempfile.NamedTemporaryFile("w", suffix=".sql", delete=False) as f:
        f.write(stmt)
        sql_path = f.name
    proc = subprocess.run(
        ["psql", DB_URL, "-v", "ON_ERROR_STOP=1", "-q", "-f", sql_path],
        capture_output=True, text=True,
    )
    os.unlink(sql_path)
    if proc.returncode != 0:
        print(proc.stderr, file=sys.stderr)
        sys.exit(1)
    print(f"view_cache | upserted {len(payloads)} keys")
    for k in sorted(payloads):
        print(f"  {k}")


if __name__ == "__main__":
    main()
