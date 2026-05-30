#!/usr/bin/env bash
# Create the preview venv used by the Streamlit dashboard preview server.
#
# The preview sandbox cannot read venv pyvenv.cfg, so the dashboard is run
# via base python + PYTHONPATH (see scripts/run_dashboard_preview.sh). This
# script just materialises a venv with streamlit + the project installed,
# whose site-packages that wrapper points at. Re-run after dependency bumps.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

BASE_PYTHON="${PREVIEW_BASE_PYTHON:-/usr/local/bin/python3.11}"

"$BASE_PYTHON" -m venv .venv-preview
.venv-preview/bin/python -m pip install -q --upgrade pip
.venv-preview/bin/python -m pip install -q -e .
echo "preview venv ready at .venv-preview"
