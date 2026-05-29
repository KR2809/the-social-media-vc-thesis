"""Generate batched UPSERT SQL for the Supabase mirror.

No SUPABASE_SERVICE_ROLE_KEY is in .env, so the normal sync_to_supabase.py
(supabase-py client) can't auth. Instead we emit raw SQL that the Supabase
MCP `execute_sql` tool runs (it uses the management API, no service key).

Each table → one or more INSERT ... ON CONFLICT DO UPDATE statements,
written to data/interim/supabase_sql/<table>_<n>.sql. Values are escaped +
typed (NULL, numbers, JSONB strings, timestamps) so the SQL is valid.

Usage:
    python scripts/gen_supabase_sql.py            # all tables
    python scripts/gen_supabase_sql.py kg_nodes   # one table
"""

from __future__ import annotations

import json
import math
import pickle
import sys
from pathlib import Path

import pandas as pd

OUT = Path("data/interim/supabase_sql")
OUT.mkdir(parents=True, exist_ok=True)
BATCH = 200  # rows per INSERT statement (keeps each statement well under limits)


def sql_val(v) -> str:
    """Render one Python value as a SQL literal."""
    if v is None:
        return "NULL"
    if isinstance(v, float) and math.isnan(v):
        return "NULL"
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    if isinstance(v, (int, float)):
        return repr(v)
    if isinstance(v, (dict, list)):
        return "'" + json.dumps(v).replace("'", "''") + "'::jsonb"
    s = str(v)
    return "'" + s.replace("'", "''") + "'"


def emit(table: str, cols: list[str], rows: list[list], conflict: str) -> int:
    """Write batched INSERT...ON CONFLICT files. Returns row count."""
    if not rows:
        # Still emit a marker so we know it ran with 0 rows.
        return 0
    # Dedup on the conflict (primary-key) columns — Postgres rejects an
    # INSERT...ON CONFLICT DO UPDATE that proposes the same key twice in one
    # statement. The scored parquet can carry dup signal_ids after a
    # re-score; keep the LAST occurrence (newest wins, matching the pipeline).
    pk_idx = [cols.index(c.strip()) for c in conflict.split(",")]
    seen: dict[tuple, list] = {}
    for row in rows:
        seen[tuple(row[i] for i in pk_idx)] = row
    rows = list(seen.values())
    updates = ", ".join(f"{c}=EXCLUDED.{c}" for c in cols if c not in conflict.split(", "))
    files = 0
    for start in range(0, len(rows), BATCH):
        chunk = rows[start : start + BATCH]
        values = ",\n".join(
            "(" + ", ".join(sql_val(v) for v in row) + ")" for row in chunk
        )
        stmt = (
            f"INSERT INTO {table} ({', '.join(cols)}) VALUES\n{values}\n"
            f"ON CONFLICT ({conflict}) DO UPDATE SET {updates};"
            if updates
            else f"INSERT INTO {table} ({', '.join(cols)}) VALUES\n{values}\n"
            f"ON CONFLICT ({conflict}) DO NOTHING;"
        )
        (OUT / f"{table}_{files:03d}.sql").write_text(stmt)
        files += 1
    return len(rows)


def df_rows(df: pd.DataFrame, cols: list[str]) -> list[list]:
    out = []
    for _, r in df.iterrows():
        out.append([r[c] if c in df.columns else None for c in cols])
    return out


def gen_signal_events():
    df = pd.read_parquet("data/interim/signal_events.parquet")
    cols = ["signal_id", "person_id", "timestamp", "platform", "raw_text",
            "engagement", "metadata", "collected_at", "source"]
    rows = []
    for _, r in df.iterrows():
        eng = r.get("engagement")
        if hasattr(eng, "items"):
            eng = dict(eng)
        meta = r.get("metadata")
        if isinstance(meta, str):
            try:
                meta = json.loads(meta)
            except Exception:
                meta = {"raw": meta}
        rows.append([
            r["signal_id"], r["person_id"], str(r["timestamp"]), r["platform"],
            r.get("raw_text"), eng if isinstance(eng, dict) else None,
            meta if isinstance(meta, dict) else None,
            str(r.get("collected_at")), r.get("source"),
        ])
    return emit("signal_events", cols, rows, "signal_id")


def gen_scored_signals():
    df = pd.read_parquet("data/processed/scored_signals.parquet")
    # Push the columns that exist in the table schema.
    schema_cols = [
        "signal_id", "person_id", "platform", "timestamp", "prompt_version", "model",
        "s1_output_cadence", "s1_format_diversity", "s1_build_in_public",
        "s1_domain_coherence", "s1_original_synthesis", "s1_production_quality",
        "s2_reading_list_breadth", "s2_specialist_vs_generalist", "s2_highbrow_mix",
        "s2_cross_domain", "s2_tool_fascination", "s3_explicit_goal",
        "s3_frustration_to_idea", "s3_public_commitment", "s3_recurring_theme",
        "s3_recruitment", "s3_counterfactual_future_self", "s4_operator_proximity",
        "s4_mentor_engagement", "s4_reciprocity", "s4_community_embedding",
        "s4_sustained_relationship", "s5_verifiable_claim", "s5_claim_specificity",
        "s5_lead_time_months", "s6_topic_label", "s6_topic_specificity",
        "overall_signal_strength", "flags", "scored_at", "raw_response",
    ]
    cols = [c for c in schema_cols if c in df.columns]
    rows = []
    for _, r in df.iterrows():
        row = []
        for c in cols:
            v = r[c]
            if c in ("timestamp", "scored_at"):
                v = str(v)
            row.append(v)
        rows.append(row)
    return emit("scored_signals", cols, rows, "signal_id")


def gen_person_features():
    df = pd.read_parquet("data/processed/person_features.parquet")
    cols = [c for c in df.columns if c != "mirror_synced_at"]
    for c in ("first_signal_date", "last_signal_date"):
        if c in df.columns:
            df[c] = df[c].astype(str)
    return emit("person_features", cols, df_rows(df, cols), "person_id")


def gen_kg_features():
    df = pd.read_parquet("data/processed/kg_features.parquet")
    cols = [c for c in df.columns if c != "mirror_synced_at"]
    return emit("kg_features", cols, df_rows(df, cols), "person_id")


def gen_allocation():
    df = pd.read_csv("data/processed/allocation.csv")
    cols = [c for c in df.columns if c in (
        "person_id", "p_emerge", "kelly_raw", "kelly_fractional",
        "allocation_capped", "allocation_normalised", "dollars_allocated")]
    return emit("allocation", cols, df_rows(df, cols), "person_id")


def gen_eval_metrics():
    df = pd.read_csv("data/processed/eval_metrics.csv")
    cols = list(df.columns)
    return emit("eval_metrics", cols, df_rows(df, cols), "name")


def gen_backtest_results():
    df = pd.read_csv("data/processed/backtest_results.csv")
    cols = ["backtest_date", "strategy", "k", "n_hits", "base_rate",
            "precision_at_k", "lift_at_k"]
    cols = [c for c in cols if c in df.columns]
    return emit("backtest_results", cols, df_rows(df, cols), "backtest_date, strategy, k")


def gen_outcome_labels():
    df = pd.read_csv("data/processed/outcome_labels.csv")
    cols = [c for c in ("person_id", "emerged", "source") if c in df.columns]
    return emit("outcome_labels", cols, df_rows(df, cols), "person_id")


def gen_kg():
    G = pickle.load(open("data/processed/graph.pkl", "rb"))  # noqa: N806 - G = graph (networkx convention)
    # Nodes: all of them.
    node_rows = []
    for nid, d in G.nodes(data=True):
        kind = d.get("kind", "?")
        node_rows.append([
            nid, kind, d.get("person_id"),
            d.get("label") or d.get("topic") or d.get("person_id") or nid.split(":", 1)[-1],
        ])
    n_nodes = emit("kg_nodes", ["node_id", "kind", "person_id", "label"], node_rows, "node_id")

    # Edges: cap to person-incident edges (EXPRESSED from Person, ABOUT to
    # Topic) so the queryable graph powers ego-networks without 178k rows.
    edge_rows = []
    for src, dst, d in G.edges(data=True):
        rel = d.get("relation", "?")
        if src.startswith("Person:") or rel in ("ABOUT", "ON_PLATFORM"):
            edge_rows.append([src, dst, rel, d.get("weight")])
    n_edges = emit("kg_edges", ["src", "dst", "relation", "weight"], edge_rows, "edge_id")
    return n_nodes, n_edges


GENERATORS = {
    "signal_events": gen_signal_events,
    "scored_signals": gen_scored_signals,
    "person_features": gen_person_features,
    "kg_features": gen_kg_features,
    "allocation": gen_allocation,
    "eval_metrics": gen_eval_metrics,
    "backtest_results": gen_backtest_results,
    "outcome_labels": gen_outcome_labels,
}


def main():
    which = sys.argv[1:] or list(GENERATORS.keys()) + ["kg"]
    for name in which:
        if name == "kg":
            nn, ne = gen_kg()
            print(f"{name}: kg_nodes={nn} kg_edges={ne} (person-incident)")
        elif name in GENERATORS:
            n = GENERATORS[name]()
            print(f"{name}: {n} rows")
        else:
            print(f"unknown table: {name}")
    files = sorted(OUT.glob("*.sql"))
    print(f"wrote {len(files)} SQL files to {OUT}")


if __name__ == "__main__":
    main()
