# #12 — Cloud-persistent memory layer (research + scoped implementation)

**Time:** 45 min research + implementation
**Depends:** —

## Why

Current state: `/remember` updates **our SQLite DB** (`contexts` table). That's the single source of truth — injected into Claude prompts + gsk `create-task` queries. Works, but:

- SQLite is tied to the running process (laptop or Fly container)
- Not shareable across multiple agents (e.g. a separate Claude Managed Agent couldn't read it)
- Not embedded/searchable semantically

User asked: *"can u look into using claude managed agents and gsk crawl thanks to make memory persistent on the cloud somewhere and retrieve that for use"*

## Options assessed

| Option | Fit | Pros | Cons |
|---|---|---|---|
| **Claude Agent SDK (`claude-agent-sdk`)** | ★★★ | Same built-in tools as Claude Code (Read/Write/Bash/Hooks/Sessions); runs in Python | Not a managed service; filesystem-backed memory (we still BYO storage); `sessions` resume only within the SDK |
| **MCP server wrapping our DB** | ★★★★★ | Claude Agent SDK + Claude Code + other agents all read via one protocol; works today | Need to build + host the MCP server |
| **Anthropic Files API** (filesystem-backed) | ★★★★ | Native Claude; scopes to project/skill; free with API | File-based, not structured; no semantic search |
| **gsk AI Drive (`gsk aidrive upload`)** | ★★★ | Already installed; stores JSON blobs; Claude can fetch via URL | Not designed as a KV/memory store; no query API |
| **gsk crawl** | ★ | Could fetch our own `/api/context` endpoint | That's a pull-from-our-db pattern, not a separate store |
| **Mem0 / Zep / Letta** | ★★★★ | Dedicated memory platforms; embeddings + retrieval; API-first | Another vendor; paid tier |
| **Supabase (Postgres + pgvector)** | ★★★★★ | Portable upgrade from SQLite; shared with derivativ.ai; embedded search | ~30 min migration |
| **Cloudflare Durable Objects + KV** | ★★ | Fits berlayar infra pattern | Overkill for demo |

## Research note: Claude Agent SDK is NOT a managed cloud service

From the official docs (2026-04-24 fetch):

> "Build production AI agents with Claude Code as a library... same tools, agent loop, and context management that power Claude Code, programmable in Python and TypeScript."

It's a **Python/TS library**, not a hosted service. Memory = filesystem + sessions. No shared KV/vector store out of the box.

**Sharing pattern**: Agent SDK + Claude Code + our FastAPI app ALL talk to the same MCP server. MCP is the shared-memory primitive, not the SDK itself.

Migration cost: our current pattern (FastAPI calls `anthropic.messages.create()` with structured JSON prompts) maps directly. We could adopt Agent SDK for tool-using flows (e.g. "give Claude access to our DB + let it make pitching decisions") but it's not required for the memory question.

## Recommended path (3-stage)

### Stage 1 — today (0 min)
Status: **our SQLite IS our memory**, propagated into every Claude/gsk call.
Value: works, demos cleanly, survives app restarts on the same machine.

### Stage 2 — port to Supabase (30 min, post-hack day)
Swap `app/db.py` to Postgres (same schema, use `supabase-py`):
- Shared with derivativ.ai infra
- Cross-device durable
- RLS for multi-tenant (when we add SME self-serve)

### Stage 3 — semantic memory via pgvector (1-2 hours)
Add `embeddings` column to `contexts` + an `embeddings` table for granular facts:
```sql
CREATE TABLE memory_facts (
  id BIGSERIAL PRIMARY KEY,
  owner_id INT REFERENCES users(id),
  text TEXT NOT NULL,
  kind TEXT,        -- 'rate' | 'cert' | 'past_work' | 'preference'
  metadata JSONB,
  embedding vector(1536)
);
```

On `/remember`: embed fact → store. On match/quote generation: semantic search ("relevant facts for MOE photography instructor tender") → inject top-3 into Claude prompt. Better than stuffing the full profile every time (saves tokens + improves relevance).

### Stage 4 (optional) — expose as MCP
Wrap our memory store as an MCP server (`beepbop-memory-mcp`) so:
- Claude Managed Agents can read/write facts
- gsk (if it gains MCP client support) can query
- Other agents (Claude Code sessions, Codex) can share the same context

## Red / Green (if picked up)

**Red:**
```python
def test_fact_persists_across_restart():
    mem.add("I charge 2000 for video fullday", kind="rate")
    # simulate app restart
    mem2 = open_memory()
    facts = mem2.search("videography rates")
    assert any("2000" in f.text for f in facts)
```

**Green:** Supabase-backed `memory_facts` table with pgvector; a `MemoryStore` class with `add(text, kind)` + `search(query, limit=5)`; `/remember` writes here; matching.py augments prompts with `search(opp_title + category)` results.

## Validation

- Stop app → restart → `/context` shows same rates.
- Remember 10 facts, then match an opp → relevant 3 are pulled (not all 10).
- Second Claude Code session querying `beepbop-memory-mcp` sees the same facts.
