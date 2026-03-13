#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

mkdir -p logs

LOG_FILE="logs/analysis-$(date +%Y-%m-%d).log"

echo "=== Analysis Started: $(date) ===" | tee -a "$LOG_FILE"

# Activate venv if it exists
if [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
fi

# Run analysis agent, tee to log and stdout
python3 analysis_agent.py 2>&1 | tee -a "$LOG_FILE"
EXIT_CODE=${PIPESTATUS[0]}

echo "=== Analysis Finished: $(date) (exit: $EXIT_CODE) ===" | tee -a "$LOG_FILE"

exit "$EXIT_CODE"
