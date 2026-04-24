# #1 — Scaffold + deploy + Google OAuth self-serve signup

**Time:** 25 min
**Depends:** —
**Blockers:** `cloudflared tunnel login` (user), Google OAuth credentials (user creates client in GCP console), `ANTHROPIC_API_KEY`

## Red (failing tests — write first)

```python
# tests/test_health.py
def test_healthz_returns_ok(client):
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "version": "0.1.0"}

def test_root_unauthenticated_redirects_to_login(client):
    r = client.get("/", follow_redirects=False)
    assert r.status_code in (302, 307)
    assert "/login" in r.headers["location"]

def test_login_page_has_google_button(client):
    r = client.get("/login")
    assert r.status_code == 200
    assert "Sign in with Google" in r.text

# tests/test_auth.py
def test_google_callback_creates_user_on_first_login(client, monkeypatch):
    # mock authlib OAuth token exchange
    monkeypatch.setattr("app.auth.exchange_code", lambda code: {
        "email": "demo@example.com", "name": "Demo", "picture": "..."
    })
    r = client.get("/auth/google/callback?code=fake&state=...", follow_redirects=False)
    assert r.status_code in (302, 307)
    assert r.headers["location"] == "/"
    # user row exists
    from app.db import get_user_by_email
    u = get_user_by_email("demo@example.com")
    assert u is not None
```

## Green (implementation)

1. **`app/main.py`** — FastAPI app with routes:
   - `GET /healthz` → `{"status": "ok", "version": "0.1.0"}`
   - `GET /` → if no session → redirect `/login`; else render `dashboard.html` (empty shell for now).
   - `GET /login` → render `login.html` with Google button → `/auth/google/start`.
   - `GET /auth/google/start` → authlib redirect to Google.
   - `GET /auth/google/callback` → exchange code → upsert user → set session cookie → redirect `/`.
   - `POST /logout` → clear session → redirect `/login`.
2. **`app/auth.py`** — authlib OAuth2 client. Scopes: `openid email profile`. Redirect URI: `{PUBLIC_BASE_URL}/auth/google/callback`.
3. **`app/db.py`** — SQLite schema:
   ```sql
   CREATE TABLE users (
     id INTEGER PRIMARY KEY AUTOINCREMENT,
     email TEXT NOT NULL UNIQUE,
     name TEXT,
     picture TEXT,
     created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
   );
   ```
   Init via `python -m app.db init`.
4. **Session**: FastAPI `SessionMiddleware` with `SECRET_KEY`, 7-day TTL, signed cookie. Stores `{"user_id": int}`.
5. **`templates/`** — `base.html` (Tailwind CDN + HTMX), `login.html`, `dashboard.html` (placeholder: "Signed in as X").
6. **Deploy**:
   ```bash
   cloudflared tunnel create beepbop
   # writes ~/.cloudflared/<UUID>.json
   cat > ~/.cloudflared/config.yml <<EOF
   tunnel: beepbop
   credentials-file: /Users/erniesg/.cloudflared/<UUID>.json
   ingress:
     - hostname: beepbop.berlayar.ai
       service: http://localhost:8000
     - service: http_status:404
   EOF
   cloudflared tunnel route dns beepbop beepbop.berlayar.ai
   cloudflared tunnel run beepbop  # background
   ```

## Validation

- `curl https://beepbop.berlayar.ai/healthz` → `{"status":"ok","version":"0.1.0"}`.
- Open `https://beepbop.berlayar.ai` in browser → redirects to `/login` → click "Sign in with Google" → complete OAuth with demo Google account → land on dashboard with "Signed in as <email>".
- **Screenshot**: the dashboard post-login.
- **Gate A**: user reviews the URL + screenshot, confirms OAuth works.
