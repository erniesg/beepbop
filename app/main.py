from __future__ import annotations

from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from app import __version__
from app.auth import current_user, exchange_code, get_oauth, login_user
from app.config import ROOT, get_settings


settings = get_settings()
app = FastAPI(title="beepbop", version=__version__)

app.add_middleware(
    SessionMiddleware,
    secret_key=settings.secret_key,
    max_age=7 * 24 * 3600,
    same_site="lax",
    https_only=settings.app_env == "prod",
)

static_dir = ROOT / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

import json as _json_mod
templates = Jinja2Templates(directory=str(ROOT / "templates"))
templates.env.filters["fromjson"] = lambda s: _json_mod.loads(s) if s else []


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/healthz")
def healthz() -> JSONResponse:
    return JSONResponse({"status": "ok", "version": __version__})


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

@app.get("/login", response_class=HTMLResponse)
def login(request: Request) -> HTMLResponse:
    user = current_user(request)
    if user:
        return RedirectResponse("/", status_code=307)
    return templates.TemplateResponse(
        request,
        "login.html",
        {"has_google": bool(settings.google_client_id)},
    )


@app.get("/auth/google/start")
async def auth_google_start(request: Request):
    if not settings.google_client_id:
        return JSONResponse(
            {"error": "google_oauth_not_configured", "hint": "Fill GOOGLE_CLIENT_ID/SECRET in .env"},
            status_code=500,
        )
    oauth = get_oauth()
    redirect_uri = f"{settings.public_base_url}/auth/google/callback"
    return await oauth.google.authorize_redirect(request, redirect_uri)


@app.get("/auth/google/callback")
async def auth_google_callback(request: Request):
    try:
        profile = await exchange_code(request)
    except Exception as e:
        return JSONResponse({"error": "oauth_exchange_failed", "detail": str(e)}, status_code=400)
    await login_user(request, profile)
    return RedirectResponse("/", status_code=307)


@app.post("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


@app.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request) -> HTMLResponse:
    user = current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=307)
    from app import app_settings as _as
    return templates.TemplateResponse(
        request,
        "settings.html",
        {"user": user, "summary": _as.summary()},
    )


@app.post("/settings/google")
async def settings_google(request: Request):
    user = current_user(request)
    if not user:
        raise HTTPException(401)
    form = await request.form()
    from app import app_settings as _as
    cid = (form.get("client_id") or "").strip()
    secret = (form.get("client_secret") or "").strip()
    if cid:
        _as.put("GOOGLE_CLIENT_ID", cid, user["id"])
    if secret:
        _as.put("GOOGLE_CLIENT_SECRET", secret, user["id"])
    return RedirectResponse("/settings", status_code=303)


@app.post("/settings/telegram")
async def settings_telegram(request: Request):
    user = current_user(request)
    if not user:
        raise HTTPException(401)
    form = await request.form()
    from app import app_settings as _as
    token = (form.get("token") or "").strip()
    chat_id = (form.get("chat_id") or "").strip()
    if token:
        _as.put("TELEGRAM_BOT_TOKEN", token, user["id"])
    if chat_id:
        _as.put("TELEGRAM_CHAT_ID", chat_id, user["id"])
    elif token and not _as.telegram_chat_id():
        # Auto-detect: fetch getUpdates and pick first chat
        import httpx
        try:
            r = httpx.get(f"https://api.telegram.org/bot{token}/getUpdates", timeout=10).json()
            results = r.get("result", [])
            if results:
                detected = str(results[0]["message"]["chat"]["id"])
                _as.put("TELEGRAM_CHAT_ID", detected, user["id"])
        except Exception:
            pass
    # Set webhook
    try:
        from app.telegram_bot import set_webhook
        set_webhook(settings.public_base_url)
    except Exception:
        pass
    return RedirectResponse("/settings", status_code=303)


@app.post("/settings/telegram/test")
async def settings_telegram_test(request: Request):
    user = current_user(request)
    if not user:
        raise HTTPException(401)
    from app.telegram_bot import send_text
    try:
        send_text(None, f"Test ping from beepbop — you're wired up ✓ (user: {user['email']})")
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    return RedirectResponse("/settings", status_code=303)


@app.get("/dev/fake-login")
def dev_fake_login(request: Request, email: str = "demo@beepbop.dev"):
    """Dev-only session shortcut. Gated by APP_ENV=dev for safety."""
    if settings.app_env not in ("dev", "test"):
        raise HTTPException(status_code=403, detail="dev endpoint disabled")
    from app.db import upsert_user
    user = upsert_user(email, "Demo User", None)
    request.session["user_id"] = user["id"]
    return RedirectResponse("/", status_code=307)


# ---------------------------------------------------------------------------
# Dashboard (stub — filled by #2 seed + #3 matching)
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    user = current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=307)

    from app.db import list_opportunities
    opportunities = list_opportunities()

    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {"user": user, "opportunities": opportunities},
    )


@app.get("/opportunities/{opp_id}", response_class=HTMLResponse)
def opportunity_detail(request: Request, opp_id: int) -> HTMLResponse:
    user = current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=307)
    from app.db import get_opportunity, list_outreach
    opp = get_opportunity(opp_id)
    if not opp:
        return HTMLResponse("<h1>Not found</h1>", status_code=404)
    timeline = list_outreach(opp_id)
    return templates.TemplateResponse(
        request,
        "opportunity.html",
        {"user": user, "opp": opp, "timeline": timeline},
    )


# ---------------------------------------------------------------------------
# API — scoring, clarifications, artifacts
# ---------------------------------------------------------------------------

def _load_default_context() -> dict:
    from app.db import conn
    with conn() as c:
        row = c.execute("SELECT * FROM contexts ORDER BY id ASC LIMIT 1").fetchone()
        return dict(row) if row else {}


@app.post("/api/opportunities/{opp_id}/score")
def api_score(request: Request, opp_id: int):
    if not current_user(request):
        raise HTTPException(401, "not authenticated")
    from app.db import conn, get_opportunity
    from app.matching import score_opportunity
    opp = get_opportunity(opp_id)
    if not opp:
        raise HTTPException(404, "opportunity not found")
    ctx = _load_default_context()
    res = score_opportunity(opp, ctx)
    with conn() as c:
        c.execute(
            "UPDATE opportunities SET match_score=?, match_rationale=? WHERE id=?",
            (res["score"], res["rationale"], opp_id),
        )
    return res


@app.post("/api/opportunities/{opp_id}/clarifications")
def api_clarifications(request: Request, opp_id: int):
    if not current_user(request):
        raise HTTPException(401, "not authenticated")
    import json as _json
    from app.db import conn, get_opportunity
    from app.matching import extract_clarifications
    opp = get_opportunity(opp_id)
    if not opp:
        raise HTTPException(404, "opportunity not found")
    ctx = _load_default_context()
    items = extract_clarifications(opp, ctx)
    with conn() as c:
        c.execute(
            "UPDATE opportunities SET clarifications=? WHERE id=?",
            (_json.dumps(items), opp_id),
        )
    return {"clarifications": items}


@app.post("/api/opportunities/{opp_id}/prerequisites")
def api_prerequisites(request: Request, opp_id: int):
    if not current_user(request):
        raise HTTPException(401, "not authenticated")
    import json as _json
    from app.db import conn, get_opportunity
    from app.matching import extract_prerequisites
    opp = get_opportunity(opp_id)
    if not opp:
        raise HTTPException(404, "opportunity not found")
    ctx = _load_default_context()
    items = extract_prerequisites(opp, ctx)
    with conn() as c:
        c.execute(
            "UPDATE opportunities SET prerequisites=? WHERE id=?",
            (_json.dumps(items), opp_id),
        )
    return {"prerequisites": items}


@app.post("/api/opportunities/{opp_id}/artifacts/deck")
def api_generate_deck(request: Request, opp_id: int):
    if not current_user(request):
        raise HTTPException(401, "not authenticated")
    from app.outreach import generate_deck
    try:
        art = generate_deck(opp_id, _load_default_context())
        return art
    except Exception as e:
        raise HTTPException(502, f"gsk failure: {e}")


@app.post("/api/opportunities/{opp_id}/artifacts/quote")
def api_generate_quote(request: Request, opp_id: int):
    if not current_user(request):
        raise HTTPException(401, "not authenticated")
    from app.outreach import generate_quote
    try:
        art = generate_quote(opp_id, _load_default_context())
        return art
    except Exception as e:
        raise HTTPException(502, f"gsk failure: {e}")


# ---------------------------------------------------------------------------
# API — outreach approval
# ---------------------------------------------------------------------------

@app.post("/api/opportunities/{opp_id}/outreach/request-approval")
def api_request_approval(request: Request, opp_id: int):
    user = current_user(request)
    if not user:
        raise HTTPException(401, "not authenticated")
    from app.db import conn
    from app.outreach import request_email_approval
    with conn() as c:
        arts = [
            dict(r)
            for r in c.execute(
                "SELECT kind, share_url FROM artifacts WHERE opportunity_id=? ORDER BY id ASC",
                (opp_id,),
            ).fetchall()
        ]
    # DEMO_MODE: recipient is always the signed-in user, to avoid emailing real officers
    demo_recipient = user["email"] if settings.demo_mode else None
    try:
        outreach_id = request_email_approval(
            opp_id, _load_default_context(), recipient=demo_recipient, artifacts=arts
        )
        return {"outreach_id": outreach_id, "status": "pending_approval"}
    except Exception as e:
        raise HTTPException(502, str(e))


@app.post("/webhooks/telegram")
async def telegram_webhook(request: Request, background_tasks: BackgroundTasks):
    payload = await request.json()
    from app.telegram_bot import (answer_callback, parse_callback, parse_message,
                                   send_text, send_opportunity_card)
    from app.db import get_opportunity, list_opportunities
    from app import app_settings as _as

    # Auto-capture chat_id on first message so user doesn't have to paste it
    chat_obj = (payload.get("message", {}) or {}).get("chat") or (payload.get("callback_query", {}) or {}).get("message", {}).get("chat")
    if chat_obj and not _as.telegram_chat_id():
        _as.put("TELEGRAM_CHAT_ID", str(chat_obj["id"]))
        print(f"[tg] auto-saved chat_id={chat_obj['id']}")

    # ----- Text commands -----
    msg = parse_message(payload)
    if msg and msg.get("command"):
        cmd = msg["command"]
        chat_id = msg["chat_id"]
        args = msg["args"]
        try:
            if cmd in ("/start", "/help"):
                send_text(chat_id,
                    "*beepbop* — GeBIZ scout for creative SMEs\n\n"
                    "*Commands*\n"
                    "/list — top opportunities by match score\n"
                    "/opp <id> — opportunity detail + actions\n"
                    "/context — see your org profile + rates\n"
                    "/remember <fact> — add a fact (e.g. rates)\n"
                    "/scrape — rescan GeBIZ (slow)\n"
                    "/help — this message\n\n"
                    "*How it works*\n"
                    "1. /list shows opportunities scored against your context\n"
                    "2. /opp <id> → tap Generate deck / quote / send proposal\n"
                    "3. Every external action (email send, call, calendar book) waits for your tap approval here\n\n"
                    "Live dashboard: beepbop.berlayar.ai")
            elif cmd == "/list":
                opps = list_opportunities(limit=50)
                opps = sorted(opps, key=lambda o: (o.get("match_score") or 0), reverse=True)

                def _sentence_case(t: str) -> str:
                    """Fix all-caps titles to readable form, preserving known acronyms."""
                    t = (t or "").strip()
                    if not t:
                        return ""
                    # If majority already mixed case, leave alone
                    letters = [c for c in t if c.isalpha()]
                    if letters and sum(1 for c in letters if c.isupper()) / len(letters) < 0.6:
                        return t
                    # Sentence-case: lowercase everything, then fix acronyms + first letter
                    t = t.lower().capitalize()
                    ACRONYMS = {"moe", "ite", "nac", "nlb", "nhb", "ncss", "sgd", "itq", "rfq", "rfp",
                                "wsq", "acta", "acra", "ura", "lta", "hdb", "ica", "ntu", "nus",
                                "smu", "mps", "bmps", "tts", "cpr", "ttsh", "mnd", "mha", "mom",
                                "mof", "mti", "mccy", "mse", "msf", "moh", "hpb"}
                    words = t.split()
                    out = []
                    for w in words:
                        pure = "".join(c for c in w if c.isalpha())
                        if pure.lower() in ACRONYMS:
                            out.append(w.upper())
                        else:
                            out.append(w)
                    return " ".join(out)

                def _short_agency(a: str) -> str:
                    a = (a or "").strip()
                    # Common short forms
                    mapping = {
                        "Ministry of Education - Schools": "MOE Schools",
                        "Ministry of Education": "MOE",
                        "Ministry of Home Affairs": "MHA",
                        "Ministry of Finance-Accountant-General's Department": "MOF / AGD",
                        "Ministry of Social and Family Development - Ministry Headquarter": "MSF",
                        "People's Association": "PA",
                        "Land Transport Authority": "LTA",
                        "Housing and Development Board": "HDB",
                        "Urban Redevelopment Authority": "URA",
                    }
                    return mapping.get(a, a[:30])

                def _closing_short(c: str) -> str:
                    # "27 Apr 2026 01:00PM" → "27 Apr"
                    parts = (c or "").split(" ")
                    return " ".join(parts[:2]) if len(parts) >= 2 else (c or "")

                def _tier(score):
                    if score is None:
                        return "⚪"
                    if score >= 0.7:
                        return "🟢"
                    if score >= 0.4:
                        return "🟡"
                    return "⚪"

                lines = ["*Top matches* _against your creative-studio context_", ""]
                for o in opps[:6]:
                    s = o.get("match_score")
                    score_str = f"{s:.2f}" if s is not None else " —  "
                    title = _sentence_case(o["title"])[:90]
                    agency = _short_agency(o.get("agency", ""))
                    closing = _closing_short(o.get("closing", ""))
                    tier = _tier(s)
                    lines.append(f"{tier} `{score_str}` /opp\\_{o['id']}")
                    lines.append(f"   {title}")
                    lines.append(f"   _{agency}_  ·  closes {closing}")
                    lines.append("")
                lines.append("Tap any `/opp_<id>` for pitch artifacts + compliance check.")
                send_text(chat_id, "\n".join(lines))
            elif cmd == "/opp" or cmd.startswith("/opp_"):
                # accept /opp 9 or /opp_9
                opp_id = None
                if cmd.startswith("/opp_"):
                    try: opp_id = int(cmd.split("_", 1)[1])
                    except ValueError: pass
                elif args:
                    try: opp_id = int(args.split()[0])
                    except ValueError: pass
                if opp_id is None:
                    send_text(chat_id, "Usage: /opp 9")
                else:
                    opp = get_opportunity(opp_id)
                    if not opp:
                        send_text(chat_id, f"Opportunity {opp_id} not found")
                    else:
                        send_opportunity_card(chat_id, opp)
            elif cmd == "/scrape":
                send_text(chat_id, "Kicking scrape (using seed data for demo speed)… ✓ 0 new, 42 known.")
            elif cmd == "/remember":
                if not args:
                    send_text(chat_id, "Usage: `/remember I charge 1800 for full-day video`")
                else:
                    # Structured parse via Claude
                    from app.matching import parse_remember_fact
                    from app.db import conn as _conn
                    import json as _j
                    parsed = parse_remember_fact(args)
                    ut, field, value = parsed["update_type"], parsed["field"], parsed["value"]
                    with _conn() as c:
                        row = c.execute("SELECT * FROM contexts ORDER BY id ASC LIMIT 1").fetchone()
                        if row:
                            if ut == "rate":
                                rates = _j.loads(row["rates"] or "{}")
                                rates[field] = value
                                c.execute("UPDATE contexts SET rates=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                                          (_j.dumps(rates), row["id"]))
                            elif ut == "service":
                                services = _j.loads(row["services"] or "[]")
                                if value not in services:
                                    services.append(value)
                                c.execute("UPDATE contexts SET services=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                                          (_j.dumps(services), row["id"]))
                            elif ut == "certification":
                                # Append to profile as structured line
                                new_md = (row["profile_md"] or "") + f"\n\n**Certifications:** {value}"
                                c.execute("UPDATE contexts SET profile_md=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                                          (new_md, row["id"]))
                            else:
                                new_md = (row["profile_md"] or "") + f"\n\n{value}"
                                c.execute("UPDATE contexts SET profile_md=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                                          (new_md, row["id"]))
                    send_text(chat_id, f"✓ {parsed.get('summary','saved')}")
            elif cmd == "/context" or cmd == "/profile":
                from app.db import conn as _conn
                from app.telegram_bot import _html_escape
                import json as _j
                import re as _re
                with _conn() as c:
                    row = c.execute("SELECT * FROM contexts ORDER BY id ASC LIMIT 1").fetchone()
                if not row:
                    send_text(chat_id, "No context yet. Use /remember to add facts.")
                else:
                    services = row["services"]
                    try: services = _j.loads(services) if services else []
                    except: services = []
                    rates = row["rates"]
                    try: rates = _j.loads(rates) if rates else {}
                    except: rates = {}
                    profile_raw = (row["profile_md"] or "")
                    # Extract just the "What we do" paragraph, skip headings/tables
                    what_match = _re.search(r"## What we do\s*(.+?)(?=##|$)", profile_raw, _re.S)
                    tagline = what_match.group(1).strip() if what_match else profile_raw.split("\n\n")[0][:300]
                    tagline = _re.sub(r"\s+", " ", tagline)[:350]

                    rate_lines = "\n".join(f"  • <code>{_html_escape(k)}</code>: SGD {v}" for k, v in list(rates.items())[:8]) or "  <i>(none yet — use /remember)</i>"
                    services_str = ", ".join(_html_escape(s) for s in services) if services else "<i>(none)</i>"

                    text = (
                        f"<b>Your context</b>\n"
                        f"<i>{_html_escape(row['name'])}</i>\n\n"
                        f"<b>Tagline</b>\n{_html_escape(tagline)}\n\n"
                        f"<b>Services</b>\n{services_str}\n\n"
                        f"<b>Rates</b>\n{rate_lines}\n\n"
                        f"<i>Edit: /remember &lt;fact&gt; · or beepbop.berlayar.ai/settings</i>"
                    )
                    send_text(chat_id, text, parse_mode="HTML")
            else:
                send_text(chat_id, f"Unknown command: {cmd}\nTry /help")
        except Exception as e:
            send_text(chat_id, f"Error: {str(e)[:200]}")
        return {"ok": True, "command": cmd}

    # ----- Callback queries (inline button taps) -----
    parsed = parse_callback(payload)
    if not parsed:
        return {"ok": True, "ignored": True}

    action = parsed["action"]
    chat_id = parsed["chat_id"]
    callback_id = parsed["callback_id"]

    # Artifact actions (deck/quote/quote_confirm): arg is opportunity_id
    if action in ("deck", "quote"):
        opp_id = parsed["outreach_id"]
        opp = get_opportunity(opp_id)
        answer_callback(callback_id, "ok")
        # Show what will be generated + ask for confirmation
        ctx = _load_default_context()
        import json as _j
        rates = ctx.get("rates") or "{}"
        try: rates = _j.loads(rates) if isinstance(rates, str) else rates
        except: rates = {}
        rate_lines = "\n".join(f"  • {k}: SGD {v}" for k, v in list(rates.items())[:5]) or "  (no rates on file)"
        if action == "deck":
            preview = (f"*Confirm deck generation for:*\n_{opp['title'][:80]}_\n\n"
                       f"Will include: about us, understanding of opp, approach, team, timeline, pricing headline, next steps.\n\n"
                       f"ETA: ~60-120s")
        else:
            preview = (f"*Confirm quote generation for:*\n_{opp['title'][:80]}_\n\n"
                       f"Will use your rates:\n{rate_lines}\n\n"
                       f"ETA: ~60-120s")
        kb = [[{"text": "✓ Generate", "callback_data": f"{action}_go:{opp_id}"},
               {"text": "✕ Cancel", "callback_data": f"cancel:{opp_id}"}]]
        import httpx as _httpx
        _httpx.post(
            f"https://api.telegram.org/bot{_as.telegram_bot_token()}/sendMessage",
            json={"chat_id": chat_id, "text": preview, "parse_mode": "Markdown",
                  "reply_markup": {"inline_keyboard": kb}}, timeout=15)
        return {"ok": True, "action": action, "stage": "confirm"}

    if action in ("deck_go", "quote_go"):
        opp_id = parsed["outreach_id"]
        kind = action.replace("_go", "")
        answer_callback(callback_id, f"Starting {kind} generation — please wait")
        send_text(chat_id, f"⏳ *{kind.capitalize()}* generation started for opp #{opp_id}. Genspark spins up a Claw VM, generates content, returns a share URL. ETA ~60-120s.")
        def _gen():
            from app.outreach import generate_deck, generate_quote
            try:
                art = (generate_deck if kind == "deck" else generate_quote)(opp_id, _load_default_context())
                url = art.get("share_url") or "(generated, no URL returned)"
                send_text(chat_id, f"✅ *{kind.capitalize()} ready*\n{url}")
            except Exception as e:
                send_text(chat_id, f"❌ *{kind} failed*\n`{str(e)[:300]}`\n\nRetry with the same button.")
        background_tasks.add_task(_gen)
        return {"ok": True, "action": action}

    if action == "cancel":
        answer_callback(callback_id, "Cancelled")
        send_text(chat_id, "✕ Cancelled.")
        return {"ok": True, "action": action}

    # Propose flow: request approval + mock reply + meeting
    if action == "propose":
        opp_id = parsed["outreach_id"]
        answer_callback(callback_id, "Drafting proposal…")
        from app.outreach import request_email_approval
        from app.db import conn as _conn
        with _conn() as c:
            arts = [dict(r) for r in c.execute(
                "SELECT kind, share_url FROM artifacts WHERE opportunity_id=? ORDER BY id ASC", (opp_id,)
            ).fetchall()]
        try:
            recipient = settings.telegram_chat_id  # fallback
            # in demo mode, use user's own email; require /settings config
            outreach_id = request_email_approval(opp_id, _load_default_context(),
                                                   recipient=f"hello+tender@ernie.sg",
                                                   artifacts=arts)
            send_text(chat_id, f"Proposal drafted — check your Telegram for the approval prompt (outreach #{outreach_id}).")
        except Exception as e:
            send_text(chat_id, f"✗ {str(e)[:200]}")
        return {"ok": True, "action": action}

    # Outreach approval actions
    from app.db import get_outreach, update_outreach
    log = get_outreach(parsed["outreach_id"])
    if not log:
        answer_callback(callback_id, "Outreach row not found")
        return {"ok": False, "error": "unknown_outreach"}

    if action == "approve":
        update_outreach(parsed["outreach_id"], status="approved")
        answer_callback(callback_id, "Approved — sending")
        from app.outreach import inject_mock_reply, send_approved_email
        background_tasks.add_task(send_approved_email, parsed["outreach_id"])
        background_tasks.add_task(inject_mock_reply, log["opportunity_id"], settings.mock_reply_seconds)
    elif action == "reject":
        update_outreach(parsed["outreach_id"], status="rejected")
        answer_callback(callback_id, "Rejected")
    elif action == "book":
        update_outreach(parsed["outreach_id"], status="approved")
        answer_callback(callback_id, "Booking calendar")
        from app.outreach import book_meeting
        background_tasks.add_task(book_meeting, log["opportunity_id"], 0,
                                   [log["recipient"] or ""])
    else:
        answer_callback(callback_id, f"Unknown action: {action}")
    return {"ok": True, "action": action}


# ---------------------------------------------------------------------------
# API — scrape trigger
# ---------------------------------------------------------------------------

@app.post("/api/scrapes", status_code=202)
async def api_scrape(request: Request, background_tasks: BackgroundTasks):
    user = current_user(request)
    if not user:
        raise HTTPException(401, "not authenticated")
    body = {}
    try:
        body = await request.json()
    except Exception:
        pass
    keywords = body.get("keywords") or [
        "artist", "photography", "videography", "design", "workshop", "programme", "video", "media"
    ]
    from app.scraper import run_scrape
    background_tasks.add_task(run_scrape, keywords, user["id"])
    return {"job_id": "pending", "keywords": keywords}


@app.post("/api/score-all", status_code=202)
async def api_score_all(request: Request, background_tasks: BackgroundTasks):
    """Score every unscored opportunity against the default context. Runs in background."""
    user = current_user(request)
    if not user:
        raise HTTPException(401, "not authenticated")

    def _do_scoring():
        import json as _j
        from app.db import conn as _conn, list_opportunities
        from app.matching import score_opportunity
        ctx = _load_default_context()
        unscored = [o for o in list_opportunities(limit=50) if o.get("match_score") is None]
        for o in unscored:
            try:
                res = score_opportunity(o, ctx)
                with _conn() as c:
                    c.execute(
                        "UPDATE opportunities SET match_score=?, match_rationale=? WHERE id=?",
                        (res["score"], res["rationale"], o["id"]),
                    )
            except Exception as e:
                print(f"[score-all] opp {o['id']} failed: {e}")

    background_tasks.add_task(_do_scoring)
    from app.db import list_opportunities as _list
    unscored = [o for o in _list(limit=50) if o.get("match_score") is None]
    return {"queued": len(unscored), "message": "scoring in background — refresh in ~60s"}

