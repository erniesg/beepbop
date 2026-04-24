"""Outreach orchestration: artifacts, emails, calendar, phone, with Telegram approval gates.

Each action is either:
  - auto_*  → fires immediately via gsk
  - approve_*  → creates outreach_log row with status=pending_approval, pings Telegram,
                 webhook callback flips status and fires the action.
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta
from typing import Any

from app import gsk_client, matching, policy, telegram_bot
from app.config import get_settings
from app.db import (
    conn,
    get_opportunity,
    get_outreach,
    insert_outreach,
    list_outreach,
    update_outreach,
)


# ---------------------------------------------------------------------------
# Artifact generation
# ---------------------------------------------------------------------------

def _existing_quote_for(opp_id: int) -> dict | None:
    """Return the most recent quote artifact for this opp if one exists."""
    with conn() as c:
        row = c.execute(
            "SELECT id, share_url, gsk_job_id FROM artifacts "
            "WHERE opportunity_id = ? AND kind = 'quote' AND share_url != '' "
            "ORDER BY id DESC LIMIT 1",
            (opp_id,),
        ).fetchone()
    return {"id": row["id"], "share_url": row["share_url"], "project_id": row["gsk_job_id"]} if row else None


def _deck_prompt(opp: dict, ctx: dict) -> str:
    quote = _existing_quote_for(opp["id"])
    quote_line = ""
    if quote and quote.get("share_url"):
        quote_line = (
            f"\n\nIMPORTANT — a quotation has already been generated for this opportunity: "
            f"{quote['share_url']}\n"
            f"On the 'Pricing headline' slide, cite this exact URL and keep numbers consistent "
            f"with the rates in our context. Do NOT invent new prices."
        )
    return (
        f"Create a 6-8 slide pitch deck for the following Singapore government tender.\n\n"
        f"Our company context:\n{ctx.get('profile_md','')[:1500]}\n\n"
        f"Opportunity:\n"
        f"- Title: {opp.get('title')}\n"
        f"- Agency: {opp.get('agency')}\n"
        f"- Category: {opp.get('procurement_category')}\n"
        f"- Closing: {opp.get('closing')}\n"
        f"{quote_line}\n\n"
        f"Slides: (1) About us, (2) Understanding of the opportunity, "
        f"(3) Proposed approach, (4) Team + past work, (5) Timeline, (6) Pricing headline, "
        f"(7) Why us, (8) Next steps."
    )


def _quote_prompt(opp: dict, ctx: dict) -> str:
    rates = ctx.get("rates")
    if isinstance(rates, str):
        try:
            rates = json.loads(rates)
        except json.JSONDecodeError:
            rates = {}
    return (
        f"Create a Google Sheets quotation for tender '{opp.get('title')}' from {opp.get('agency')}.\n"
        f"Columns: Item | Qty | Unit | Rate SGD | Subtotal.\n"
        f"Seed rows from our studio rates card: {json.dumps(rates or {})}.\n"
        f"Include a summary row with total + 9% GST + grand total."
    )


_GSK_BASE_URL = "https://www.genspark.ai"


def _extract_artifact_urls(res: dict) -> tuple[str, str]:
    """Pull (project_id, share_url) out of a gsk create_task response.

    gsk shape: {"status": "ok", "message": "...", "data": {"project_id": "...", ...}}.
    Older/alt shapes may put urls/ids at top level — check both.
    """
    data = res.get("data") if isinstance(res.get("data"), dict) else {}
    project_id = (
        data.get("project_id")
        or data.get("task_id")
        or res.get("project_id")
        or res.get("task_id")
        or res.get("job_id")
        or ""
    )
    share_url = (
        data.get("project_url")
        or data.get("share_url")
        or data.get("preview_url")
        or data.get("url")
        or res.get("share_url")
        or res.get("url")
        or ""
    )
    if not share_url and project_id:
        share_url = f"{_GSK_BASE_URL}/agents?id={project_id}"
    # Log raw response for debugging (rotating jsonl)
    try:
        import pathlib
        log_path = pathlib.Path("/tmp/beepbop-gsk-responses.jsonl")
        with log_path.open("a") as f:
            f.write(json.dumps({"ts": datetime.utcnow().isoformat(), "res": res}) + "\n")
    except Exception:
        pass
    return project_id, share_url


def generate_deck(opportunity_id: int, ctx: dict) -> dict:
    opp = get_opportunity(opportunity_id)
    if not opp:
        raise ValueError(f"opp {opportunity_id} not found")
    res = gsk_client.create_slides(_deck_prompt(opp, ctx))
    project_id, share_url = _extract_artifact_urls(res)
    with conn() as c:
        cur = c.execute(
            "INSERT INTO artifacts (opportunity_id, kind, gsk_job_id, share_url, expires_at) VALUES (?, ?, ?, ?, ?)",
            (
                opportunity_id,
                "deck",
                project_id,
                share_url,
                (datetime.utcnow() + timedelta(minutes=1440)).isoformat(),
            ),
        )
        art_id = int(cur.lastrowid)
    return {"id": art_id, "kind": "deck", "share_url": share_url, "project_id": project_id, "raw": res}


def generate_quote(opportunity_id: int, ctx: dict) -> dict:
    opp = get_opportunity(opportunity_id)
    if not opp:
        raise ValueError(f"opp {opportunity_id} not found")
    res = gsk_client.create_sheet(_quote_prompt(opp, ctx))
    project_id, share_url = _extract_artifact_urls(res)
    with conn() as c:
        cur = c.execute(
            "INSERT INTO artifacts (opportunity_id, kind, gsk_job_id, share_url) VALUES (?, ?, ?, ?)",
            (opportunity_id, "quote", project_id, share_url),
        )
        art_id = int(cur.lastrowid)
    return {"id": art_id, "kind": "quote", "share_url": share_url, "project_id": project_id, "raw": res}


# ---------------------------------------------------------------------------
# Email draft + approval + send
# ---------------------------------------------------------------------------

def _draft_email(opp: dict, ctx: dict, artifacts: list[dict]) -> dict:
    """Return {subject, body_html, recipient}. DEMO_MODE overrides recipient to the signed-in user."""
    settings = get_settings()
    title = opp.get("title", "")
    agency = opp.get("agency", "")
    deck_link = next((a["share_url"] for a in artifacts if a["kind"] == "deck"), "")
    quote_link = next((a["share_url"] for a in artifacts if a["kind"] == "quote"), "")

    subject = f"Interest in {title[:80]} ({opp.get('opportunity_no','')})"
    body_html = (
        f"<p>Hi,</p>"
        f"<p>We're writing to express interest in <b>{title}</b> at <b>{agency}</b> "
        f"(ref {opp.get('opportunity_no','')}).</p>"
        f"<p>A short overview of our proposed approach: "
        f"<a href='{deck_link}'>pitch deck</a>. Indicative pricing: "
        f"<a href='{quote_link}'>quotation</a>.</p>"
        f"<p>A few clarifications we'd like to confirm before finalising:</p>"
        f"<ul><li>Scope and deliverables</li><li>Access or login for document download</li>"
        f"<li>Start date + any milestones</li></ul>"
        f"<p>Happy to jump on a call at your convenience.</p>"
        f"<p>— ernie.sg</p>"
    )
    # Find recipient — in DEMO_MODE, override to demo account email (passed in via ctx.owner email)
    recipient = ctx.get("_demo_recipient") or opp.get("_contact_email") or ""
    return {"subject": subject, "body_html": body_html, "recipient": recipient}


def request_email_approval(
    opportunity_id: int, ctx: dict, *, recipient: str, artifacts: list[dict]
) -> int:
    opp = get_opportunity(opportunity_id)
    draft = _draft_email(opp, ctx | {"_demo_recipient": recipient}, artifacts)
    outreach_id = insert_outreach(
        opportunity_id=opportunity_id,
        channel="email",
        direction="out",
        status="pending_approval",
        recipient=draft["recipient"],
        subject=draft["subject"],
        body=draft["body_html"],
    )

    # Policy pre-check (might short-circuit approval)
    history = {"emails_sent": 0, "replies_received": 0}
    mode = policy.decide_outreach_mode(opp, ctx, history)
    update_outreach(outreach_id, policy_rationale=mode.get("rationale"))

    if mode["mode"] == "auto_email":
        # skip approval, fire immediately
        send_approved_email(outreach_id)
        return outreach_id

    # approve_email path: Telegram ping
    tg_text = (
        f"*Send email?*\n\n"
        f"To: `{draft['recipient']}`\n"
        f"Re: *{draft['subject'][:80]}*\n\n"
        f"Policy: {mode.get('rationale','(approve_email)')}"
    )
    try:
        tg = telegram_bot.send_approval(outreach_id, tg_text)
        update_outreach(outreach_id, telegram_message_id=str(tg.get("message_id", "")))
    except Exception as e:
        # Non-fatal; user can approve via UI
        update_outreach(outreach_id, policy_rationale=f"telegram failed: {e}")
    return outreach_id


def send_approved_email(outreach_id: int) -> dict:
    log = get_outreach(outreach_id)
    if not log:
        raise ValueError(f"outreach {outreach_id} not found")
    try:
        res = gsk_client.email_send(
            to=log["recipient"],
            subject=log["subject"],
            body_html=log["body"],
            skip_confirmation=True,
        )
        update_outreach(
            outreach_id,
            status="sent",
            external_id=str(res.get("id") or res.get("message_id") or ""),
        )
    except Exception as e:
        update_outreach(outreach_id, status="failed", policy_rationale=f"send error: {e}")
        raise
    return {"outreach_id": outreach_id, "status": "sent"}


# ---------------------------------------------------------------------------
# Mock reply (demo crutch)
# ---------------------------------------------------------------------------

DEFAULT_MOCK_REPLY = (
    "Thanks for reaching out on the tender. A couple of quick questions: "
    "Are you available on 29 Apr 2026 14:00 or 30 Apr 2026 10:00 for a 30-min call? "
    "— sent from mock reply for demo"
)


async def inject_mock_reply(opportunity_id: int, delay_seconds: int) -> None:
    await asyncio.sleep(delay_seconds)
    insert_outreach(
        opportunity_id=opportunity_id,
        channel="email",
        direction="in",
        status="replied",
        recipient="(mock-sender)",
        subject="Re: your proposal",
        body=DEFAULT_MOCK_REPLY,
    )


# ---------------------------------------------------------------------------
# Meeting draft + calendar
# ---------------------------------------------------------------------------

def propose_meeting_from_replies(opportunity_id: int) -> dict:
    """Scan inbound replies for proposed times; return a meeting draft."""
    replies = [r for r in list_outreach(opportunity_id) if r["direction"] == "in"]
    if not replies:
        return {"slots": [], "subject": ""}
    # For demo, hardcoded slots extracted from DEFAULT_MOCK_REPLY
    slots = [
        {"start": "2026-04-29T14:00:00+08:00", "end": "2026-04-29T14:30:00+08:00"},
        {"start": "2026-04-30T10:00:00+08:00", "end": "2026-04-30T10:30:00+08:00"},
    ]
    return {"slots": slots, "subject": "Tender discussion"}


def book_meeting(
    opportunity_id: int, slot_index: int, attendees: list[str], title: str = "Tender discussion"
) -> dict:
    draft = propose_meeting_from_replies(opportunity_id)
    if slot_index >= len(draft["slots"]):
        raise ValueError("slot_index out of range")
    slot = draft["slots"][slot_index]
    res = gsk_client.calendar_create(
        title=title,
        start_iso=slot["start"],
        end_iso=slot["end"],
        attendees=attendees,
        description=f"From beepbop opportunity #{opportunity_id}",
    )
    event_id = res.get("event_id") or res.get("id") or ""
    with conn() as c:
        c.execute(
            "UPDATE opportunities SET calendar_event_id = ? WHERE id = ?",
            (event_id, opportunity_id),
        )
    insert_outreach(
        opportunity_id=opportunity_id,
        channel="calendar",
        direction="out",
        status="sent",
        recipient=",".join(attendees),
        subject=title,
        body=f"slot {slot['start']}",
        external_id=event_id,
    )
    return {"event_id": event_id, "slot": slot, "raw": res}
