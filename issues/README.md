# Issues — TDD roadmap

Each issue has **Red** (failing test) / **Green** (passes when) / **Validation** (how the human gate is checked) / **Time budget**.

Critical path: `#1 → #3 → #5 → #6`. Parallelizable: `#2, #4, #7, #8`.

| # | Title | Time | Depends |
|---|-------|------|---------|
| [01](./01-scaffold.md) | Scaffold FastAPI + deploy + Google OAuth self-serve signup | 25m | — |
| [02](./02-seed.md) | Seed workshop DB + live scrape trigger | 15m | #1 |
| [03](./03-match-artifacts.md) | Match scoring + clarifications + `gsk` artifact gen | 40m | #2 |
| [04](./04-telegram.md) | Telegram approval loop | 30m | #1 |
| [05](./05-email.md) | Email send + mock reply + meeting draft | 25m | #3, #4 |
| [06](./06-calendar.md) | Calendar invite via second approval | 15m | #5 |
| [07](./07-policy.md) | Claude-decided outreach policy (auto/approve × email/phone) | 15m | #5 |
| [08](./08-docs-submission.md) | CLAUDE.md + Devfolio MCP + submission | 15m | all |
| [09](./09-compliance.md) | Compliance / prerequisites agent (MOE Registered Instructor, WSQ, vendor reg) | 20m | #3 |
| [10](./10-scraper-rewrite.md) | Rewrite gebiz scraper in-repo (drop subprocess) | 15m | #2 |
| [11](./11-closed-opps-pricing-advisor.md) | Closed opportunities scraper + pricing advisor (bid recs from historical awards) | 25m | #10 |

**Total build: 180m.** Setup/blockers run in parallel with user action.

## Gates (human review points)

- **Gate A (after #1)**: you load `https://beepbop.berlayar.ai`, sign in with Google demo account. → verifies deploy + auth.
- **Gate B (after #3)**: you click through an opportunity, see match score, clarifications, clickable deck + sheet URLs. → verifies the core value prop.
- **Gate C (after #4)**: your phone pings with a Telegram inline-keyboard approval. → verifies approval loop.
- **Gate D (after #6)**: end-to-end demo: context → opportunity → deck → approval → email → reply → approval → calendar invite, all on timeline. → demo-ready.
- **Gate E (after #8)**: Devfolio submission live. → done.
