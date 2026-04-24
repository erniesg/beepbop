"""Scraper wrapper — imports scraper_core in-process, no shelling out."""
from __future__ import annotations

import asyncio
import json
import tempfile
from datetime import datetime
from pathlib import Path

from app.config import get_settings
from app.db import conn


async def run_scrape(
    keywords: list[str],
    owner_id: int | None,
    max_pages: int = 3,
) -> dict:
    """Kick off a scrape; ingest results; record job status. Returns summary dict."""
    settings = get_settings()
    with conn() as c:
        cur = c.execute(
            "INSERT INTO scrape_jobs (owner_id, keywords, status, started_at) VALUES (?, ?, 'running', ?)",
            (owner_id, json.dumps(keywords), datetime.utcnow().isoformat()),
        )
        job_id = int(cur.lastrowid)

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

            result = await asyncio.wait_for(
                asyncio.to_thread(_blocking),
                timeout=settings.scrape_timeout_seconds,
            )
            records = result.get("records", [])

        # Ingest
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
        with conn() as c:
            c.execute(
                "UPDATE scrape_jobs SET status='failed', error=?, finished_at=? WHERE id=?",
                (str(e)[:500], datetime.utcnow().isoformat(), job_id),
            )
        raise
