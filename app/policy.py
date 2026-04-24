"""Decide outreach mode: auto vs approve × email vs phone.

Signature: decide_outreach_mode(opp, ctx, history) -> Literal[
    'auto_email', 'approve_email', 'auto_phone', 'approve_phone'
]

Uses Claude for nuance; falls back to simple rules when LLM fails or is absent.
Respects opportunity.policy_mode:
  - 'human'  → forces approve_* mode
  - 'auto'   → Claude may return auto_*
"""
from __future__ import annotations

import json
import re
from typing import Literal

from anthropic import Anthropic

from app.config import get_settings
from app.matching import _claude_with_retry  # reuse retry wrapper


OutreachMode = Literal["auto_email", "approve_email", "auto_phone", "approve_phone"]


_client: Anthropic | None = None


def _ai() -> Anthropic:
    global _client
    if _client is None:
        key = get_settings().anthropic_api_key
        if not key:
            raise RuntimeError("ANTHROPIC_API_KEY not set")
        _client = Anthropic(api_key=key)
    return _client


POLICY_SYSTEM = """You pick the right outreach mode for a Singapore government tender opportunity.

Modes:
- "auto_email"      — low stakes, send email without human approval
- "approve_email"   — default, ask human for approval before sending
- "auto_phone"      — call is obvious, dial immediately (rare; only if user opted-in via policy_mode=auto)
- "approve_phone"   — call needed, ask for approval first (typical after N ignored emails or closing very soon)

Output STRICT JSON only:
{"mode": "<mode>", "rationale": "<one sentence>"}

Rules:
- If policy_mode == "human", pick an approve_* mode
- If closing in ≤2 days AND ignored emails ≥2, prefer approve_phone
- If closing in ≤5 days AND ignored emails ≥1, prefer approve_email (push)
- Otherwise approve_email as the safe default
- auto_* only if policy_mode == "auto" AND stakes are genuinely low"""


def _fallback(opp: dict, history: dict) -> dict:
    closing = opp.get("closing_days")
    sent = history.get("emails_sent", 0)
    replies = history.get("replies_received", 0)
    if (closing is not None and closing <= 2) and sent >= 2 and replies == 0:
        return {"mode": "approve_phone", "rationale": "urgent + ignored"}
    if opp.get("policy_mode") == "auto":
        return {"mode": "auto_email", "rationale": "opted auto"}
    return {"mode": "approve_email", "rationale": "default"}


def decide_outreach_mode(opp: dict, ctx: dict, history: dict) -> dict:
    """Return {mode: OutreachMode, rationale: str}."""
    try:
        payload = {
            "opportunity": {
                "title": opp.get("title"),
                "closing_days": opp.get("closing_days"),
                "est_value_sgd": opp.get("est_value_sgd"),
                "policy_mode": opp.get("policy_mode", "human"),
            },
            "context": {"profile": ctx.get("profile_md", "")[:500]},
            "history": history,
        }
        text = _claude_with_retry(POLICY_SYSTEM, json.dumps(payload), max_tokens=200)
        text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.MULTILINE).strip()
        data = json.loads(text)
        mode = data.get("mode")
        if mode not in {"auto_email", "approve_email", "auto_phone", "approve_phone"}:
            raise ValueError(f"invalid mode: {mode}")
        # Enforce human override even if Claude suggests auto
        if opp.get("policy_mode", "human") == "human" and mode.startswith("auto_"):
            mode = mode.replace("auto_", "approve_")
        return {"mode": mode, "rationale": data.get("rationale", "")}
    except Exception as e:
        return _fallback(opp, history) | {"rationale_error": str(e)[:80]}
