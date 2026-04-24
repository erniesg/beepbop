def test_scraper_core_is_importable():
    """Confirms scraper_core lives in-repo (no subprocess to ../scripts/)."""
    from app.scraper_core import run_search, parse_detail_text, normalize_ws
    assert callable(run_search)
    assert callable(parse_detail_text)
    assert callable(normalize_ws)


def test_scraper_module_does_not_shell_subprocess():
    """app/scraper.py should not call subprocess."""
    import inspect
    import app.scraper as s
    src = inspect.getsource(s)
    assert "subprocess" not in src
    assert "scraper_core" in src
