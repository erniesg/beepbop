# #8 — CLAUDE.md + Devfolio MCP + submission

**Time:** 15 min
**Depends:** all

## Red

- `beepbop/CLAUDE.md` missing → fresh Claude session can't orient.
- Master `/Users/erniesg/code/erniesg/CLAUDE.md` has no "beepbop" section.
- Devfolio MCP not registered; no submission.

## Green

1. **`beepbop/CLAUDE.md`** — already drafted with this scaffold. Verify sections: stack, key files, commands, demo flow, env vars, known quirks.
2. **Master `CLAUDE.md`** — add a "`beepbop/`" subsection under "Core Integration Stack" or a new "Singapore SME/creator tools" section, pointing to `beepbop/CLAUDE.md`.
3. **Devfolio MCP** — register in `.claude/settings.local.json` per https://guide.devfolio.co/docs/guide/devfolio-mcp:
   ```json
   {
     "mcpServers": {
       "devfolio": { "command": "...", "args": [...], "env": { "DEVFOLIO_TOKEN": "..." } }
     }
   }
   ```
4. **`beepbop/devfolio/submission.md`** — fields:
   - Tagline: "GeBIZ → pitch deck → email → meeting, on autopilot. For SMEs, creators, artists."
   - Problem: SMEs and creators miss Singapore government tenders because searching GeBIZ daily + writing pitches + chasing clarifications is a full-time admin job.
   - Solution: beepbop watches GeBIZ for you, generates pitch artifacts in one click, handles approval + outreach via Telegram, falls back to phone if needed.
   - Tech: FastAPI, Claude Sonnet 4.6, Genspark Claw, Cloudflare Tunnel, Telegram Bot API, Playwright.
   - Demo URL: `https://beepbop.berlayar.ai`
   - GitHub: `https://github.com/<user>/beepbop` (create push-ready repo)
   - Team: erniesg
   - Demo video: 90s Loom — record the flow.
5. **Demo video** (`docs/DEMO.md` describes recording script):
   - 0:00 — land on beepbop.berlayar.ai, sign in
   - 0:10 — dashboard shows 20 GeBIZ opportunities, click "Digital Artist"
   - 0:20 — match score + clarifications
   - 0:30 — Generate deck (Genspark Claw URL opens)
   - 0:40 — Generate quote (Google Sheet opens)
   - 0:50 — "Request approval" → phone rings with Telegram
   - 1:00 — tap Yes → email sent
   - 1:10 — mock reply arrives → meeting draft
   - 1:20 — second approval → calendar event
   - 1:30 — fin

## Validation

- Fresh `claude code` session in `beepbop/` answers "how do I demo this?" from CLAUDE.md alone.
- Devfolio submission page shows the project with all fields and demo URL clickable.
- Demo video plays end-to-end without cuts.
- **Gate E**: user confirms submission visible on Devfolio.
