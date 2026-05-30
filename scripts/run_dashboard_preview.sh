#!/usr/bin/env bash
# Launch the Streamlit dashboard for the preview sandbox.
#
# Why this wrapper exists: the preview sandbox denies reading
# `.venv*/pyvenv.cfg`, so launching a venv-relative python (or the venv's
# streamlit shim, which re-execs that python) dies with
# `PermissionError: ... pyvenv.cfg`. The base interpreter has no
# pyvenv.cfg to read, so we run it directly and inject the preview venv's
# site-packages via PYTHONPATH. Streamlit + deps are installed there
# (see scripts/setup_preview_venv.sh).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

BASE_PYTHON="${PREVIEW_BASE_PYTHON:-/usr/local/bin/python3.11}"
SITE_PACKAGES="$REPO_ROOT/.venv-preview/lib/python3.11/site-packages"
PORT="${1:-8501}"

if [[ ! -d "$SITE_PACKAGES" ]]; then
  echo "preview venv missing: $SITE_PACKAGES" >&2
  echo "run scripts/setup_preview_venv.sh first" >&2
  exit 1
fi

export PYTHONPATH="$SITE_PACKAGES${PYTHONPATH:+:$PYTHONPATH}"
exec "$BASE_PYTHON" -m streamlit run dashboard/app.py \
  --server.headless true \
  --server.port "$PORT"
