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

# Auto-commit latest condensed data + updated PUCK.md to GitHub
if [ "$EXIT_CODE" -eq 0 ]; then
    echo "Updating PUCK.md..." | tee -a "$LOG_FILE"
    python3 update_puck.py 2>&1 | tee -a "$LOG_FILE" || echo "PUCK.md update failed (non-fatal)" | tee -a "$LOG_FILE"

    echo "Pushing latest data to GitHub..." | tee -a "$LOG_FILE"
    git add data/latest-feeds-condensed.json data/latest-feeds.json PUCK.md 2>&1 | tee -a "$LOG_FILE" || true
    git diff --cached --quiet || \
        git commit -m "data: feed update $(date -u '+%Y-%m-%d %H:%M UTC')" 2>&1 | tee -a "$LOG_FILE"
    git push origin main 2>&1 | tee -a "$LOG_FILE" || echo "Git push failed (non-fatal)" | tee -a "$LOG_FILE"
fi

exit "$EXIT_CODE"
