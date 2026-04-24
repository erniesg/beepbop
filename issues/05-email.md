# #5 — Email send + mock reply + meeting draft

**Time:** 25 min
**Depends:** #3, #4

## Red

```python
def test_approved_outreach_fires_gsk_email_send(mock_gsk, seeded_outreach_approved):
    from app.outreach import send_approved_email
    send_approved_email(outreach_log_id=seeded_outreach_approved.id)
    assert mock_gsk.called_with("gsk", "email", "send", ...)
    from app.db import get_outreach
    assert get_outreach(seeded_outreach_approved.id).status == "sent"

def test_mock_reply_injection_after_timer(seeded):
    from app.outreach import schedule_mock_reply
    # opportunity has mock_reply_after_seconds=2
    schedule_mock_reply(opportunity_id=1, outreach_log_id=1)
    import time; time.sleep(3)
    from app.db import list_outreach
    replies = [o for o in list_outreach(1) if o.direction == "in"]
    assert len(replies) >= 1
    assert "available" in replies[0].body.lower()

def test_draft_meeting_after_reply(seeded_with_reply):
    from app.outreach import draft_meeting_from_reply
    draft = draft_meeting_from_reply(opportunity_id=1)
    assert "proposed_slots" in draft
    assert len(draft["proposed_slots"]) >= 1
```

## Green

1. **`app/outreach.py`**:
   - `send_approved_email(outreach_log_id)` — looks up body/recipient; shells `gsk email send --to=... --subject=... --body=... --content_type=text/html --skip_confirmation=true`. For demo, **recipient is overridden to the demo Google account** regardless of seeded contact email (guardrail against emailing real officers).
   - `schedule_mock_reply(opportunity_id, outreach_log_id)` — if opportunity has `mock_reply_after_seconds`, schedules a background task that inserts an `outreach_log(direction='in', status='replied', body=<canned>)` after the delay. Canned body: "Thanks for reaching out. Are you available on [DATE1] or [DATE2] for a short discussion?"
   - `draft_meeting_from_reply(opportunity_id)` — Claude reads the reply body, extracts proposed dates, drafts accept message with 2 `proposed_slots`.
2. **Wire to #4**: when webhook sets `status='approved'`, background task calls `send_approved_email`. On `send_approved_email` completion, calls `schedule_mock_reply`.
3. **UI** — opportunity page timeline shows: Approval requested → Approved → Email sent → Reply received → Meeting draft (collapsible card with proposed slots + "Request approval to book" button).

## Validation

- Approve on Telegram (from #4) → real email lands in `ernie@...` demo inbox within 5s.
- After `MOCK_REPLY_SECONDS` (default 10), mock reply appears on the opportunity page timeline.
- Meeting draft card renders with 2 proposed slots extracted from the reply.
- **Screenshot**: opportunity page timeline showing full chain up through meeting draft.
