# Devfolio Draft Rewrite Proposal

This is a local draft only. Nothing has been submitted or updated through Devfolio MCP.

## Tagline

AI bid ops for creators, artists, and SMEs chasing public-sector work.

## The Problem Your Project Solves

If you work in the arts, creative services, or as a small SME, you are often hungry for money while one of Singapore's biggest customers, the state, is buying work every day.

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

## Use Of Genspark

Genspark handles the artifact work that usually blocks small teams from bidding quickly:

- Pitch deck generation for a selected tender.
- Quote sheet generation from the studio rate card.
- Email and calendar execution through connected tools.

The key use is not just content generation; it is converting a tender into submission-ready business artifacts fast enough for a small operator to act.

## Use Of Claude

Claude acts as the reasoning layer:

- Decomposes a creative-studio profile into GeBIZ search terms.
- Scores each opportunity against the user's context.
- Produces match rationales.
- Extracts clarification questions.
- Infers Singapore-specific compliance gates such as MOE instructor requirements, police checks, insurance, and GeBIZ trading partner registration.
- Drafts outreach and meeting follow-up decisions.

Claude Code also helped produce the submission demo asset: it used the HyperFrames skill to build the kinetic text-mask video and adapted the opening around a real Esplanade/Singapore night image.

## Closing Line

Skill unlocked: securing lunch for every creator and every SME, so small teams can scale into public-sector work.

## Required Fixes Before Publish

- Add deployed URL organizer answer: `https://beepbop.berlayar.ai`
- Change GitHub link to `https://github.com/erniesg/beepbop`
- Add the uploaded demo video URL once the final recording is hosted.
