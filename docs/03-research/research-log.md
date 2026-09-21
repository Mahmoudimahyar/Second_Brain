# Research Log

> **Methodology note (2026-05-20):** WebSearch and WebFetch were denied in this research session, so I could not verify late-breaking 2025/2026 posts, benchmark numbers, or version strings against live sources. Citations below are **canonical project/docs URLs only** (homepages, docs roots, pricing pages, paper landing pages). Anything that would require a freshly-fetched blog post or benchmark is flagged with `[needs live verification]`. Substantive claims about features/limits draw on knowledge through Jan 2026. Mahyar should re-run the live-source pass before ratifying the ADRs.
>
> **UPDATE 2026-05-29:** the live-source pass was finally run — see **`R-010-sota-review-2026-05.md`** (8-pillar SOTA review, all citations live-verified). It found several R-001…R-009 premises stale/overstated (trust-tier novelty, GraphRAG cost, DITTO-as-SOTA, the proxy-throughput claim) and drives ADR-021…026 + the V1.7 doc corrections. **New rule (AGENTS.md / research-protocol):** no ADR may move to `accepted` while a load-bearing citation is `[needs live verification]`.

---

## R-001 — Graph DB selection (2026-05-20)

**Question:** Which graph store best fits a workstation-scale (millions of nodes/edges), temporally-attributed, 1-3 hop traversal workload with optional native vector search, for V1 internal use on a GTX 1080 + 64 GB RAM box, under hard cost discipline?

**Sources reviewed (canonical):**
- Neo4j docs root: <https://neo4j.com/docs/> and Community edition page <https://neo4j.com/deployment-center/?edition=community>
- Memgraph docs: <https://memgraph.com/docs> ; vector search page <https://memgraph.com/docs/advanced-algorithms/available-algorithms/vector_search>
- Kùzu docs + repo: <https://kuzudb.com/> and <https://github.com/kuzudb/kuzu>
- Apache AGE: <https://age.apache.org/> ; repo <https://github.com/apache/age>
- SurrealDB: <https://surrealdb.com/docs> ; graph relations page <https://surrealdb.com/docs/surrealql/statements/relate>
- LDBC Social Network Benchmark (the only credible apples-to-apples graph perf reference): <https://ldbcouncil.org/benchmarks/snb/>
- Kùzu vs Neo4j paper "Kùzu Graph Database Management System" (CIDR 2023): <https://www.cidrdb.org/cidr2023/papers/p48-jin.pdf>
- `[needs live verification]` Recent 2025-2026 Memgraph & Kùzu release-note posts.

**Options compared:**

| Option | Storage model | Vector index | Temporal edges | License (server) | Fit for V1 |
|---|---|---|---|---|---|
| Neo4j Community 5.x | Native graph, on-disk + page cache | HNSW vector index (built-in since 5.11) | Properties on relationships, no first-class bitemporal | GPL v3 server, single-DB limit on Community | Solid, conservative default |
| Memgraph 2.x | In-memory primary, on-disk durability | HNSW vector index (added 2024) | Edge properties | BSL → community OK for non-DBaaS internal use | Fast traversals; **RAM bound** |
| Kùzu 0.6-0.7+ | Embedded, columnar, vectorized | HNSW (added 2024); read-optimized | Edge properties | MIT | Excellent for batch analytics + GraphRAG; weak for OLTP |
| Postgres + Apache AGE | Postgres tables under a Cypher facade | Via pgvector (sidecar) | Standard SQL temporal patterns | Apache 2.0 | Lowest ops cost; lags Neo4j Cypher coverage |
| Postgres + pgvector + adjacency tables | Pure relational; recursive CTEs for hops | pgvector HNSW | SQL native | PostgreSQL license | Cheapest, weakest 3-hop ergonomics |
| SurrealDB 2.x | Multi-model (doc + graph + KV + vector) | Built-in HNSW | Edge records with arbitrary props | BSL 1.1 | Interesting, but **immature for analytical graph** |

**Recommendation:** **Kùzu (primary), with Postgres + Apache AGE as the justified runner-up.**

Justification:
1. The V1 workload is *predominantly batch ETL* (ingest 500K threads, extract, link, conflict-resolve), not high-concurrency OLTP. Kùzu's columnar, vectorized engine is purpose-built for that shape and routinely beats Neo4j Community on bulk loads and multi-hop analytical queries on a single node (per the CIDR'23 paper and the project's published microbenchmarks — `[needs live verification]` for the most recent numbers).
2. Kùzu is **embedded** (no server to babysit, no JVM, no separate Docker stack). On a single workstation that is a real ergonomic win and frees RAM for the LLM and HNSW indexes.
3. It has a native HNSW vector index, so for V1 you can stay on one engine for graph + vectors and defer the sidecar decision (see R-002).
4. Cypher dialect coverage is sufficient for 1-3 hop traversals, shortest-path, and the trust-tier-weighted retrieval patterns described in the brainstorm-dump.

Runner-up rationale (Postgres + AGE + pgvector): if Mahyar's downstream agents need transactional writes (HITL queue updates, audit log, user accounts), keeping everything in Postgres collapses ops to one engine. AGE's Cypher coverage is narrower than Kùzu/Neo4j and graph perf is materially worse at the multi-hop end, but it is the lowest-risk "one DB to rule them all" option.

**Tradeoffs:**
- Kùzu's biggest weakness is **concurrent writes**: it's a single-writer, multi-reader embedded DB. For V1 internal use that's a non-issue; for V2 multi-user serving it would force a migration (likely to Neo4j or a Postgres sidecar for write traffic).
- Memgraph would be the fastest at query time but **in-memory primary storage on 64 GB RAM is a hard ceiling** once we add embeddings, OS cache, and the LLM. Rejected on hardware grounds.
- Neo4j Community 5 is the safest "you've heard of it" choice but the **single-database limit** in Community, GPLv3, JVM tuning overhead, and slower bulk-load throughput than Kùzu argue against it for an internal-only V1.
- SurrealDB is tempting on paper (one engine for graph + doc + vector) but production reports through 2025 still flag stability and query-planner regressions; not appropriate for a system that will hold curated ground truth.

**Risks:**
- **R1**: Kùzu API/storage-format churn — still pre-1.0; expect at least one schema-rewrite migration before V2.
- **R2**: HNSW index in Kùzu is newer/less battle-tested than Qdrant or pgvector. Mitigation: keep retrieval-layer pluggable (see R-002).
- **R3**: No managed/cloud Kùzu offering. If V2 needs SaaS hosting, plan an exit path to Neo4j Aura or a Postgres+AGE setup.

**User decision needed:** **Yes.** Specific decision points:
- (a) Accept "embedded, single-writer" constraint for V1? (Recommended: yes.)
- (b) Will V2 need multi-user concurrent writes? If yes, plan migration target now (Neo4j vs Postgres+AGE).
- (c) Is GPL-v3 acceptable for any future bundled distribution? If no, that rules out Neo4j Community entirely and reinforces Kùzu (MIT) / AGE (Apache 2.0).

**Docs to update:** `docs/04-architecture/tech-stack.md`, `docs/11-decisions/ADR-001-graph-db.md` (draft pending Mahyar's ratification).

---

## R-002 — Vector / hybrid retrieval (2026-05-20)

**Question:** What is the simplest viable stack that supports hybrid (BM25 + dense vector + graph traversal) retrieval for trust-tier-aware GraphRAG over the cleaned corpus?

**Sources reviewed (canonical):**
- pgvector: <https://github.com/pgvector/pgvector>
- Qdrant docs: <https://qdrant.tech/documentation/> ; hybrid search guide <https://qdrant.tech/articles/hybrid-search/>
- Weaviate docs: <https://weaviate.io/developers/weaviate>
- LanceDB docs: <https://lancedb.github.io/lancedb/>
- sqlite-vec: <https://github.com/asg017/sqlite-vec>
- Kùzu vector search: <https://docs.kuzudb.com/extensions/vector/>
- Neo4j vector index docs (see R-001)
- ANN-Benchmarks: <https://ann-benchmarks.com/>
- Microsoft GraphRAG paper + repo (the design these recommendations are calibrated against): <https://github.com/microsoft/graphrag> ; paper <https://arxiv.org/abs/2404.16130>
- `[needs live verification]` 2025 hybrid-retrieval benchmark posts.

**Options compared:**

| Option | BM25? | Dense | Hybrid (RRF/fusion) | Co-locates with graph? | Ops cost on workstation |
|---|---|---|---|---|---|
| pgvector | via `pg_trgm`/`paradedb` | yes (HNSW) | manual | yes, if graph is in Postgres+AGE | low |
| Qdrant | yes (sparse vectors, since 1.10) | yes (HNSW + quantization) | yes (native fusion) | separate service | medium |
| Weaviate | yes (BM25F native) | yes | yes (hybrid alpha) | separate service | medium-high |
| sqlite-vec | no (use FTS5 alongside) | yes | manual | yes (single file) | trivial |
| LanceDB | yes (Tantivy-backed FTS) | yes | yes (since 2024) | embedded; columnar | low |
| Kùzu native vector | no native BM25 | yes (HNSW) | manual | yes (same engine) | trivial (embedded) |
| Neo4j vector index | no native BM25 (has fulltext index) | yes (HNSW) | manual fusion | yes | medium |

**Recommendation:** **Kùzu's native vector index for V1, plus Tantivy or Postgres FTS for BM25, with a thin retrieval-router (Python) doing reciprocal-rank fusion.** Runner-up: **Qdrant as a sidecar** if Kùzu's HNSW proves immature or if we need quantization to fit recall targets in RAM.

Justification:
1. If R-001 lands on Kùzu, co-locating dense vectors in the same embedded engine eliminates an entire service and an entire copy of the embedding column. That is the simplest viable thing.
2. The cleaned KG will be small enough (probably <50M embedded chunks at 384-d for BGE-small) that a single-node HNSW comfortably fits in RAM with quantization.
3. BM25 on Kùzu is missing → run a separate Tantivy/Lucene FTS index over the same chunk-id space, or piggy-back on Postgres `tsvector` if the HITL/audit DB is Postgres anyway. RRF fusion in Python is ~30 lines.

When to escalate to Qdrant:
- Recall@10 on the eval set is <85% with Kùzu HNSW after tuning, OR
- We need server-side filtered search with complex payload filters (Qdrant's filter pushdown is the best-in-class).

**Native graph-DB vector vs sidecar — verdict:** For V1, native is good enough. Neo4j 5's HNSW vector index and Kùzu's vector extension both target the same ANN quality bar (HNSW with cosine/L2). The historical reason to bolt on Qdrant/Weaviate was **scale + quantization + filtered ANN throughput**, none of which dominate for a 500K-thread internal V1. Re-evaluate when corpus > 5M chunks OR concurrent query QPS > 50.

**Tradeoffs:**
- Sticking with Kùzu vector: one less service, but if you later want filtered ANN with complex predicates you'll hit a wall.
- Qdrant sidecar: more ops, but the best hybrid (sparse+dense) story today and the most mature filtered ANN.
- pgvector: only attractive if R-001 also lands on Postgres+AGE. With Kùzu picked, pgvector adds an engine for no benefit.

**Risks:**
- **R1**: Kùzu HNSW behavior under deletions/updates is less proven than Qdrant's. Mitigation: treat the vector index as derived state; rebuild nightly from canonical embeddings stored in a Parquet/SQL "embedding store."
- **R2**: BM25 quality from Postgres FTS or Tantivy on noisy forum text is mediocre without tuning (stemming, stopwords, n-grams). Budget ~1 week of eval-driven tuning.

**User decision needed:** **No** — recommendation follows mechanically from R-001. Only revisit if R-001 changes.

**Docs to update:** `docs/04-architecture/tech-stack.md`, `docs/11-decisions/ADR-002-vector-retrieval.md` (draft pending).

---

## R-003 — Extraction stack for noisy forum text (2026-05-20)

**Question:** What extraction strategy minimizes cost × error for ~500K threads (~225M input tokens assumed), on a GTX 1080 8 GB + 64 GB RAM workstation, given that a prior GPT-4o-mini freeform run was unsatisfactory?

**Sources reviewed (canonical):**
- Llama 3.1 model card: <https://huggingface.co/meta-llama/Llama-3.1-8B-Instruct>
- Phi-3.5 model card: <https://huggingface.co/microsoft/Phi-3.5-mini-instruct>
- Mistral 7B model card: <https://huggingface.co/mistralai/Mistral-7B-Instruct-v0.3>
- GLiNER: <https://github.com/urchade/GLiNER> ; paper <https://arxiv.org/abs/2311.08526>
- Outlines: <https://github.com/dottxt-ai/outlines>
- lm-format-enforcer: <https://github.com/noamgat/lm-format-enforcer>
- Instructor (Pydantic structured outputs): <https://github.com/jxnl/instructor>
- BGE embedding family: <https://huggingface.co/BAAI/bge-small-en-v1.5>
- Anthropic pricing (Claude Haiku/Sonnet/Opus, batch + caching): <https://www.anthropic.com/pricing> and <https://docs.anthropic.com/en/docs/build-with-claude/batch-processing>
- OpenAI pricing: <https://openai.com/api/pricing/>
- Google Gemini pricing: <https://ai.google.dev/pricing>
- `[needs live verification]` Concrete Haiku 4.5 / Sonnet 4.6 batch rates and any Q1-Q2 2026 price changes.

**Strategies compared (cost figures are estimates; verify rate cards before commit):**

### Strategy A — Full-local cascade
- Llama-3.1-8B-Instruct 4-bit (AWQ/GPTQ) on GTX 1080. Realistic throughput: ~10-25 tok/s output on Pascal (no FP16 tensor cores). For 225M *input* tokens with say 200 output tokens per thread (~100M output tokens) the wall-clock is **weeks to months** if naively serial. Even with vLLM/llama.cpp batching, Pascal's lack of FP16 throughput makes this painful.
- GLiNER (DeBERTa-v3 small/medium) is the real workhorse: zero-shot NER, ~100-500 docs/sec on the GTX 1080, very strong on entity types you can describe in natural language (school names, programs, GPA, DAT score, year).
- spaCy for tokenization, sentence splitting, and rule-based fallback.
- Outlines / lm-format-enforcer for JSON-schema-constrained decoding to kill hallucinated keys.
- Cost: ~$0 in API, but **electricity + wall-clock weeks**.

### Strategy B — API-only
- Claude Haiku 4.5 (or GPT-4o-mini, or Gemini 2.x Flash) via batch API.
- Order-of-magnitude cost (Haiku class, batch discount ~50%, prompt caching for the static system prompt): roughly **$150-$400** for 225M input tokens + ~50M output tokens. **`[needs live verification]` of exact 2026 rates.**
- Pydantic/Instructor for structured output; near-zero structural error.
- Throughput: rate-limit bound, not hardware bound. Days, not weeks.

### Strategy C — Hybrid cascade (recommended)
1. **Stage 1, local, on 100% of threads:** spaCy + GLiNER for "does this thread mention a school/program/year?" + lightweight rule-based filter. Expected pass rate: ~10-25% of threads survive (Mahyar's own assumption was 10-20%).
2. **Stage 2, local, on the survivors:** GLiNER does the entity extraction (school, program, year, score) where it's already strong. ~70-90% of needed structured facts come from here.
3. **Stage 3, API, on the residual:** Claude Haiku 4.5 (or Sonnet 4.6 for the hardest ~5% — sentiment + nuanced interview-question extraction + conflict candidates) with Pydantic-schema-constrained output and prompt caching on the system prompt + ontology.
- Cost: at 15% × 225M = ~34M input tokens to API (mostly Haiku), realistically **$25-$75 total**. **`[needs live verification]`**.
- Wall-clock: 2-4 days end-to-end including Stage 1 sweep.

**Recommendation:** **Strategy C (hybrid cascade).** Strategy A's wall-clock penalty on Pascal is the killer; Strategy B's accuracy on noisy forum text without local pre-filtering wastes money on low-signal threads.

**Throughput sketch on the GTX 1080:**
- GLiNER medium 4-bit / fp16: ~200-400 short docs/sec → 500K threads in ~25-45 min.
- Llama-3.1-8B 4-bit batched via llama.cpp: ~15 tok/s aggregated → impractical for full corpus, OK for spot use.
- BGE-small embeddings (33M params): >2,000 chunks/sec via ONNX → 500K embeddings in <10 min.

**Accuracy delta (educated estimate, not measured):**
- Strategy A: 0.65-0.75 F1 on entity+relation extraction; struggles with sarcasm/sentiment.
- Strategy B: 0.80-0.88 F1; weakness is school-alias disambiguation without your ADEA canonical list in prompt.
- Strategy C: 0.85-0.92 F1 with HITL on ambiguous ~3-5% of cases.

**Late-breaking 2025-2026 notes (knowledge through Jan 2026; verify):**
- Anthropic released Claude Haiku 4.5 with materially better instruction-following at Haiku-tier price; this is what tilts Strategy C decisively over a Sonnet-only API approach.
- Gemini 2.x Flash dropped batch prices late 2025; if Anthropic price moves, re-eval.
- DeepSeek-V3 / Qwen-2.5 32B variants are credible OSS challengers but **do not fit on 8 GB VRAM** even at 4-bit — irrelevant for this workstation.
- GLiNER v2.5 (2025) reportedly improved few-shot generalization; verify before pinning a version.

**Risks:**
- **R1**: Stage-1 filter false-negatives drop signal silently. Mitigation: 1-2% random-sample audit through full pipeline weekly.
- **R2**: API rate limits / Anthropic price hikes. Mitigation: keep Strategy A as a degraded fallback path; abstract the LLM behind a single interface.
- **R3**: GLiNER's school-name recall on unusual spellings ("Penn Dental Med", "HSDM") may underperform. Mitigation: seed canonical-name + alias list from ADEA SQL and pre-attach in extraction prompt.

**User decision needed:** **Yes.** Specific decision points:
- (a) Approve API spend budget (~$100-300/full sweep including reruns).
- (b) Accept Anthropic as primary API vendor (vs Gemini Flash for cheaper unit price, vs OpenAI for tooling familiarity).
- (c) HITL queue throughput target — drives Stage-3 model choice (Haiku vs Sonnet).

**Docs to update:** `docs/04-architecture/tech-stack.md`, `docs/11-decisions/ADR-003-extraction-stack.md` (draft pending).

---

## R-004 — Orthogonal: DSPy 2.x vs BAML for prompt-program optimization (2026-05-20)

**Question:** Should we adopt DSPy or BAML (or both) as the prompt-engineering substrate for the extraction agents?

**Sources reviewed (canonical):**
- DSPy: <https://github.com/stanfordnlp/dspy> ; docs <https://dspy.ai/>
- DSPy paper (MIPRO): <https://arxiv.org/abs/2406.11695>
- BAML: <https://github.com/BoundaryML/baml> ; docs <https://docs.boundaryml.com/>
- Instructor (baseline alternative): <https://github.com/jxnl/instructor>
- Outlines: <https://github.com/dottxt-ai/outlines>
- `[needs live verification]` Recent independent comparison blog posts.

**Comparison:**

| Axis | DSPy 2.x | BAML |
|---|---|---|
| Primary value prop | Auto-optimize prompts/few-shots against a metric | Strongly-typed prompt definitions compiled to client libraries |
| Programming model | Python; "Signatures" + "Modules"; teleprompter optimizers (MIPROv2, BootstrapFewShotWithRandomSearch) | DSL file → generates Python/TS/Ruby clients; type-checked schemas |
| Structured output | Yes, via signature types | Yes, first-class, with robust schema-aligned parsing ("Schema-Aligned Parsing") |
| Best when | You can write an automatic eval metric and want to *optimize* | You want **reliable** structured extraction in production, not auto-tuning |
| Maturity (Jan 2026) | Mature, large community; some API churn through 2025 | Mature for prod use; less community than DSPy but very active |
| Ergonomic cost | Steep learning curve; metric design is the real work | Adds a build step + DSL learning, but very clean once set up |

**Recommendation:** **Use BAML as the production prompt definition + structured-output layer for extraction agents. Use DSPy selectively as an offline optimizer for the few prompts where we have a labeled eval set (Stage-3 LLM extraction, sentiment classifier).**

These are complementary, not competing:
- BAML solves "make sure the JSON parses, the types are right, and the prompt is versioned with the code" — that is the daily pain.
- DSPy solves "find the few-shots and instructions that maximize F1 on my labeled set" — but only if you have the labeled set. For V1 we won't have one until HITL has produced a few thousand gold examples.

Concrete adoption path:
1. V1: BAML for all extraction prompts. Instructor as a lighter fallback if BAML's build step feels heavy.
2. V1.5 (once HITL has produced ~2-5K gold examples for the hardest extraction targets): DSPy MIPROv2 optimization runs against Haiku 4.5 to compress prompts and lift accuracy.

**Risks:**
- **R1**: BAML DSL adds a build step. For a solo dev that's friction. Mitigation: trial it on one extraction prompt before standardizing.
- **R2**: DSPy's optimizer can burn surprising amounts of API spend during compile if the search space is wide. Mitigation: always run optimizers against local models first, then transfer the winning prompt to the API model.

**User decision needed:** **No** for the headline (BAML primary, DSPy later). **Yes** if Mahyar prefers to skip BAML and stick with vanilla Instructor — that's defensible too and removes the DSL.

**Docs to update:** `docs/04-architecture/tech-stack.md`, `docs/11-decisions/ADR-004-prompt-framework.md` (draft pending).

---

## R-005 — Anything else surprising / late-breaking (2026-05-20)

(All items below are knowledge-through-Jan-2026; `[needs live verification]`.)

1. **Microsoft GraphRAG → "LazyGraphRAG"** — Microsoft published LazyGraphRAG late 2024 / 2025, dropping the expensive global community summarization in favor of on-demand local expansion. It is the closest published cousin to the architecture Mahyar described and is worth treating as the reference design. Repo: <https://github.com/microsoft/graphrag>.
2. **Neo4j Community licensing** — Neo4j Community 5.x is GPLv3 with a single-database-per-instance limit. If V2 wants multi-tenant separation by database, this forces Enterprise. Argues further for Kùzu/AGE.
3. **GTX 1080 is the binding hardware constraint, not VRAM alone.** Pascal lacks FP16 tensor cores; per-token throughput on 7-8B models is 3-5× slower than on Ampere/Ada at the same VRAM. Plan the local cascade around GLiNER + embeddings (which Pascal handles fine), not around a local 8B LLM as the workhorse.
4. **HNSW under writes** — HNSW indexes (in pgvector, Kùzu, Memgraph, Neo4j) all degrade under heavy deletion/update workloads. For an evolving graph with continuous re-extraction, plan to rebuild the vector index on a schedule rather than relying on incremental updates.
5. **Pydantic v2 + Instructor + provider-side structured outputs** — OpenAI, Anthropic, and Google all now support server-side JSON-schema enforcement (Anthropic via tool-use, OpenAI via Structured Outputs, Gemini via responseSchema). For 80% of cases this removes the need for Outlines/lm-format-enforcer at the API tier. Local models still need them.
6. **Reddit + SDN ToS** — Out of scope for this research log but worth a separate gap-register entry: bulk-archive use of Reddit content has been a moving compliance target since 2023. Confirm provenance and license of the 500K-thread archive before any external publication, even though V1 is internal-only.
7. **Trust-tier-aware retrieval is under-published.** There is no widely-adopted reference implementation of source-trust scoring inside a GraphRAG retriever. Expect to invent this layer ourselves; budget for it as an R&D track, not as integration work.

---

## Cross-cutting recommendation summary

- **Graph DB:** Kùzu (embedded, MIT). Runner-up: Postgres + Apache AGE.
- **Vectors:** Kùzu's native HNSW + a separate BM25 (Tantivy or Postgres FTS) + RRF fusion in Python. Escalate to Qdrant only if recall/QPS fails.
- **Extraction:** Hybrid cascade — spaCy + GLiNER local filter on 100%; GLiNER extraction on survivors; Claude Haiku 4.5 (API, batch) for the residual ~10-15%.
- **Prompt framework:** BAML for production extraction; DSPy as a later offline optimizer once HITL has produced gold data.

All four ADRs above are **drafts pending Mahyar's ratification** and a **live-source verification pass** (the WebSearch/WebFetch permissions issue blocked confirmation of 2026 benchmark numbers and pricing).

---

## R-008 — Cost/accuracy methods for extraction at scale (2026-05-20)

**Status: BLOCKED — web access denied, research not performed.**

**Question:** For the 500K-thread / ~225M input-token extraction workload, what are the SOTA cost-reduction and accuracy-improvement techniques in 2025-2026, across sampling, prompt caching, batch APIs, cascade rejection, distillation, speculative decoding, structural validators, extraction caches, retrieval-augmented extraction, constrained decoding, few-shot curation, Chain-of-Verification, multi-pass disagreement, domain NER, active learning, embedding-based alias resolution, multi-resolution context, and self-consistency voting?

**Tools required per task spec:** WebSearch + WebFetch. Mahyar explicitly stated "If web access denied, fail loudly." Both tools were denied in this session (same blocker as R-001..R-005 above):

- `WebSearch` — `Permission to use WebSearch has been denied.`
- `WebFetch` against `docs.anthropic.com/en/docs/build-with-claude/prompt-caching` — `Permission to use WebFetch has been denied.`
- `WebFetch` against `www.anthropic.com/pricing` — same denial.

**Why I am not writing a body from training knowledge alone:**

Every technique on the brief depends on **2025-2026-specific numbers** that I cannot responsibly assert without a live fetch:

- Anthropic prompt-caching multipliers, TTL options (5 min vs 1 hour), and minimum-cacheable-token thresholds changed materially through 2025; the only credible source is the live docs page.
- Batch-API discount levels (50% vs deeper), SLA windows, and failure modes differ across Anthropic, OpenAI, and Gemini and have shifted at least twice in 2025.
- Constrained-decoding SOTA (XGrammar, lm-format-enforcer, Outlines vNext, BAML SAP, provider-native structured outputs) moved fast in 2025 — exact perf/accuracy claims need primary sources.
- Embedding-model leaderboards (MTEB, voyage-3, BGE-M3, GTE-Qwen2, mistral-embed) have shifted; a non-live recommendation would be stale.
- GLiNER v2.x feature claims, distillation recipes (e.g., DistillKit, MiniLLM), and speculative-decoding state (Medusa, EAGLE-2, n-gram drafting) all need 2026 verification.

Writing the requested ~3,000-word recommendation from January-2026 priors only would violate Mahyar's "fail loudly" instruction and produce false-confidence numbers that would propagate into ADRs.

**What needs to happen to unblock:**

1. Grant `WebSearch` and `WebFetch` permissions in `.claude/settings.json` (project or user scope).
2. Re-run R-008 with the same prompt; the search plan is queued below.

**Queued search plan (for the rerun):**

Cost-reduction:
1. "Anthropic prompt caching pricing 2026 Claude Haiku 4.5 TTL" + WebFetch `docs.anthropic.com/.../prompt-caching` + `www.anthropic.com/pricing`.
2. "Anthropic batch API discount 2026 SLA failure modes" + WebFetch `docs.anthropic.com/.../batch-processing`.
3. "OpenAI Batch API 50% discount 2026" + WebFetch `platform.openai.com/docs/guides/batch`.
4. "Gemini batch API pricing 2026 responseSchema" + WebFetch `ai.google.dev/pricing`.
5. "Stratified sampling LLM extraction R&D subset best practices 2025".
6. "Cascade rejection cheap classifier LLM pipeline 2025 GLiNER spaCy fastText".
7. "Distillation Haiku to small model labeling 2026 DistillKit MiniLLM data volume".
8. "Speculative decoding API + local draft 2026 Medusa EAGLE-3 n-gram".
9. "Content-addressable extraction cache canonicalization LLM pipeline 2025".
10. "Retrieval-augmented extraction snap to canonical list cost accuracy 2026".

Accuracy:
11. "XGrammar Outlines lm-format-enforcer BAML SAP benchmark 2025".
12. "Anthropic tool-use structured outputs OpenAI Structured Outputs Gemini responseSchema 2026 reliability".
13. "Few-shot example selection semantic similarity vs static 2026".
14. "Chain-of-Verification CoVe extraction cost accuracy 2025 paper".
15. "Multi-pass extraction disagreement two-model ensemble 2025".
16. "GLiNER v2.5 vs fine-tuned BERT vs LLM NER 2026 noisy text".
17. "Active learning LLM extraction low-volume HITL 2025 patterns".
18. "MTEB 2026 leaderboard voyage-3 BGE-M3 GTE-Qwen2 mistral-embed entity disambiguation".
19. "Multi-resolution context filtering title first-N tokens extraction loss curves 2025".
20. "Self-consistency extraction voting temperature 2025 paper".

Each query will be paired with a WebFetch against the top 1-2 canonical sources (arxiv, project docs, vendor pricing pages, well-known 2025-2026 engineering blogs) before any claim is committed.

**No recommendations are made in this entry.** Re-run after permissions are restored. The 5-lever summary Mahyar asked for cannot be produced honestly without the live data.

