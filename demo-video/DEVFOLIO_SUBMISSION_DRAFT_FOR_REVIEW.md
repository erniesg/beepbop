# Devfolio Submission Draft For Review

Local review draft only. Do not update Devfolio until explicitly approved.

## Project Metadata

- Hackathon: Push to Prod Hackathon with Genspark & Claude
- Hackathon slug: `push-to-prod`
- Project name: `beepbop`
- Tagline: `AI bid ops for creators and SMEs`
- Status to keep while editing: `draft`
- Deployed URL: `https://beepbop.berlayar.ai`
- GitHub URL: `https://github.com/erniesg/beepbop`
- Platforms: `Web`
- Technologies: `Python`, `FastAPI`, `Claude`, `Genspark`, `HTMX`, `Playwright`, `Cloudflare`, `Telegram`
- Demo video URL: `TBD after upload`

## Skills

Securing lunch for every creator, every artist, every SME.

## The Problem Your Project Solves

Artists need money. The State is the biggest buyer.

The problem is not that opportunities do not exist. The problem is that public-sector work is hidden behind a workflow that feels like death by tab-switching:

- Monitor GeBIZ every day.
- Guess which keywords matter.
- Open dozens of listings.
- Read tender details and hidden prerequisites.
- Build a pitch deck.
- Build a quote.
- Email the procurement officer.
- Chase clarifications.
- Book the follow-up.

That is a real internal workflow problem for small creative teams. It is repetitive, manual, easy to forget, and expensive because every missed tender is lost revenue.

## How You Are Solving It

beepbop is a bot that helps creators, artists, and SMEs bid on opportunities from the biggest customer in Singapore: the state.

It turns the GeBIZ bidding workflow into an AI-native approval loop:

- It watches public GeBIZ listings.
- Claude scores opportunities against the studio profile and explains the fit.
- Claude extracts clarification questions and hidden compliance gates.
- Genspark creates the pitch deck and quotation sheet.
- Telegram asks the human before anything external is sent.
- On approval, beepbop sends the email and can turn replies into meeting drafts.

BeepBop is the bid-ops layer around a small team. Creators keep making, teaching, shooting, producing, and serving agencies. Managed agents handle monitoring, matching, compliance checks, decks, quotes, outreach, and handoffs. Telegram keeps the human at the decision points.

Singapore and GeBIZ are the first wedge. Globally, the pattern is portable: portal adapters, local compliance skills, artifact agents, and approval loops. Swap the procurement portal and rules, and the same managed-agent loop helps creators and SMEs bid into public-sector demand anywhere.

## Use Of Genspark

Genspark handles the artifact and execution work that usually blocks small teams from bidding quickly:

- Pitch deck generation for a selected tender.
- Quote sheet generation from the studio rate card.
- Email and calendar execution through connected tools.
- A shareable workspace link that can be opened straight from Telegram.

The key use is not just content generation. It converts a tender into submission-ready business artifacts fast enough for a small operator to act while the opportunity is still fresh.

## Use Of Claude

Claude acts as the reasoning layer:

- Reads the creator/SME context as operating memory: services, rates, portfolio, and preferences.
- Decomposes a creative-studio profile into GeBIZ search terms.
- Scores each opportunity against the user's context.
- Produces match rationales.
- Extracts clarification questions.
- Infers Singapore-specific compliance gates such as MOE instructor requirements, police checks, insurance, and GeBIZ trading partner registration.
- Drafts outreach and meeting follow-up decisions.

Claude Code also helped produce the submission demo asset using the HyperFrames skill: a kinetic text-mask video over a real Esplanade/Singapore night image, with callouts layered over the Telegram walkthrough.

We also used a GeBIZ scraping/download workflow hardened around Singapore-specific portal behavior: Playwright search, contact scraping, downloaded attachments when Singpass permits, and guardrails around GeBIZ's multiple-window/session traps. For the demo, public listing mode is enough to show the bid loop; the Singpass document-download handoff is documented as the next production step.

## Challenges

- **Token pressure.** The build had to stay focused: enough context for Claude/Genspark to reason well, without turning every tender into a kitchen-sink prompt.
- **GeBIZ + Singpass.** Tender document downloads hit Singpass QR login. For the demo, beepbop uses public GeBIZ listings and contact data, with a documented path to remote-browser Singpass handoff.
- **GSK slide generation.** Two compounding bugs slowed the deck flow: the wrong streaming endpoint and orphaned jobs from restarting `uvicorn` mid-generation. The fix was switching from `/api/tool_cli/create_task` to `/api/tool_cli/agent_ask`, where `project_id` appears early in the stream; once we stopped killing in-flight jobs, the deck URL landed by DM in under 20 seconds.
- **Scope pressure.** After two failed correction loops, the project narrowed to the strongest working path: monitor opportunities, score fit, generate artifacts, and keep the human approval loop.

## Closing Line

Skill unlocked: securing lunch for every creator, every artist, every SME, so small teams can scale into public-sector work.

## Video Upload Plan

Devfolio MCP expects `video_url`, not a video binary. The MP4 should be uploaded elsewhere first.

Recommended options:

- Loom: best if you combine this 14s intro with a screen recording walkthrough.
- YouTube unlisted: best stable public URL for judges.
- Google Drive public link: fast, but verify permissions in an incognito window.
- Vimeo unlisted: cleanest playback if available.

After upload, the URL goes into Devfolio as `video_url`.

The exact MCP update payload to review is in `DEVFOLIO_MCP_UPDATE_PAYLOAD_DRAFT.json`.

## Current Local Video Files

- Review render: `renders/beepbop-demo-trailer-review-v3.mp4`
- Previous high-quality render: `renders/beepbop-demo-trailer-final.mp4`

## Current Devfolio Draft Fixes To Apply Later

- Add missing deployed URL organizer field: `https://beepbop.berlayar.ai`
- Replace wrong GitHub link with `https://github.com/erniesg/beepbop`
- Add final hosted video URL
- Keep status as `draft` until final approval
