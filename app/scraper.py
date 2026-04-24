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

        # Persistent profile for docs-mode so the Singpass session survives between runs
        profile_root = (
            Path.home() / ".beepbop" / "gebiz_profile"
            if with_docs
            else None
        )
        if profile_root:
            profile_root.mkdir(parents=True, exist_ok=True)

        # Trust the persistent profile: if a non-empty Cookies file already exists
        # we skip the visible-browser QR step and go straight to a headless scrape.
        # Downloads succeed when the session is still valid, fail gracefully when
        # it's not — much less brittle than the page.evaluate-based login probe
        # which kept dying with "Execution context was destroyed".
        cookies_file = profile_root / "Default" / "Cookies" if profile_root else None
        cookies_present = bool(
            cookies_file and cookies_file.exists() and cookies_file.stat().st_size > 1024
        )
        effective_login_wait = 0 if (with_docs and cookies_present) else (
            login_wait_seconds if with_docs else 0
        )

        def _notify_safe(text: str) -> None:
            try:
                from app.telegram_bot import send_text
                send_text(notify_chat_id, text)
            except Exception:
                pass

        if with_docs and cookies_present:
            _notify_safe(
                "🍪 <b>Reusing saved Singpass session</b> — skipping QR step. "
                "If downloads come back empty, run /scrape_docs again to refresh the session."
            )

        def _login_state(state: str) -> None:
            msg = {
                "browser_open": "🪟 Chrome opened on your Mac. Scan Singpass QR to log in — I'll poll for access every 3s.",
                "login_detected": "✅ Singpass login detected — starting keyword scrape + document download.",
                "login_timeout": f"⏱ Login wait expired after {login_wait_seconds}s — proceeding without doc access.",
            }.get(state)
            if msg:
                _notify_safe(msg)

        # Timeout budget: docs mode needs login wait + download time, so add headroom
        effective_timeout = settings.scrape_timeout_seconds + (
            effective_login_wait + 300 if with_docs else 0
        )

        # For docs mode, use a persistent output dir so downloads survive past job end
        persistent_docs_root = Path.home() / ".beepbop" / "docs"
        if with_docs:
            persistent_docs_root.mkdir(parents=True, exist_ok=True)

        async def _run_blocking(output_dir: str) -> dict:
            def _blocking() -> dict:
                return run_search(
                    keywords=keywords,
                    output_dir=output_dir,
                    max_total=max_pages * 15,
                    profile_dir=str(profile_root) if profile_root else str(Path(output_dir) / "profile"),
                    # Hide browser when we're trusting cached cookies — only pop a
                    # visible window if we genuinely need the user to scan a QR.
                    headless=not (with_docs and effective_login_wait > 0),
                    skip_downloads=not with_docs,
                    wait_for_login_seconds=effective_login_wait,
                    on_login_state=_login_state if with_docs and effective_login_wait > 0 else None,
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
