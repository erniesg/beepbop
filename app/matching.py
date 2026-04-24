"""Claude-powered matching + clarification extraction.

Two entry points:
  - score_opportunity(opp_row, ctx_row) -> {score, rationale}
  - extract_clarifications(opp_row, ctx_row) -> list[{question, severity, passage_ref}]

Falls back to a lexical TF-IDF-ish overlap if ANTHROPIC_API_KEY is absent.
"""
from __future__ import annotations

import json
import re
from typing import Any

import time

from anthropic import Anthropic
from anthropic._exceptions import APIStatusError, RateLimitError

from app.config import get_settings


_client: Anthropic | None = None


def _ai() -> Anthropic:
    global _client
    if _client is None:
        key = get_settings().anthropic_api_key
        if not key:
            raise RuntimeError("ANTHROPIC_API_KEY not set")
        _client = Anthropic(api_key=key)
    return _client


def _claude_with_retry(system: str, user_content: str, max_tokens: int, *, retries: int = 3) -> str:
    """Call Claude with exponential backoff on 429/529 overloads."""
    settings = get_settings()
    delay = 2.0
    last_exc: Exception | None = None
    for attempt in range(retries):
        try:
            msg = _ai().messages.create(
                model=settings.anthropic_model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": user_content}],
            )
            return msg.content[0].text.strip()
        except (RateLimitError, APIStatusError) as e:
            # Only retry on 429 / 529-style errors
            status = getattr(e, "status_code", None)
            if status not in (429, 503, 529) and not isinstance(e, RateLimitError):
                raise
            last_exc = e
            if attempt < retries - 1:
                time.sleep(delay)
                delay *= 2
    if last_exc:
        raise last_exc
    raise RuntimeError("claude retry exhausted without exception")


def _context_summary(ctx: dict) -> str:
    parts = [ctx.get("name", "context")]
    # Preferences (name, pronouns, tone) — important for personalised outputs
    prefs = ctx.get("preferences")
    if prefs:
        if isinstance(prefs, str):
            try:
                prefs = json.loads(prefs)
            except json.JSONDecodeError:
                prefs = {}
        if prefs:
            pref_lines = [f"  {k}: {v}" for k, v in prefs.items()]
            parts.append("User preferences (use these in outputs):\n" + "\n".join(pref_lines))
    if ctx.get("profile_md"):
        parts.append(ctx["profile_md"][:1500])
    services = ctx.get("services")
    if services:
        if isinstance(services, str):
            try:
                services = json.loads(services)
            except json.JSONDecodeError:
                services = []
        parts.append("Services: " + ", ".join(services))
    return "\n".join(parts)


def _opportunity_summary(opp: dict) -> str:
    return (
        f"Title: {opp.get('title')}\n"
        f"Agency: {opp.get('agency')}\n"
        f"Category: {opp.get('procurement_category')}\n"
        f"Closing: {opp.get('closing')}\n"
        f"Status: {opp.get('status')}\n"
        f"Keyword matched: {opp.get('matched_keyword')}\n"
        f"Remarks: {(opp.get('raw_json') and json.loads(opp['raw_json']).get('remarks', ''))[:500]}"
    )


# ---------------------------------------------------------------------------
# Matching
# ---------------------------------------------------------------------------

SCORE_SYSTEM = """You score how well a Singapore GeBIZ tender opportunity fits an SME's context.

Output STRICT JSON only, no prose around it:
{"score": <float 0.0-1.0>, "rationale": "<one sentence>"}

Scoring rubric:
- 0.9+ = direct service match, agency/domain fit, reasonable closing window
- 0.6-0.9 = partial service match, could pitch with stretch
- 0.3-0.6 = tangential
- <0.3 = unrelated / wrong industry"""


def score_opportunity(opp: dict, ctx: dict) -> dict:
    """Return {score: float, rationale: str}."""
    try:
        text = _claude_with_retry(
            SCORE_SYSTEM,
            f"CONTEXT:\n{_context_summary(ctx)}\n\nOPPORTUNITY:\n{_opportunity_summary(opp)}",
            max_tokens=200,
        )
        text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.MULTILINE).strip()
        data = json.loads(text)
        score = max(0.0, min(1.0, float(data["score"])))
        return {"score": score, "rationale": data.get("rationale", "")}
    except Exception as e:
        return _lexical_score(opp, ctx, reason=str(e))


def _lexical_score(opp: dict, ctx: dict, reason: str = "fallback") -> dict:
    """Deterministic fallback when Claude is unavailable."""
    services = ctx.get("services")
    if isinstance(services, str):
        try:
            services = json.loads(services)
        except json.JSONDecodeError:
            services = []
    services = [s.lower() for s in (services or [])]
    haystack = " ".join(
        str(v or "").lower()
        for v in (opp.get("title"), opp.get("procurement_category"), opp.get("matched_keyword"))
    )
    hits = sum(1 for s in services if s and s in haystack)
    score = min(1.0, 0.25 * hits + (0.2 if opp.get("matched_keyword") else 0))
    return {
        "score": round(score, 2),
        "rationale": f"lexical fallback ({reason[:60]}): {hits} service overlap",
    }


# ---------------------------------------------------------------------------
# Clarifications
# ---------------------------------------------------------------------------

CLARIFY_SYSTEM = """You extract clarifying questions an SME should ask a procurement officer before submitting a bid on a Singapore government tender.

Output STRICT JSON:
{"clarifications": [{"question": "<concrete question>", "severity": "low|med|high", "why": "<one short reason>"}]}

Return 2-5 questions. Favour deliverable scope, timeline, access/login, payment terms, evaluation criteria. Skip questions already answered in the listing."""


def extract_clarifications(opp: dict, ctx: dict) -> list[dict]:
    try:
        text = _claude_with_retry(
            CLARIFY_SYSTEM,
            f"CONTEXT:\n{_context_summary(ctx)}\n\nOPPORTUNITY:\n{_opportunity_summary(opp)}",
            max_tokens=500,
        )
        text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.MULTILINE).strip()
        data = json.loads(text)
        items = data.get("clarifications", [])
        return [
            {
                "question": i.get("question", "").strip(),
                "severity": i.get("severity", "med"),
                "why": i.get("why", ""),
            }
            for i in items
            if i.get("question")
        ][:5]
    except Exception:
        return [
            {
                "question": "What is the exact scope and deliverable list?",
                "severity": "high",
                "why": "fallback",
            },
            {
                "question": "What's the expected start date and any milestones?",
                "severity": "med",
                "why": "fallback",
            },
        ]


# ---------------------------------------------------------------------------
# Compliance / prerequisites
# ---------------------------------------------------------------------------

PREREQ_SYSTEM = """You extract HARD COMPLIANCE GATES a Singapore SME must pass before bidding on a government tender.

Use BOTH:
  (a) anything explicitly stated in the tender body
  (b) DOMAIN KNOWLEDGE about Singapore procurement regimes (infer gates that are standard for this type of work, even if not spelled out)

Known Singapore regimes (use these names exactly, infer when applicable):
- MOE Registered Instructor — ANY instructor / trainer role in MOE schools (CCA, enrichment, curriculum). ALWAYS required for school-based instructor roles even if not stated.
- WSQ ACTA / DACE — training/assessment tenders issuing WSQ certs
- ACRA business registration — any government contract
- GeBIZ Trading Partner registration — required to submit on GeBIZ
- NCSS clearance — youth / social services / vulnerable groups
- NAC Arts Education Programme panel — arts ed with schools (inferred when school + arts)
- Public Liability + Professional Indemnity insurance — physical-presence work (workshops, on-site services)
- First Aid / CPR — physical-activity programmes with students
- Police clearance / ECDC check — working with minors on MOE premises

For EACH prereq, compare against the user's context to decide user_meets. If the tender involves school premises + instructor role, MOE Registered Instructor IS a hard gate — return it even if the listing doesn't spell it out.

Output STRICT JSON:
{"prerequisites": [{"requirement": "<name>", "category": "certification|registration|insurance|clearance|other", "required": true, "user_meets": <bool>, "evidence": "<tender excerpt or reason inferred>", "how_to_comply": "<one-line action + link if known>"}]}

Return 2-5 items — always at least 2 for school/government work. Order by severity (highest first)."""


REMEMBER_SYSTEM = """You convert a user's free-text memory into a STRUCTURED context update for their SME org profile.

If the input is AMBIGUOUS (e.g. "I charge 6000 for a day" — which service? photography? videography? workshop?), return a clarification request INSTEAD of guessing.

Output STRICT JSON only, one of these shapes:

Shape A — direct update:
{
  "update_type": "rate" | "service" | "certification" | "preference" | "profile",
  "field": "<key>",
  "value": <value — number for rates, string otherwise>,
  "summary": "<short human-readable confirmation>"
}

"preference" is for identity / communication preferences: preferred name, pronouns, tone, languages. Keys:
- preferred_name  → e.g. "Ernie"
- pronouns        → e.g. "she/her", "they/them", "he/him"
- tone            → e.g. "formal", "casual", "direct"
- signoff         → e.g. "Warmly, Ernie"

Shape B — needs clarification:
{
  "update_type": "needs_clarification",
  "question": "<short question to ask the user>",
  "options": ["<opt1>", "<opt2>", "<opt3>", "<opt4>"]
}

Examples (direct):
"I charge 1800 for videography full-day" → {"update_type":"rate","field":"videography_fullday","value":1800,"summary":"Rate saved: videography full-day = SGD 1800"}
"My photography half-day is $650" → {"update_type":"rate","field":"photography_halfday","value":650,"summary":"Rate saved: photography half-day = SGD 650"}
"We're MOE Registered Instructors" → {"update_type":"certification","field":"certifications","value":"MOE Registered Instructor","summary":"Added: MOE Registered Instructor"}
"We also do motion graphics" → {"update_type":"service","field":"services","value":"motion graphics","summary":"Added service: motion graphics"}
"Call me Ernie" → {"update_type":"preference","field":"preferred_name","value":"Ernie","summary":"Preferred name: Ernie"}
"My pronouns are she/her" → {"update_type":"preference","field":"pronouns","value":"she/her","summary":"Pronouns: she/her"}
"I'm not a man, use they/them" → {"update_type":"preference","field":"pronouns","value":"they/them","summary":"Pronouns: they/them"}
"Keep emails casual" → {"update_type":"preference","field":"tone","value":"casual","summary":"Tone preference: casual"}

Examples (needs clarification):
"I charge 6000 for a day" → {"update_type":"needs_clarification","question":"Which service is SGD 6000/day for?","options":["photography","videography","workshop","something else"]}
"Full day is 1500" → {"update_type":"needs_clarification","question":"Full day of what service?","options":["photography","videography","workshop","something else"]}
"I changed my rate" → {"update_type":"needs_clarification","question":"Which rate changed?","options":["photography_halfday","photography_fullday","videography_fullday","something else"]}

Pick "rate" only when service AND duration are specified. Otherwise clarify.
If clearly about a service you offer but unclear detail, clarify.
If it's prose/history/context (no numbers), use update_type="profile"."""


def parse_remember_fact(text: str, extra_hint: str | None = None) -> dict:
    """Turn free-text /remember fact into a structured update. May return
    {update_type: 'needs_clarification', question, options} if ambiguous.
    Fallback to profile append on API error."""
    user_content = text if not extra_hint else f"{text}\n(user clarified: {extra_hint})"
    try:
        raw = _claude_with_retry(REMEMBER_SYSTEM, user_content, max_tokens=400)
        raw = re.sub(r"^```(?:json)?|```$", "", raw, flags=re.MULTILINE).strip()
        data = json.loads(raw)
        ut = data.get("update_type")
        if ut in {"rate", "service", "certification", "preference", "profile", "needs_clarification"}:
            return data
    except Exception:
        pass
    return {
        "update_type": "profile",
        "field": "profile_md",
        "value": f"- {text}",
        "summary": f"Remembered: {text[:80]}",
    }


def extract_prerequisites(opp: dict, ctx: dict) -> list[dict]:
    import os as _os
    try:
        text = _claude_with_retry(
            PREREQ_SYSTEM,
            f"CONTEXT:\n{_context_summary(ctx)}\n\nOPPORTUNITY:\n{_opportunity_summary(opp)}",
            max_tokens=1500,
        )
        text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.MULTILINE).strip()
        data = json.loads(text)
        items = data.get("prerequisites", [])
        return [
            {
                "requirement": i.get("requirement", "").strip(),
                "category": i.get("category", "other"),
                "required": bool(i.get("required", True)),
                "user_meets": bool(i.get("user_meets", False)),
                "evidence": i.get("evidence", ""),
                "how_to_comply": i.get("how_to_comply", ""),
            }
            for i in items
            if i.get("requirement")
        ][:5]
    except Exception as e:
        if _os.getenv("BEEPBOP_DEBUG"):
            import traceback; traceback.print_exc()
        return []
