# Architecture tour

A map for someone opening the code for the first time. For the *why* behind each choice, every
major decision has an ADR in [`docs/11-decisions/`](../11-decisions/); for the original design
narrative see [`system-overview.md`](../04-architecture/system-overview.md).

## The shape of it

```text
                 sources (each declares a trust tier)
                              │
   src/ingestion   adapters ──┤ canonical, content-hashed records
                              ▼
   src/extraction  Pass 1 structural ─ Pass 2 labels ─ Pass 3 clusters ─ Pass 4 LLM extraction
        │              │  mentions                                            │ claims
        │              ▼                                                      ▼
        │         src/er  entity resolution                          src/conflict  cascade
        │              │                                                      │
        ▼              ▼                                                      ▼
   src/graph   ───────────────  bitemporal, tier-stamped graph (Kùzu) + SQLite side store
                              │                                   ▲
                              ▼                                   │ decisions
   src/retrieval  hybrid index · ranking · ask · evidence ·  src/hitl  review queue
   src/research   dossier · research protocol
                              │
        src/cli.py · src/web (FastAPI) · src/retrieval/mcp_server.py · flows/ (Prefect)
```

Everything an LLM does goes through `src/gateway/`. Everything that changes state is recorded by
`src/observability/` in an append-only audit log.

## Packages

| Package | Responsibility | Start reading at |
|---|---|---|
| `src/ingestion/` | Source adapters (Reddit-style dumps, threaded forums, HTML, PDF, spreadsheets, a staged website crawler) and external-database connectors (PostgreSQL, MySQL, SQLite, Neo4j) with schema discovery and delta pulls. Dumps are content-hashed and immutable. | `adapters/base.py`, `sources/base.py`, `api.py` |
| `src/extraction/` | The passes: structural graph builder, label promotion, clustering (k-means, HDBSCAN, signed-spectral), the utility filter, LLM extraction, the content-addressed cache, table-to-graph mapping suggestions. | `pass1_structural.py`, `utility_filter.py`, `cache.py` |
| `src/er/` | Canonical index, alias expansion, mention matching, cross-graph linking. | `canonical_index.py`, `alias_expansion.py` |
| `src/credibility/` | Author-credibility rubrics, one per platform family, computed in Pass 1. | `__init__.py` |
| `src/conflict/` | The resolver cascade, temporal-decay table, three-vendor judge, web verification, L1 claim supersede, the joint-confidence resolver, prompt templates. | `resolver.py`, `halo_table.py`, `judge.py` |
| `src/graph/` | `GraphClient` protocol with `Node` / `Edge`, and the Kùzu implementation: idempotent upserts, bulk `COPY` loads, atomic bitemporal `supersede_edge`. | `client.py`, `kuzu_client.py` |
| `src/embeddings/` | Embedding services: a dependency-free `hash` stand-in, BGE-small, Qwen3-Embedding. Models load lazily and default to CPU. | `__init__.py` |
| `src/retrieval/` | `query_graph`, the hybrid index (BM25 + vector + reciprocal-rank fusion), tier-as-prior ranking, cross-source consistency, the ask agent, evidence answer engine, dossier engine, query planner, provenance store, deterministic rendering, and the engine's MCP server. | `api.py`, `ranking.py`, `dossier.py`, `provenance.py` |
| `src/research/` | The research protocol: estimands, clustered confidence intervals, shrinkage, temporal and cohort analysis, calibration, quality scoring. | `protocol.py`, `stats.py` |
| `src/gateway/` | The only place vendor SDKs may be imported. Provider adapters, per-task routing, fallback, calibrated cascade. | `api.py`, `routing.py` |
| `src/hitl/` | The human review queue (claim / commit / escalate) on SQLite. | `__init__.py` |
| `src/teams/` | Aggregations behind the per-team console views. | — |
| `src/web/` | FastAPI app factory, routers, Pydantic schemas, audit middleware, the dev orchestrator behind `secbrain ui`. | `app.py`, `routes/` |
| `src/observability/` | Append-only audit log. | `__init__.py` |
| `src/shared/` | Generic utilities only; imports nothing from feature packages. | — |
| `flows/` | Prefect 3 flows that wrap the same functions the CLI calls — scheduling, retries and observability without a second implementation. | `full_sweep.py` |
| `tools/graphrag/` | A *second*, smaller GraphRAG that indexes this repository's docs, code and tests, served over MCP for coding agents. | `architecture.md` |
| `tools/doc_lint/` | The gate that fails the build when docs claim more than the code does. | `check_status_truth.py` |
| `tools/docs/` | Generates the CLI and REST reference pages from the code. | `gen_reference.py` |
| `web/` | The Next.js operations console. | `web/README.md` |

## Rules the layout enforces

- **Dependency direction.** Feature packages do not reach into each other's internals, and
  `src/shared/` depends on nothing. See [`dependency-rules.md`](../04-architecture/dependency-rules.md).
- **Vendor isolation is a lint rule, not a convention.** `pyproject.toml` bans `anthropic`,
  `openai` and `google.genai` imports outside `src/gateway/`, and bans `langchain` and `requests`
  everywhere (`[tool.ruff.lint.flake8-tidy-imports.banned-api]`).
- **Builders are pure.** Pass builders turn records into `Node` / `Edge` lists and never touch the
  graph; the caller persists. That is what makes ingest idempotent, batchable and resumable.
- **Heavy imports are lazy.** Importing the CLI must not import torch — there is a test for it
  (`tests/test_cli_no_gpu_import.py`).
- **One implementation, many entry points.** The CLI, the Prefect flows, the REST routes and the
  MCP tools call the same service functions.

## Storage

| Store | Holds |
|---|---|
| **Kùzu** (embedded graph DB, `data/graph/`) | every node and edge, with tier, rank and both time intervals |
| **SQLite** (`data/sqlite/store.db`) | L1 tables and aliases, the HITL queue, the extraction cache, crawl registry, the audit log |
| **Filesystem** (`data/dumps/`) | immutable, content-hashed raw payloads |

On a large graph, set `SECBRAIN_KUZU_BUFFER_POOL_BYTES`: Kùzu otherwise sizes its buffer pool to
most of the machine's RAM.

## Tests

`tests/` mirrors the package layout (`tests/conflict/`, `tests/retrieval/`, …). Notable guards:

| Test | Protects |
|---|---|
| `tests/doc_lint/test_repo_clean.py` | runs doc-lint against the real repo: accepted ADRs may not cite missing files; status docs may not over-claim; the resolver may not be wired without its judge |
| `tests/docs/test_reference_docs.py` | the generated CLI / REST reference matches the code |
| `tests/examples/test_quickstart.py` | the quickstart walkthrough still produces what its README shows |
| `tests/test_cli_no_gpu_import.py` | importing the CLI never pulls torch |
| `tests/test_cli_console_encoding.py` | `--help` works on non-UTF-8 consoles |
| `tests/retrieval/test_ranking.py` | a fresh, corroborated community claim can outrank a stale official one |

The suite needs no API keys, no corpus and no GPU; vendor calls are stubbed.
