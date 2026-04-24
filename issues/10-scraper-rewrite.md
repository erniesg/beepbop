# #10 — Rewrite gebiz scraper in-repo

**Time:** 15 min
**Depends:** #2 (seed / current wrapper)

## Why

Current `app/scraper.py` shells `python3 ../scripts/gebiz_contacts.py`. Problems:
- Hidden dependency outside the repo (breaks if someone clones beepbop alone).
- Subprocess boundary makes progress reporting + cancellation awkward.
- Can't reuse parsing helpers (`normalize_ws`, field labels) in matching.

## Red

```python
def test_scraper_core_module_importable():
    from app.scraper_core import run_search  # no subprocess needed
    assert callable(run_search)


def test_scrape_integration_runs_without_subprocess(monkeypatch, tmp_db):
    """Mock playwright; assert no subprocess invocation."""
    calls = {"subprocess": 0}
    import subprocess as _sp
    monkeypatch.setattr(_sp, "Popen", lambda *a, **kw: (_ for _ in ()).throw(AssertionError("no subprocess!")))
    import asyncio
    from app.scraper import run_scrape
    # Uses the in-repo scraper_core
    # (mocked to return fixture data)
    ...
```

## Green

1. **Copy source** `scripts/gebiz_contacts.py` → `beepbop/app/scraper_core.py` with these changes:
   - Convert `sync_playwright` → `async_playwright` (FastAPI compatibility).
   - Remove `if __name__ == '__main__'` CLI block (keep as `run_search(keywords, output_dir, max_pages)` function).
   - Leave parsing helpers (`normalize_ws`, `parse_opportunity_detail`, etc.) as module-level functions so matching.py can import them.

2. **Update `app/scraper.py`**:
   ```python
   from app.scraper_core import run_search

   async def run_scrape(keywords, owner_id, max_pages=3):
       ... # no subprocess, just await run_search(...)
   ```

3. **Keep `scripts/gebiz_contacts.py`** untouched (other projects may still use it as a standalone CLI).

4. **Test fixture**: `tests/fixtures/gebiz_sample.html` — snapshot of a listing page, used by unit tests of parsing without hitting the network.

## Validation

- Dashboard "Scrape now" button triggers run through the in-repo module; no `ps aux | grep gebiz_contacts` shows up.
- Unit test: `test_scraper_core_module_importable` passes.
- Existing `/api/scrapes` endpoint returns 202 + ingests rows.
- **Screenshot**: dashboard before/after a scrape run.
