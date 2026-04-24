# Devfolio Draft Rewrite Proposal

This is a local draft only. Nothing has been submitted or updated through Devfolio MCP.

## Tagline

AI bid ops for creators, artists, and SMEs chasing public-sector work.

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

The user does not have to live in tabs. They stay in control at the decision points.

The point is not to make artists become procurement operators. The point is to let them focus on what they love: making work, teaching workshops, shooting shows, producing campaigns, serving schools and public agencies. BeepBop handles the bid ops layer around them.

The same pattern can scale beyond Singapore. GeBIZ is the first market, but the system is really a managed-agent workflow for public-sector opportunity operations: one agent monitors listings, one agent reasons about fit and compliance, one agent generates artifacts, and one agent coordinates approvals and follow-up. Swap the procurement portal and local compliance knowledge, and the same bid ops loop can support creators and SMEs in other countries.

## Use Of Genspark

Genspark handles the artifact work that usually blocks small teams from bidding quickly:

- Pitch deck generation for a selected tender.
- Quote sheet generation from the studio rate card.
- Email and calendar execution through connected tools.
- A shareable workspace link that can be opened straight from Telegram.

The key use is not just content generation; it is converting a tender into submission-ready business artifacts fast enough for a small operator to act while the opportunity is still fresh.

## Use Of Claude

Claude acts as the reasoning layer:

- Reads the creator/SME context as operating memory: services, rates, portfolio, and preferences.
- Decomposes a creative-studio profile into GeBIZ search terms.
- Scores each opportunity against the user's context.
- Produces match rationales.
- Extracts clarification questions.
- Infers Singapore-specific compliance gates such as MOE instructor requirements, police checks, insurance, and GeBIZ trading partner registration.
- Drafts outreach and meeting follow-up decisions.

Claude Code also helped produce the submission demo asset: it used the HyperFrames skill to build the kinetic text-mask video and adapted the opening around a real Esplanade/Singapore night image, with callouts layered over the Telegram walkthrough.

We also used a GeBIZ scraping/download workflow hardened around Singapore-specific portal behavior: Playwright search, contact scraping, downloaded attachments when Singpass permits, and guardrails around GeBIZ's multiple-window/session traps. For the demo, public listing mode is enough to show the bid loop; the Singpass document-download handoff is documented as the next production step.

## Challenges

- **Token pressure.** The build had to stay focused: enough context for Claude/Genspark to reason well, without turning every tender into a kitchen-sink prompt.
- **GeBIZ + Singpass.** Tender document downloads hit Singpass QR login. For the demo, beepbop uses public GeBIZ listings and contact data, with a documented path to remote-browser Singpass handoff.
- **GSK slide generation.** Two compounding bugs slowed the deck flow: the wrong streaming endpoint and orphaned jobs from restarting `uvicorn` mid-generation. The fix was switching from `/api/tool_cli/create_task` to `/api/tool_cli/agent_ask`, where `project_id` appears early in the stream; once we stopped killing in-flight jobs, the deck URL landed by DM in under 20 seconds.
- **Scope pressure.** After two failed correction loops, the project narrowed to the strongest working path: monitor opportunities, score fit, generate artifacts, and keep the human approval loop.

## Closing Line

Skill unlocked: securing lunch for every creator, every artist, every SME, so small teams can scale into public-sector work.

## Required Fixes Before Publish

- Add deployed URL organizer answer: `https://beepbop.berlayar.ai`
- Change GitHub link to `https://github.com/erniesg/beepbop`
- Add the uploaded demo video URL once the final recording is hosted.
