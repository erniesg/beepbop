from __future__ import annotations

import json
import sqlite3
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from app.config import ROOT, get_settings


SCHEMA_PATH = ROOT / "data" / "schema.sql"


def _connect() -> sqlite3.Connection:
    settings = get_settings()
    settings.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(settings.sqlite_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def conn() -> Iterator[sqlite3.Connection]:
    c = _connect()
    try:
        yield c
        c.commit()
    except Exception:
        c.rollback()
        raise
    finally:
        c.close()


def init() -> None:
    """Create all tables if missing, then run idempotent additive migrations."""
    with conn() as c:
        c.executescript(SCHEMA_PATH.read_text())
    _run_additive_migrations()
    print(f"[db] initialized at {get_settings().sqlite_path}", file=sys.stderr)


# Additive-only migrations: each statement runs and we swallow the
# "duplicate column" error when the column already exists. We avoid a
# real migration framework because the hackathon timeline doesn't justify it.
_ADDITIVE_MIGRATIONS: list[str] = [
    "ALTER TABLE opportunities ADD COLUMN awarded_amount REAL",
    "ALTER TABLE opportunities ADD COLUMN awarded_supplier TEXT",
    "ALTER TABLE opportunities ADD COLUMN awarded_at TEXT",
    "ALTER TABLE opportunities ADD COLUMN award_currency TEXT",
]


def _run_additive_migrations() -> None:
    with conn() as c:
        for sql in _ADDITIVE_MIGRATIONS:
            try:
                c.execute(sql)
            except sqlite3.OperationalError as e:
                if "duplicate column" not in str(e).lower():
                    raise


def ensure_schema() -> None:
    """Run migrations without re-creating tables — safe at app startup."""
    _run_additive_migrations()


def count(table: str) -> int:
    with conn() as c:
        row = c.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()
        return int(row["n"])


# User helpers --------------------------------------------------------------

def upsert_user(email: str, name: str | None, picture: str | None) -> dict:
    with conn() as c:
        c.execute(
            "INSERT INTO users (email, name, picture) VALUES (?, ?, ?) "
            "ON CONFLICT(email) DO UPDATE SET name=excluded.name, picture=excluded.picture",
            (email, name, picture),
        )
        row = c.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        return dict(row)


def get_user(user_id: int) -> dict | None:
    with conn() as c:
        row = c.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return dict(row) if row else None


def get_user_by_email(email: str) -> dict | None:
    with conn() as c:
        row = c.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        return dict(row) if row else None


# Opportunity helpers -------------------------------------------------------

def list_opportunities(context_id: int | None = None, limit: int = 50) -> list[dict]:
    sql = "SELECT * FROM opportunities"
    args: tuple[Any, ...] = ()
    if context_id is not None:
        sql += " WHERE context_id = ?"
        args = (context_id,)
    sql += " ORDER BY discovered_at DESC LIMIT ?"
    args = args + (limit,)
    with conn() as c:
        return [dict(r) for r in c.execute(sql, args).fetchall()]


def get_opportunity(opp_id: int) -> dict | None:
    with conn() as c:
        row = c.execute("SELECT * FROM opportunities WHERE id = ?", (opp_id,)).fetchone()
        if not row:
            return None
        d = dict(row)
        if d.get("raw_json"):
            try:
                d["raw"] = json.loads(d["raw_json"])
            except (json.JSONDecodeError, TypeError):
                d["raw"] = {}
        return d


# Outreach helpers ----------------------------------------------------------

def insert_outreach(**fields: Any) -> int:
    cols = ", ".join(fields.keys())
    placeholders = ", ".join(["?"] * len(fields))
    with conn() as c:
        cur = c.execute(
            f"INSERT INTO outreach_log ({cols}) VALUES ({placeholders})",
            tuple(fields.values()),
        )
        return int(cur.lastrowid)


def update_outreach(outreach_id: int, **fields: Any) -> None:
    assignments = ", ".join(f"{k} = ?" for k in fields)
    args = (*fields.values(), outreach_id)
    with conn() as c:
        c.execute(
            f"UPDATE outreach_log SET {assignments}, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            args,
        )


def get_outreach(outreach_id: int) -> dict | None:
    with conn() as c:
        row = c.execute("SELECT * FROM outreach_log WHERE id = ?", (outreach_id,)).fetchone()
        return dict(row) if row else None


def list_outreach(opportunity_id: int) -> list[dict]:
    with conn() as c:
        rows = c.execute(
            "SELECT * FROM outreach_log WHERE opportunity_id = ? ORDER BY created_at ASC",
            (opportunity_id,),
        ).fetchall()
        return [dict(r) for r in rows]


# CLI entry -----------------------------------------------------------------

if __name__ == "__main__":
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "init"
    if cmd == "init":
        init()
    else:
        raise SystemExit(f"unknown command: {cmd}")
