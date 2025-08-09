#!/bin/bash
set -euo pipefail

while true; do
  echo "[CLEANUP_LOOP] Running cleanup script..."
  /home/brandon/flaccy/scripts/run_cleanup.sh
  echo "[CLEANUP_LOOP] Cleanup finished. Sleeping for 10 minutes."
  sleep 600
done
