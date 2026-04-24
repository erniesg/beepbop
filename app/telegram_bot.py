"""Telegram bot — outbound approval prompts + inbound webhook callbacks.

Usage:
    # Outbound: from anywhere
    from app.telegram_bot import send_approval
    send_approval(outreach_id=42, text="Send email to Alice?", actions={"approve": "YES", "reject": "NO"})

    # Inbound: POST /webhooks/telegram (wired in main.py)
"""
from __future__ import annotations

import json
from typing import Any

import httpx

from app.config import get_settings

TG_API = "https://api.telegram.org"


def _api_url(path: str) -> str:
    from app.app_settings import telegram_bot_token
    token = telegram_bot_token()
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN not set")
    return f"{TG_API}/bot{token}/{path}"


def send_text(chat_id: str | None, text: str) -> dict:
    from app.app_settings import telegram_chat_id as _tg_chat
    chat_id = chat_id or _tg_chat()
    if not chat_id:
        raise RuntimeError("no chat_id available (set TELEGRAM_CHAT_ID)")
    r = httpx.post(
        _api_url("sendMessage"),
        json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"},
        timeout=15,
    )
    r.raise_for_status()
    return r.json()


def send_approval(
    outreach_id: int,
    text: str,
    actions: dict[str, str] | None = None,
    chat_id: str | None = None,
) -> dict:
    """Send a message with inline-keyboard buttons.

    `actions` keys become callback_data prefixes: e.g. {"approve": "YES"} produces
    a button labelled "YES" that sends callback_data "approve:<outreach_id>".
    """
    actions = actions or {"approve": "✅ YES", "reject": "❌ NO"}
    from app.app_settings import telegram_chat_id as _tg_chat
    chat_id = chat_id or _tg_chat()
    if not chat_id:
        raise RuntimeError("TELEGRAM_CHAT_ID not set")

    keyboard = [
        [{"text": label, "callback_data": f"{action}:{outreach_id}"}]
        for action, label in actions.items()
    ]
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown",
        "reply_markup": {"inline_keyboard": keyboard},
    }
    r = httpx.post(_api_url("sendMessage"), json=payload, timeout=15)
    r.raise_for_status()
    body = r.json()
    return {"message_id": body["result"]["message_id"], "raw": body}


def set_webhook(public_url: str) -> dict:
    r = httpx.post(
        _api_url("setWebhook"),
        json={"url": f"{public_url.rstrip('/')}/webhooks/telegram"},
        timeout=15,
    )
    return r.json()


def answer_callback(callback_query_id: str, text: str = "") -> None:
    httpx.post(
        _api_url("answerCallbackQuery"),
        json={"callback_query_id": callback_query_id, "text": text},
        timeout=10,
    )


def parse_callback(payload: dict) -> dict | None:
    """Extract {action, outreach_id, callback_id, chat_id, message_id} or None."""
    cq = payload.get("callback_query")
    if not cq:
        return None
    data = cq.get("data", "")
    if ":" not in data:
        return None
    action, id_str = data.split(":", 1)
    try:
        outreach_id = int(id_str)
    except ValueError:
        return None
    return {
        "action": action,
        "outreach_id": outreach_id,
        "callback_id": cq.get("id"),
        "chat_id": cq.get("message", {}).get("chat", {}).get("id"),
        "message_id": cq.get("message", {}).get("message_id"),
    }


def parse_message(payload: dict) -> dict | None:
    """Extract {command, args, text, chat_id, user_id} from a text message, or None."""
    msg = payload.get("message")
    if not msg:
        return None
    text = (msg.get("text") or "").strip()
    if not text:
        return None
    parts = text.split(maxsplit=1)
    cmd = parts[0]
    args = parts[1] if len(parts) > 1 else ""
    return {
        "command": cmd if cmd.startswith("/") else None,
        "text": text,
        "args": args,
        "chat_id": msg.get("chat", {}).get("id"),
        "user_id": msg.get("from", {}).get("id"),
    }


def send_opportunity_card(chat_id: str | int, opp: dict) -> dict:
    """Send an opportunity summary with inline action buttons."""
    score_badge = f"*{opp['match_score']:.2f}*" if opp.get("match_score") is not None else "?"
    text = (
        f"*{opp['title']}*\n"
        f"_{opp.get('agency','')}_\n"
        f"closing {opp.get('closing','')}\n"
        f"match: {score_badge}"
    )
    if opp.get("match_rationale"):
        text += f"\n\n_{opp['match_rationale'][:200]}_"

    keyboard = [
        [
            {"text": "📝 Generate deck", "callback_data": f"deck:{opp['id']}"},
            {"text": "💰 Generate quote", "callback_data": f"quote:{opp['id']}"},
        ],
        [{"text": "✉️ Send proposal", "callback_data": f"propose:{opp['id']}"}],
    ]
    r = httpx.post(
        _api_url("sendMessage"),
        json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown",
              "reply_markup": {"inline_keyboard": keyboard}},
        timeout=15,
    )
    r.raise_for_status()
    return r.json()
