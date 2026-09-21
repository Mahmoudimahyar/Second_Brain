# GraphRAG Repo MCP Server — Architecture

> Concrete component design for `tools/graphrag/`. Pairs with `IMPLEMENTATION_PLAN.md` (the build sequence) and `verification-harness.md` (how we know it works).

## High-level diagram

```
                                     ┌───────────────────────┐
                                     │  Claude Code (caller) │
                                     └───────────┬───────────┘
                                                 │ stdio MCP
                                                 ▼
   ┌─────────────────────────────────────────────────────────────────┐
   │                  tools/graphrag/mcp_server.py                   │
   │  (Python; spawns + stdin/stdout via `mcp` SDK)                  │
   │                                                                 │
   │  ┌──────────────────────────────────────────────────────────┐   │
   │  │  Tool dispatcher (per tools/mcp/tools.md):              │   │
   │  │  search_codebase / explain_feature / plan_change /      │   │
   │  │  find_symbol / get_feature_packet / get_related_tests / │   │
   │  │  get_docs_for_code / get_code_for_doc /                 │   │
   │  │  find_stale_docs / validate_feature_docs /              │   │
   │  │  create_task_brief                                      │   │
   │  └──────────────┬──────────────────────────────────────────┘   │
   │                 ▼                                               │
   │  ┌──────────────────────────────────────────────────────────┐   │
   │  │  Retrieval primitives (tools/graphrag/retrieval/*.py)    │   │
   │  │  - Hybrid (BM25 + HNSW + RRF)                            │   │
   │  │  - Graph traversal (1-3 hop)                             │   │
   │  │  - Citation assembly                                     │   │
   │  └──────────────┬──────────────────────────────────────────┘   │
   │                 ▼                                               │
   │  ┌──────────────────────────────────────────────────────────┐   │
   │  │  GraphClient (Protocol; one impl per ADR-001 winner)    │   │
   │  └──────────────┬──────────────────────────────────────────┘   │
   └──────────────────┼─────────────────────────────────────────────┘
                      ▼
        ┌─────────────────────────┐       ┌─────────────────────────┐
        │  Graph DB (separate     │       │  BM25 / FTS index       │
        │  instance from product) │       │  (Tantivy / pgsql FTS)  │
        │  + HNSW                 │       └─────────────────────────┘
        └─────────────────────────┘
                      ▲
                      │ indexed by
                      │
   ┌─────────────────────────────────────────────────────────────────┐
   │                  tools/graphrag/index.py                        │
   │  (Python CLI: --full | --incremental [path-globs])              │
   │                                                                 │
   │  Parsers (parsers/*.py)  →  Node store                          │
   │  Edge derivers (edges.py) →  Edge store                         │
   │  Embedder (BGE-small ONNX) → HNSW                               │
   │  Symbol indexer            → BM25/FTS                           │
   │                                                                 │
   │  Snapshot ID = hash(commit_sha + content-hashes)                │
   └─────────────────────────────────────────────────────────────────┘
                      ▲
                      │ reads
                      │
   ┌─────────────────────────────────────────────────────────────────┐
   │                  SecBrain repo                                  │
   │  docs/ (markdown)                                               │
   │  src/  (Python — when V1 product implementation lands)          │
   │  tests/                                                         │
   │  tools/                                                         │
   │  CLAUDE.md, AGENTS.md, etc.                                     │
   └─────────────────────────────────────────────────────────────────┘
```

## Components

### `tools/graphrag/parsers/`

One module per content kind. Pure functions: `parse(file_path) -> Iterable[Node | Edge]`.

| Module | File kinds | Node types emitted |
|---|---|---|
| `markdown.py` | `*.md` | `DocPage`, `DocSection` (per H1/H2/H3) |
| `feature_packet.py` | `docs/05-features/<slice>/*.md` | `Feature`, `Requirement`, `AcceptanceCriterion` |
| `adr.py` | `docs/11-decisions/ADR-*.md` | `ADR` with `status`, `date`, `decision_summary` extracted from headers |
| `python_code.py` | `src/**/*.py`, `tests/**/*.py`, `tools/**/*.py` | `CodeFile`, `Function`, `Class` via `ast` |
| `baml.py` | `src/prompts/*.baml` | `Prompt` with `prompt_id` + `prompt_version` |
| `test_file.py` | `tests/**/*.py` | `TestFile`, `TestCase`; extracts AC-* / FR-* / NFR-* references from docstrings |
| `config.py` | `pyproject.toml`, `.env.example` | `ConfigKey` |
| `known_issues.py` | `**/known-issues.md` | `KnownIssue` |

Each parser:
- Returns a stream of `(node, edge_or_none)` tuples.
- Idempotent — same input → same output.
- No graph-DB or filesystem side effects (pure data).

### `tools/graphrag/edges.py`

Cross-parser edge derivation. Runs after all parsers emit nodes.

Rules:

```python
def derive_feature_has_requirement(nodes: NodeIndex) -> Iterable[Edge]:
    """For each FR-* / NFR-* node in <slice>/requirements.md, link to the slice's Feature."""
    ...

def derive_requirement_has_acceptance_criterion(nodes: NodeIndex) -> Iterable[Edge]:
    """Parse the AC-* → FR-* mapping from <slice>/test-plan.md."""
    ...

def derive_doc_section_references_code(nodes: NodeIndex) -> Iterable[Edge]:
    """Scan DocSection text for backtick-wrapped paths / identifiers matching known Code symbols."""
    ...

# ... one rule per edge type
```

Each rule has unit-test coverage per `verification-harness.md`.

### `tools/graphrag/store/`

Abstracts the chosen graph DB + BM25 backend.

- `client.py` — the `GraphClient` Protocol (shared with V1 product engine via `src/shared/graphrag_core/` when refactored).
- `<engine>_client.py` — concrete implementations:
  - `ladybug_client.py` if ADR-001 lands on LadybugDB
  - `graphiti_client.py` if ADR-001 lands on Graphiti+Neo4j
  - `postgres_age_client.py` if ADR-001 lands on Postgres+AGE
- `bm25.py` — Tantivy or Postgres FTS adapter.
- `embeddings.py` — BGE-small via `sentence-transformers` (or ONNX runtime for CPU).

The repo MCP server uses **a separate database instance/file** from the V1 product engine — same engine, different data. Postgres = different schema; LadybugDB = different `.db` file; Neo4j = different database.

### `tools/graphrag/retrieval/`

One module per MCP tool. Pure functions: `(query, GraphClient) -> Result`.

| File | Tool |
|---|---|
| `search_codebase.py` | hybrid search |
| `explain_feature.py` | feature aggregation |
| `plan_change.py` | semantic + cluster |
| `find_symbol.py` | symbol exact lookup |
| `get_feature_packet.py` | feature doc bundle |
| `get_related_tests.py` | test traversal |
| `get_docs_for_code.py` | reverse traversal |
| `get_code_for_doc.py` | forward traversal |
| `find_stale_docs.py` | timestamp-diff |
| `validate_feature_docs.py` | feature checklist |
| `create_task_brief.py` | task brief composer |

### `tools/graphrag/mcp_server.py`

Stdio MCP server wrapping the retrieval primitives. Uses Anthropic's `mcp` Python SDK.

Per tool:
1. Pydantic input schema (validated at the boundary).
2. Sandbox + path validation (per `tools/mcp/security.md`).
3. Call the retrieval primitive.
4. Pydantic output schema (validated before returning).
5. Audit-log to `tools/graphrag/logs/mcp.jsonl`.
6. Convert any `StructuredError` to MCP error response.

### `tools/graphrag/index.py`

CLI entry: `python tools/graphrag/index.py [--full | --incremental] [--paths <globs>]`.

Modes:
- `--full`: parse the whole repo; rebuild the graph + HNSW + BM25 from scratch.
- `--incremental`: diff filesystem mtime vs prior snapshot; re-parse only changed files; cascade re-derive affected edges; re-embed only changed chunks.

Both modes:
- Compute `snapshot_id = hash(commit_sha + content-hashes of indexed files)`.
- Tag every node + edge written with the `snapshot_id`.
- Optionally prune old snapshots on demand (`--prune <keep-N>`).

### `.mcp.json`

Repo-root MCP configuration pointing Claude Code at the server:

```json
{
  "mcpServers": {
    "secbrain-graphrag": {
      "command": "python",
      "args": ["tools/graphrag/mcp_server.py"],
      "env": {}
    }
  }
}
```

## Snapshots + change detection

Every node + edge carries a `snapshot_id`. Useful for:
- **Time-travel queries**: "what did `tools/graphrag/` know on 2026-05-15?" → filter by snapshot_id.
- **Stale-doc detection** (`find_stale_docs`): compare DocSection's last `snapshot_id` against referenced CodeFile's last `snapshot_id`.
- **Reindex sanity**: incremental runs assert that the new `snapshot_id` only diffs in the expected files' content-hashes.

## Caching

- **Embedding cache**: per chunk content-hash → embedding vector. Reused across reindexes. SQLite-backed.
- **Parser cache**: per file content-hash → parsed nodes. Avoids re-parsing unchanged files in incremental mode.

## Concurrency model

- `index.py` is single-process, single-threaded for V1 simplicity. The repo is small (< 200 docs at full bootstrap).
- `mcp_server.py` handles one request at a time per the stdio MCP protocol; that's fine for V1.

## Configuration

Env vars consumed by `tools/graphrag/`:

```
SECBRAIN_REPO_ROOT=.                   # repo root for parsing + sandbox
GRAPHRAG_DB_PATH=./data/graph/repo.db  # LadybugDB-mode
GRAPHRAG_NEO4J_URI=                    # Neo4j-mode
GRAPHRAG_POSTGRES_DSN=                 # Postgres+AGE-mode
GRAPHRAG_EMBED_MODEL=BAAI/bge-small-en-v1.5
GRAPHRAG_LOG_PATH=./tools/graphrag/logs/mcp.jsonl
```

All vars listed in the relevant block of repo-root `.env.example`.

## Logging

- `tools/graphrag/logs/mcp.jsonl` — every MCP tool call: timestamp, tool name, args (content-hashes only, not raw), output size, latency, error code if any.
- `tools/graphrag/logs/index.jsonl` — every indexing run: snapshot_id, files-parsed counts, edges-derived counts, durations.
- structlog JSON renderer for both.

## Security

Per `tools/mcp/security.md`:
- Path validation rejects parent-traversal.
- `.env` content never returned in tool responses.
- No write tools in V1.
- Sandbox = repo root.

## Out of scope for this MCP server

- The V1 product engine MCP (`src/mcp/`) — different deployment, different data, separate sandbox.
- Indexing data outside the SecBrain repo (e.g., `External Data\` — that's the V1 product engine's domain).
- Real-time file-watcher / auto-reindex. V1 = manual `python tools/graphrag/index.py --incremental` or git-hook integration.

## Open design questions (parked)

- Should `Function` nodes carry a docstring summary or a full body? (Trade-off: index size vs retrieval quality.) Default: docstring + signature; body fetched on demand via `get_code_for_doc`.
- Should we index test fixtures themselves or just test functions? Default: just functions.
- Should we index git blame for per-line authorship? V1: no. V2 maybe.
- Single shared graph DB instance vs separate from V1 product engine? V1: **separate instances** (avoid schema pollution; same engine OK).

Decisions on these defer to implementation start.
