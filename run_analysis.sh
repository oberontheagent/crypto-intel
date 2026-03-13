#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

mkdir -p logs

LOG_FILE="logs/analysis-$(date +%Y-%m-%d).log"

echo "=== Analysis Started: $(date) ===" | tee -a "$LOG_FILE"

# Load .env if present
if [ -f ".env" ]; then
    set -a; source .env; set +a
fi

# Activate venv if it exists
if [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
fi

# Run analysis agent, tee to log and stdout
python3 analysis_agent.py 2>&1 | tee -a "$LOG_FILE"
EXIT_CODE=${PIPESTATUS[0]}

echo "=== Analysis Finished: $(date) (exit: $EXIT_CODE) ===" | tee -a "$LOG_FILE"

# Auto-commit latest report to GitHub
if [ "$EXIT_CODE" -eq 0 ]; then
    echo "Pushing latest report to GitHub..." | tee -a "$LOG_FILE"
    git add reports/latest-report.md reports/report-*.md 2>&1 | tee -a "$LOG_FILE" || true
    git diff --cached --quiet || \
        git commit -m "report: intel briefing $(date -u '+%Y-%m-%d %H:%M UTC')" 2>&1 | tee -a "$LOG_FILE"
    git push origin main 2>&1 | tee -a "$LOG_FILE" || echo "Git push failed (non-fatal)" | tee -a "$LOG_FILE"
fi

exit "$EXIT_CODE"
