# GraphRAG Repo MCP Server — Implementation Plan

> **Scope**: the `tools/graphrag/` MCP context server (gate #6 per CLAUDE.md). Indexes the SecBrain repo (docs / code / tests / feature packets) so the coding agent has low-token retrieval before broad file reads. **NOT** the V1 product engine (which lives under `src/` and indexes ingested dental data).
>
> **Status**: spec + plan only. Implementation requires Mahyar's explicit go-ahead per the V1-gates-pass rule.

## Why this exists

CLAUDE.md + AGENTS.md mandate GraphRAG/MCP context retrieval before broad repo exploration. Without an implementation:
- The coding agent reads raw files (high token spend, poor recall on cross-doc relationships).
- Cross-doc relationships (Feature → Requirement → Code → Test → ADR) are invisible to retrieval.
- Stale-doc detection is impossible.
- `tools/graphrag/verification-checklist.md` cannot pass → gate #6 stays blocked → V1 product code can't start.

This plan turns the GraphRAG spec into a concrete buildable thing.

## Design summary

Three layers:

1. **Indexer** — parses repo content (markdown, Python, etc.), extracts nodes + edges, stores in a graph + vector store.
2. **Store** — graph DB (LadybugDB or Graphiti+Neo4j or Postgres+AGE — same as V1 product engine bake-off winner; both deployments can share a driver but use separate database files / instances).
3. **MCP server** — stdio process exposing the retrieval tools from `tools/mcp/tools.md`.

A shared core library (`src/shared/graphrag_core/`) is optional but recommended — both `tools/graphrag/` (repo MCP) and the V1 product engine retrieval need the same primitives.

## Phased implementation

Sequential phases with hard exit gates. TDD discipline per AGENTS.md throughout.

### Phase 0 — Prereqs

| # | Item | Status when ready |
|---|---|---|
| 0.1 | Graph-DB bake-off complete + ADR-001 ratified | Driver pick known |
| 0.2 | `tools/graphrag/schema.md` finalized with property conventions | Done; can be done in parallel |
| 0.3 | `tools/graphrag/retrieval-policy.md` finalized with concrete algorithms | Done; can be done in parallel |
| 0.4 | `tools/graphrag/verification-harness.md` finalized | Done; can be done in parallel |
| 0.5 | `tools/mcp/tools.md` finalized with full signatures | Done; can be done in parallel |

Phase 0 exit: bake-off winner known + all four reference docs finalized.

### Phase 1 — Parsers

Parse the SecBrain repo into typed records. One module per content kind.

| Module | Input | Output node types |
|---|---|---|
| `tools/graphrag/parsers/markdown.py` | `*.md` files | `DocPage`, `DocSection` (per H1/H2/H3) |
| `tools/graphrag/parsers/feature_packet.py` | `docs/05-features/<slice>/*.md` | `Feature`, `Requirement` (FR-* / NFR-*), `AcceptanceCriterion` (AC-*), per-file `DocPage` |
| `tools/graphrag/parsers/adr.py` | `docs/11-decisions/ADR-*.md` | `ADR` with `status` extracted from frontmatter/headers |
| `tools/graphrag/parsers/python_code.py` | `src/**/*.py` + `tests/**/*.py` + `tools/**/*.py` | `CodeFile`, `Function`, `Class` via `ast` |
| `tools/graphrag/parsers/baml.py` | `src/prompts/*.baml` | `Prompt` nodes with `prompt_id` + `prompt_version` |
| `tools/graphrag/parsers/test_file.py` | `tests/**/*.py` | `TestFile`, `TestCase` (test functions); link to `Function` / `Requirement` via docstring tags |
| `tools/graphrag/parsers/config.py` | `pyproject.toml`, `.env.example` | `ConfigKey` nodes |
| `tools/graphrag/parsers/known_issues.py` | `docs/05-features/<slice>/known-issues.md` + slice-specific files | `KnownIssue` nodes |

**Failing-first test per parser**: `tests/graphrag/test_<parser>.py::test_extract_nodes_from_fixture` — load a fixture, assert expected nodes + edges.

**Exit gate**: every parser has unit tests passing; integration test loads the full SecBrain repo without errors.

### Phase 2 — Edge derivation

Cross-parser edge derivation. Run AFTER all parsers have emitted nodes.

| Edge type | Derivation rule |
|---|---|
| `FEATURE_HAS_REQUIREMENT` | `Requirement` nodes (FR-*, NFR-*) in `<slice>/requirements.md` → linked to the `Feature` from `<slice>/README.md` |
| `REQUIREMENT_HAS_ACCEPTANCE_CRITERION` | AC-* mapped to FR-* via the `test-plan.md` mapping table |
| `FEATURE_DOCUMENTED_BY` | Files under `docs/05-features/<slice>/` are documents of the slice's Feature |
| `FEATURE_IMPLEMENTED_BY` | Code files under `src/` mentioned in the slice's `plan.md` OR matching a naming convention (e.g., `src/<area>/` for `area`-named features) |
| `DOC_SECTION_REFERENCES_CODE` | DocSection text contains `\`src/...\`` or backtick-wrapped Python identifier matching a known `Function`/`Class`/`CodeFile` |
| `FUNCTION_CALLS_FUNCTION` | AST analysis of Python; `Call` nodes → callee symbol |
| `TEST_COVERS_REQUIREMENT` | TestCase docstring contains `AC-*` / `FR-*` / `NFR-*` reference |
| `TEST_COVERS_FUNCTION` | TestCase imports / calls a specific `Function` / `Class` |
| `ADR_DECIDES` | ADR text references `src/<path>` / `docs/<path>` / specific symbols / specific `Requirement` IDs |
| `KNOWN_ISSUE_AFFECTS` | KnownIssue text references a `Function` / `Class` / `Feature` |
| `PROMPT_USED_BY` | BAML `Prompt` → `Function` that invokes it via gateway |

Edge derivation lives in `tools/graphrag/edges.py`. Each rule is a function taking the node graph and emitting edges; rules compose.

**Failing-first test**: `tests/graphrag/test_edges.py::test_feature_to_requirement_links` etc.

**Exit gate**: per-rule unit tests pass; integration test on the full repo produces a non-empty graph with all `verification-checklist.md` edge types present.

### Phase 3 — Store + indexing

Persist parsed nodes + edges + chunk embeddings into the chosen graph DB.

| Operation | Detail |
|---|---|
| Chunk + embed docs | DocSections chunked by paragraph; chunks embedded via BGE-small (same as V1 product engine); stored in graph DB native HNSW |
| Symbol search index | Functions / Classes / Endpoints / ConfigKeys indexed by name (exact + prefix) via Postgres FTS or Tantivy (same backend as ADR-002) |
| Snapshot ID | Every indexing run gets a `snapshot_id` = `hash(commit_sha + content-hashes of indexed files)`. Stored on every node + edge → allows time-travel queries |
| Incremental reindex | Subsequent runs diff filesystem vs prior snapshot; only re-parse changed files; cascade re-derive edges that depend on changed nodes |

`tools/graphrag/index.py` is the CLI entrypoint: `python tools/graphrag/index.py [--full | --incremental]`.

**Failing-first test**: `tests/graphrag/test_indexer.py::test_full_index_then_incremental` — full index → mutate one doc → incremental sees only the diff.

**Exit gate**: full index of SecBrain repo completes in < 60 sec on Mahyar's workstation; incremental on a single-file change completes in < 5 sec.

### Phase 4 — Retrieval

Implement the retrieval primitives per `retrieval-policy.md`.

| Tool | Algorithm |
|---|---|
| `search_codebase(query)` | Hybrid: BM25 over filenames + names → HNSW over chunk embeddings → RRF fusion → return top-N with snippets + node-IDs |
| `explain_feature(feature)` | Locate `Feature` by name or canonical ID → return README + requirements summary + linked Code roots + Tests + ADRs + Known issues, all linked |
| `plan_change(request)` | Semantic search → cluster results by Feature → output (likely files, likely tests, likely docs, risks from KnownIssues, ADR constraints) |
| `find_symbol(symbol)` | Symbol-name exact match → Function/Class/Endpoint/ConfigKey nodes → linked CodeFile + Tests |
| `get_feature_packet(feature)` | All `Document`s under `docs/05-features/<slice>/` for the slice |
| `get_related_tests(target)` | Traverse `TEST_COVERS_FUNCTION` / `TEST_COVERS_REQUIREMENT` from `target` |
| `get_docs_for_code(file_or_symbol)` | Reverse-traverse `FEATURE_IMPLEMENTED_BY` + `DOC_SECTION_REFERENCES_CODE` |
| `get_code_for_doc(doc_path)` | Forward-traverse `DOC_SECTION_REFERENCES_CODE` from the DocPage |
| `find_stale_docs(changed_files)` | For each changed file, find DocSections that reference it; filter to those last-edited before the code's last-edit timestamp |
| `validate_feature_docs(feature)` | Run a checklist against the Feature's documents: required files present + required sections present + required `requirements.md` IDs present |
| `create_task_brief(goal)` | Compose: relevant Feature(s) + linked docs + relevant tests + relevant ADRs + relevant Known issues. Returns a Markdown brief. |

Each retrieval tool is a function in `tools/graphrag/retrieval/<tool>.py` with a unit test against a fixture graph.

**Failing-first test**: `tests/graphrag/retrieval/test_<tool>.py`.

**Exit gate**: every tool has a unit test + an integration test against the indexed SecBrain repo; p95 latency per tool < 200 ms on the V1 corpus.

### Phase 5 — MCP wrapper

Wrap the retrieval primitives as MCP tools per `tools/mcp/tools.md`.

| Item | Detail |
|---|---|
| Transport | stdio per `MCP_SERVER_REQUIREMENTS.md` |
| Server entrypoint | `tools/graphrag/mcp_server.py` — `python tools/graphrag/mcp_server.py` |
| Schema | Each tool registered with the `mcp` Python SDK; input + output schemas via Pydantic |
| Sandbox | Repo root; path validation per `tools/mcp/security.md` |
| Audit log | Every tool call → `tools/graphrag/logs/mcp.jsonl` |
| Project config | `.mcp.json` in repo root tells Claude Code to launch this server |

**Failing-first test**: `tests/graphrag/test_mcp_contract.py` — start the server in test mode, call each tool with sample args, assert the schema-validated response shape.

**Exit gate**: stdio MCP server passes its contract tests; `.mcp.json` configured; Claude Code can call every tool successfully.

### Phase 6 — Verification (gate #6)

Run the harness in `tools/graphrag/verification-harness.md`. Each `tools/graphrag/verification-checklist.md` item maps to a concrete pass/fail check. All must pass before declaring gate #6 closed.

**Exit gate**: every box in `verification-checklist.md` is ticked + the verification report is written under `/.agent/reports/graphrag-verification-<date>.md`.

### Phase 7 — Integration with AGENTS.md / CLAUDE.md

Update agent contracts to reference the live MCP server:
- `AGENTS.md` already says to use GraphRAG/MCP before broad reads — confirm wording stays accurate.
- `CLAUDE.md` already gates this — confirm wording stays accurate.
- Add a section to `docs/04-architecture/system-overview.md` referencing the live tools/graphrag/ deployment.
- Add a context-pack under `docs/14-context-packs/tools-graphrag-build/` for maintainers.

**Exit gate**: AGENTS.md + CLAUDE.md consistent with live tools; one context pack written.

## Risk register

| Risk | Mitigation |
|---|---|
| Graph-DB driver pick changes after V1 product implementation begins | `GraphClient` Protocol in shared core library lets both deployments swap implementations without affecting parsers / retrieval |
| Incremental reindex misses cross-file edges (e.g., `FUNCTION_CALLS_FUNCTION` broken when callee renamed) | Cascade re-derive edges that depend on changed nodes; nightly full-rebuild as belt-and-braces |
| HNSW recall drops on the small SecBrain corpus | Augment with BM25 + RRF (same architecture as V1 product engine retrieval) |
| Schema drift between this repo MCP server and V1 product engine | Both deployments share `src/shared/graphrag_core/` (when implemented); schema definitions live there |
| Indexing slow on `node_modules`-style large dirs | Hard-coded ignore list + `.graphragignore` support |
| MCP stdio fragile under Claude Code's auto-restart | Implement graceful restart + state-recovery from snapshot |

## Time estimate

| Phase | Hours |
|---:|---|
| 0 — Prereqs (docs only — most done) | 4 |
| 1 — Parsers | 16 |
| 2 — Edge derivation | 10 |
| 3 — Store + indexing | 12 |
| 4 — Retrieval primitives | 18 |
| 5 — MCP wrapper | 8 |
| 6 — Verification (gate #6) | 6 |
| 7 — Integration | 4 |
| **Total** | **~78 hours** (2 focused weeks) |

This is *implementation* hours, not docs. Docs (this file + the 5 sibling docs in `tools/graphrag/` and `tools/mcp/`) account for the remaining bootstrap effort and are done.

## Sequence for Mahyar

1. Decide whether to share core lib between repo MCP + V1 product engine (recommended: yes).
2. Pick whether to start repo MCP **before** or **after** the bake-off ratifies ADR-001 (recommended: after, so both deployments use the same driver from day one).
3. Approve implementation (move from Option (b) to Option (a)).
4. Then this plan executes.

## Related docs

- `tools/graphrag/MCP_SERVER_REQUIREMENTS.md` — security + tool surface
- `tools/graphrag/verification-checklist.md` — gate #6 checklist
- `tools/graphrag/architecture.md` — detailed component design
- `tools/graphrag/schema.md` — node + edge types with properties
- `tools/graphrag/retrieval-policy.md` — retrieval algorithms
- `tools/graphrag/verification-harness.md` — test plan for the checklist
- `tools/mcp/tools.md` — full MCP tool signatures
- `tools/mcp/security.md` — security rules
- `CLAUDE.md` — gate #6 mandate
- `AGENTS.md` — retrieval-before-broad-reads principle
