#!/usr/bin/env bash
# Bulk-load the generated Supabase SQL files (data/interim/supabase_sql/*.sql)
# into the thesis Postgres in one shot, via psql.
#
# WHY THIS EXISTS: the small analytical tables (eval_metrics, person_features,
# kg_features, allocation, outcome_labels, backtest_results) were loaded via
# the Supabase MCP execute_sql during the 2026-05-29 data-expansion session.
# The large tables (signal_events ~2.1k, scored_signals ~2.2k, kg_nodes ~4.2k,
# kg_edges ~6.6k) are too many statements to paste through the MCP one-by-one.
# This runner loads ALL of them (idempotent UPSERTs) once you have the DB
# connection string.
#
# GET THE CONNECTION STRING: Supabase dashboard → Project Settings →
# Database → Connection string (URI). It looks like:
#   postgresql://postgres:[PASSWORD]@db.uhhcylfvoxgyrqijlxjk.supabase.co:5432/postgres
#
# USAGE:
#   1. Regenerate SQL if data changed:  python scripts/gen_supabase_sql.py
#   2. export SUPABASE_DB_URL='postgresql://postgres:...@db...supabase.co:5432/postgres'
#   3. bash scripts/load_supabase_sql.sh
set -euo pipefail

SQL_DIR="data/interim/supabase_sql"
: "${SUPABASE_DB_URL:?set SUPABASE_DB_URL to the Postgres connection string}"

if ! command -v psql >/dev/null 2>&1; then
  echo "psql not found — install postgresql client (brew install libpq)" >&2
  exit 1
fi

shopt -s nullglob
files=("$SQL_DIR"/*.sql)
echo "loading ${#files[@]} SQL files into Supabase…"
for f in "${files[@]}"; do
  echo "  → $(basename "$f")"
  psql "$SUPABASE_DB_URL" -v ON_ERROR_STOP=1 -q -f "$f"
done
echo "done — $(basename "$SQL_DIR") loaded."
