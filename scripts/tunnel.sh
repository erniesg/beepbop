#!/usr/bin/env bash
# Run beepbop locally + expose via Cloudflare Tunnel.
# Prereqs: cloudflared logged in (~/.cloudflared/cert.pem), tunnel named "beepbop" created,
#          DNS route beepbop.berlayar.ai → tunnel configured.
set -euo pipefail

cd "$(dirname "$0")/.."

export $(grep -v '^#' .env | xargs) 2>/dev/null || true

# Config guardrail
if [ ! -f ~/.cloudflared/cert.pem ]; then
  echo "ERROR: ~/.cloudflared/cert.pem missing. Run: cloudflared tunnel login"
  exit 1
fi

if ! cloudflared tunnel info beepbop >/dev/null 2>&1; then
  echo "Creating tunnel 'beepbop'..."
  cloudflared tunnel create beepbop
  cloudflared tunnel route dns beepbop beepbop.berlayar.ai
fi

TUNNEL_ID=$(cloudflared tunnel info beepbop | awk '/ID:/ {print $2}')
if [ -z "$TUNNEL_ID" ]; then
  echo "ERROR: could not resolve tunnel ID"
  exit 1
fi

# Write tunnel config
cat > ~/.cloudflared/config.yml <<EOF
tunnel: $TUNNEL_ID
credentials-file: $HOME/.cloudflared/$TUNNEL_ID.json
ingress:
  - hostname: beepbop.berlayar.ai
    service: http://localhost:8000
  - service: http_status:404
EOF

echo "Starting uvicorn on :8000 (background)..."
nohup uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload > /tmp/beepbop-uvicorn.log 2>&1 &
UVICORN_PID=$!
echo "uvicorn pid: $UVICORN_PID"

echo "Starting cloudflared tunnel (foreground)..."
echo "  → https://beepbop.berlayar.ai"
trap "kill $UVICORN_PID 2>/dev/null" EXIT
cloudflared tunnel run beepbop
