"""Policy tests — use fallback (no API key required) for determinism."""
from __future__ import annotations


def test_fallback_default_is_approve_email(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    from app.config import get_settings
    get_settings.cache_clear()
    import app.policy as p
    p._client = None
    out = p._fallback(
        opp={"title": "Minor art supplies", "closing_days": 14, "policy_mode": "human"},
        history={"emails_sent": 0, "replies_received": 0},
    )
    assert out["mode"] == "approve_email"


def test_fallback_urgent_and_ignored_picks_phone():
    from app.policy import _fallback
    out = _fallback(
        opp={"title": "Urgent", "closing_days": 2, "policy_mode": "human"},
        history={"emails_sent": 2, "replies_received": 0},
    )
    assert out["mode"] == "approve_phone"


def test_auto_mode_hint_maps_to_auto_email():
    from app.policy import _fallback
    out = _fallback(
        opp={"title": "Small job", "closing_days": 10, "policy_mode": "auto"},
        history={"emails_sent": 0, "replies_received": 0},
    )
    assert out["mode"] == "auto_email"


def test_decide_real_claude_still_enforces_human_override(monkeypatch):
    """If opp.policy_mode == 'human' and Claude returns auto_*, we must downgrade."""
    import os
    if not os.getenv("ANTHROPIC_API_KEY"):
        import pytest
        pytest.skip("needs real API key")
    from app.policy import decide_outreach_mode
    out = decide_outreach_mode(
        opp={"title": "x", "closing_days": 10, "policy_mode": "human"},
        ctx={"profile_md": "photo studio"},
        history={"emails_sent": 0, "replies_received": 0},
    )
    assert out["mode"].startswith("approve_")
