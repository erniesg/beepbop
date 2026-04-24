# beepbop — agent handoff

> You are picking up a live hackathon project at the Push to Prod Hackathon (Genspark + Claude, Singapore, 2026-04-24). Everything below is current as of the handoff moment. Read this file once, then `ls issues/` for the TDD red/green specs.

## URLs

- **Live app**: https://beepbop.berlayar.ai
- **GitHub**: https://github.com/erniesg/beepbop
- **Telegram bot**: `@beepbopsg_bot`
- **Devfolio hackathon**: slug `push-to-prod` (MCP registered in `.claude/settings.local.json`)

## What this project is

GeBIZ opportunity scout for Singapore creative SMEs. Real ask from a real user:

> "SMEs miss government tenders because searching GeBIZ + writing pitches + chasing clarifications is a full-time admin job. Let Claude + Genspark do it, with a Telegram approval loop on every external action."

Core loop: scrape → match → generate deck+quote → Telegram-approved email → (mock) reply → Telegram-approved calendar invite.

Differentiator vs naive "AI for tenders": the **compliance agent** infers unstated prereqs (MOE Registered Instructor, WSQ ACTA, Police/ECDC checks, NAC AEP panel) via Singapore domain knowledge.

## Current state — what works right now

| Layer | State |
|---|---|
| FastAPI + HTMX + SQLite scaffold | ✅ Live |
| Google OAuth self-serve sign-in | ✅ Code complete (Client ID/Secret pasteable at /settings; not yet filled) |
| Dev bypass login | ✅ `/dev/fake-login?email=<any>` works when APP_ENV=dev |
| 42 real GeBIZ opportunities seeded + scored | ✅ All scored 0.0-0.97 by Claude |
| Clarifications extraction | ✅ Claude, 2-5 per opp |
| Compliance/prerequisites agent | ✅ Claude w/ Singapore-specific domain prompt |
| Policy engine (4 outreach modes × human override) | ✅ Tested |
| Telegram bot: /start /help /list /opp /context /remember /forget /scrape | ✅ Live, HTML parse mode |
| /remember Claude-parsed with clarification loop for ambiguous inputs | ✅ Returns `needs_clarification` shape with inline-keyboard options |
| /remember handles preferences (preferred_name, pronouns, tone, signoff) | ✅ Injected into all downstream Claude prompts |
| gsk slides + sheets via `create_task` | ✅ **Just fixed** — required flags: `--task_name --query --instructions` |
| gsk email (Gmail) send + mock reply + meeting draft | ✅ Code complete, untested E2E |
| gsk calendar create via second Telegram approval | ✅ Code complete, untested E2E |
| gsk phone-call | ❌ **Plus/Pro only — user is on free plan**. Gate is at the tool level; no bypass via Claw. Options: upgrade, mock for demo, or skip (demo is email-only) |
| Cloudflare Tunnel deploy | ✅ `beepbop.berlayar.ai` → `localhost:8000` via named tunnel `beepbop` |
| In-repo scraper (Playwright) | ✅ Copied from `../scripts/gebiz_contacts.py` to `app/scraper_core.py`; async-thread-wrapped |
| Live scrape button on dashboard | ⚠️  Jobs stuck at `running` (Playwright + Chrome inside asyncio thread stalls). Seed data is plenty for demo. |

## Known blockers / must-know-to-not-break

1. **Docker listens on port 8000 on this machine.** `cloudflared` must target `http://127.0.0.1:8000` NOT `http://localhost:8000` — Docker wins the IPv6 race for "localhost" and returns its own 404. Tunnel config is already correct; don't change it.
2. **Anthropic 529 Overloaded is common.** `app/matching.py::_claude_with_retry` does exp backoff on 429/503/529. Don't remove it.
3. **Telegram Markdown parser is fragile.** Many strings contain underscores (rate keys, agency names) or markdown table syntax that breaks legacy Markdown. Default to HTML parse mode; `send_text()` auto-falls-back to plain text on 400.
4. **Anthropic max_tokens=600 truncated prereq JSON** → changed to 1500. Don't reduce.
5. **gsk `create_task` signature** (checked today via `gsk help create_task`): `slides|sheets|docs|...` positional, then `--task_name`, `--query`, `--instructions` (the last is required at runtime but not in help output).
6. **`parse_remember_fact` whitelist** — must include "preference". Missed this the first time and silently fell through to profile fallback.

## Current tasks

- `#5 pending` — Live gsk email send round-trip (code complete, awaiting user tap on Telegram)
- `#6 pending` — Live calendar invite round-trip (same — chain after email)
- `#8 in_progress` — Devfolio submission (draft payload at `/tmp/beepbop-submission.json`, 3 screenshots already uploaded to Devfolio S3; **do NOT fire `createHackathonProject` without explicit user green light per memory `feedback_never_auto_submit`**)
- `#11 pending (stretch)` — Closed opps + pricing advisor (spec'd in `issues/11-*.md`)
- `#15 pending (stretch)` — Supabase + pgvector memory layer + MCP exposure (spec'd in `issues/12-*.md`)

## Hard user preferences (live memory these conversations generated)

- Never auto-submit to external platforms (Devfolio, real email, phone) without fresh per-call approval. Drafts count as submissions. See `~/.claude/projects/-Users-erniesg-code-erniesg/memory/feedback_never_auto_submit.md`.
- Don't echo leaked secrets back in plaintext responses; flag + remind rotation. Multiple leaks this session: Anthropic key, Devfolio MCP key, Claw remote-desktop password, Telegram bot token. See `memory/feedback_redact_leaked_secrets.md`.
- User is female (she/her). If you ever saw me suggest "they/them" in examples, those were hypothetical; no assumption was made.

## File tour (you only need these)

```
beepbop/
├── CLAUDE.md          # stack, commands, demo flow
├── README.md
├── HANDOFF.md         # you are here
├── issues/            # TDD red/green specs per feature (#1-#12)
├── app/
│   ├── main.py        # FastAPI app + all routes + Telegram webhook handler
│   ├── matching.py    # Claude prompts: score, clarifications, prereqs, parse_remember_fact, advise_pricing (stub)
│   ├── policy.py      # 4-mode outreach decision + human override
│   ├── outreach.py    # generate_deck/quote, email approve+send, mock reply, book_meeting
│   ├── telegram_bot.py  # send_text, send_approval, send_opportunity_card, parse_callback, parse_message
│   ├── gsk_client.py  # subprocess wrappers around gsk CLI
│   ├── app_settings.py  # runtime settings override (.env → DB fallback chain)
│   ├── auth.py        # Google OAuth (authlib)
│   ├── db.py          # SQLite + helpers
│   ├── seed.py        # load 19 real opps from ../tmp/gebiz_contacts_live6/*.json
│   ├── scraper.py     # async wrapper around scraper_core
│   └── scraper_core.py  # copied from ../scripts/gebiz_contacts.py, exports run_search()
├── templates/         # base, login, dashboard, opportunity, settings (Jinja2 + HTMX + Tailwind CDN)
├── data/
│   ├── schema.sql     # SQLite DDL (source of truth)
│   ├── beepbop.db     # gitignored
│   ├── opportunities.json  # seed (real scrape output)
│   └── context.md     # seed org context
├── tests/             # 22 tests, ~17 reliably pass (5 skip without ANTHROPIC_API_KEY)
└── scripts/tunnel.sh  # starts uvicorn + cloudflared
```

## How to run (local)

```bash
cd beepbop
source .venv/bin/activate
export ANTHROPIC_API_KEY=$(grep '^ANTHROPIC_API_KEY=' .env | cut -d= -f2)
uvicorn app.main:app --host 127.0.0.1 --port 8000 &
# tunnel already running under supervisor: cloudflared tunnel run beepbop
pytest tests/ --tb=line    # expects 17 pass, 5 skip
```

## What to do next — in order

1. **Ask the user what they want tested**. Do NOT assume; they've been steering tightly. Good options:
   - Test Generate deck/quote on Telegram now that the `--query --instructions` fix is in (they last hit `unknown option '--task'` before this fix).
   - Wire the phone mock (10 min) so the demo has a phone escalation beat.
   - Record the 90s demo video.
   - Submit to Devfolio (payload at `/tmp/beepbop-submission.json`, 3 screenshots at `docs/screenshots/06-live-dashboard.png`, `07-live-opp-9.png`, `08-live-settings.png` — already S3-uploaded with filePaths in `/tmp/beepbop-pictures.json`).
2. If they say "submit", use the Devfolio MCP (`.claude/settings.local.json` has the key) via `httpx` with the existing payload. **Always ask "submit now?" first** — see the memory note.
3. If they ask about phone-call: answer is final — Plus/Pro gate at tool level, no Claw bypass.
4. If UI formatting shows raw Markdown tags, switch to HTML parse mode. `send_text` default is already HTML.

## Security checklist (remind user at end of session)

- Rotate Anthropic API key (leaked in chat early session)
- Rotate Devfolio MCP API key (leaked when URL shared)
- Rotate Genspark Claw remote-desktop password (leaked in chat)
- Rotate Telegram bot token (leaked when pasting from BotFather)

All are in `.env` or `.claude/settings.local.json` (gitignored) + still functioning. Rotate after hackathon wraps.

## Latest commits (most recent on top)

```
291d31d fix: gsk create_task also requires --instructions (runtime-enforced)
87a9824 fix: gsk create_task uses --query flag, not --task
591e184 fix: three Telegram UX bugs in one pass
d707f61 feat: /forget command for clearing preferences / rates / specific keys
9577966 fix: add 'preference' to parse_remember_fact allowed update_types
fba5bfd feat: /remember handles identity preferences (name, pronouns, tone)
6813dea feat: /remember clarifies ambiguous facts with inline keyboard
f3066dd fix: telegram /context uses HTML parse mode
e52be32 fix: telegram send_text falls back to plain text on Markdown parse error
4f6f259 docs: Claude Agent SDK research + MCP recommendation in #12
13e7542 feat: structured /remember (Claude-parsed) + cloud memory layer issue #12
a8c67bf feat: quote/deck confirm-before-generate + progress updates + /context command
1bb577e polish: Telegram /list with sentence-case titles + agency shorts + tier emoji
8a24f9a fix: correct gsk create-task syntax for slides + sheets
d3f7419 feat: beepbop — initial vertical
```

## One-line start

```
Read HANDOFF.md then ask the user what they want next.
```
