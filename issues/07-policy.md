# #7 — Claude-decided outreach policy

**Time:** 15 min
**Depends:** #5

## Red

```python
# tests/test_policy.py
def test_low_value_low_urgency_returns_approve_email():
    from app.policy import decide_outreach_mode
    mode = decide_outreach_mode(
        opp={"title": "Minor art supplies", "closing_days": 14, "est_value_sgd": 3000},
        ctx={"profile_md": "photo studio"},
        history={"emails_sent": 0, "replies_received": 0, "days_since_last_outreach": None},
    )
    assert mode == "approve_email"

def test_closing_soon_with_ignored_emails_returns_approve_phone():
    from app.policy import decide_outreach_mode
    mode = decide_outreach_mode(
        opp={"title": "Urgent", "closing_days": 2, "est_value_sgd": 50000},
        ctx={"profile_md": "photo studio"},
        history={"emails_sent": 2, "replies_received": 0, "days_since_last_outreach": 4},
    )
    assert mode == "approve_phone"

def test_auto_mode_opportunity_respects_auto_hint():
    from app.policy import decide_outreach_mode
    mode = decide_outreach_mode(
        opp={"title": "x", "closing_days": 10, "est_value_sgd": 1000, "policy_mode": "auto"},
        ctx={"profile_md": "photo studio"},
        history={"emails_sent": 0, "replies_received": 0, "days_since_last_outreach": None},
    )
    assert mode in {"auto_email", "approve_email"}  # Claude still has final call
```

## Green

1. **`app/policy.py::decide_outreach_mode(opp, ctx, history) -> Literal['auto_email','approve_email','auto_phone','approve_phone']`**:
   - Claude Sonnet 4.6 with structured output.
   - Inputs: opportunity summary + closing urgency + est value + context + outreach history (counts + recency).
   - Returns one of 4 modes + rationale (stored in outreach_log).
   - If `opp.policy_mode == 'human'` → force `approve_*` (user opt-out of autonomy per-opportunity).
   - If `opp.policy_mode == 'auto'` → Claude may return `auto_*`.
2. **Wire into `request_approval`** in #4: before sending Telegram, check mode. If `auto_email`, skip approval and fire email directly (logs rationale). If `approve_*`, current behavior.
3. **Phone escalation scenario (seeded)**: one opportunity has `mock_reply_after_seconds=null` AND a `mock_no_reply_escalate_after_seconds=20` field. Background task checks: if no reply within that window, re-invoke `decide_outreach_mode` → returns `approve_phone` → fires Telegram "Call [contact]?" → on approve, `gsk phone-call`.
4. **Config toggle**: `GET/POST /api/opportunities/:id/policy` flips `policy_mode` between `auto` and `human`. Dashboard has a tiny toggle per row.

## Validation

- Seeded escalation opportunity: approve email → email "sent" → wait 20s, no reply → Telegram buzzes with "Call [contact]? [Yes] [No]" → tap Yes → `gsk phone-call` fires (you hear your phone; or if testing, mock).
- Unit tests pass for the 3 policy scenarios.
- **Screenshot**: Telegram showing the "Call X?" escalation prompt.
