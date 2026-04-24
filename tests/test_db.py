def test_db_init_creates_tables(tmp_db):
    import sqlite3
    c = sqlite3.connect(tmp_db)
    rows = c.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()
    names = {r[0] for r in rows}
    assert {"users", "contexts", "opportunities", "contacts", "artifacts", "outreach_log", "scrape_jobs"} <= names


def test_upsert_user_creates_then_updates(tmp_db):
    from app.db import upsert_user, get_user_by_email
    u1 = upsert_user("a@b.com", "Alice", "pic1")
    assert u1["email"] == "a@b.com"
    u2 = upsert_user("a@b.com", "Alice Updated", "pic2")
    assert u2["id"] == u1["id"]
    assert u2["name"] == "Alice Updated"

    fetched = get_user_by_email("a@b.com")
    assert fetched["id"] == u1["id"]
