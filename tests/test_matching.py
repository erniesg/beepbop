"""Smoke tests for matching. Use lexical fallback when no API key."""
from __future__ import annotations

import os

import pytest


PHOTO_OPP = {
    "title": "INVITATION TO QUOTE FOR PROVISION OF DIGITAL ARTIST",
    "agency": "Ministry of Education",
    "procurement_category": "Administration & Training ⇒ Music & Video",
    "closing": "29 Apr 2026 01:00PM",
    "status": "OPEN",
    "matched_keyword": "artist",
    "raw_json": '{"remarks": "Contractor to provide a digital artist."}',
}

IT_OPP = {
    "title": "PROCUREMENT OF FIREWALLS AND NETWORK INFRASTRUCTURE",
    "agency": "GovTech",
    "procurement_category": "IT ⇒ Network Infra",
    "closing": "29 Apr 2026 01:00PM",
    "status": "OPEN",
    "matched_keyword": "",
    "raw_json": "{}",
}

PHOTO_CTX = {
    "name": "ernie.sg creative studio",
    "profile_md": "Boutique photography + video studio for schools and arts orgs.",
    "services": '["photography", "videography", "editing", "workshop"]',
}


def test_lexical_fallback_ranks_artist_above_firewall(monkeypatch):
    # Force fallback by clearing the key
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    from app.config import get_settings
    get_settings.cache_clear()
    # Reset the matching singleton
    import app.matching as m
    m._client = None
    from app.matching import _lexical_score
    s1 = _lexical_score(PHOTO_OPP, PHOTO_CTX)
    s2 = _lexical_score(IT_OPP, PHOTO_CTX)
    assert s1["score"] >= s2["score"]


@pytest.mark.skipif(not os.getenv("ANTHROPIC_API_KEY"), reason="needs real API key")
def test_claude_scores_photography_higher_than_it():
    from app.matching import score_opportunity
    s1 = score_opportunity(PHOTO_OPP, PHOTO_CTX)
    s2 = score_opportunity(IT_OPP, PHOTO_CTX)
    assert s1["score"] >= s2["score"]
    assert 0.0 <= s1["score"] <= 1.0
    assert 0.0 <= s2["score"] <= 1.0


@pytest.mark.skipif(not os.getenv("ANTHROPIC_API_KEY"), reason="needs real API key")
def test_clarifications_returned():
    from app.matching import extract_clarifications
    qs = extract_clarifications(PHOTO_OPP, PHOTO_CTX)
    assert 2 <= len(qs) <= 5
    assert all(q.get("question") for q in qs)
