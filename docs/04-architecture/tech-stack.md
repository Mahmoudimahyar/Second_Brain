# Tech Stack

> **V1 internal-only.** Picks below are post-R-006/R-007/R-008/R-009 live-verified, **plus R-010 (2026-05-29 live SOTA review — see ADR-021…026).** "Locked" in this doc means a decision is made (an ADR exists), **not** that it is implemented — for what actually runs, see `docs/00-bootstrap/implementation-status.md` (single source of truth). The original research ran with web access denied; R-010 is the live-verified pass.

## Graph store — ADR-001 **(accepted — Kùzu, bake-off complete 2026-05-21)**

**Winner: Kùzu** (`kuzu==0.11.3`, embedded, MIT), per the bake-off in `docs/05-features/bake-off-graph-db/` (Neo4j 0.600 / Kùzu 0.564 / AGE 0.528; margin < 0.10 → M5 ops-complexity tiebreak → Kùzu). Code runs on `src/graph/kuzu_client.py`. **Watch items carried into ADR-001 consequences:** (a) Kùzu scored *worst* on M4 bitemporal ergonomics (no native bitemporal operators — the 4-tuple lives as ISO-string edge props + WHERE filtering), which is in tension with non-negotiable #3 — bitemporal **supersede is not yet implemented** (GAP-053); (b) Kùzu's HNSW was **not exercised** in the bake-off (escalate to a Qdrant sidecar per ADR-002 if it proves inadequate). Runner-up + V2-swap-target: **Graphiti + Neo4j Community** (also the substrate candidate in the ADR-025 engine spike). Other candidate: Postgres 16 + Apache AGE + pgvector.

> Note: "Rejected: Kùzu (Apple acquisition)" referred to the **archived upstream repo**; we pin the **`kuzu==0.11.3` PyPI release** and track the LadybugDB MIT fork. Memgraph ($25k/yr/16GB paywall) and SurrealDB (immature) remain rejected.

## Vector / hybrid retrieval — ADR-002
- HNSW native to the chosen graph DB.
- BM25 via Tantivy or Postgres FTS.
- Reciprocal Rank Fusion in Python.
- Sidecar Qdrant only if recall@10 < 0.85 at corpus > 5M chunks or QPS > 50.

## Side store
**SQLite** for V1 (embedded). L1 ground truth (loaded from ADEA + CODA Excel), HITL queue, content-addressable extraction cache, audit log. Absorbed into Postgres if AGE wins bake-off.

## Extraction stack — ADR-003 (hybrid cascade)

| Stage | Tool | Role |
|---|---|---|
| 1 — filter (100%) | spaCy 3.x + **GLiNER2** + regex | "Does this mention a school/program/year?" |
| 2 — local extract (survivors) | **GLiNER2** + **Qwen3-Embedding-0.6B** (↑ from BGE-small per ADR-022/Q-030; A/B-validated WP4.2, BGE = low-VRAM fallback) HNSW blocking → **DITTO**/DistilBERT reranker, **LLM-matcher fallback on the low-confidence band (ADR-022)** | Snap-to-canonical against ADEA. DITTO = strong cost-efficient closed-world matcher (no longer "SOTA" — LLM matchers win the hard tail, ADR-022) |
| 3 — API extract (residual ~10-15%) | **Model gateway** (see below) | Sentiment, interview-Q harvesting, conflict candidates |
| Constrained decoding (local) | **XGrammar / XGrammar-2** | Schema-locked output |
| Extraction cache | **content-addressable** `hash(thread+prompt+schema+model)` (SQLite-backed) | 90-99% off reruns |

Embedding model: `BAAI/bge-small-en-v1.5` (384-d, ONNX, > 2,000 chunks/sec on GTX 1080).

## Model gateway — ADR-011 (post-R-009)

**LiteLLM in SDK mode (NOT proxy) + our own `LLMClient` ABC.**

Why SDK mode (corrected rationale per ADR-023 / R-010): keep the gateway **in-process to avoid operating another stateful service** (Redis/Postgres) — the honest reason. ⚠️ The previously-cited "proxy mode 1.7-4× throughput drop" figure is **out of regime**: it comes from a self-hosted vLLM high-RPS issue (LiteLLM #21046), not our API-bound vendor-call workload where proxy overhead is single-digit-ms. SDK mode = direct vendor SDKs unified behind a single Python interface, no extra hop. (If a gateway hop ever becomes the bottleneck, a thin Go gateway like Bifrost is the noted future option.)

Why a custom ABC wrapper on top: the ABC owns:
- `ttl: 3600` lint enforcement (GAP-031) at the boundary — vendor-specific cache primitives wrapped uniformly.
- Per-task model routing (the matrix below).
- Fallback chain (Haiku 5xx → Gemini Flash-Lite → GPT-4o-mini, etc.).
- Cost telemetry per call (Langfuse sink).
- Idempotent retries (audit-log keyed).

Runner-up: **Portkey self-hosted** (Apache 2.0 since March 2026) — if LiteLLM SDK proves too thin a layer.

**Rejected**: Vercel AI SDK (Python second-class), OpenRouter (extra network hop for V1 internal, billing centralization unwanted).

Telemetry: **Langfuse** — per-call cost + latency + cache-hit + vendor breakdown, dashboard for sweep cost-attribution.

## V1.5 additions (post-V1.5-R1 + R2, 2026-05-24)

**Frontend stack** (ADR-013):
- Next.js 15 (App Router) + TypeScript + Tailwind 4 + shadcn/ui + Tremor + Sigma.js + TanStack Query + Lucide React.
- Pydantic → Zod codegen via `datamodel-code-generator` + `pydantic-to-zod`.
- Vitest + React Testing Library + Playwright + axe-core for FE testing.

**Backend web layer**:
- FastAPI (Python 3.12) under `src/web/` mounting `/api/v1/*`.
- uvicorn for dev; gunicorn for V2 prod (out of V1.5 scope).
- Pydantic 2.x models as type source-of-truth.

**External-DB connectors** (ADR-014):
- `psycopg[binary]` 3.x + `psycopg_pool` for Postgres.
- `mysql-connector-python` for MySQL.
- stdlib `sqlite3` for SQLite.
- `neo4j` Python driver for Neo4j.
- `testcontainers-python` for integration tests.
- Optional extras: `pip install secbrain[postgres,mysql,neo4j]`.

**Web-search provider** (ADR-016 v2):
- `tavily-python` SDK (only provider in V1.5c; key in `TAVILY_API_KEY`).
- `trafilatura` for HTML content extraction fallback (only used in edge cases).

**Per-task model matrix additions** (extends ADR-003 addendum below):

| Task | Primary | Fallback | Switch criteria |
|---|---|---|---|
| `mapping_suggestion` (V1.5a column embeddings → node-type proposal) | local BGE-small (CPU/GPU) | — | recall < 0.85 on suggestion gold |
| `make_question_from_claim` (V1.5c) | Gemini 2.5 Flash-Lite | Haiku 4.5 | confidence < 0.8 |
| `paraphrase_question` (V1.5c) | Gemini 2.5 Flash-Lite | Haiku 4.5 | edit-distance heuristic fails |
| `verify_claim_from_evidence` (V1.5c, two-vendor parallel) | Haiku 4.5 + Gemini Flash (both required) | — | one provider 5xx → degraded to single + `low_confidence` |
| `team_content_angles` (V1.5c, model-swappable per V1.5-R2) | **Gemini 2.5 Flash-Lite** | Haiku 4.5 | switch via per-task matrix edit; no code change |
| `extract_sentiment` / `extract_interview_q` / `extract_conflict_candidate` (V1) — **with V1.5b `context_block` parameter (ADR-018)** | Haiku 4.5 + cache | Sonnet 4.6 | precision regression on V1 gold sets |

**Feedback-loop infrastructure** (ADR-017 + ADR-018):
- `feedback_log` SQLite table — append-only, retain forever.
- `FeedbackContextLoader` — active-learning hybrid scoring (relevance + recency + diversity + frequency).
- Hard cap K=4 positive examples per template (per few-shot collapse research).
- Blocklist cap 50, LFU+LRU eviction.
- `BlocklistFilter` post-hoc safety net (cosine > 0.92).

## V1.6a additions (ratified 2026-05-27, ADR-019 + ADR-020)

**Website-crawl engine** (ADR-019):
- `crawl4ai>=0.8,<0.9` — primary local crawl engine (Apache-2.0). Wraps Playwright Chromium for JS-rendered pages; ships sitemap.xml + robots.txt + Common-Crawl seeding + adaptive depth.
- `playwright` Chromium — installed via `crawl4ai-setup` post-install hook.
- `trafilatura` — main-content extraction fallback. **Invoked as a subprocess** (`TRAFILATURA_SUBPROCESS_BIN` env var) per known-issues.md §1 to keep its GPL-3.0+ boundary outside SecBrain's import graph.
- `pikepdf>=8` — PDF metadata + repair (MPL-2.0).
- `tabula-py>=2.9` — robust HTML / PDF table extraction (MIT).
- `croniter>=2` — per-domain cadence parsing + next-run preview (MIT).
- `pandas>=2.2` — already present; reused for `pandas.read_html` on HTML `<table>` blocks.
- Optional `easyocr>=1.7` (extras: `secbrain[ocr]`) — per-domain opt-in image OCR.
- Optional `scrapingbee>=1.2` (extras: `secbrain[proxy]`) — opt-in fallback proxy when local fetch is bounced by Cloudflare / DataDome / PerimeterX.
- Dev: `pytest-httpx` + `respx` for adapter HTTP mocking; `pytest-benchmark` for NFR-1.6a-1 perf gates.

**Staged graph ingestion** (ADR-020):
- L0 / L1 / L2 are opt-in per domain. L0 is always on; L1 + L2 require user upgrade. Each stage idempotent, incremental on re-crawl.
- L1 reuses V1's `Pass1MentionExtractor` + BGE-small embeddings + rapidfuzz canonical-match.
- L2 reuses V1's Pass-4 + Pass-5 machinery + V1.5c's `WebVerificationAgent` for conflict step 5. No new web-verify infrastructure.
- Budget gating fires at 3 points per crawl: pre-run projection (`avg_recent × queued × 1.2`), cumulative spent inside the run, dispatcher boot.

**Per-task model matrix additions** (extends ADR-003 addendum):

| Task | Primary | Fallback | Switch criteria |
|---|---|---|---|
| `website_l2_cluster_summary` (V1.6a, one call per cluster) | Gemini 2.5 Flash-Lite | Haiku 4.5 | Cluster summary incoherent (heuristic on length + entity-coverage) |
| `website_l2_claim_extract` (V1.6a, selective Pass-4-style) | Haiku 4.5 + cache | Sonnet 4.6 | Confidence < 0.7 |
| `website_l1_entity_tag` (V1.6a) | GLiNER2 local | spaCy NER fallback | GPU OOM or model load failure |

All other V1.6a LLM calls (none on L0/L1 paths) flow through existing per-task matrix entries unchanged.

**`.env` additions** (per `data.md` § ".env additions"):
- Required: `CRAWL4AI_USER_AGENT`, `CRAWL4AI_CONTACT_EMAIL`, `CRAWL4AI_MAX_CONCURRENCY`, `WEBSITE_CRAWL_DEFAULT_BUDGET_USD`, `WEBSITE_CRAWL_DEFAULT_BUDGET_PAGES`, `WEB_CACHE_DIR`, `WEB_CACHE_MAX_BYTES`, `TRAFILATURA_SUBPROCESS_BIN`.
- Optional: `SCRAPINGBEE_API_KEY`.

## Per-task model assignment matrix — ADR-003 addendum (R5-revised)

The 5-pass architecture means most work happens without an LLM. The matrix below applies only where an LLM is invoked.

| Task | Primary model | Fallback / escalation | Switch criteria (testable) |
|---|---|---|---|
| **Pass 1 — fuzzy entity match** | `rapidfuzz` (CPU, no LLM) | — | If recall < 0.85 on canonical-list eval → consider Pass 2 fall-through to Pass 3 clustering for unresolved mentions |
| **Pass 2 — label promotion** | None (direct metadata extraction) | — | — |
| **Pass 3 — embeddings** | local BGE-small | BGE-M3 (multilingual) / Voyage-3-large | Recall@10 < 0.85 on retrieval eval |
| **Pass 3 — cluster summary** | **Gemini 2.5 Flash-Lite** (one call per cluster) | Haiku 4.5 | Flash-Lite summary incoherent (heuristic on summary length + entity-coverage) |
| **Pass 4 — sentiment (broad)** | **Gemini 2.5 Flash-Lite** | Haiku 4.5 | F1 on sentiment gold < 0.85 |
| **Pass 4 — interview-Q harvest** | **Claude Haiku 4.5** (batch + `ttl:3600`) | Sonnet 4.6 | Haiku confidence < 0.7 |
| **Pass 4 — conflict candidates** | **Claude Haiku 4.5** | Sonnet 4.6 | Same |
| **Pass 4 — hardest 2%** | **Claude Sonnet 4.6** | GPT-4.1 | (this is already the escalation tier) |
| **Reranker (entity resolution)** | **DITTO / DistilBERT (local)** | Cohere Rerank v3.5 (API) | F1 < 0.92 on alias gold set |
| **LLM-as-judge** (conflict resolution only, NOT extraction) | **Three-vendor mandatory**: Sonnet 4.6 + Gemini 2.5 Flash + GPT-4.1-mini, ≥2/3 agreement | HITL escalation | Always 3-vendor (R-007b + R-009; JudgeBiasBench >50% single-vendor error) |
| **HITL summary generation** | **Gemini 2.5 Flash-Lite** | Haiku 4.5 | Cheapest tier wins by default |

**Net effect on cost vs prior matrix**: Stage-3 workhorse demoted from Haiku 4.5 → Gemini 2.5 Flash-Lite (5× cheaper) for sentiment + cluster summary + initial harvest. Haiku 4.5 becomes the mid-tier escalation. Sonnet 4.6 reserved for the rarest hardest cases. Pass 1-3 do most of the structural work at $0.

**Dropped from candidate set:**
- **Gemini 1.5 Flash** — deprecated / 404'd in 2026. (Mahyar named this; substitute is 2.5 Flash-Lite.)

**Kept as alternates (not primary V1):**
- GPT-5.4-nano / GPT-5.4-mini.
- Grok 4.1-Fast.

## Prompt framework — ADR-004

- **BAML 0.222.0+** as production prompt-definition + schema-aligned-parsing (SAP). Vendor-portable prompt definitions feed the gateway.
- **DSPy 3.0 + GEPA** as post-V1 offline optimizer once HITL gold accumulates (35× fewer rollouts than MIPROv2).
- **Instructor** as a lighter fallback for prototyping.

## Conflict resolution + graph algorithms — ADR-006

- Signed-graph community detection on SUPPORTS/CONTRADICTS edges (NOT vanilla Leiden).
- HALO per-edge-type half-life decay (NOT global) — see `system-overview.md` §5.
- LLM-as-judge restricted to same-tier same-year tie-breaks with three-vendor calibration (above).

## Trust-tier schema — ADR-005

Wikidata-style `rank` enum (`preferred`/`normal`/`deprecated`) + `references` array + `qualifiers` dict. `source_tier` enum L1..L5. Bitemporal 4-tuple on every edge.

## User-credibility — ADR-008

Source-aware split rubric. Reddit-rubric uses karma; SDN-rubric uses volume + longevity + on-topic ratio (no upvote signal in SDN). V1 = 10-feature hand-weighted; V1.1 = logistic regression. Author IDs namespaced `reddit:<sub>:<author>` vs `sdn:<author>`.

## MCP — ADR-011 (component-policy) + ADR-009 (two-deployment framing)

**Three-tier component-MCP policy** (post-R-009):
- **Tier 0 — Python API only** (default for internal components).
- **Tier 1 — API + MCP** (when an LLM-driven non-deterministic caller benefits from tool discovery + schema-validated invocation).
- **Tier 2 — API + MCP + HTTP shim** (when cross-process access needed).

**V1 deployments:**
- `tools/graphrag/` — repo MCP server (stdio); indexes SecBrain repo for the coding agent. Gate #6.
- V1 product engine MCP — stdio for V1 internal use.

**V1 MCP surface assignment:**

| Component | Tier | Reason |
|---|---|---|
| Ingestion plane (outbound: `register_dump`, `get_gaps`, `get_research_needs`) | Tier 1 | Crawler is an external agent system |
| Graph retrieval (inbound: `query_graph`, `get_canonical_entity`) | Tier 1 | Coding agent + future downstream agents will call this |
| Cascade extraction | Tier 0 | Internal pipeline step, deterministic invocation |
| Entity resolver | Tier 0 | Internal pipeline step |
| Conflict resolver | Tier 0 | Internal pipeline step |
| Bitemporal graph writer | Tier 0 | Internal storage primitive |
| Model gateway | Tier 0 in V1 → Tier 1 in V1.x | When downstream agents arrive (V2), they'll want gateway access |
| HITL queue | Tier 0 in V1 (CLI) → Tier 1 in V1.x | When external reviewers come in |
| Audit log | Tier 0 (queried via SQL) | No agent-call benefit |

## Language + runtime

- **Python 3.12+**.
- **pandas** + **openpyxl** for Excel ingest (L1).
- **orjson** + **zstandard** for fast JSONL/zstd.
- **httpx** + **anthropic** + **openai** + **google-genai** SDKs (via LiteLLM).
- **litellm** Python SDK (SDK mode).

## Testing

- **pytest** + **pytest-asyncio** + **hypothesis** for property-based tests on canonical-alias resolution + temporal-decay math.
- **freezegun** for bitemporal tests.
- **respx** + **httpx-mock** for vendor API mocking. Plus LiteLLM's mock provider for cross-vendor switch tests.
- Eval harnesses in `evals/` (gold-set growth per GAP-028).

## Operations + observability

- **Langfuse** for LLM-call telemetry (cost + latency + cache-hit + vendor breakdown).
- **structlog** for structured app logs.
- **OpenTelemetry** (optional V1; required V2).
- **DuckDB** for ad-hoc analysis over SQLite `audit_log` / `extraction_cache`.
- **rich** + **typer** for V1 HITL CLI.

## Deployment

- V1: single workstation. Docker only for Neo4j (if Graphiti+Neo4j wins bake-off).
- V2: containerized; cloud TBD; multi-tenant security rewrite.

## Locked vs pending

| Decision | Status | ADR slot |
|---|---|---|
| Hybrid cascade (spaCy + GLiNER2 + Haiku 4.5) | **Locked** | ADR-003 |
| Per-task model matrix + switch criteria | **Locked** (R-009) | ADR-003 addendum |
| LiteLLM SDK + `LLMClient` ABC | **Locked** (R-009) | ADR-011 |
| Three-tier MCP-per-component policy | **Locked** (R-009) | ADR-011 |
| BAML prompt framework | **Locked** | ADR-004 |
| Wikidata-rank trust schema | **Locked** | ADR-005 |
| Signed-graph community detection | **Decided, NOT built** — V1 uses plain k-means; signed-graph is V1.x (GAP-049). Use as disagreement-detector, not truth-adjudicator (ADR-026) | ADR-006 → ADR-026 |
| HALO per-edge-type half-life | **Wired** — `src/conflict/halo_table.py` consumed by the ranker (GAP-050 closed in V1.7) | ADR-007 |
| LLM-as-judge restrictions (3-vendor required) | **Wired** (R-007b + R-009; ADR-024 family-exclusion + independent vote) — judge built via `factory.py`, passed to the resolver in cli + Pass-4 flow (GAP-052 closed in V1.7) | ADR-006 |
| Bitemporal edges | **Locked** | ADR-005 |
| Source-aware user-credibility | **Locked direction** | ADR-008 |
| Content-addressable extraction cache | **Locked** | ADR-003 |
| Prompt-cache `ttl: 3600` pinning | **Locked** | ADR-003 |
| Langfuse for LLM telemetry | **Locked** (R-009) | ADR-011 |
| Graph DB | **Locked (accepted) — Kùzu `0.11.3`** (bake-off complete 2026-05-21) | ADR-001 |
| Retrieval ranking = tier-as-prior + RA-RAG consistency (not tier-first sort) | **Wired** — `src/retrieval/ranking.py` wired into `query_graph` (GAP-048 closed in V1.7) | ADR-021 |
| ER modernization — embedder swap + LLM-matcher | **Wired** — Qwen3-0.6B adopted (A/B ≥ BGE, WP4.2); LLM-matcher fallback on the borderline band (`src/er/llm_matcher.py`, `--llm-matcher`); NuNER-Zero A/B still pending | ADR-022 |
| Calibrated cascade + learned first-hop router | **Wired (default off)** — `CalibratedCascade` (`src/gateway/routing.py`) + isotonic `calibration.py`; gateway-registered under `SECBRAIN_CASCADE=1` (Q-031 → built in-task cascade) | ADR-023 |
| LLM-judge family-exclusion + independent vote | **Decided** (R-010); judge not yet wired (GAP-052) | ADR-024 |
| GraphRAG engine (custom vs LightRAG/Graphiti) | **Proposed — spike** | ADR-025 |
| Conflict resolution (cascade vs learned truth-discovery) | **Proposed — spike** | ADR-026 |
| Hybrid retrieval (HNSW + BM25 + RRF) | **Wired** — `HybridIndex` constructed + wired into `query_graph` seed lookup (GAP-051 closed in V1.7); engines tied to ADR-001 | ADR-002 |
| Side store (SQLite default; Postgres if AGE wins) | **Locked direction** | ADR-009 |
| Orchestrator (Prefect / Dagster / plain) | **Pending** (V1 feature-packet driven) | ADR-010 |
| Anthropic vs Gemini vendor primacy | **Locked Anthropic V1 primary**; Gemini quality-eval V1.x | ADR-003 addendum |

## Dependencies + minimum versions (V1 baseline)

| Package | Min version | Purpose |
|---|---|---|
| `python` | 3.12 | Runtime |
| `pandas` | 2.2 | L1 Excel ingest |
| `openpyxl` | 3.1 | Excel reader |
| `orjson` | 3.10 | Fast JSON |
| `zstandard` | 0.22 | Reddit dump decompression |
| `spacy` | 3.7 | Tokenization, NER fallback |
| `gliner` | 0.2.x (GLiNER2 — EMNLP 2025 **System Demonstrations**, not main-track; NuNER-Zero A/B per ADR-022) | Zero-shot NER |
| `sentence-transformers` | 3.0 | BGE-small embeddings |
| `xgrammar` | 0.1.x | Constrained decoding (local) |
| `litellm` | latest | Multi-vendor gateway (SDK mode) |
| `anthropic`, `openai`, `google-genai` | latest | Vendor SDKs (consumed via LiteLLM) |
| `baml-py` | 0.222 | Prompt definition |
| `mcp` | latest | MCP SDK |
| `pydantic` | 2.x | Structured output validation |
| `structlog` | 24.x | Logging |
| `langfuse` | latest | LLM telemetry |
| `pytest`, `pytest-asyncio`, `hypothesis`, `freezegun`, `respx` | latest | Test stack |
| `typer`, `rich` | latest | HITL CLI |

`graphiti-core`, `kuzu`/`ladybugdb`, `neo4j` driver, `psycopg`, `pgvector`, `apache-age` bindings — added by ADR-001 based on bake-off winner.

## Cost envelope (V1)

- V1 slice (1 subreddit + ADEA L1) → first sweep < $25.
- V1 full sweep (all forum + all L1, revised after corpus inspection) → $80-300.
- V2 distillation pulls back down per R-008 projection.

Pending Mahyar's Q-016 ceiling.
