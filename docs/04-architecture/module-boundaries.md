# Module Boundaries

> ⚠️ **Historical (written 2026-05-20, before implementation).** The repo-layout tree below was the *planned* layout: several files it names were never created or landed under other names, and a Next.js console now lives in `web/`. The **dependency-direction rules remain in force** and are enforced by ruff (`[tool.ruff.lint.flake8-tidy-imports.banned-api]` in `pyproject.toml`). For the current layout see the repository README; for what runs, `docs/00-bootstrap/implementation-status.md`.

> V1 product-engine is a Python monorepo. No frontend in V1 (HITL is CLI + flat-file YAML). The web-app boilerplate that was here is replaced by the V1 engine layout.

## Repo layout

```
SecBrain/
├── src/
│   ├── ingestion/          # Tier 1 MCP (outbound) + Python API
│   │   ├── __init__.py
│   │   ├── api.py          # IngestionService
│   │   ├── adapters/
│   │   │   ├── l1_excel.py
│   │   │   ├── l5_reddit.py
│   │   │   ├── l5_sdn.py
│   │   │   └── base.py     # SourceAdapter Protocol
│   │   ├── normalize.py
│   │   └── mcp.py          # MCP wrapper around api.py
│   ├── extraction/         # Tier 0 (API only)
│   │   ├── stage1_filter.py
│   │   ├── stage2_er.py
│   │   ├── stage3_api.py
│   │   ├── cascade.py
│   │   └── cache.py        # Content-addressable extraction cache
│   ├── er/                 # Tier 0
│   │   ├── api.py          # EntityResolver
│   │   ├── canonical_index.py
│   │   ├── blocking.py     # BGE-small HNSW blocking
│   │   └── reranker.py     # DITTO/DistilBERT
│   ├── gateway/            # Tier 0 in V1 (graduates to Tier 1 in V1.x)
│   │   ├── api.py          # LLMClient ABC
│   │   ├── litellm_adapter.py
│   │   ├── routing.py      # Per-task selection criteria
│   │   ├── fallback.py     # Vendor fallback chain
│   │   └── cost_telemetry.py  # Langfuse integration
│   ├── conflict/           # Tier 0
│   │   ├── resolver.py
│   │   ├── halo_table.py
│   │   ├── llm_judge.py    # 3-vendor calibration (V1.x onwards)
│   │   └── signed_graph.py # Nightly clustering job
│   ├── graph/              # Tier 0
│   │   ├── bitemporal.py
│   │   ├── client.py       # Abstract graph client (driven by ADR-001 winner)
│   │   ├── ladybug_client.py     # implementation if bake-off wins LadybugDB
│   │   ├── graphiti_client.py    # implementation if Graphiti+Neo4j wins
│   │   └── postgres_age_client.py # implementation if Postgres+AGE wins
│   ├── retrieval/          # Tier 1 MCP (inbound) + Python API
│   │   ├── api.py
│   │   ├── query_graph.py
│   │   ├── get_canonical_entity.py
│   │   ├── ranking.py      # tier × rank × decay × user-credibility
│   │   ├── rrf.py          # Reciprocal Rank Fusion (BM25 + HNSW)
│   │   └── mcp.py
│   ├── credibility/        # Tier 0
│   │   ├── reddit_rubric.py
│   │   ├── sdn_rubric.py
│   │   └── api.py          # CredibilityScorer (V1: rubric; V1.1: logreg)
│   ├── hitl/               # Tier 0 in V1 (CLI). Tier 1 in V1.x.
│   │   ├── api.py          # HITLQueue
│   │   ├── cli.py          # typer/rich CLI (`hitl pull`, `hitl commit`)
│   │   ├── queue.py
│   │   └── yaml_io.py
│   ├── observability/      # Tier 0
│   │   ├── audit.py        # AuditLog
│   │   ├── lint_ttl.py     # ttl: 3600 enforcement (also a standalone tool)
│   │   └── langfuse_sink.py
│   ├── prompts/            # BAML prompt definitions (vendor-portable)
│   │   ├── stage3_sentiment.baml
│   │   ├── stage3_interview_q.baml
│   │   ├── stage3_conflict_candidate.baml
│   │   └── schema.baml
│   └── shared/             # truly generic utilities only
│       ├── content_hash.py
│       ├── timestamps.py   # Unix-epoch ↔ ISO-8601 ↔ UTC datetime
│       ├── ids.py          # namespaced ID generators
│       └── errors.py       # structured error catalog (single source of truth)
├── tests/                  # mirrors src/ layout
│   ├── ingestion/
│   ├── extraction/
│   ├── er/
│   ├── gateway/
│   ├── conflict/
│   ├── graph/
│   ├── retrieval/
│   ├── credibility/
│   ├── hitl/
│   ├── observability/
│   ├── perf/               # NFR-1 latency tests
│   ├── cost/               # NFR-2 cost regression tests
│   └── fixtures/
├── evals/                  # Gold-set eval harnesses (F1, precision, recall)
│   ├── alias_resolution.py
│   ├── sentiment.py
│   ├── interview_q.py
│   ├── gold/
│   └── results/
├── tools/
│   ├── graphrag/           # Repo MCP context server (gate #6, separate from V1 product engine)
│   ├── lint_ttl_pinning.py # Standalone lint (also imported by src/observability/lint_ttl.py)
│   └── bake_off/           # bake-off harness scripts (post-Mahyar-green-light)
├── docs/                   # As scaffolded by the bootstrap kit
├── data/                   # Local data dir (gitignored)
│   ├── dumps/              # Immutable raw payloads
│   │   ├── L1/<date>/
│   │   ├── L5/<date>/
│   │   └── ...
│   ├── hitl/               # Reviewer YAML files
│   ├── graph/              # Graph DB data files (when embedded)
│   └── sqlite/             # Side store
├── External Data/          # Mahyar's raw data (gitignored, manually managed)
├── pyproject.toml
├── .env.example
├── .env                    # gitignored
├── README.md
└── ...
```

## Public Python APIs (the only modules other modules import)

| Module | Public symbols other modules use |
|---|---|
| `src/ingestion` | `IngestionService`, `DumpReceipt`, `DumpManifest`, `SourceAdapter` |
| `src/extraction` | `CascadePipeline`, `Stage1Result`, `Stage2Result`, `Stage3Result`, `ExtractionCache` |
| `src/er` | `EntityResolver`, `SnapResult`, `ResolutionCandidate` |
| `src/gateway` | `LLMClient`, `GatewayResponse`, `TaskID` (enum), `RoutingDecision` |
| `src/conflict` | `ConflictResolver`, `ResolutionOutcome`, `halo_table` (constants module) |
| `src/graph` | `GraphClient` (Protocol), `BitemporalWriter`, `Edge`, `Node` |
| `src/retrieval` | `RetrievalService`, `QueryResult`, `CanonicalEntity` |
| `src/credibility` | `CredibilityScorer`, `Score`, source-specific `RedditRubric` / `SDNRubric` |
| `src/hitl` | `HITLQueue`, `HITLItem`, `Decision` |
| `src/observability` | `AuditLog`, `Trace`, `cost_telemetry` |
| `src/shared` | `content_hash()`, `to_utc()`, `make_id()`, `ErrorCode` enum, `StructuredError` |

Anything not listed above is **internal** and must not be imported across module boundaries.

## Allowed import graph

```
                    ┌────────────────┐
                    │ src/ingestion  │
                    └───┬────────────┘
                        │ uses
                        ▼
                ┌──────────────────┐
                │ src/extraction   │──► src/gateway
                │ src/er           │──► src/gateway
                └────────┬─────────┘
                         │
                         ▼
              ┌────────────────────┐
              │ src/conflict       │──► src/credibility
              │                    │──► src/gateway (V1.x — 3-vendor judge)
              └────────┬───────────┘
                       │
                       ▼
                ┌─────────────────┐
                │ src/graph       │  (universal sink)
                └─────────────────┘
                       ▲
                       │
                ┌─────────────────┐
                │ src/retrieval   │
                └─────────────────┘

      src/observability  ──► imported by ALL (audit/logging)
      src/shared         ──► imported by ALL (generic utilities)
      src/hitl           ──► imported by src/conflict (escalation) + src/er (borderline routing)
```

## Forbidden imports

- Any module importing a **vendor SDK directly** (`import anthropic` / `import openai` / `import google.genai`) outside `src/gateway/`. Enforced by `ruff` rule.
- Cross-feature internal imports — e.g., `src/conflict` reaching into `src/extraction/stage3_api.py`. Only public APIs cross boundaries.
- `src/shared` importing anything from `src/<feature>/`. Shared utilities must be **truly** generic.
- `src/graph` importing from `src/extraction` or `src/conflict` (it's a sink, not a participant).
- Tests importing private modules — tests import public APIs only, mirroring how product code would.

## Adapter pattern (for source-type pluggability — A-013)

Every source-type adapter (L1 Excel, L5 Reddit JSONL, L5 SDN JSONL, future L2 HTML, L3 CSV, L4 PDF) implements the `SourceAdapter` Protocol:

```python
class SourceAdapter(Protocol):
    source_tier: Literal["L1","L2","L3","L4","L5"]
    accepts_schema: list[str]   # schema fingerprints this adapter handles
    def normalize(self, raw_payload) -> Iterable[CanonicalRecord]: ...
    def extract_seeds(self, canonical_records) -> Iterable[SeedEntity]: ...
    def metadata(self) -> AdapterMetadata: ...
```

Adapters are auto-discovered at startup via `entry_points` in `pyproject.toml`. Adding a new adapter is a one-file PR + tests; no core-engine changes.

## Graph-DB driver pattern (for ADR-001 portability)

The `GraphClient` Protocol in `src/graph/client.py` is the only graph-DB-aware code outside the per-engine implementation files. Other modules depend only on the Protocol. Swap drivers (LadybugDB / Graphiti+Neo4j / Postgres+AGE) by changing the binding in `pyproject.toml` `[tool.engine.graph]` — no other code changes needed.

```python
class GraphClient(Protocol):
    def upsert_node(self, node: Node) -> NodeID: ...
    def upsert_edge(self, edge: Edge) -> EdgeID: ...
    def query(self, query: GraphQuery) -> Iterable[Record]: ...
    def vector_search(self, embedding: list[float], k: int, filter: dict) -> list[VectorHit]: ...
    def as_of(self, time: datetime) -> GraphSnapshot: ...
```

## Boundary tests

- **Import-cycle test**: `pytest tests/test_import_graph.py` walks `src/` AST and asserts no cycles.
- **Vendor-SDK-ban test**: `tests/test_vendor_lockin.py` greps for forbidden imports outside `src/gateway/`.
- **Public API stability test**: `tests/test_public_apis.py` snapshots each module's public symbols; PR-blocking on accidental deletions or signature changes.
