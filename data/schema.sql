-- beepbop — SQLite schema
-- See app/db.py init() which executes this file.

CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  email TEXT NOT NULL UNIQUE,
  name TEXT,
  picture TEXT,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS contexts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  owner_id INTEGER REFERENCES users(id),
  name TEXT NOT NULL,
  profile_md TEXT,
  services TEXT,        -- JSON array
  rates TEXT,           -- JSON object
  keywords TEXT,        -- JSON array — decomposed by Claude
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS opportunities (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  opportunity_no TEXT UNIQUE NOT NULL,
  title TEXT NOT NULL,
  agency TEXT,
  status TEXT,
  closing TEXT,
  procurement_category TEXT,
  detail_url TEXT,
  raw_json TEXT,        -- full gebiz scrape blob
  matched_keyword TEXT,
  match_score REAL,
  match_rationale TEXT,
  clarifications TEXT,  -- JSON array
  prerequisites TEXT,   -- JSON array (compliance gates: MOE instructor, WSQ, etc.)
  mock_reply_after_seconds INTEGER,  -- demo crutch
  mock_no_reply_escalate_after_seconds INTEGER,
  policy_mode TEXT DEFAULT 'human',  -- 'auto' | 'human'
  calendar_event_id TEXT,
  discovered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  context_id INTEGER REFERENCES contexts(id)
);

CREATE TABLE IF NOT EXISTS contacts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT,
  email TEXT,
  phone TEXT,
  role TEXT,            -- 'primary' | 'secondary' | 'awarding'
  agency TEXT,
  opportunity_id INTEGER REFERENCES opportunities(id)
);

CREATE TABLE IF NOT EXISTS artifacts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  opportunity_id INTEGER REFERENCES opportunities(id),
  kind TEXT NOT NULL,   -- 'deck' | 'quote'
  gsk_job_id TEXT,
  share_url TEXT,
  expires_at TIMESTAMP,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS outreach_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  opportunity_id INTEGER REFERENCES opportunities(id),
  channel TEXT NOT NULL,         -- 'email' | 'phone'
  direction TEXT NOT NULL,       -- 'out' | 'in'
  status TEXT NOT NULL,          -- 'pending_approval' | 'approved' | 'rejected' | 'sent' | 'replied' | 'failed'
  recipient TEXT,
  subject TEXT,
  body TEXT,
  external_id TEXT,              -- gsk email id / call id
  policy_rationale TEXT,         -- why Claude picked this mode
  telegram_message_id TEXT,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS scrape_jobs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  owner_id INTEGER REFERENCES users(id),
  keywords TEXT NOT NULL,        -- JSON array
  status TEXT NOT NULL,          -- 'queued' | 'running' | 'done' | 'failed'
  rows_ingested INTEGER DEFAULT 0,
  error TEXT,
  started_at TIMESTAMP,
  finished_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS app_settings (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_by INTEGER REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS idx_opp_context ON opportunities(context_id);
CREATE INDEX IF NOT EXISTS idx_outreach_opp ON outreach_log(opportunity_id);
CREATE INDEX IF NOT EXISTS idx_artifacts_opp ON artifacts(opportunity_id);
CREATE INDEX IF NOT EXISTS idx_contacts_opp ON contacts(opportunity_id);
