import os
import pytest


PHOTO_INSTRUCTOR = {
    "title": "Provision of BMPS Photography Instructor 2027",
    "agency": "Beatty Secondary School (MOE)",
    "procurement_category": "Administration & Training ⇒ Music & Video",
    "raw_json": (
        '{"remarks": "Instructor must be a MOE Registered Instructor with relevant photography experience. '
        'Vendor must hold current Public Liability insurance."}'
    ),
}

PHOTO_STUDIO_CTX = {
    "name": "ernie.sg",
    "profile_md": "Boutique photography studio. Not yet MOE Registered.",
    "services": '["photography", "videography"]',
}


@pytest.mark.skipif(not os.getenv("ANTHROPIC_API_KEY"), reason="needs API key")
def test_surfaces_moe_registered_instructor():
    from app.matching import extract_prerequisites
    prereqs = extract_prerequisites(PHOTO_INSTRUCTOR, PHOTO_STUDIO_CTX)
    assert len(prereqs) >= 1
    names = " ".join(p["requirement"].lower() for p in prereqs)
    assert "moe" in names and "instructor" in names


@pytest.mark.skipif(not os.getenv("ANTHROPIC_API_KEY"), reason="needs API key")
def test_each_prereq_has_gap_assessment():
    from app.matching import extract_prerequisites
    prereqs = extract_prerequisites(PHOTO_INSTRUCTOR, PHOTO_STUDIO_CTX)
    for p in prereqs:
        assert "user_meets" in p
        assert "how_to_comply" in p
        assert p["category"] in {"certification", "registration", "insurance", "clearance", "other"}


def test_empty_on_api_error(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    from app.config import get_settings
    get_settings.cache_clear()
    import app.matching as m
    m._client = None
    prereqs = m.extract_prerequisites(PHOTO_INSTRUCTOR, PHOTO_STUDIO_CTX)
    assert prereqs == []
