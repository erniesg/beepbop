# beepbop — CLAUDE.md

> GeBIZ opportunity scout for SMEs, creators, and artists in Singapore. Takes an org context, decomposes keywords, scrapes GeBIZ, matches opportunities, generates pitch decks + quotations via Genspark Claw, routes approvals via Telegram, and executes outreach (email, phone, calendar) on approval.

Live: https://beepbop.berlayar.ai (Cloudflare Tunnel → local FastAPI)

## Stack

| Layer | Choice | Why |
|---|---|---|
| Backend | FastAPI (Python 3.10+) | Async, quick, Playwright-compatible |
| Frontend | Jinja2 + HTMX + Tailwind (CDN) | No build step, renders fast, demo-friendly |
| DB | SQLite (file) | Zero-config for hackathon; Postgres-portable schema |
| Auth | Google OAuth (authlib) | Self-serve signup, ties to demo Google account for gsk |
| Approvals | python-telegram-bot with inline keyboards | Mobile, instant, free |
| Scraper | `scripts/gebiz_contacts.py` (Playwright, outside repo) | Already built — we shell out to it |
| Artifacts & outreach | Genspark CLI `gsk` | Slides, Sheets, email (Gmail/Outlook), phone, calendar in one tool |
| LLM | Claude Sonnet 4.6 via `anthropic` SDK | Matching, keyword decomposition, policy decisions, email drafting |
| Deploy | Cloudflare Tunnel (`cloudflared`) → `beepbop.berlayar.ai` | HTTPS + public URL without hosted runtime |

## Key files

```
beepbop/
├── app/
│   ├── main.py         # FastAPI app, routes, startup
│   ├── config.py       # pydantic-settings
│   ├── db.py           # SQLite schema + helpers
│   ├── auth.py         # Google OAuth flow
│   ├── models.py       # pydantic models + DB row dataclasses
│   ├── seed.py         # loads data/*.json into DB
│   ├── matching.py     # Claude-based match scoring + keyword decomposition
│   ├── policy.py       # decide_outreach_mode: auto/approve × email/phone
│   ├── outreach.py     # email/phone/calendar orchestration (shells gsk)
│   ├── telegram_bot.py # outbound approval messages + inbound callbacks
│   ├── gsk_client.py   # wrapper around `gsk` CLI (slides, sheets, email, phone, calendar)
│   └── scraper.py      # wrapper around ../scripts/gebiz_contacts.py
├── templates/          # Jinja2 + HTMX
├── data/
│   ├── schema.sql      # DDL
│   ├── opportunities.json  # seed: 20 real GeBIZ entries (creative/design bias)
│   ├── contacts.json   # seed: procurement officers + SME collaborators
│   └── beepbop.db      # SQLite (gitignored)
├── tests/              # pytest
├── scripts/
│   ├── tunnel.sh       # cloudflared tunnel run beepbop
│   └── setup.sh        # one-shot env setup
└── issues/             # issue-by-issue TDD red/green specs
```

## Commands

```bash
# Setup
cd beepbop && python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env  # fill secrets
python -m app.db init  # creates SQLite schema
python -m app.seed     # loads demo data

# Dev
uvicorn app.main:app --reload --port 8000    # http://localhost:8000
./scripts/tunnel.sh                            # exposes https://beepbop.berlayar.ai

# Tests (TDD — write red first, implement green)
pytest -xvs tests/
pytest -xvs tests/test_matching.py::test_scores_photography_tender_higher_than_it

# Manual demo flow
open https://beepbop.berlayar.ai              # sign in with Google demo account
# dashboard → pick "Digital Artist" opportunity
# click "Match & extract clarifications" → see score + questions
# click "Generate pitch deck" → gsk returns share URL
# click "Generate quote" → gsk returns Google Sheets URL
# click "Request approval to send" → Telegram bot pings phone
# reply Yes on Telegram → email fires via gsk email send
# mock reply lands after MOCK_REPLY_SECONDS → meeting draft shown
# Telegram prompts "Book meeting?" → Yes → calendar invite fires
```

## Demo data

- **20 real GeBIZ opportunities** copied from `../tmp/gebiz_contacts_live6/gebiz-opportunities-20260423-233132.json` — keyword-matched to creative terms (artist, design, photography, video, workshop, programme).
- **Seeded contacts** are real emails extracted from those opportunities (e.g. `Clarise_AATHAR@moe.gov.sg`). **Do NOT actually send email to these in the demo** — swap recipient to the demo Google account before any `gsk email send`.
- **One seeded context** — "ernie.sg creative studio" — stored in `data/context.md`; user can edit at `/contexts/mine`.

## Architecture notes & constraints

- **Singpass blocker (known):** GeBIZ document download (tender PDFs) requires Singpass app QR auth. For the hackathon: `scraper.py` runs in public-listing mode (no login) → opportunities + contact info work, doc bodies don't. Post-hack: remote Playwright + user scans QR on phone against the remote browser screen (the Singpass QR is active for ~30s, which is enough).
- **`gsk` is a local Node CLI** — it cannot run inside a Cloudflare Worker. That's why the runtime is local FastAPI exposed via Cloudflare Tunnel.
- **Telegram approval cadence:** every outreach action (email send, phone call, calendar invite) goes through an approval unless the opportunity has `policy_mode='auto'` AND the policy engine returns an auto mode.
- **Policy engine:** `decide_outreach_mode(opportunity, context, history) -> Literal['auto_email', 'approve_email', 'auto_phone', 'approve_phone']`. Call site: any outreach kickoff. Claude sees opportunity value, closing urgency, prior response rate on this channel.

## Env vars

See `.env.example`. Required: `ANTHROPIC_API_KEY`, `GOOGLE_CLIENT_ID`/`SECRET`, `TELEGRAM_BOT_TOKEN`/`CHAT_ID`, `SECRET_KEY`. Optional: `GSK_PROJECT_ID`.

## Known quirks

- `gsk create-task --type=slides` is async — returns a job ID; poll via `gsk download` or use `gsk claw share_link` once generated.
- Google OAuth dev flow needs `http://localhost:8000/auth/google/callback` AND `https://beepbop.berlayar.ai/auth/google/callback` both authorized in GCP console.
- Cloudflare Tunnel DNS route requires `cloudflared tunnel login` first (writes `~/.cloudflared/cert.pem` for the `berlayar.ai` zone).
- SQLite journal files in `data/` — gitignored, but don't commit `beepbop.db` either.

## Tests to maintain

- `test_health.py` — sanity.
- `test_seed.py` — seed script is idempotent, 20 opportunities loaded.
- `test_matching.py` — golden-file: photography context ranks creative tenders above IT services.
- `test_policy.py` — low-value + low-urgency + no prior contact → `approve_email`; high-value + closing-in-2-days + 2 ignored emails → `approve_phone`.
- `test_telegram.py` — webhook payload fixture round-trips to status update.

## Related repos

- Scraper source: `../scripts/gebiz_contacts.py`
- Berlayar (sibling subdomain pattern): `../berlayar/` (Cloudflare Workers + Next.js + D1 — reference only, not imported)
- gsk CLI installed at repo root: `../node_modules/@genspark/cli/`
- derivativ/derivativ.ai are unrelated; share no code.
