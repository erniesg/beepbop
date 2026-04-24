"""Runtime app_settings (DB-backed, overrides .env)."""
from __future__ import annotations

import shutil
import subprocess

from app.config import get_settings as _env
from app.db import conn

_KEYS = (
    "GOOGLE_CLIENT_ID",
    "GOOGLE_CLIENT_SECRET",
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_CHAT_ID",
)


def get(key: str) -> str | None:
    with conn() as c:
        row = c.execute("SELECT value FROM app_settings WHERE key=?", (key,)).fetchone()
        return row["value"] if row else None


def put(key: str, value: str, user_id: int | None = None) -> None:
    with conn() as c:
        c.execute(
            "INSERT INTO app_settings (key, value, updated_by) VALUES (?, ?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=CURRENT_TIMESTAMP, updated_by=excluded.updated_by",
            (key, value, user_id),
        )
    _invalidate_caches(key)


def _invalidate_caches(key: str) -> None:
    # Force OAuth + Telegram clients to re-init on next use
    if key.startswith("GOOGLE_"):
        import app.auth as _a
        _a._oauth = None
    # telegram_bot reads live from effective(), nothing to invalidate


def effective(key: str) -> str:
    """DB value wins, else env. Never raises."""
    val = get(key)
    if val is not None:
        return val
    env = _env()
    return getattr(env, key.lower(), "") or ""


def google_client_id() -> str:
    return effective("GOOGLE_CLIENT_ID")


def google_client_secret() -> str:
    return effective("GOOGLE_CLIENT_SECRET")


def telegram_bot_token() -> str:
    return effective("TELEGRAM_BOT_TOKEN")


def telegram_chat_id() -> str:
    return effective("TELEGRAM_CHAT_ID")


def gsk_status() -> dict:
    """Check whether `gsk` is authenticated by calling `gsk me`."""
    bin_path = shutil.which("gsk") or "/Users/erniesg/code/erniesg/node_modules/.bin/gsk"
    try:
        p = subprocess.run([bin_path, "me", "--output", "json"], capture_output=True, text=True, timeout=10)
        if p.returncode == 0:
            return {"ok": True, "raw": p.stdout.strip()[:200]}
        return {"ok": False, "error": (p.stderr or p.stdout).strip()[:200]}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


def summary() -> dict:
    """Everything the /settings page needs to render."""
    env = _env()
    return {
        "google": {
            "configured": bool(google_client_id() and google_client_secret()),
            "client_id_masked": _mask(google_client_id()),
            "redirect_uri": f"{env.public_base_url}/auth/google/callback",
            "source": "db" if get("GOOGLE_CLIENT_ID") else "env",
        },
        "telegram": {
            "configured": bool(telegram_bot_token()),
            "token_masked": _mask(telegram_bot_token()),
            "chat_id": telegram_chat_id() or "(not set)",
            "source": "db" if get("TELEGRAM_BOT_TOKEN") else "env",
        },
        "anthropic": {
            "configured": bool(env.anthropic_api_key),
            "key_masked": _mask(env.anthropic_api_key),
            "model": env.anthropic_model,
            "source": "env",
        },
        "gsk": gsk_status(),
    }


def _mask(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 12:
        return "•" * len(value)
    return value[:6] + "…" + value[-4:]
