# beepbop

**GeBIZ opportunity scout for creative SMEs.** Find Singapore government tenders that match your work, auto-generate pitch decks + quotes, and let a Telegram approval loop send emails / book meetings / make fallback phone calls on your behalf.

Live demo: https://beepbop.berlayar.ai

## What it does

1. **You sign in with Google** and write (or paste) an org context — what you do, rates, past work.
2. **beepbop decomposes your context into keywords** and scrapes GeBIZ for matching opportunities.
3. **Each opportunity is scored + clarifications extracted** from the tender doc by Claude.
4. **One click → pitch deck** (Genspark Claw) and **quotation sheet** (Google Sheets).
5. **Telegram ping to your phone:** "Send this pitch to the procurement officer? [Yes] [Edit] [No]".
6. Tap Yes → email goes out via `gsk`. When they reply, beepbop drafts the meeting accept + clarifications.
7. Another Telegram ping → you approve the time slot → Google Calendar invite fires.
8. **No reply after N days?** Claude decides: wait, resend, or escalate to phone call (with your approval).

## Quickstart

See [`CLAUDE.md`](./CLAUDE.md) for full commands. Short version:

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env  # fill in Google OAuth, Anthropic, Telegram
python -m app.db init && python -m app.seed
uvicorn app.main:app --reload --port 8000
```

## Issues (TDD roadmap)

Each issue in [`issues/`](./issues/) has a **Red** (failing test) + **Green** (passes when) + **Validation** (how we prove it).

## Devfolio

See [`docs/DEMO.md`](./docs/DEMO.md) for the 90-second submission storyline.
