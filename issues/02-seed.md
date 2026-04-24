# #2 — Seed workshop DB + live scrape trigger

**Time:** 15 min
**Depends:** #1

## Red

```python
# tests/test_seed.py
def test_seed_loads_20_opportunities(tmp_db):
    from app.seed import run_seed
    run_seed()
    from app.db import count
    assert count("opportunities") >= 20
    assert count("contacts") >= 5
    assert count("contexts") == 1

def test_seed_is_idempotent(tmp_db):
    from app.seed import run_seed
    run_seed(); run_seed()
    from app.db import count
    assert count("opportunities") == 20  # no duplicates

# tests/test_scrape.py
def test_scrape_endpoint_enqueues_job(client, authed):
    r = client.post("/api/scrapes", json={"keywords": ["artist", "design"]})
    assert r.status_code == 202
    assert "job_id" in r.json()
```

## Green

1. **`app/seed.py`** — loads `data/opportunities.json` (copy of `../tmp/gebiz_contacts_live6/gebiz-opportunities-20260423-233132.json`) into SQLite. Dedup on `opportunity_no`. Creates derived `contacts` rows from unique `awarding_contact_email`. Creates one default `contexts` row for the signed-in user if none exists.
2. **`data/schema.sql`**:
   ```sql
   CREATE TABLE contexts (
     id INTEGER PRIMARY KEY AUTOINCREMENT,
     owner_id INTEGER REFERENCES users(id),
     name TEXT NOT NULL,
     profile_md TEXT,
     services TEXT,  -- JSON array
     rates TEXT,     -- JSON object
     keywords TEXT,  -- JSON array, populated by LLM
     created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
   );
   CREATE TABLE opportunities (
     id INTEGER PRIMARY KEY AUTOINCREMENT,
     opportunity_no TEXT UNIQUE NOT NULL,
     title TEXT NOT NULL,
     agency TEXT,
     status TEXT,
     closing TEXT,
     procurement_category TEXT,
     raw_json TEXT,  -- full JSON blob
     match_score REAL,
     match_rationale TEXT,
     clarifications TEXT,  -- JSON array
     mock_reply_after_seconds INTEGER,
     policy_mode TEXT DEFAULT 'human',  -- 'auto' | 'human'
     discovered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
     context_id INTEGER REFERENCES contexts(id)
   );
   CREATE TABLE contacts (
     id INTEGER PRIMARY KEY AUTOINCREMENT,
     name TEXT,
     email TEXT,
     phone TEXT,
     role TEXT,
     agency TEXT,
     opportunity_id INTEGER REFERENCES opportunities(id)
   );
   CREATE TABLE artifacts (
     id INTEGER PRIMARY KEY AUTOINCREMENT,
     opportunity_id INTEGER REFERENCES opportunities(id),
     kind TEXT NOT NULL,  -- 'deck' | 'quote'
     gsk_job_id TEXT,
     share_url TEXT,
     expires_at TIMESTAMP,
     created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
   );
   CREATE TABLE outreach_log (
     id INTEGER PRIMARY KEY AUTOINCREMENT,
     opportunity_id INTEGER REFERENCES opportunities(id),
     channel TEXT NOT NULL,  -- 'email' | 'phone'
     direction TEXT NOT NULL,  -- 'out' | 'in'
     status TEXT NOT NULL,  -- 'pending_approval' | 'approved' | 'sent' | 'replied' | 'failed'
     recipient TEXT,
     subject TEXT,
     body TEXT,
     external_id TEXT,  -- gsk email id / call id
     created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
     updated_at TIMESTAMP
   );
   CREATE TABLE scrape_jobs (
     id INTEGER PRIMARY KEY AUTOINCREMENT,
     owner_id INTEGER REFERENCES users(id),
     keywords TEXT NOT NULL,  -- JSON array
     status TEXT NOT NULL,  -- 'queued' | 'running' | 'done' | 'failed'
     rows_ingested INTEGER DEFAULT 0,
     error TEXT,
     started_at TIMESTAMP,
     finished_at TIMESTAMP
   );
   ```
3. **`app/scraper.py`** — wrapper that shells `python ../scripts/gebiz_contacts.py --keywords=... --output=...` and streams the output JSON into `opportunities` via `app/seed.py::ingest_file`. Public-listing mode only for demo (no `--wait-for-login`).
4. **`POST /api/scrapes`** — enqueues a job in `scrape_jobs`, kicks a background task via `asyncio.create_task`.
5. **Dashboard**: `GET /` renders list of `opportunities` ordered by `discovered_at` desc, with match score badges.

## Validation

- `python -m app.seed` → `sqlite3 data/beepbop.db 'select count(*) from opportunities'` returns 20.
- Dashboard shows 20 rows, titles include "INVITATION TO QUOTE FOR PROVISION OF DIGITAL ARTIST".
- Click "Scrape now" button → job status goes queued → running → done; new rows may appear (or "no new" if dedup matches).
- **Screenshot**: dashboard with 20 opportunities.
