"""Scraper wrapper — imports scraper_core in-process, no shelling out."""
from __future__ import annotations

import asyncio
import json
import tempfile
from datetime import datetime
from pathlib import Path

from app.config import get_settings
from app.db import conn


class ScrapeAlreadyRunning(RuntimeError):
    """A scrape is already in-flight — refuse to start another."""


def running_scrape_id() -> int | None:
    """Return the id of an in-flight scrape if any, else None."""
    with conn() as c:
        row = c.execute(
            "SELECT id FROM scrape_jobs WHERE status IN ('running','queued') ORDER BY id DESC LIMIT 1"
        ).fetchone()
    return int(row["id"]) if row else None


def create_scrape_job(keywords: list[str], owner_id: int | None) -> int:
    """Atomically create a scrape job row.

    Must be called synchronously before spawning the background task, so that
    a rapid second click finds the row and bails out (see ScrapeAlreadyRunning).
    Raises ScrapeAlreadyRunning if one is already in flight.
    """
    with conn() as c:
        c.execute("BEGIN IMMEDIATE")
        row = c.execute(
            "SELECT id FROM scrape_jobs WHERE status IN ('running','queued') LIMIT 1"
        ).fetchone()
        if row:
            raise ScrapeAlreadyRunning(
                f"scrape #{row['id']} already in flight — wait or inspect /api/scrape-status"
            )
        cur = c.execute(
            "INSERT INTO scrape_jobs (owner_id, keywords, status, started_at) VALUES (?, ?, 'running', ?)",
            (owner_id, json.dumps(keywords), datetime.utcnow().isoformat()),
        )
        return int(cur.lastrowid)


async def run_scrape_job(
    job_id: int,
    keywords: list[str],
    max_pages: int = 3,
    notify_chat_id: str | None = None,
    with_docs: bool = False,
    login_wait_seconds: int = 120,
    awarded_only: bool = False,
) -> dict:
    """Execute a previously-created scrape job. Ingests results, updates status.

    On completion (done or failed), emits a Telegram DM to notify_chat_id (if
    provided) or the configured admin chat_id. Always safe — failures to DM
    are swallowed so the scrape result is still returned.
    """
    settings = get_settings()

    def _notify(text: str) -> None:
        try:
            from app.telegram_bot import send_text
            send_text(notify_chat_id, text)
        except Exception:
            pass  # DM is best-effort; don't fail the job

    try:
        from app.scraper_core import run_search

        # Persistent profile for docs-mode AND awarded-mode — the awarded $ amount
        # + supplier are Singpass-gated (confirmed: invisible on public pages),
        # so we reuse cookies from a prior /scrape_docs run. Headless either way;
        # if the session is stale, awarded fields just come back blank and we
        # nudge the user to run /scrape_docs to refresh.
        profile_root = (
            Path.home() / ".beepbop" / "gebiz_profile"
            if (with_docs or awarded_only)
            else None
        )
        if profile_root:
            profile_root.mkdir(parents=True, exist_ok=True)

        def _notify_safe(text: str) -> None:
            try:
                from app.telegram_bot import send_text
                send_text(notify_chat_id, text)
            except Exception:
                pass

        # Awarded amounts + suppliers are Singpass-gated, same as tender PDFs.
        # So awarded_only opens the visible-browser login handoff just like docs mode.
        needs_login = with_docs or awarded_only

        def _login_state(state: str) -> None:
            after = "starting document download" if with_docs else "starting awarded-tender scrape"
            msg = {
                "browser_open": "🪟 Chrome opened on your Mac. Log in with Singpass — I'll watch for the Logout link to appear and proceed automatically.",
                "login_detected": f"✅ Singpass login detected — {after}.",
                "login_timeout": f"⏱ Login wait expired after {login_wait_seconds}s — proceeding without auth (amounts/docs may be blank).",
            }.get(state)
            if msg:
                _notify_safe(msg)

        # Timeout budget — both docs and awarded modes need login wait time;
        # awarded additionally chews through ~15 detail pages (~3s each).
        extra = 0
        if with_docs:
            extra = login_wait_seconds + 300
        elif awarded_only:
            extra = login_wait_seconds + 300
        effective_timeout = settings.scrape_timeout_seconds + extra

        # For docs mode, use a persistent output dir so downloads survive past job end
        persistent_docs_root = Path.home() / ".beepbop" / "docs"
        if with_docs:
            persistent_docs_root.mkdir(parents=True, exist_ok=True)

        # Awarded mode caps the work to keep the run snappy — 15 awarded rows
        # is plenty to seed pricing analytics for v1.
        effective_max = 15 if awarded_only else (max_pages * 15)

        async def _run_blocking(output_dir: str) -> dict:
            def _blocking() -> dict:
                return run_search(
                    keywords=keywords,
                    output_dir=output_dir,
                    max_total=effective_max,
                    profile_dir=str(profile_root) if profile_root else str(Path(output_dir) / "profile"),
                    # Visible browser whenever we need auth (docs OR awarded mode).
                    headless=not needs_login,
                    # Only download tender PDFs in docs mode — awarded mode just needs amounts.
                    skip_downloads=not with_docs,
                    wait_for_login_seconds=login_wait_seconds if needs_login else 0,
                    on_login_state=_login_state if needs_login else None,
                    awarded_only=awarded_only,
                )
            return await asyncio.wait_for(asyncio.to_thread(_blocking), timeout=effective_timeout)

        try:
            if with_docs:
                result = await _run_blocking(str(persistent_docs_root))
            else:
                with tempfile.TemporaryDirectory(prefix="beepbop_scrape_") as tmpdir:
                    result = await _run_blocking(tmpdir)
        except asyncio.TimeoutError as te:
            raise TimeoutError(
                f"scrape timed out after {effective_timeout}s "
                f"(keywords={keywords!r}, with_docs={with_docs}); "
                f"trim keyword list or raise scrape_timeout_seconds"
            ) from te
        records = result.get("records", [])

        from app.seed import ensure_default_context, ingest_opportunities

        ctx_id = ensure_default_context()
        rows = ingest_opportunities(records, context_id=ctx_id)

        with conn() as c:
            c.execute(
                "UPDATE scrape_jobs SET status='done', rows_ingested=?, finished_at=? WHERE id=?",
                (rows, datetime.utcnow().isoformat(), job_id),
            )
        _notify(
            f"✅ <b>Scrape #{job_id} done</b>\n"
            f"Keywords: <code>{' '.join(keywords)[:120]}</code>\n"
            f"Ingested: {rows} new/updated rows — use <b>/list</b>."
        )
        return {"job_id": job_id, "rows_ingested": rows, "status": "done"}

    except Exception as e:
        err = str(e) or f"{type(e).__name__}: (no message)"
        with conn() as c:
            c.execute(
                "UPDATE scrape_jobs SET status='failed', error=?, finished_at=? WHERE id=?",
                (err[:500], datetime.utcnow().isoformat(), job_id),
            )
        _notify(f"❌ <b>Scrape #{job_id} failed</b>\n<code>{err[:300]}</code>")
        raise


async def run_scrape(keywords: list[str], owner_id: int | None, max_pages: int = 3) -> dict:
    """Back-compat wrapper: create job + run it. Prefer create_scrape_job + run_scrape_job for endpoints."""
    job_id = create_scrape_job(keywords, owner_id)
    return await run_scrape_job(job_id, keywords, max_pages)
