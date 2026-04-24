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


async def run_scrape_job(job_id: int, keywords: list[str], max_pages: int = 3) -> dict:
    """Execute a previously-created scrape job. Ingests results, updates status."""
    settings = get_settings()
    try:
        from app.scraper_core import run_search

        with tempfile.TemporaryDirectory(prefix="beepbop_scrape_") as tmpdir:
            def _blocking() -> dict:
                return run_search(
                    keywords=keywords,
                    output_dir=tmpdir,
                    max_total=max_pages * 15,
                    profile_dir=str(Path(tmpdir) / "profile"),
                    headless=True,
                    skip_downloads=True,
                )

            try:
                result = await asyncio.wait_for(
                    asyncio.to_thread(_blocking),
                    timeout=settings.scrape_timeout_seconds,
                )
            except asyncio.TimeoutError as te:
                raise TimeoutError(
                    f"scrape timed out after {settings.scrape_timeout_seconds}s "
                    f"(keywords={keywords!r}); trim the keyword list or raise scrape_timeout_seconds"
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
        return {"job_id": job_id, "rows_ingested": rows, "status": "done"}

    except Exception as e:
        err = str(e) or f"{type(e).__name__}: (no message)"
        with conn() as c:
            c.execute(
                "UPDATE scrape_jobs SET status='failed', error=?, finished_at=? WHERE id=?",
                (err[:500], datetime.utcnow().isoformat(), job_id),
            )
        raise


async def run_scrape(keywords: list[str], owner_id: int | None, max_pages: int = 3) -> dict:
    """Back-compat wrapper: create job + run it. Prefer create_scrape_job + run_scrape_job for endpoints."""
    job_id = create_scrape_job(keywords, owner_id)
    return await run_scrape_job(job_id, keywords, max_pages)
