# ADR-009: Two MCP Deployments + SQLite Side Store

Status: **accepted**
Date: 2026-05-20

## Context

The repo + product have **two distinct MCP servers** that share a name but should never be confused:

1. **`tools/graphrag/` repo MCP context server** — indexes the SecBrain repo (docs, code, tests, feature packets) so the coding agent (Claude Code) has low-token retrieval. Required by CLAUDE.md + START_HERE before V1 product code starts (gate #6).
2. **V1 product engine MCP** — indexes ingested dental data (ADEA + Reddit + SDN). Inbound for retrieval + outbound for crawler.

Additionally, V1 needs a lightweight relational side store for L1 ground truth (loaded from Excel), HITL queue, content-addressable extraction cache, and audit log. SQLite is the embedded default; absorbed into Postgres if ADR-001 lands on Postgres+AGE.

## Decision

### Two MCP deployments, distinct

| | `tools/graphrag/` | V1 product engine MCP |
|---|---|---|
| **Purpose** | Repo retrieval for coding agent | Dental-data retrieval + outbound to crawler |
| **Indexed corpus** | SecBrain repo (docs/code/tests/feature packets) | Dental data (L1 ADEA + L5 Reddit/SDN) |
| **Transport** | stdio | stdio (V1); reopens in V2 |
| **Sandbox** | repo root | V1 product-engine process |
| **Read/write** | Read-only V1 (write tools V2 with ADR) | Inbound = read; Outbound = write (only `register_dump`) |
| **Tools** | `search_codebase`, `explain_feature`, `find_symbol`, `get_feature_packet`, `get_related_tests`, `get_docs_for_code`, `get_code_for_doc` | Inbound: `query_graph`, `get_canonical_entity` (+V1.x more). Outbound: `register_dump`, `get_gaps`, `get_research_needs` (+V1.x more) |
| **Verification** | `tools/graphrag/verification-checklist.md` (gate #6) | V1 slice `test-plan.md` AC-5 + acceptance criteria |
| **May share code** | Optional shared core library for indexing patterns | Likely; see consequences below |

Both run via the `mcp` Python SDK.

### SQLite side store (V1)

V1 baseline side store = **SQLite** with WAL mode. Tables:
- `l1_school`, `l1_school_year_metric`, `l1_program` — L1 canonical data loaded from ADEA / CODA Excel.
- `dump`, `alias` — provenance + alias registry.
- `hitl_queue` — pending / claimed / committed items.
- `extraction_cache` — content-addressable (R-008 §1.8).
- `audit_log` — append-only event log.

If ADR-001 bake-off picks **Postgres + AGE + pgvector**, the side store is absorbed into the same Postgres instance (single engine). Otherwise (LadybugDB or Graphiti+Neo4j), SQLite remains the lightweight side store.

## Consequences

- The "two MCP deployments" framing must be documented + referenced in every architectural file (`system-overview.md`, `tech-stack.md`, `security-model.md`, `mcp-security.md`) so future contributors don't conflate them.
- A shared core library for graph indexing patterns is possible — would live under `src/shared/graphrag_core/` or a separate `tools/graphrag_core/` package. Not blocking V1; revisit when the repo MCP server is being implemented.
- SQLite WAL mode gives concurrent reads + single-writer-OK semantics; matches V1 single-user posture.
- Backup discipline: `data/sqlite/engine.db` is the only stateful artifact worth backing up (other data is reproducible from `External Data/` + audit log).
- Audit log can grow large in V1 full-corpus sweep; monitor disk usage; archival policy TBD V1.x.

## Alternatives considered

- **One unified MCP server** for both repo + product: rejected. Sandboxes, tool surfaces, and lifecycle are fundamentally different (the repo MCP runs while Claude Code is active; the product MCP is spawned by callers).
- **Postgres as V1 side store** (regardless of bake-off): adds an always-on service for V1's lightweight needs. Rejected unless bake-off picks Postgres+AGE.
- **DuckDB as side store**: great for analytics, no native concurrent writers. Rejected for HITL queue + audit log.
- **No side store** (everything in the graph DB): pollutes the graph with relational concerns + makes audit log + cache schema-mismatched. Rejected.
- **HTTP transport** for MCP V1: overkill for single-workstation; deferred to V2.

## Related docs

- `tools/graphrag/IMPLEMENTATION_PLAN.md` — repo MCP server spec
- `tools/graphrag/MCP_SERVER_REQUIREMENTS.md` — security + tool requirements
- `tools/graphrag/verification-checklist.md` — gate #6
- `docs/04-architecture/system-overview.md` "Two distinct GraphRAG deployments" section
- `docs/04-architecture/tech-stack.md` Side store section + MCP section
- `docs/12-security/mcp-security.md` — security rules across both deployments
- `docs/00-bootstrap/assumptions.md` A-009, A-022, A-023, A-044

## Related code

- `tools/graphrag/` — repo MCP server
- `src/retrieval/mcp_server.py` — V1 product-engine inbound MCP tools (`query_graph`, `get_canonical_entity`)
- `src/ingestion/api.py` (`register_dump`) + `src/integrations/mcp_crawl_tools.py` — outbound / ingestion MCP surface
- SQLite side-store schema — created in-module per table (`src/observability/audit.py`, `src/hitl/queue.py`, `src/extraction/cache.py`); no central `.sql` file
