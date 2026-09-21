# Library Decision Matrix

> Replaces the React/Next.js boilerplate scaffold. V1 is a Python project with no frontend — CLI + MCP stdio + (later) downstream consumers. Picks below cite their ADR slot.

## Core stack (V1 baseline)

### Runtime

| Need | Pick | Why | ADR |
|---|---|---|---|
| Language | **Python 3.12+** | Mature ecosystem for ML/NLP + LLM gateways; first-class support across all V1 dependencies. | tech-stack.md |
| Package manager | `uv` (preferred) or `poetry` (fallback) | Fast resolver; lockfile reproducibility. | TBD at impl start |

### Data + IO

| Need | Pick | Alternatives considered | Why |
|---|---|---|---|
| Excel ingest (L1) | `pandas` + `openpyxl` | `xlrd` (legacy), `polars` (slower for `.xlsx`) | Industry standard; reads complex ADEA Report schemas reliably. |
| JSON parsing | `orjson` | stdlib `json`, `ujson` | 2-3× faster on Reddit JSONL streaming; preserves int / float fidelity. |
| Zstandard decompression | `zstandard` | stdlib gzip (not applicable) | Reddit Pushshift archives are zstd-compressed; pure-Python `zstandard` is fast enough. |
| Parquet (optional sample storage) | `pyarrow` | `fastparquet` | Better ecosystem integration with pandas + DuckDB. |
| Dataframes for ad-hoc analysis | `pandas` (write) + `duckdb` (query) | `polars` (lazy advantages) | pandas is what Mahyar already uses; DuckDB for fast queries over `audit_log` + `extraction_cache`. |

### NLP / ML local

| Need | Pick | Alternatives considered | Why | ADR |
|---|---|---|---|---|
| Tokenization + sentence split | `spacy` 3.x | `nltk`, `stanza` | Best Python NER pipeline integration. | ADR-003 |
| Zero-shot NER | **GLiNER2** (EMNLP 2025) | OpenAI ner, finetuned BERT | Best zero-shot domain NER for closed-set entity types (R-006). | ADR-003 |
| Embedding | `BAAI/bge-small-en-v1.5` via `sentence-transformers` | OpenAI `text-embedding-3-small`, Voyage-3 | Local, fast, 384-d adequate for our ER + retrieval (R-002 + R-009). | ADR-003 |
| Entity-resolution reranker | DITTO / DistilBERT via `transformers` | Embedding-only similarity | Reranker improves F1 on ambiguous variants (R-007a). | ADR-003 |
| Constrained decoding (local) | **XGrammar / XGrammar-2** | Outlines, Guidance, lm-format-enforcer | New 2026 SOTA for local-model schema enforcement (R-006). | ADR-003 |

### LLM + gateway

| Need | Pick | Alternatives considered | Why | ADR |
|---|---|---|---|---|
| Multi-vendor gateway | **`litellm` SDK mode** + custom `LLMClient` ABC | LiteLLM proxy mode, OpenRouter, Portkey, Vercel AI SDK | SDK mode avoids documented 1.7-4× throughput drop + memory leaks of proxy mode (R-009). ABC owns `ttl: 3600` lint + per-task routing. | ADR-011 |
| Stage 3 default model | **Claude Haiku 4.5** | Sonnet 4.6, Gemini 2.5 Flash-Lite, GPT-4o-mini | Cost / accuracy sweet spot for noisy forum text; switch criteria documented in tech-stack.md matrix. | ADR-003 addendum |
| Stage 3 hardest cases | **Claude Sonnet 4.6** | GPT-4.1, Gemini 2.5 Pro | Best instruction-following for nuanced extraction; only ~2% of volume routed here. | ADR-003 addendum |
| LLM-as-judge | **Mandatory 3-vendor**: Sonnet 4.6 + Gemini 2.5 Flash + GPT-4.1-mini | Single-vendor judge | JudgeBiasBench shows single-vendor error >50%; three-vendor ≥2/3 agreement (R-007b + R-009). | ADR-006 |
| HITL summary generation | **Gemini 2.5 Flash-Lite** | Haiku 4.5 | Cheapest summarization tier. | ADR-003 addendum |
| Prompt definition | **BAML 0.222.0+** | Instructor, LangChain prompts, raw Python | Schema-aligned parsing + vendor-portable prompts (R-004 + R-006). | ADR-004 |
| Prompt optimization (post-V1) | **DSPy 3.0 + GEPA** | DSPy MIPROv2 | 35× fewer rollouts than MIPROv2 (R-006). | ADR-004 |
| Structured output validation | `pydantic` 2.x | dataclasses, attrs | Industry standard for LLM I/O typing. | tech-stack.md |

### Vendor watchlist (NOT picked, but tracked)

- Gemini 1.5 Flash: dropped (404'd in 2026).
- GPT-5.4-nano / mini: alternates, re-evaluate if cost shifts.
- Grok 4.1-Fast: alternate, re-evaluate.
- DeepSeek V3 / V3.5: rates rose; less attractive as of 2026-05.

### Graph DB (pending ADR-001 — bake-off in progress)

| Need | Candidates | Status |
|---|---|---|
| Graph store + vector index | **LadybugDB** (MIT Kùzu fork) / **Graphiti + Neo4j Community** / **Postgres + AGE + pgvector** | Bake-off scheduled per `docs/05-features/bake-off-graph-db/`. |

| Rejected | Why |
|---|---|
| Kùzu | Acquired by Apple; OSS archived 2025-10-10 (R-006). |
| Memgraph | Enterprise paywall $25k/yr/16GB (R-006). |
| SurrealDB | Production stability + query-planner regressions (R-001). |

### Retrieval

| Need | Pick | Alternatives | Why | ADR |
|---|---|---|---|---|
| Vector index | Native HNSW of chosen graph DB | Qdrant sidecar | Native is good enough at V1 scale; sidecar only if recall fails (R-002). | ADR-002 |
| BM25 / sparse retrieval | Tantivy (if Tantivy fits the engine) or Postgres FTS | Lucene-via-PyLucene, sqlite-fts5 | Pick depends on graph-DB winner. | ADR-002 |
| Hybrid fusion | Reciprocal Rank Fusion in Python | Cross-encoder fusion | Simple, well-understood, ~30 LOC (R-002). | ADR-002 |

### MCP

| Need | Pick | Why | ADR |
|---|---|---|---|
| MCP SDK | `mcp` (Anthropic official) | First-party; stdio transport supported. | ADR-009 |
| Transport | stdio | V1 single-workstation; network transport considered V2. | ADR-009 |

### Side store

| Need | Pick | Alternatives | Why |
|---|---|---|---|
| L1 + HITL + audit log + cache | **SQLite** (V1) | Postgres standalone | Embedded, no service. Absorbed into Postgres if AGE wins bake-off (then SQLite drops). |
| SQLite driver | stdlib `sqlite3` | `apsw` | stdlib is sufficient; `apsw` only if Postgres-class features needed. |
| SQLite WAL mode | enabled | rollback journal | Better concurrent-reader behavior + crash recovery. |

### Observability

| Need | Pick | Alternatives | Why | ADR |
|---|---|---|---|---|
| LLM call telemetry | **Langfuse** | Helicone, PostHog | Best per-call cost + latency + cache-hit + vendor breakdown (R-009). | ADR-011 |
| Structured logging | `structlog` | stdlib `logging` + JSONLogger | Composable processors + JSON output. | tech-stack.md |
| Trace propagation (V2) | OpenTelemetry | Lightstep, Datadog | Optional V1; required V2. | TBD V2 |
| Ad-hoc analysis | `duckdb` | pandas + sqlite3 | Fast queries over `audit_log` + Parquet `extraction_cache`. | tech-stack.md |

### Orchestration

| Need | Pick | Alternatives | Why | ADR |
|---|---|---|---|---|
| Pipeline orchestration | **TBD** — Prefect 3, Dagster, or plain Python | Airflow (too heavyweight), Argo (k8s-only) | Decision deferred to V1 implementation start; depends on sweep cadence + retry semantics. | ADR-010 (pending) |

### CLI + UX

| Need | Pick | Alternatives | Why |
|---|---|---|---|
| CLI framework | `typer` | `click`, `argparse` | Type-driven; Pydantic-friendly. |
| Pretty terminal output | `rich` | `colorama` | Tables + progress + tree views. |
| YAML round-trip (HITL items) | `ruamel.yaml` | `pyyaml` | Preserves comments + ordering; matters for HITL reviewer edits. |

### HTTP

| Need | Pick | Alternatives | Why |
|---|---|---|---|
| HTTP client (where needed) | `httpx` | `requests`, `aiohttp` | Sync + async parity; future-proof for V2 streaming. |

### Test stack

| Need | Pick | Alternatives | Why |
|---|---|---|---|
| Test runner | `pytest` | unittest | Standard Python choice. |
| Async tests | `pytest-asyncio` | trio-pytest | Standard. |
| Coverage | `pytest-cov` | coverage.py | Plugin convenience. |
| Property-based | `hypothesis` | nose-faker | Best Python option for invariant tests. |
| Time mocking | `freezegun` | time-machine | Bitemporal tests need this. |
| HTTP mocking | `respx` | vcr.py, httpretty | httpx-native. |
| Lint | `ruff` | flake8 + black + isort | Single tool replaces 3-4 legacy ones. |
| Type-check | `mypy --strict` | pyright | Default Python ecosystem; PR feedback friendly. |

### Banned / discouraged libraries

(per `dependency-rules.md`)
- `requests` — use `httpx` for sync + async parity.
- `pickle` over the wire — security risk.
- `langchain` — abstractions duplicate ours, churn fast.
- Web frameworks (`fastapi`, `flask`, `django`) — V1 has no HTTP server.
- Heavy ML frameworks (`pytorch-lightning`, `accelerate`) — overkill for inference-only.

## Decision rule (before adding any library)

Answer all five before opening the PR:

1. Can the existing stack solve it? (Most often: yes.)
2. Is the library actively maintained? (Last commit < 6 months; active issue triage.)
3. Is the license acceptable per `dependency-rules.md`?
4. What's the maintenance burden if the library disappears? (Could we replace it with stdlib + 100 LOC?)
5. Is there a security or vendor-lock-in concern?

If "yes" to all, add it to `pyproject.toml` + update this matrix.

## How to remove a library

- All call sites refactored away.
- Lockfile regenerated.
- `pip-licenses` audit passes.
- This matrix updated.
- ADR if the removal changes architecture (e.g., dropping LiteLLM in favor of direct vendor SDKs would be an ADR — and an architectural regression).
