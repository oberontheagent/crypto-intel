#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

mkdir -p logs

LOG_FILE="logs/collector-$(date +%Y-%m-%d).log"

echo "=== Feed Collection Started: $(date) ===" | tee -a "$LOG_FILE"

# Load .env if present
if [ -f ".env" ]; then
    set -a; source .env; set +a
fi

# Activate venv if it exists
if [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
fi

# Run collector, tee to log and stdout
python3 feed_collector.py 2>&1 | tee -a "$LOG_FILE"
EXIT_CODE=${PIPESTATUS[0]}

echo "=== Feed Collection Finished: $(date) (exit: $EXIT_CODE) ===" | tee -a "$LOG_FILE"

exit "$EXIT_CODE"
