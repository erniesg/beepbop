# Devfolio Submission Draft For Review

Local review draft only. Do not update Devfolio until explicitly approved per call.

## Project Metadata

- Hackathon: Push to Prod Hackathon with Genspark & Claude
- Hackathon slug: `push-to-prod`
- Project name: `beepbop`
- Tagline: `AI bid ops for creators and SMEs`
- Status while editing: `draft` (flip to `submitted` only on explicit user approval)
- Deployed URL: `https://beepbop.berlayar.ai`
- GitHub URL: `https://github.com/erniesg/beepbop`
- Platforms: `Web`
- Technologies: `Python`, `FastAPI`, `Claude`, `Genspark`, `HTMX`, `Playwright`, `Cloudflare`, `Telegram`
- Demo video URL: `TBD after v3 upload` (local file: `renders/beepbop-submission-video-v3.mp4`)

## Skill unlocked

Securing lunch for every creator, every artist, every SME.

## The Problem Your Project Solves

**Artists need money. The State is the biggest buyer.**

The opportunity exists. Small creative teams lose it anyway, because public-sector procurement turns opportunity into death-by-tab-switching:

- Monitor GeBIZ every day.
- Guess which keywords matter.
- Open dozens of listings.
- Read tender details and hidden prerequisites.
- Build a pitch deck.
- Build a quote.
- Email the procurement officer.
- Chase clarifications.
- Book the follow-up.

That is real internal workflow pain: repetitive, manual, easy to forget, and expensive because every missed tender is lost revenue.

Creators do not need to become procurement operators. They need the bid ops to happen around them.

## How You Are Solving It

beepbop is a Telegram-first bid-ops bot for creators, artists, and SMEs.

**You do not live in tabs.** Managed agents do.

- The GeBIZ skill watches the market: public listings, awarded prices, supplier signals.
- Claude scores fit against the studio profile and extracts hidden compliance gates.
- Genspark generates the pitch deck and quote sheet.
- Telegram asks the human before anything external is sent.
- On approval, beepbop sends the email and can turn replies into meeting drafts.

The creator stays in control at decision points. The rest is scaffolding. Monitoring, matching, compliance extraction, artifact generation, outreach, and follow-up handoffs are all handled by managed agents so creators can focus on the work they love.

Singapore and GeBIZ are the first wedge. The pattern is portable: portal adapters, local compliance skills, artifact agents, and approval loops. Swap the procurement portal and the local rules, and the same managed-agent loop helps creators and SMEs bid into public-sector demand anywhere.

## Use Of Genspark

Genspark is the artifact and execution layer that usually blocks small teams from bidding quickly:

- Pitch deck generation for a selected tender.
- Quote sheet generation from the studio rate card.
- Email and calendar execution through connected tools.
- A shareable workspace link that opens straight from Telegram.

The key use is not just content generation. It converts a tender into submission-ready business artifacts fast enough for a small operator to act while the opportunity is still fresh.

## Use Of Claude

Claude is the reasoning layer:

- Reads the creator/SME context as operating memory: services, rates, portfolio, preferences.
- Decomposes a creative-studio profile into GeBIZ search terms.
- Scores each opportunity against the user's context and explains why.
- Extracts clarification questions and hidden compliance gates (MOE instructor requirements, police checks, insurance, GeBIZ trading partner registration).
- Drafts outreach and meeting follow-up decisions.
- Keeps the human approval loop coherent across Telegram turns.

**Claude Code reviewed and enhanced the final submission asset** (this demo video, the submission copy, and the final bid-ops narrative). The Esplanade/Singapore text-mask intro, walkthrough callouts, and closing line were authored with the HyperFrames skill and signed off via Claude Code.

## GeBIZ Skill

The project uses a GeBIZ-focused workflow for Singapore portal behaviour:

- Public listing search and ranked retrieval.
- Contact scraping for procurement officers and awarding ministries.
- Awarded/closed opportunity mining for pricing signals.
- A documented Singpass handoff path for protected tender documents (remote-browser QR scan, ~30s window).

Guardrails handle GeBIZ's multi-window/session quirks so the scrape stays stable.

## Challenges

- **Token pressure.** The context had to stay sharp, not become a kitchen-sink prompt. Every tender ingest is opportunity, not a dumping ground.
- **GeBIZ + Singpass.** Tender document downloads hit Singpass QR login. For the demo, beepbop uses public GeBIZ listings and contact data, with a documented remote-browser Singpass handoff path for production.
- **GSK slide generation bug.** Two compounding bugs slowed the deck flow: the wrong streaming endpoint hid `project_id`, and restarting `uvicorn` orphaned in-flight deck jobs. Switching from `/api/tool_cli/create_task` to `/api/tool_cli/agent_ask` exposed `project_id` early in the stream; once we stopped killing mid-generation jobs, the deck URL landed by DM in under 20s.
- **Kitchen-sink failure → fresh handoff.** After two failed correction loops, the project was drifting into kitchen-sink territory: stretchy scope, accreting prompts, a narrative pulling in every direction. We cut the session, snapshotted context into a fresh handoff, and brought in a clean agent pass to re-anchor on the strongest working loop: monitor opportunities, score fit, generate artifacts, keep the human in the approval seat. The narrow loop is what got shipped — and what the demo video shows.
- **Scope pressure.** Hackathon time meant choosing: one tight bid-ops loop over Telegram, with real data and approval gates, versus a broader product surface. We chose the loop.

## Closing Line

Securing lunch for every creator, every artist, every SME, so small teams can scale into public-sector work without living in tabs.

## Video Upload Plan

Devfolio's `video_url` field expects a hosted URL, not a binary. Upload `renders/beepbop-submission-video-v3.mp4` to one of:

- YouTube (unlisted) — best for judges, stable public URL.
- Loom — good if combining with a longer narrated walkthrough.
- Google Drive (public link) — verify in incognito before submitting.
- Vimeo (unlisted) — cleanest playback.

Then paste that URL into the Devfolio field (or the MCP payload before firing).

## Current Local Video Files

- Final v3 submission render: `renders/beepbop-submission-video-v3.mp4`
- v2 archive: `renders/beepbop-submission-video-v2.mp4`
- v3 intro standalone: `renders/beepbop-intro-v3.mp4`
- Bot walkthrough overlaid v3: `renders/beepbop-bot-demo-overlaid-v3.mp4`
- v3 contact sheet: `review-frames/contact-sheet-submission-v3.jpg`

## Pre-flight Check Before Firing updateHackathonProject MCP Call

- [ ] Hosted video URL is in hand and opens in an incognito window.
- [ ] `DEVFOLIO_MCP_UPDATE_PAYLOAD_DRAFT.json` has been re-read end-to-end.
- [ ] Desired `status` is confirmed (`draft` or `submitted`).
- [ ] User gave fresh per-call approval (per saved `never auto-submit` rule).
- [ ] GitHub link points to `https://github.com/erniesg/beepbop`.
- [ ] Deployed URL resolves: `https://beepbop.berlayar.ai`.
