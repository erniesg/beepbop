# #11 — Closed opportunities scraper + pricing advisor

**Time:** 25 min (stretch goal)
**Depends:** #10 (scraper in-repo)

## Why

User insight: *"Should allow me to scrape/investigate closed opportunities and advise me on pricing strategy also"*

GeBIZ shows **AWARDED** tenders (with `awarded_price` visible for some) plus **CLOSED** and **PENDING AWARD**. For an SME considering a bid, the single most valuable signal is: *what did the previous 3-5 similar tenders go for?*

Examples:
- "MPS Photography Instructor 2027" → look for past MPS instructor awards → "last 3 awarded 9.8k–14k SGD over 2-year terms"
- "School Yearbook design + print" → search awarded yearbooks → "awarded 4-8k SGD range, MOE tends to pick mid-range quotes"

## Red

```python
# tests/test_pricing.py
def test_scraper_fetches_awarded_status_opps():
    """run_search called with status_filter='AWARDED' returns opps with awarded_price field."""
    ...

def test_pricing_advisor_returns_range_and_suggestion():
    from app.matching import advise_pricing
    opp = {"title": "MPS Photography Instructor 2027", "agency": "MOE Schools",
           "procurement_category": "Administration & Training"}
    similar = [
        {"title": "Photography Instructor Beatty Secondary 2024", "awarded_price_sgd": 12000, "status": "AWARDED"},
        {"title": "Photography Instructor Fuhua Primary 2023", "awarded_price_sgd": 9800, "status": "AWARDED"},
        {"title": "Arts Instructor Raffles Institution 2024", "awarded_price_sgd": 14500, "status": "AWARDED"},
    ]
    out = advise_pricing(opp, similar, user_rates={"photography_fullday": 1000})
    assert "price_range" in out
    assert out["price_range"]["min"] <= out["price_range"]["max"]
    assert out["suggested_bid"]
    assert out["rationale"]
```

## Green

1. **Scraper enhancement** (`app/scraper_core.py::run_search`):
   - New arg `status_filter: str | None` — filter by OPEN / AWARDED / CLOSED
   - New fields in parsed records: `awarded_price_sgd`, `awarded_to`, `awarded_date`
   - Update `STATUS_WORDS` regex + field extraction to grab the award block

2. **New matching function** `app/matching.py::advise_pricing(opp, similar_awards, user_rates) -> dict`:
   - Claude call; inputs:
     - Current opportunity (title/category/agency)
     - 3-10 similar historical awards (awarded_price + title)
     - User's rates card
   - Output JSON:
     ```json
     {
       "price_range": {"min": 9800, "max": 14500, "median": 12000},
       "suggested_bid": 12500,
       "rationale": "Middle of observed range; MOE Schools historically award lowest-but-credible quote...",
       "confidence": "medium",
       "sample_size": 3
     }
     ```

3. **Schema addition**:
   ```sql
   ALTER TABLE opportunities ADD COLUMN awarded_price_sgd REAL;
   ALTER TABLE opportunities ADD COLUMN awarded_to TEXT;
   ALTER TABLE opportunities ADD COLUMN awarded_date TEXT;
   ```

4. **New endpoint** `POST /api/opportunities/:id/pricing`:
   - Finds similar awarded opps via title keyword overlap + same procurement_category
   - Calls `advise_pricing`
   - Returns + persists

5. **UI** on opportunity page: new "Pricing strategy" card alongside Clarifications + Prerequisites:
   - Sparkline of historical prices
   - Suggested bid with rationale
   - "View similar awards" expander

6. **Telegram command** `/pricing <opp_id>` — runs the advisor, returns range + suggestion.

## Validation

- Run a live closed-status scrape against photography instructor keyword → ≥3 awarded opps ingested with `awarded_price_sgd` populated.
- Click Pricing on opp #9 → Claude returns range + median + suggested bid with rationale.
- **Screenshot**: opportunity page with Pricing strategy card populated.

## Out of scope for this issue

- Multi-year trend analysis (year-over-year award inflation)
- Cross-category price modelling (e.g. photography rates inferred from adjacent training tenders)
- Competitor analysis (who's been winning these awards)
