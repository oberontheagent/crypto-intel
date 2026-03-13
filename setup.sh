#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== Crypto Intel Pipeline Setup ==="

# Create venv if not exists
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
else
    echo "Virtual environment already exists."
fi

# Install dependencies
echo "Installing Python dependencies..."
.venv/bin/pip install --upgrade pip -q
.venv/bin/pip install feedparser requests beautifulsoup4 openai python-dateutil -q

# Create directories
mkdir -p data logs reports
echo "Created data/, logs/, reports/ directories."

# Make shell scripts executable
chmod +x run_crypto_intel.sh run_analysis.sh setup.sh
echo "Made shell scripts executable."

echo ""
echo "=== Setup Complete ==="
echo "Next steps:"
echo "  1. Set OPENAI_API_KEY:  export OPENAI_API_KEY='your-key'"
echo "  2. Collect feeds:       ./run_crypto_intel.sh"
echo "  3. Generate report:     ./run_analysis.sh"
