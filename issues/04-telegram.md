# #4 — Telegram approval loop

**Time:** 30 min
**Depends:** #1
**Blocker:** user creates bot via @BotFather, provides `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID`

## Red

```python
# tests/test_telegram.py
def test_request_approval_sends_message(mock_tg):
    from app.telegram_bot import request_approval
    msg_id = request_approval(outreach_log_id=1, text="Send email to Alice?", options=["YES", "NO", "EDIT"])
    assert msg_id
    assert mock_tg.sent[0]["reply_markup"]["inline_keyboard"][0][0]["text"] == "YES"

def test_webhook_callback_updates_outreach_status(client, seeded_outreach):
    payload = {
        "callback_query": {
            "id": "cb1",
            "from": {"id": 12345},
            "data": f"approve:{seeded_outreach.id}",
            "message": {"message_id": 99}
        }
    }
    r = client.post("/webhooks/telegram", json=payload)
    assert r.status_code == 200
    from app.db import get_outreach
    assert get_outreach(seeded_outreach.id).status == "approved"
```

## Green

1. **`app/telegram_bot.py`**:
   - `send_text(chat_id, text)` — raw Bot API call via `httpx`.
   - `request_approval(outreach_log_id, text, options=['YES','NO','EDIT']) -> message_id` — sends message with `reply_markup.inline_keyboard`. Callback data format: `"{action}:{outreach_log_id}"` where action ∈ `{approve, reject, edit}`.
   - Sets Telegram webhook on startup via `setWebhook` to `{PUBLIC_BASE_URL}/webhooks/telegram` (only if `PUBLIC_BASE_URL` is HTTPS).
2. **`POST /webhooks/telegram`**:
   - Parses `callback_query.data`, maps to `outreach_log_id` + action.
   - Updates `outreach_log.status = 'approved' | 'rejected'`.
   - Acknowledges callback via `answerCallbackQuery`.
   - Triggers next step via background task (e.g. if `approved` + `channel=email`, call `outreach.send_email`).
3. **UI** — on opportunity page, "Request approval" button → `POST /api/opportunities/:id/outreach/request-approval` → creates `outreach_log(status='pending_approval')`, calls `request_approval`. UI polls status every 2s via HTMX and reflects change.

## Validation

- Click "Request approval" on opportunity → your phone buzzes within 3s with inline keyboard "Send email to [contact]? YES / NO / EDIT".
- Tap YES on phone → within 3s the opportunity page flips to "Approved ✓".
- **Screenshot**: Telegram message on phone (you take this), and the opportunity page showing "Approved".
- **Gate C**: user confirms phone got the message and tap-back worked.
