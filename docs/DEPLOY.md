# Deploy

Two paths. For hackathon demo → **Path A (Tunnel)**. For 24/7 after → **Path B (Fly)**.

## Path A — Cloudflare Tunnel (recommended for hack)

### One-time setup (~5 min)

```bash
# User-side: authorizes cloudflared for the berlayar.ai zone (opens browser)
cloudflared tunnel login

# Create tunnel + DNS route
cloudflared tunnel create beepbop
# outputs: Created tunnel beepbop with id <UUID>
#          credentials written to /Users/erniesg/.cloudflared/<UUID>.json

cloudflared tunnel route dns beepbop beepbop.berlayar.ai
# outputs: Added CNAME beepbop.berlayar.ai which will route to this tunnel <UUID>
```

### Config file

```yaml
# ~/.cloudflared/config.yml
tunnel: beepbop
credentials-file: /Users/erniesg/.cloudflared/<UUID>.json
ingress:
  - hostname: beepbop.berlayar.ai
    service: http://localhost:8000
  - service: http_status:404
```

### Run

```bash
# Terminal 1 — app
cd beepbop && source .venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000

# Terminal 2 — tunnel
cloudflared tunnel run beepbop
# OR: scripts/tunnel.sh (backgrounds both)
```

### Verify

```bash
curl https://beepbop.berlayar.ai/healthz
# {"status":"ok","version":"0.1.0"}
```

### Why Tunnel counts as "deploy"

- Cloudflare handles HTTPS (auto cert), DDoS, DNS, global edge routing.
- Your laptop is the origin; Tunnel is an outbound persistent connection (no inbound ports exposed).
- Same model Cloudflare sells as "Zero Trust" / "Cloudflare for Teams" to enterprises.
- Difference from hosted: origin is one machine, not replicated. For a 3h demo, irrelevant.

## Path B — Fly.io (post-hack 24/7)

### Dockerfile

```dockerfile
FROM python:3.11-slim

# Node for gsk
RUN apt-get update && apt-get install -y curl gnupg && \
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y nodejs && rm -rf /var/lib/apt/lists/*

# Playwright deps
RUN apt-get update && apt-get install -y \
    libglib2.0-0 libnss3 libnspr4 libdbus-1-3 libatk1.0-0 libatk-bridge2.0-0 \
    libcups2 libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 \
    libxrandr2 libgbm1 libasound2 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml ./
RUN pip install --no-cache-dir -e ".[dev]"
RUN playwright install chromium

# Install gsk globally
RUN npm install -g @genspark/cli@1.0.13

COPY . .
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### fly.toml

```toml
app = "beepbop"
primary_region = "sin"

[build]

[[services]]
  internal_port = 8000
  protocol = "tcp"
  [[services.ports]]
    port = 443
    handlers = ["tls", "http"]

[mounts]
  source = "beepbop_data"
  destination = "/app/data"

[env]
  APP_ENV = "prod"
  PUBLIC_BASE_URL = "https://beepbop.fly.dev"

# Secrets set via `fly secrets set ANTHROPIC_API_KEY=... GSK_API_KEY=... TELEGRAM_BOT_TOKEN=... GOOGLE_CLIENT_SECRET=...`
```

### Deploy

```bash
fly launch --no-deploy  # creates app
fly volumes create beepbop_data --size 1 --region sin
fly secrets set ANTHROPIC_API_KEY=... GSK_API_KEY=... TELEGRAM_BOT_TOKEN=... GOOGLE_CLIENT_ID=... GOOGLE_CLIENT_SECRET=... SECRET_KEY=...
fly deploy
fly certs add beepbop.berlayar.ai  # custom domain
```

### `gsk` auth in container

On your laptop: `gsk login` → grab the API key from `~/.genspark-tool-cli/config.json` (field `apiKey`). Set as `GSK_API_KEY` secret on Fly. The Node CLI honors this env var.

## Path C — Modal (alternative)

Same container idea, but Modal's model is function-based. Less natural fit for a long-running FastAPI server with SQLite. Skip unless you specifically want Modal's GPU/async.

## DNS

The `berlayar.ai` zone is already in your Cloudflare account (berlayar worker deployed there). `beepbop.berlayar.ai` subdomain:

- **Path A**: `cloudflared tunnel route dns beepbop beepbop.berlayar.ai` creates a CNAME to the tunnel.
- **Path B**: `fly certs add beepbop.berlayar.ai` then add CNAME `beepbop → beepbop.fly.dev` in Cloudflare DNS (proxied: off, so Fly's cert works).

Either path, the subdomain is ours.
