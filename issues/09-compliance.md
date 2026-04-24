# #9 — Compliance / prerequisites agent

**Time:** 20 min
**Depends:** #3 (matching module)

## Why

Many Singapore government tenders have hard gates before you can bid:
- **MOE Registered Instructor** status (CCA, enrichment, curriculum roles)
- **WSQ-certified** trainers for skills training tenders
- **Vendor / supplier registration** with specific agencies (GeBIZ vendor registration, agency panels like NAC, NLB, NHB)
- **NCSS clearance** (National Council of Social Services) for youth-facing work
- **Insurance** (public liability, professional indemnity)
- **First Aid / CPR** certs for physical-activity programmes

If a user doesn't qualify, they shouldn't waste cycles drafting a deck. If they almost qualify, the agent should walk them through the gap.

## Red

```python
# tests/test_prerequisites.py
def test_moe_photography_instructor_surfaces_registered_instructor():
    from app.matching import extract_prerequisites
    opp = {
        "title": "Provision of BMPS Photography Instructor",
        "agency": "Ministry of Home Affairs / Beatty Secondary",
        "procurement_category": "Administration & Training",
        "raw_json": '{"remarks": "Instructor must be a MOE Registered Instructor with relevant photography experience."}',
    }
    ctx = {"profile_md": "Boutique photo studio", "services": '["photography"]'}
    prereqs = extract_prerequisites(opp, ctx)
    names = [p["requirement"].lower() for p in prereqs]
    assert any("moe" in n and "instructor" in n for n in names)
    # Each prereq has a gap assessment
    assert all("user_meets" in p for p in prereqs)
    assert all("how_to_comply" in p for p in prereqs)


def test_prerequisites_flags_gap_when_context_missing_cert():
    from app.matching import extract_prerequisites
    opp = {
        "title": "WSQ-certified trainer for workshop",
        "agency": "SkillsFuture",
        "raw_json": '{"remarks": "Trainer must hold WSQ Advanced Certificate in Training and Assessment (ACTA)."}',
    }
    ctx = {"profile_md": "Photography studio, no formal training certs.", "services": '["photography"]'}
    prereqs = extract_prerequisites(opp, ctx)
    wsq = next((p for p in prereqs if "wsq" in p["requirement"].lower()), None)
    assert wsq is not None
    assert wsq["user_meets"] is False
```

## Green

1. **`app/matching.py::extract_prerequisites(opp, ctx) -> list[dict]`**:
   - Claude call with structured output:
     ```json
     [
       {
         "requirement": "MOE Registered Instructor",
         "category": "certification | registration | insurance | clearance",
         "required": true,
         "user_meets": false,
         "evidence": "excerpt from tender body",
         "how_to_comply": "Apply at moe.gov.sg/... (2-4 week lead time)"
       }
     ]
     ```
   - Prompt grounds Claude in known Singapore compliance regimes (MOE RI, WSQ, ACRA vendor registration, NCSS, NAC Arts Education Programme panel, etc.) so it doesn't hallucinate.

2. **`POST /api/opportunities/:id/prerequisites`** — runs the extraction, persists to `opportunities.prerequisites` (new TEXT column, JSON). Returns list.

3. **Schema add**: `ALTER TABLE opportunities ADD COLUMN prerequisites TEXT;`.

4. **UI** — opportunity page: new "Prerequisites" card alongside Clarifications. Each item rendered as:
   - ✅ green if `user_meets`
   - ❌ amber if gap + `how_to_comply` shown
   - Group: certs / registrations / clearances / insurance.

5. **Stretch (time permitting)**: "Help me apply" button per gap → Claude drafts the application letter + lists required documents, user downloads or Telegram-approves sending to the relevant agency.

## Validation

- Photography Instructor opportunity shows "MOE Registered Instructor" as required + "how to apply" steps.
- Digital Artist opportunity (scope doesn't require registration) shows 0–1 prereqs (e.g., just a business registration).
- **Screenshot**: opportunity page with prerequisites card visible alongside clarifications.
