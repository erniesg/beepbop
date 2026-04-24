# #6 — Calendar invite via second approval

**Time:** 15 min
**Depends:** #5

## Red

```python
def test_second_approval_creates_calendar_event(mock_gsk, seeded_with_meeting_draft):
    from app.outreach import book_meeting_on_approval
    book_meeting_on_approval(outreach_log_id=2, slot_index=0)
    assert mock_gsk.called_with("gsk", "google-calendar", "create", ...)
    from app.db import get_opportunity
    opp = get_opportunity(1)
    assert opp.calendar_event_id is not None
```

## Green

1. **Schema addition**: `ALTER TABLE opportunities ADD COLUMN calendar_event_id TEXT;`
2. **`app/outreach.py::book_meeting_on_approval(outreach_log_id, slot_index)`** — shells `gsk google-calendar create --title=... --start=... --end=... --attendees=...`. Stores returned event ID on the opportunity row.
3. **Telegram**: "Book [DATE] with [contact]? [Yes] [Pick other] [Decline]". Reuses `request_approval` from #4 with action prefix `book:`.
4. **Webhook handler** in `/webhooks/telegram` routes `book:{id}` → `book_meeting_on_approval`.
5. **UI**: timeline adds "Meeting scheduled — [date] [Calendar link]".

## Validation

- After meeting draft appears (from #5), click "Request approval to book" → Telegram pings phone.
- Tap Yes → Google Calendar event appears on demo account's calendar within 5s.
- Opportunity page timeline shows "Meeting scheduled — 29 Apr 2026 14:00" with clickable calendar link.
- **Screenshot**: (a) timeline, (b) the calendar event in Google Calendar.
- **Gate D**: user runs the full chain context → opp → deck → email → reply → meeting, confirms all 7 timeline stages present.
