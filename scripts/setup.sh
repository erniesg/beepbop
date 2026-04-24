#!/usr/bin/env bash
# One-shot local setup. Assumes python3.10+, node 20+, git, cloudflared installed.
set -euo pipefail

cd "$(dirname "$0")/.."

if [ ! -d .venv ]; then
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate

pip install --upgrade pip
pip install -e ".[dev]"

# Playwright browser (only needed if running scraper locally)
python -m playwright install chromium

# Init DB
python -m app.db init
python -m app.seed

if [ ! -f .env ]; then
  cp .env.example .env
  echo "⚠  Edit .env with GOOGLE_CLIENT_*, TELEGRAM_BOT_TOKEN, ANTHROPIC_API_KEY"
fi

echo "✓ setup complete. Next:"
echo "  1. Fill .env secrets (Google OAuth, Telegram bot)."
echo "  2. cloudflared tunnel login  (one-time, opens browser)"
echo "  3. ./scripts/tunnel.sh  (runs app + tunnel together)"
