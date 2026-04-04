#!/usr/bin/env bash
# ArcaneaClaw Local Demo — Quick Start
# Usage: bash demo.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== ArcaneaClaw E2E Demo ==="
echo ""

# Check .env
if [ ! -f .env ]; then
  echo "ERROR: No .env file found. Copy .env.example to .env and fill in values."
  echo "  Required: SUPABASE_URL, SUPABASE_SERVICE_KEY, GEMINI_API_KEY"
  exit 1
fi

# Check demo media
MEDIA_COUNT=$(find demo-media -type f \( -name "*.webp" -o -name "*.jpg" -o -name "*.png" \) 2>/dev/null | wc -l)
if [ "$MEDIA_COUNT" -eq 0 ]; then
  echo "WARNING: No images in demo-media/. Copying guardian heroes..."
  mkdir -p demo-media
  cp ../apps/web/public/guardians/*-hero.webp demo-media/ 2>/dev/null || true
  MEDIA_COUNT=$(find demo-media -type f | wc -l)
fi
echo "Found $MEDIA_COUNT demo images."

# Create data dirs
mkdir -p data/staging data/processed data/logs

# Check Python
if ! command -v python &> /dev/null; then
  echo "ERROR: Python not found. Install Python 3.11+."
  exit 1
fi

# Create venv if needed
if [ ! -d .venv ]; then
  echo "Creating virtual environment..."
  python -m venv .venv
fi

# Activate
source .venv/Scripts/activate 2>/dev/null || source .venv/bin/activate

# Install deps
echo "Installing dependencies..."
pip install -q -r requirements.txt

# Run with local config
echo ""
echo "Starting ArcaneaClaw daemon..."
echo "  Config: config.local.yaml"
echo "  Health: http://localhost:8080/health"
echo "  Pipeline interval: 60s (demo mode)"
echo ""
echo "Press Ctrl+C to stop."
echo "==========================================="
echo ""

ARCANEA_CLAW_CONFIG="$SCRIPT_DIR/config.local.yaml" python engine/daemon.py
