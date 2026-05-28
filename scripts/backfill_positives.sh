#!/usr/bin/env bash
# Drive per-handle Wayback backfill in ISOLATED processes.
#
# Wayback throttles per-client in a batch loop, so each handle runs in a
# fresh `python` process (no carried-over connection state) with a hard
# timeout (macOS has no `timeout`, so we use a watchdog kill) and a gap
# between handles to let the throttle window reset.
#
# Usage: bash scripts/backfill_positives.sh [per_handle_timeout_sec] [gap_sec]

set -u

PY=".venv/bin/python"
TIMEOUT="${1:-360}"   # 6 min hard cap per handle
GAP="${2:-30}"        # rest between handles

# The 13 X-native positives missing signals (cohort x_handles).
HANDLES=(
  levelsio yongfook tdinh_me noahwbragg monicalent Nicolascole77
  thibaultlell tomjacquesson im_roy_lee herfirst100k KateBour
  damengchen simplrads
)

run_one() {
  local handle="$1"
  echo ">>> [$(date +%H:%M:%S)] backfilling ${handle} (timeout ${TIMEOUT}s)"
  # Launch the isolated per-handle job; filter snscrape noise.
  "$PY" scripts/backfill_one_handle.py "$handle" --max-signals 120 \
    2>&1 | grep -E "RESULT|ERROR|Wayback|tweets|wayback" &
  local job_pid=$!

  # Watchdog: kill the job if it exceeds TIMEOUT.
  ( sleep "$TIMEOUT"; kill -TERM "$job_pid" 2>/dev/null; ) &
  local wd_pid=$!

  wait "$job_pid" 2>/dev/null
  kill "$wd_pid" 2>/dev/null  # cancel watchdog if job finished first
  wait "$wd_pid" 2>/dev/null
}

echo "=== Wayback positive backfill: ${#HANDLES[@]} handles ==="
for h in "${HANDLES[@]}"; do
  run_one "$h"
  sleep "$GAP"
done
echo "=== backfill driver complete ==="
