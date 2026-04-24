"""Seed loader: ingest a gebiz_contacts.py JSON output into the DB.

Usage:
    python -m app.seed                  # uses data/opportunities.json
    python -m app.seed path/to/file.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Iterable

from app.config import ROOT
from app.db import conn, init

DEFAULT_JSON = ROOT / "data" / "opportunities.json"
DEFAULT_CONTEXT_MD = ROOT / "data" / "context.md"


def ingest_opportunities(records: Iterable[dict], context_id: int | None = None) -> int:
    """Upsert opportunities + derive contacts. Returns rows inserted/updated."""
    rows = 0
    with conn() as c:
        for r in records:
            opp_no = r.get("opportunity_no")
            if not opp_no:
                continue

            raw_json = json.dumps(r, ensure_ascii=False)
            # Upsert
            c.execute(
                """
                INSERT INTO opportunities
                  (opportunity_no, title, agency, status, closing, procurement_category,
                   detail_url, raw_json, matched_keyword, context_id,
                   awarded_amount, awarded_supplier, awarded_at, award_currency)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(opportunity_no) DO UPDATE SET
                  title = excluded.title,
                  agency = excluded.agency,
                  status = excluded.status,
                  closing = excluded.closing,
                  procurement_category = excluded.procurement_category,
                  raw_json = excluded.raw_json,
                  -- Only overwrite awarded fields when the new scrape actually
                  -- has them — preserves data when re-scraping in OPEN mode.
                  awarded_amount = COALESCE(excluded.awarded_amount, opportunities.awarded_amount),
                  awarded_supplier = COALESCE(NULLIF(excluded.awarded_supplier, ''), opportunities.awarded_supplier),
                  awarded_at = COALESCE(NULLIF(excluded.awarded_at, ''), opportunities.awarded_at),
                  award_currency = COALESCE(NULLIF(excluded.award_currency, ''), opportunities.award_currency)
                """,
                (
                    opp_no,
                    r.get("title", "").strip() or "(untitled)",
                    r.get("agency"),
                    r.get("status"),
                    r.get("closing"),
                    r.get("procurement_category"),
                    r.get("detail_url"),
                    raw_json,
                    r.get("matched_keyword"),
                    context_id,
                    r.get("awarded_amount"),
                    r.get("awarded_supplier"),
                    r.get("awarded_at"),
                    r.get("award_currency"),
                ),
            )
            rows += 1

            opp_id = c.execute(
                "SELECT id FROM opportunities WHERE opportunity_no = ?", (opp_no,)
            ).fetchone()["id"]

            # Clear then re-insert contacts for this opportunity (idempotent)
            c.execute("DELETE FROM contacts WHERE opportunity_id = ?", (opp_id,))
            for role in ("primary", "secondary", "awarding"):
                name = r.get(f"{role}_contact_name")
                email = r.get(f"{role}_contact_email")
                phone = r.get(f"{role}_contact_phone")
                if not any((name, email, phone)):
                    continue
                c.execute(
                    """
                    INSERT INTO contacts (name, email, phone, role, agency, opportunity_id)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (name, email, phone, role, r.get("agency"), opp_id),
                )
    return rows


def ensure_default_context() -> int:
    """Create the seed 'ernie.sg creative studio' context if none exists; return its id."""
    with conn() as c:
        row = c.execute("SELECT id FROM contexts ORDER BY id ASC LIMIT 1").fetchone()
        if row:
            return int(row["id"])
        profile_md = DEFAULT_CONTEXT_MD.read_text() if DEFAULT_CONTEXT_MD.exists() else ""
        services = json.dumps(
            ["photography", "videography", "editing", "workshop", "creative direction"]
        )
        rates = json.dumps(
            {"photography_halfday": 600, "videography_fullday": 1400, "workshop_fullday": 1800}
        )
        cur = c.execute(
            "INSERT INTO contexts (owner_id, name, profile_md, services, rates) VALUES (?, ?, ?, ?, ?)",
            (None, "ernie.sg creative studio", profile_md, services, rates),
        )
        return int(cur.lastrowid)


def run_seed(json_path: Path | None = None) -> dict:
    """Init schema, seed default context, ingest opportunities. Returns summary."""
    init()
    ctx_id = ensure_default_context()
    path = json_path or DEFAULT_JSON
    if not path.exists():
        raise FileNotFoundError(f"seed JSON not found: {path}")
    records = json.loads(path.read_text())
    rows = ingest_opportunities(records, context_id=ctx_id)
    from app.db import count
    return {
        "context_id": ctx_id,
        "rows_ingested": rows,
        "opportunities_total": count("opportunities"),
        "contacts_total": count("contacts"),
    }


if __name__ == "__main__":
    arg = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    summary = run_seed(arg)
    print(json.dumps(summary, indent=2))
