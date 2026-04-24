# #3 — Match scoring + clarifications + `gsk` artifact generation

**Time:** 40 min
**Depends:** #2

## Red

```python
# tests/test_matching.py
def test_photography_context_ranks_creative_tenders_above_it_services(seeded):
    from app.matching import score_opportunities_for_context
    ctx = {"profile_md": "Boutique photography + video studio serving Singapore schools and arts organisations.", "services": ["photography", "videography", "editing"]}
    ranked = score_opportunities_for_context(ctx, limit=5)
    top_titles = [r["title"].lower() for r in ranked[:3]]
    assert any("photography" in t or "digital artist" in t or "music & video" in t for t in top_titles)
    assert all(r["score"] >= 0 and r["score"] <= 1 for r in ranked)

def test_clarifications_extracted(seeded):
    from app.matching import extract_clarifications
    opp = {"title": "MPS Photography Instructor 2027", "raw_json": {...}}
    qs = extract_clarifications(opp, context={"services": ["photography"]})
    assert len(qs) >= 2
    assert all("question" in q and "severity" in q for q in qs)

# tests/test_artifacts.py
def test_generate_deck_creates_artifact_row(seeded, mock_gsk):
    from app.outreach import generate_deck
    art = generate_deck(opportunity_id=1)
    assert art["share_url"].startswith("https://")
    assert art["kind"] == "deck"

def test_generate_quote_creates_artifact_row(seeded, mock_gsk):
    from app.outreach import generate_quote
    art = generate_quote(opportunity_id=1)
    assert "docs.google.com/spreadsheets" in art["share_url"]
```

## Green

1. **`app/matching.py`**:
   - `decompose_context_to_keywords(ctx_md, services) -> list[{term, weight, rationale}]` — Claude call with structured output, cached per context version.
   - `score_opportunities_for_context(ctx, limit) -> list[opp_with_score]` — for each opportunity, Claude scores 0.0–1.0 + one-sentence rationale, using context keywords + opportunity title/category/agency. Batched (send 10 at a time) for speed.
   - `extract_clarifications(opp, ctx) -> list[{question, passage_ref, severity}]` — Claude reads `raw_json` (title + remarks + procurement_category) and emits 2–5 questions.
2. **`app/gsk_client.py`**:
   - `gsk_create_slides(prompt: str) -> {job_id, share_url}` — shells `gsk create-task --type=slides --query="..."`, parses JSON output.
   - `gsk_create_sheet(prompt: str) -> {sheet_id, url}` — shells `gsk sheets create`.
   - Both set `expires_at = now + 1440 min` (Claw share links max).
3. **`app/outreach.py`**:
   - `generate_deck(opportunity_id) -> artifact` — builds prompt from context + opportunity + clarifications, calls `gsk_create_slides`, writes `artifacts` row.
   - `generate_quote(opportunity_id) -> artifact` — same for sheet.
4. **UI** — `templates/opportunity.html`:
   - Show title, agency, closing date, status.
   - Match score badge (green ≥0.7, amber 0.4–0.7, red <0.4) + rationale.
   - Clarifications as checklist.
   - Two buttons: "Generate deck", "Generate quote" (HTMX POST, swap in returned artifact card with URL).
   - Timeline section (empty for now — filled by #5–#6).

## Validation

- Click through "INVITATION TO QUOTE FOR PROVISION OF DIGITAL ARTIST":
  - match score ≥ 0.6 (photography context)
  - ≥2 clarifications
  - "Generate deck" returns a Genspark Claw URL that opens a deck mentioning MOE + digital artist
  - "Generate quote" returns a Google Sheets URL with line items
- **Screenshot**: opportunity detail with match score + clarifications + both artifact buttons green-checked.
- **Gate B**: user clicks through one opportunity, both artifacts render correctly.
