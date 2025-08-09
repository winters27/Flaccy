#!/bin/bash
# Wrapper to run the Flaccy artifact cleanup script and append output to logs/cleanup.log
# Intended to be run from cron (user-level).

set -euo pipefail

REPO_DIR="/home/brandon/flaccy"
INSTANCE_DIR="${REPO_DIR}/instance"
LOG_DIR="${REPO_DIR}/logs"
SCRIPT="${REPO_DIR}/app/cleanup.py"

mkdir -p "${LOG_DIR}"

# Defaults: TTL 10 minutes, max total 20 GiB
TTL_MINUTES=10
MAX_BYTES=$((20 * 1024 * 1024 * 1024))

export PYTHONUNBUFFERED=1

echo "[$(date -u +'%Y-%m-%dT%H:%M:%SZ')] Starting cleanup (ttl=${TTL_MINUTES}m, max=$((${MAX_BYTES})) bytes)" >> "${LOG_DIR}/cleanup.log"
python3 "${SCRIPT}" --instance-path "${INSTANCE_DIR}" --ttl-minutes "${TTL_MINUTES}" --max-bytes "${MAX_BYTES}" >> "${LOG_DIR}/cleanup.log" 2>&1 || echo "[$(date -u +'%Y-%m-%dT%H:%M:%SZ')] Cleanup script exited with non-zero status" >> "${LOG_DIR}/cleanup.log"
echo "[$(date -u +'%Y-%m-%dT%H:%M:%SZ')] Cleanup finished" >> "${LOG_DIR}/cleanup.log"
