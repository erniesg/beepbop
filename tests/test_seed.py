from pathlib import Path


def test_seed_loads_opportunities(tmp_db):
    from app.seed import run_seed
    summary = run_seed()
    assert summary["rows_ingested"] >= 15
    assert summary["context_id"] >= 1


def test_seed_is_idempotent(tmp_db):
    from app.seed import run_seed
    from app.db import count
    run_seed()
    first = count("opportunities")
    run_seed()
    assert count("opportunities") == first


def test_seed_creates_contacts_from_awarding_officers(tmp_db):
    from app.seed import run_seed
    from app.db import count
    run_seed()
    # At least some opportunities in the seed JSON have awarding_contact_email set
    assert count("contacts") >= 5
