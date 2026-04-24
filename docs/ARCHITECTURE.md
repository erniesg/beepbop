# Architecture

## One picture

```
                      ┌────────────────────────────────────┐
                      │  User's phone (Telegram)           │
                      │    YES / NO inline keyboards        │
                      └──────────────┬─────────────────────┘
                                     │ webhook callbacks
                                     ▼
┌─────────────────────┐    ┌──────────────────────────────────┐
│ beepbop.berlayar.ai │───▶│  FastAPI (app/main.py)           │
│ (Cloudflare Tunnel) │    │   routes: /healthz /auth/*        │
└─────────────────────┘    │           /  /opportunities/:id   │
                           │           /api/outreach/*          │
                           │           /webhooks/telegram       │
                           └─────┬──────────────┬───────────────┘
                                 │              │
                   ┌─────────────┘              └────────────┐
                   ▼                                         ▼
         ┌──────────────────┐                    ┌─────────────────┐
         │  SQLite          │                    │  Background     │
         │  beepbop.db      │                    │  tasks (asyncio)│
         │  users contexts  │                    │  scrape, reply, │
         │  opportunities   │                    │  escalation     │
         │  contacts        │                    └──────┬──────────┘
         │  artifacts       │                           │
         │  outreach_log    │                           ▼
         │  scrape_jobs     │                  ┌────────────────────┐
         └──────────────────┘                  │  gsk CLI (Node)    │
                   ▲                           │  • create-task     │
                   │                           │     --type=slides  │
                   │                           │  • sheets create   │
                   │                           │  • email send      │
                   │                           │  • phone-call      │
         ┌─────────┴──────────┐                │  • google-calendar │
         │  scripts/          │                └────────────────────┘
         │  gebiz_contacts.py │                           │
         │  (Playwright)      │                           │
         └─────────┬──────────┘                  ┌────────┴─────────┐
                   │                             │ Genspark Claw VM │
                   ▼                             │ Gmail / Outlook  │
         ┌────────────────────┐                  │ Google Sheets    │
         │  GeBIZ (public)    │                  │ Google Calendar  │
         │  opportunities,    │                  │ Phone gateway    │
         │  contacts          │                  └──────────────────┘
         └────────────────────┘

                   ┌─────────────────────┐
                   │  Anthropic API      │
                   │  Claude Sonnet 4.6  │◀──── matching, clarifications,
                   └─────────────────────┘       keyword decomp, policy,
                                                 email drafting
```

## Data flow for a single opportunity

```
1. user signs in (Google OAuth) → user row
2. user writes context → ctx row → Claude decomposes → keywords stored
3. user clicks "Scrape" → scripts/gebiz_contacts.py runs (public, no Singpass)
   → opportunities + contacts loaded into DB
4. bg task scores each new opportunity against context (Claude)
5. user opens opportunity detail
   → clarifications extracted on demand (Claude)
   → user clicks "Generate deck" → gsk create-task --type=slides → artifact row
   → user clicks "Generate quote" → gsk sheets create → artifact row
6. user clicks "Request approval"
   → policy engine decides mode (Claude)
   → if approve_email: Telegram inline keyboard → webhook → approval
   → if auto_email: skip approval
7. on approval, gsk email send
   → mock reply after MOCK_REPLY_SECONDS (demo crutch)
   → Claude drafts meeting accept
8. user approves meeting slot via Telegram
   → gsk google-calendar create → event_id stored
9. (escalation case) no reply after N sec → policy re-evaluates → approve_phone
   → Telegram "Call X?" → gsk phone-call
```

## Why these choices

- **SQLite, not Postgres/Supabase**: 3h hack; single-user demo; migration to Postgres = sed-replace the connection string later.
- **HTMX, not React**: zero build step, renders on server, polling is a `hx-trigger="every 2s"` attribute. Saves 20 min of setup.
- **`gsk` over native integrations**: four separate OAuth apps (Gmail, Sheets, Calendar, plus our own) → too much for 3h. `gsk` is one auth.
- **Telegram over WhatsApp**: Twilio WA Sandbox requires account + join phrase; Telegram bot is 5 min via BotFather.
- **Cloudflare Tunnel over hosted**: zero container building; laptop is fine for a demo; Fly is documented for after.
- **Claude Sonnet 4.6 over Haiku for policy**: policy is a decision-maker; precision > cost.

## Failure modes & guardrails

- **Real emails accidentally sent**: `DEMO_MODE=true` forces all recipient overrides to demo Google account. Seeded officer emails are display-only.
- **`gsk` quota**: deck gen is the heavy call. Add simple per-user daily cap (5 decks / 10 sheets).
- **Singpass blocker**: scraper runs public mode for demo. Document download flagged as M9 (remote browser + phone-scanned QR).
- **Claude 5xx**: matching falls back to simple TF-IDF (string overlap) with a UI banner.
- **Telegram webhook unreachable**: fallback to UI approval button (poll shows same state).
