# Demo script

## 90-second live demo (for Devfolio video)

**Setup before recording:**
- Laptop open, tunnel + uvicorn running
- Telegram app open on phone
- Google demo account logged into Chrome
- Demo inbox open in a second tab to show arriving email

**Storyline:**

| Time | On screen | Voiceover |
|---|---|---|
| 0:00 | Browser → `beepbop.berlayar.ai` | "beepbop finds Singapore government tenders suited to creative SMEs and handles the pitch loop." |
| 0:05 | Click "Sign in with Google" | "Sign in with any Google account — self-serve." |
| 0:10 | Dashboard with 20 opportunities | "It's scraped 20 live GeBIZ opportunities matched against my creative-studio context." |
| 0:15 | Click "INVITATION TO QUOTE FOR PROVISION OF DIGITAL ARTIST" | "This one's MOE, closing in 5 days, matched at 0.82 with my services." |
| 0:20 | Point at match rationale + clarifications | "Claude extracted three clarifying questions from the tender I should ask before pitching." |
| 0:30 | Click "Generate pitch deck" → wait 3s → click the URL | "One click. Genspark Claw generates a pitch deck tailored to my context + the opportunity." |
| 0:45 | Back. Click "Generate quote" → click the URL | "And a quotation spreadsheet pre-filled from my rates." |
| 1:00 | Click "Request approval to send" | "Before anything leaves my outbox, I approve it on my phone." |
| 1:05 | Phone buzzes; show Telegram | "Telegram ping — tap Yes." |
| 1:10 | Email lands in demo inbox | "Email out. A reply comes back..." |
| 1:15 | Mock reply appears on timeline | "...with two proposed meeting times." |
| 1:20 | Phone buzzes again | "Another approval: book 29 April?" |
| 1:25 | Tap Yes; calendar event appears | "Meeting on the calendar. Done." |
| 1:30 | Back to dashboard | "For no-response tenders, Claude escalates to a phone call — also with your approval." |

## Live judging flow (if judges interact)

1. Give them a laptop pointed at `beepbop.berlayar.ai`.
2. They sign in with their own Google.
3. They see the 20 seeded opportunities (scoped to a fresh context).
4. They pick any, walk through deck + quote + email approval.
5. We pre-pin a test recipient so any email they "send" lands in a burner inbox they can see.

## Canned cold-start

```bash
# single command demo reset
./scripts/demo-reset.sh
# → clears outreach_log, artifacts; keeps users/contexts/opportunities
```
