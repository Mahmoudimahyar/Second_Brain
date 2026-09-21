# Glossary

> Domain + technical terms used across the bootstrap docs + architecture. Keep this alphabetized.

| Term | Definition |
|---|---|
| **ABC (LLMClient)** | Abstract Base Class wrapping LiteLLM SDK; owns `ttl: 3600` pinning, per-task routing, cost telemetry, fallback chain. Every LLM call in product code goes through this. |
| **ADEA** | American Dental Education Association. Source of L1 dental-school ground-truth data (Reports 1-4 + Trends, 10-yr coverage 2015-16 → 2024-25). |
| **Alias** | A non-canonical string referring to a canonical entity. Stored in `alias` table; linked to canonical via `HAS_ALIAS` edge. |
| **Anomaly** | A claim that falls outside the consensus cluster (signed-graph community detection) but is preserved (`Status: Anomaly`), not deleted. Queryable via `include_anomalies=True`. |
| **Audit log** | Append-only structured log of every extraction, retrieval, HITL decision, ingestion event. Source of truth for replay + reconstruction. |
| **Bake-off** | The 1-2 day evaluation of graph-DB candidates (LadybugDB / Graphiti+Neo4j / Postgres+AGE+pgvector). See `docs/05-features/bake-off-graph-db/`. |
| **BAML** | Boundary's prompt-definition + schema-aligned-parsing (SAP) framework. V1 primary prompt layer. |
| **BGE-small** | `BAAI/bge-small-en-v1.5`. 384-dim embedding model. Used for entity-resolution blocking + retrieval embeddings. |
| **Bitemporal edge** | An edge with both `t_valid_*` (wall-clock validity) and `t_ingest_*` (when the graph learned it). Enables "as of past date" reconstruction. |
| **Cache TTL** | Prompt-cache time-to-live. Anthropic silently changed the default from 1h to 5m in March 2026. The codebase explicitly pins `ttl: 3600` everywhere. |
| **Canonical entity** | An L1 node (`source_tier=L1`, `rank=preferred`) representing the authoritative version of a thing (school, program). L5 aliases snap to these via ER. |
| **Cascade extraction** | The 3-stage pipeline: Stage 1 (local filter) → Stage 2 (local ER) → Stage 3 (API LLM). Cost discipline by tier. |
| **CODA** | Commission on Dental Accreditation. Source of L1 residency/advanced-program ground truth (SADV, 10-yr coverage). |
| **Content-addressable cache** | Extraction cache keyed by `hash(thread + prompt + schema + model)`. 90-99% off reruns. |
| **DITTO** | A pre-trained entity-resolution model (DistilBERT variant). Used as reranker after BGE-small HNSW blocking. |
| **Dump** | A discrete data drop received via `register_dump(...)`. Has a manifest, a payload, an immutable raw, and a `dump_id`. |
| **ER (Entity resolution)** | The pipeline that snaps a mention ("Penn Dental") to a canonical entity (`University of Pennsylvania School of Dental Medicine`). BGE + DITTO + thresholding. |
| **Gateway (model gateway)** | The vendor-abstraction layer: LiteLLM SDK + `LLMClient` ABC. Routes per-task to Anthropic/OpenAI/Google. Fallback chain. Lint enforcement. |
| **GLiNER2** | Zero-shot named-entity recognition model (EMNLP 2025). Replaces GLiNER v2.x as V1 default. |
| **Graphiti** | MIT-licensed temporal-KG engine (arxiv 2501.13956, KGC 2025). ~90% of our 3-layer bitemporal architecture. Bake-off candidate (on top of Neo4j). |
| **HALO decay** | Per-edge-type half-life decay table. Different edge types decay at different rates (`tuition` 1y, `interview_format` 3y, `founding_year` ∞). |
| **HITL** | Human-in-the-loop. The reviewer flow for borderline alias matches + conflict tie-breaks + new-type proposals. V1 = CLI + flat YAML; V2 = web UI. |
| **HNSW** | Hierarchical Navigable Small World graph (approximate nearest-neighbor index). Default vector index across our graph-DB candidates. |
| **L1..L5** | Trust-tier levels: L1 structured truth (ADEA SQL) > L2 unstructured truth (official websites) > L3 structured non-official > L4 unstructured non-official > L5 unstructured community (Reddit/SDN). |
| **LadybugDB** | MIT-licensed active fork of Kùzu after Apple's October 2025 acquisition + archival of the Kùzu OSS repo. Bake-off candidate. |
| **Langfuse** | LLM-call observability platform. Cost + latency + cache-hit + vendor breakdown per call. V1 telemetry sink. |
| **LazyGraphRAG** | Microsoft's lazy variant of GraphRAG — defers expensive global community summarization until query time. Reference architecture per R-005. |
| **LiteLLM SDK mode** | LiteLLM used as a Python SDK (not as a proxy). Avoids the 1.7-4× throughput drop + memory leaks documented in proxy mode. |
| **LLM-as-judge** | Using an LLM to arbitrate between conflicting claims. Restricted to same-tier same-year tie-breaks with three-vendor calibration (Sonnet 4.6 + Gemini 2.5 Flash + GPT-4.1-mini), ≥ 2/3 agreement. |
| **MCP** | Model Context Protocol (Anthropic). Tool-discovery + schema-validated invocation surface. V1 uses MCP for ingestion outbound + retrieval inbound (Tier 1 per the three-tier policy). |
| **MCP-per-component policy** | Three-tier: Tier 0 API-only (default) | Tier 1 API+MCP (when LLM-driven non-deterministic caller benefits) | Tier 2 API+MCP+HTTP shim (cross-process). |
| **Prompt caching** | Anthropic feature reducing repeat-input cost by 90%. Requires explicit `ttl: 3600` pin in our codebase. |
| **Rank (Wikidata-style)** | Per-claim flag: `preferred` (the chosen version) / `normal` (acceptable alternate) / `deprecated` (outdated but preserved). |
| **`references`** | Citation back-pointers on every claim edge. Source `dump_id` + `post_id`. Drives the ≥99% citation traceability requirement. |
| **Research need** | A record emitted by the conflict resolver when L5 disputes L1 ground truth. Consumed by the crawler (separate system) via `get_research_needs()`. |
| **SADV** | Survey of Advanced Dental Education (CODA). Yearly Excel files for residency programs. |
| **SDE** | Survey of Dental Education (ADEA). Yearly Excel files for dental schools. |
| **SDN** | Student Doctor Network. Online forum (`forums.studentdoctor.net`). L5 source. ~173K threads in `External Data\`. |
| **Signed-graph community detection** | Community-detection algorithm that respects positive (SUPPORTS) and negative (CONTRADICTS) edges. Replaces vanilla Leiden for the opinion layer. |
| **Slice (V1 slice)** | The first vertical end-to-end demonstration: ADEA L1 + r/DentalSchool L5 → tier-attributed graph + retrieval + HITL. See `docs/05-features/01-slice-trust-tier-canonicalize/`. |
| **Snap-to-canonical** | Retrieval-augmented extraction pattern: inject top-K BGE-similar canonical candidates into the extraction prompt so the model picks from a closed set. R-008 §1.9 lever. |
| **Source tier** | See L1..L5. |
| **State `Status: Invalidated_by_Official_Data`** | Flag set on a forum claim when it conflicts with an L1 fact. L1 is never modified. |
| **State `Status: Anomaly`** | Flag set on an outlier claim in a signed-graph community. Preserved, queryable. |
| **`t_valid_*`** | The wall-clock interval during which a claim is asserted to be true. |
| **`t_ingest_*`** | The clock interval during which the graph held this version of the claim. Replaced by a newer `t_ingest_from` when superseded. |
| **Three-vendor LLM-as-judge** | The cross-vendor calibration pattern (Sonnet 4.6 + Gemini 2.5 Flash + GPT-4.1-mini) used to mitigate the >50% single-vendor judge-bias error rate measured on JudgeBiasBench. |
| **Trust-tier weighting** | Retrieval ranking factor combining `source_tier × rank × HALO decay × user-credibility(source)`. |
| **Unresolved entity** | A mention that failed alias-snap (similarity < 0.75). Preserved as a marker node; re-attempted automatically on future ingests. |
| **User-credibility rubric** | Per-source author-score: Reddit-rubric (10 features) vs SDN-rubric (7 features, no karma signal). V1 hand-weighted; V1.1 logistic regression. |
| **Wikidata-style rank** | See `Rank`. |
| **XGrammar / XGrammar-2** | Constrained-decoding library for local-model schema enforcement. Replaces Outlines/Guidance/lm-format-enforcer as V1 default for local-model paths. |
| **documents.sqlite** | Thread-complete raw store (1.79 GB) shipping in the V1-June12 bundle. 3.325M rows: every Reddit post, every Reddit comment, every SDN post. Point-lookup by `doc_id` (= graph node id); thread reconstruction via `thread_id`. Built by `cloud/build_documents_sqlite.py`. FTS5 planned (GAP-061). |
| **EAE (Evidence Answer Engine)** | The V1.7 multi-signal answer pipeline: (R1) source-typed evidence counts → (R2) tier-weighted reliability → (R3) popular-vs-correct adjudication → (R4) stance clustering → (R5) popular-vs-correct verdict → (R6) drill-down to individual sources → (R7) comment recall. Design complete 2026-06-16; implementation tasks EAE-1..EAE-7 (tasks #49–55). |
| **ForumConsensus** | Derived graph node (one per school × metric type) holding forum-aggregate statistics: n, p25, p50, p75, range. Built by `cloud/resolve_and_persist.py`; 432 nodes + `CONSENSUS_FOR` edges in V1. |
| **KPA (Key Point Analysis)** | SOTA technique for clustering argument-level stance in a set of documents — outputs "80% say X, 15% say Y, 5% say Z" distributions. Required for EAE-R4 (stance clustering). Not yet built; planned in EAE-6 (task #54). |
| **Page** | L1 graph node for a crawled web page from an official domain (adea.org, ada.org, etc.). `source_tier=L1`, carries `url`, `title`, `content_hash`, `retrieved_date`. Created by `flows/website_crawl_worker.py`. |
| **RA-RAG (Reliability-Aware RAG)** | arXiv 2410.22954. Retrieval architecture that weights sources by tier/reliability and flags popular-vs-correct disagreements. SecBrain's `src/retrieval/consistency.py` implements this. EAE-R3/R5 wire it into the ask path. |
| **SemanticIndex** | Persisted embedding index (18 fp32 shards, 1.27 GB) over 877K Reddit posts (BGE-small 384-dim). Read by `src/retrieval/semantic_index.py` (34 ms warm cosine top-k). Posts-only; comments not yet embedded (GAP-061). |
| **SentimentAnnotation** | Derived graph node: per-document polarity verdict (positive/negative/neutral) extracted by Pass 4. Linked via `ANNOTATES` edge. **Not the same as stance clustering** — polarity is a property of the document, not a position on a contested question (see KPA / GAP-059). |
| **V1-June12 bundle** | Portable 3.27 GB zip (md5 a5a2abf4893d56a26cf57e7204d82f36) containing the full raw corpus, Parquet graph export, and self-contained MCP server. No graph engine required. Assembled by `cloud/assemble_bundle_vm.py`; download at `secbrain-corpus-V1-June12.zip`. |
