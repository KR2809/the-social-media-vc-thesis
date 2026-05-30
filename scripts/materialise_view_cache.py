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
BACKTEST_DATES = ["2022-01-01", "2023-01-01", "2024-01-01"]
K_VALUES = [5, 10, 20]
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
    for m in members:
        pid = m.x_handle.lower()
        out[f"kg/ego/{pid}"] = ego_graph(pid, top_signals=14)

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


def main() -> None:
    if not DB_URL:
        print("set SUPABASE_DB_URL", file=sys.stderr)
        sys.exit(1)
    payloads = _payloads()
    # Build one multi-row UPSERT.
    values = []
    for key, payload in payloads.items():
        j = _sql_escape(json.dumps(payload, default=str))
        values.append(f"('{_sql_escape(key)}', '{j}'::jsonb, now())")
    stmt = (
        "INSERT INTO view_cache (key, payload, computed_at) VALUES\n"
        + ",\n".join(values)
        + "\nON CONFLICT (key) DO UPDATE SET payload = EXCLUDED.payload, computed_at = EXCLUDED.computed_at;"
    )
    proc = subprocess.run(
        ["psql", DB_URL, "-v", "ON_ERROR_STOP=1", "-q", "-c", stmt],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        print(proc.stderr, file=sys.stderr)
        sys.exit(1)
    print(f"view_cache | upserted {len(payloads)} keys")
    for k in sorted(payloads):
        print(f"  {k}")


if __name__ == "__main__":
    main()
