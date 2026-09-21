# R-006 — Live verification of R-001..R-005 (2026-05-20)

> Per-claim verification of the prior research log using live WebSearch. WebFetch was denied this session, so all citations are search-result-summary level (vendor blogs, vendor pricing pages, GitHub releases, recent technical posts surfaced by search). Where claims could not be verified beyond search snippets, that limit is called out.

## Methodology
- **Tools used:** WebSearch (WebFetch denied; noted where it would have helped).
- **Date:** 2026-05-20.
- **Source priority:** vendor official docs > vendor blogs > GitHub releases > third-party 2025-2026 engineering posts > older posts.
- **Seed values (treated as known-correct, then sanity-checked):** Haiku 4.5 $1/$5 standard, $0.50/$2.50 batch, 90% caching discount, $0.05/1M cached batch input.

---

## R-001 verification — Graph DB

### CONFIRMED
- **Neo4j Community 5.x license = GPLv3, single-database-per-instance.** Confirmed across Neo4j community forum and GitHub issue threads. ([Limitation of Neo4j Community Edition](https://community.neo4j.com/t/limitation-of-neo4j-community-edition/74547), [GitHub issue #8331 — GPL v3 vs AGPL v3](https://github.com/neo4j/neo4j/issues/8331)) No 2025-2026 license change for the Community edition. Enterprise Edition moved to "Open Core" but that doesn't affect Community.
- **Memgraph license = BSL 1.1**, converting to Apache 2.0 after change date. Enterprise priced from ~$25k/yr per 16 GB; license metered on managed memory. ([Memgraph BSL.txt](https://github.com/memgraph/memgraph/blob/master/licenses/BSL.txt), [Memgraph pricing](https://memgraph.com/pricing), [HN thread on Memgraph cost](https://news.ycombinator.com/item?id=43813626))
- **Memgraph now ships an ON_DISK_TRANSACTIONAL storage tier** (HDD/SSD) — partly mitigates the "in-memory only" criticism in R-001 but at lower performance. ([Storage memory usage docs](https://memgraph.com/docs/fundamentals/storage-memory-usage))
- **Apache AGE is actively maintained.** Releases through Sep 2025 + Jan 21 2026 added row-level security and id-column indexes; openCypher coverage still narrower than Neo4j/Kùzu. ([Apache AGE release notes](https://age.apache.org/release-notes/))

### CORRECTED — major change
- **Kùzu was acquired by Apple; the open-source repo was archived 2025-10-10.** The GitHub repo is read-only, the website is gone, the company was wound down. This invalidates Kùzu-as-primary in R-001. ([The Register: KuzuDB abandoned](https://www.theregister.com/2025/10/14/kuzudb_abandoned/), [9to5Mac: Kuzu joins Apple's recent acquisitions](https://9to5mac.com/2026/02/11/kuzu-database-company-joins-apples-list-of-recent-acquisitions/), [MacRumors](https://www.macrumors.com/2026/02/11/apple-acquires-new-database-app/), [HN: KuzuDB archived after Apple acquisition — migration guide](https://news.ycombinator.com/item?id=47152757))
- **Last released version was 0.11.0 (July 2025), introducing single-file `.kuzu`/`.kz` databases and an LLM extension.** ([Kuzu 0.11.0 release blog](https://blog.kuzudb.com/post/kuzu-0.11.0-release/)) No 1.0 ever happened.
- **Community continuations exist but are not corporate-backed:**
  - **LadybugDB** — most active fork. Stable 0.16.1 (May 4 2026), dev 0.17.0.dev released May 19 2026. Already adds disk-based HNSW vector indexes with cosine/L2, configurable m/ef. Positioned for "edge agent memory" and regulated industries. ([LadybugDB site](https://ladybugdb.com/), [Ladybug GitHub releases](https://github.com/LadybugDB/ladybug/releases), [v0.12.0 release blog](https://blog.ladybugdb.com/post/ladybug-release/), [Vector search in LadybugDB](https://medium.com/@volodymyrpavlyshyn/vector-search-in-ladybugdb-to-power-up-rag-46ccaf5df4fa))
  - **Bighorn** (Kineviz fork) and **Vela-Engineering/kuzu** (adds concurrent multi-writer for multi-agent AI) also exist. ([Vela Partners: KuzuDB fork for AI agents](https://vela.partners/blog/kuzudb-ai-agent-memory-graph-database), [Neo4j Alternatives in 2026 — ArcadeDB blog](https://arcadedb.com/blog/neo4j-alternatives-in-2026-a-fair-look-at-the-open-source-options/))

### NEW 2025-2026 info
- **NaviX paper (VLDB 2025, vol 18, p4438)** — Kùzu team's predicate-agnostic vector index design, published before the Apple acquisition; codebase lives on in LadybugDB. ([NaviX arxiv](https://arxiv.org/html/2506.23397v1))
- **FalkorDB** has matured as an embedded GraphRAG-focused alternative (sparse-matrix engine, FalkorDBLite Python embedded variant, own GraphRAG SDK). ([FalkorDBLite blog](https://www.falkordb.com/blog/falkordblite-embedded-python-graph-database/), [FalkorDB GraphRAG-SDK](https://github.com/FalkorDB/GraphRAG-SDK))
- **No credible 2025-2026 LDBC SNB run** compares all four (Kùzu/Memgraph/Neo4j/AGE) head-to-head. Memgraph's "Benchgraph" is self-published and explicitly *not* an official LDBC implementation. ([Memgraph mgbench README](https://github.com/memgraph/memgraph/blob/master/tests/mgbench/README.md))

### VERDICT
**Pick changes.** Kùzu as named is gone. Three viable replacements ranked for the V1 brief:
1. **LadybugDB** (Kùzu fork, MIT, single-file embedded, HNSW vectors, active dev) — direct drop-in for the original Kùzu recommendation. Risk: small community, no corporate sponsor; treat as a calculated bet justified by API/format continuity.
2. **Postgres + Apache AGE + pgvector** — promoted from runner-up to primary defensible choice if Mahyar prefers a sponsored, Apache-licensed stack with a one-engine story; AGE Cypher coverage still narrower than Neo4j.
3. **FalkorDB / FalkorDBLite** — newcomer worth piloting; tighter GraphRAG-native ergonomics, but earlier in maturity for analytical workloads than LadybugDB.

Memgraph rejected on cost (BSL + $25k/yr enterprise gate). Neo4j Community still defensible but GPLv3 + single-DB still hold.

---

## R-002 verification — Vector / hybrid retrieval

### CONFIRMED
- **Qdrant remains best-in-class for hybrid sparse+dense.** Qdrant 1.16 (early 2026) added configurable RRF `k`, ACORN filtered-ANN search algorithm for weak-selectivity multi-filter queries, and Inline Storage for HNSW on disk. ([Qdrant 1.16 blog](https://qdrant.tech/blog/qdrant-1.16.x/), [Qdrant hybrid queries docs](https://qdrant.tech/documentation/search/hybrid-queries/), [Qdrant sparse-vectors article](https://qdrant.tech/articles/sparse-vectors/))
- **LanceDB hybrid (BM25 via Tantivy + dense + RRF) is production-validated in 2026.** Now offers Lance-native SQL retrieval via DuckDB, 1.5M IOPS benchmarks, multimodal lakehouse positioning. Viable as an all-in-one replacement for the (vector + BM25 + RRF) layer. ([LanceDB FTS docs](https://docs.lancedb.com/search/full-text-search), [LanceDB hybrid+reranking playbook](https://optyxstack.com/rag-reliability/hybrid-search-reranking-playbook), [LanceDB site](https://www.lancedb.com/))
- **The "Kùzu native HNSW" piece of the R-002 plan persists in LadybugDB.** Native disk-based HNSW with cosine/L2, configurable m/ef, query-in-Cypher integration is shipped. ([Vector search in LadybugDB](https://medium.com/@volodymyrpavlyshyn/vector-search-in-ladybugdb-to-power-up-rag-46ccaf5df4fa), [Hybrid Graph RAG with LadybugDB](https://volodymyrpavlyshyn.medium.com/hybrid-graph-rag-with-ladybugdb-when-vectors-meet-graphs-aa7ddec45632))

### CORRECTED
- The R-002 recommendation cites "Kùzu's native HNSW" — that engine is archived. Substitute **LadybugDB's HNSW** (same code lineage) or fall back to **Postgres + pgvector + tsvector** if R-001 lands on AGE.

### NEW 2025-2026 info
- **Qdrant hybrid has a known 2026 bug** where `BM25 sparse encoder` is instantiated even when the embedder provides native sparse vectors — worth knowing before benchmarks. ([agno-agi issue #7432](https://github.com/agno-agi/agno/issues/7432))

### VERDICT
**Pick stands in shape, swap engine.** Hybrid stack = (LadybugDB HNSW **or** pgvector) + (Tantivy/LanceDB FTS **or** Postgres FTS) + RRF in Python. Escalate to Qdrant only on recall/QPS failure. If Mahyar wants the simplest possible thing, **LanceDB alone** is a credible single-engine replacement for the "vectors + BM25 + RRF" layer in 2026.

---

## R-003 verification — Extraction stack

### CONFIRMED
- **Haiku 4.5 standard pricing $1.00/$5.00 per 1M in/out tokens.** Released Oct 15 2025, 200K context. ([Anthropic pricing](https://platform.claude.com/docs/en/about-claude/pricing), [pecollective pricing guide](https://pecollective.com/tools/claude-pricing-guide/), [BenchLM Apr 2026 snapshot](https://benchlm.ai/blog/posts/claude-api-pricing))
- **Batch API = 50% off both directions across all Claude models.** Async, 24h SLA, typical completion in minutes. ([Anthropic batch pricing references in cloudzero/Finout/etc.](https://www.finout.io/blog/anthropic-api-pricing))
- **Prompt caching multipliers:** 5-min cache write = 1.25× base input; 1-hr cache write = 2× base input; cache read = 0.1× (i.e., 90% off). Sonnet 4.6 example: $3.75 / $6.00 / $0.30 per MTok. ([Anthropic prompt caching docs](https://platform.claude.com/docs/en/build-with-claude/prompt-caching), [aicheckerhub 2026 caching guide](https://aicheckerhub.com/anthropic-prompt-caching-2026-cost-latency-guide))
- **Sonnet 4.6 = $3.00/$15.00 standard, $1.50/$7.50 batch, 1M-token context at flat rate.** ([apidog Sonnet 4.6 pricing](https://apidog.com/blog/claude-sonnet-4-6-pricing/), [pecollective](https://pecollective.com/tools/anthropic-api-pricing/))
- **GPT-4o-mini = $0.15/$0.60; GPT-4.1-mini = $0.40/$1.60 per 1M.** Batch = 50% off, caching up to 90%. ([OpenAI API pricing](https://openai.com/api/pricing/), [pricepertoken GPT-4o-mini page](https://pricepertoken.com/pricing-page/model/openai-gpt-4o-mini))
- **Gemini 2.5 Flash = $0.30/$2.50 standard; batch $0.15/$1.25. Flash-Lite = $0.10/$0.40 standard, $0.05/$0.20 batch.** Long-context (>200K) tier is more expensive. ([Gemini pricing guide](https://www.finout.io/blog/gemini-pricing-in-2026), [Google Gemini pricing](https://ai.google.dev/gemini-api/docs/pricing))
- **DeepSeek-V3 ≈ $0.27/$1.10 per 1M as of March 2026** (after the 2026-04-26 price adjustment cycle). Cache-hit input at 1/10 launch price. ([DeepSeek pricing](https://api-docs.deepseek.com/quick_start/pricing/))
- **GLiNER v2 ("GLiNER2") landed late 2025** — schema-driven multi-task model (NER + classification + structured extraction), <500M params, edge-deployable, EMNLP 2025 demo. Newer "Million-Label NER" bi-encoder paper reports 61.5% Micro-F1 on CrossNER zero-shot and ~130× throughput at 1024 labels. ([GLiNER2 ACL Anthology](https://aclanthology.org/2025.emnlp-demos.10/), [GLiNER2 arxiv](https://arxiv.org/html/2507.18546v1), [Million-Label NER paper](https://arxiv.org/pdf/2602.18487))
- **spaCy 3.x is still the stable line.** Latest stable is 3.8.14 (Mar 29 2026). spaCy 4 is still pre-release (dev3, Apr 2024). ([spaCy on PyPI](https://pypi.org/project/spacy/))
- **Constrained-decoding SOTA shifted to XGrammar** (and XGrammar-2 released May 2026 — 80× faster compile vs original). XGrammar default in 2026; Outlines for very complex reused schemas; lm-format-enforcer fallback. ([XGrammar paper](https://arxiv.org/pdf/2411.15100), [SGLang structured outputs](https://docs.sglang.ai/advanced_features/structured_outputs.html), [JSONSchemaBench](https://arxiv.org/pdf/2501.10868))

### CORRECTED
- **March 2026 silent TTL regression.** Anthropic appears to have silently changed the prompt-cache default TTL from 1h → 5m around early March 2026, causing 20-32% cache-creation cost inflation for users who didn't re-pin the longer TTL. Pin TTL explicitly. ([dev.to: 5-Minute TTL Change](https://dev.to/whoffagents/claude-prompt-caching-in-2026-the-5-minute-ttl-change-thats-costing-you-money-4363), [claude-code issue #46829](https://github.com/anthropics/claude-code/issues/46829))
- **DeepSeek-V3 unit price has crept up** vs. R-003's implicit "ultra-cheap OSS API" framing. $0.27/$1.10 (V3) and V3.2 variants make it less of a steal vs Gemini 2.5 Flash-Lite at $0.10/$0.40.

### NEW 2025-2026 info
- **GLiNER bi-encoder lets you precompute label embeddings**, which makes pre-filter step on 100% of corpus essentially free at the throughput end. Pin a specific version when standardizing.
- **XGrammar-2 is the default constrained-decoding choice in 2026** for local models; for API tiers, all three majors now have server-side schema enforcement (Anthropic tool-use, OpenAI Structured Outputs, Gemini responseSchema).

### VERDICT
**Pick stands.** Hybrid cascade (spaCy + GLiNER2 filter → GLiNER2/bi-encoder extraction → Haiku 4.5 residual w/ BAML + batch + caching) is still the right architecture; pricing math from R-003 holds. Minor adjustments: pin GLiNER2 (not vague v2.5), pin XGrammar over Outlines as the local constrained-decoder default, pin cache TTL explicitly to avoid the silent regression, treat Gemini 2.5 Flash-Lite as a credible substitute for the residual API tier if Anthropic rate-limits bind.

---

## R-004 verification — Prompt frameworks

### CONFIRMED
- **BAML is actively maintained and used in production.** Latest release 0.222.0 on Apr 27 2026. Weekly cadence. Schema-Aligned Parsing (SAP) <10ms Rust-based parser remains the differentiator vs. Instructor / vanilla function-calling / constrained generation. ([BAML GitHub](https://github.com/BoundaryML/baml), [BAML SAP blog](https://boundaryml.com/blog/schema-aligned-parsing), [Pydantic vs Instructor vs BAML 2026 comparison](https://medium.com/@rajkundalia/how-baml-brings-engineering-discipline-to-llm-powered-systems-983c06d31bf8))
- **DSPy 3.0 shipped Aug 12 2025** (3.0.3 by Aug 31). Stable. ([DSPy releases](https://github.com/stanfordnlp/dspy/releases), [Databricks DSPy 3.0 session](https://www.databricks.com/dataaisummit/session/dspy-30-and-dspy-databricks))

### CORRECTED — meaningful update to the optimizer story
- **GEPA has displaced MIPROv2 as the recommended DSPy optimizer.** GEPA (Genetic-Pareto, Agrawal et al. 2025, arxiv:2507.19457) "consistently outperforms top RL approaches like GRPO and leading optimizers like MIPROv2, all while using up to 35× fewer rollouts" — exposed as `dspy.GEPA`. R-004's "DSPy MIPROv2 later" line should be rewritten to **"DSPy GEPA later"** unless a specific reason to prefer few-shot-bootstrap optimization applies. ([dspy.GEPA overview](https://dspy.ai/api/optimizers/GEPA/overview/), [GEPA repo](https://github.com/gepa-ai/gepa), [GEPA-as-game-changer post](https://medium.com/superagentic-ai/gepa-the-game-changing-dspy-optimizer-for-agentic-ai-bfc1da20383a))

### NEW 2025-2026 info
- **TextGrad** (Yuksekgonul et al., 2025, Nature) and **AdalFlow** (LLM-AutoDiff, Yin & Wang 2025) are credible competitors to DSPy GEPA — backprop-style textual gradients. ([TextGrad guide](https://www.morphllm.com/textgrad), [AdalFlow repo](https://github.com/SylphAI-Inc/AdalFlow))
- **promptolution** (arxiv 2512.02840) surveys/unifies all four families — worth a skim when V1.5 optimization work starts.
- No equivalently mature competitor displaces BAML for the *production* (typed structured output, multi-language client) niche.

### VERDICT
**Pick stands with a name change.** BAML as production-prompt layer; DSPy **GEPA** (not MIPROv2) as the V1.5 offline optimizer once HITL gold data accumulates. TextGrad/AdalFlow are on the radar but not yet preferable to DSPy for a Python-first solo dev.

---

## R-005 verification — Misc late-breaking

### CONFIRMED
- **LazyGraphRAG is real, has Microsoft Research backing, but is *not yet* in the open-source `microsoft/graphrag` library.** Production infra in Microsoft Discovery + Azure Local from June 2025; OSS integration tracked for Q1-Q2 2026 with "next milestone" status confirmed by Microsoft devs on GitHub as of early 2026. Claimed cost: ~0.1% of full GraphRAG indexing, ~700× lower query cost on global queries with comparable quality. ([Microsoft Research LazyGraphRAG blog](https://www.microsoft.com/en-us/research/blog/lazygraphrag-setting-a-new-standard-for-quality-and-cost/), [graphrag discussion #1490](https://github.com/microsoft/graphrag/discussions/1490))
- **GraphRAG fork landscape (LightRAG, fast-graphrag, nano-graphrag, HippoRAG) is active in 2026.** LightRAG (HKUDS) crossed 23k+ GitHub stars by Nov 2025 ([Chao Huang tweet](https://x.com/huang_chao4969/status/1990277067431424465)), EMNLP 2025 paper, OpenSearch backend added March 2026. fast-graphrag (Circlemind) claims 27× faster + 40% more accurate than GraphRAG. HippoRAG sells "10-30× cheaper multi-hop reasoning." ([Fast GraphRAG vs LightRAG comparison](https://www.aitoolnet.com/compare/fast-graphrag-vs-lightrag), [Awesome-GraphRAG curated list](https://github.com/DEEP-PolyU/Awesome-GraphRAG), [GraphRAG vs HippoRAG vs PathRAG comparison](https://medium.com/graph-praxis/graphrag-vs-hipporag-vs-pathrag-vs-og-rag-choosing-the-right-architecture-for-your-knowledge-graph-a4745e8b125f))
- **2026 GraphRAG benchmarks exist:** GraphRAG-Bench (arxiv 2506.02404), WildGraphBench (arxiv 2602.02053), "When to use Graphs in RAG" (arxiv 2506.05690). Existing UltraDomain + HotpotQA are now called out as inadequate (skewed question distributions: UltraDomain 97% contextual-summarize, HotpotQA 78% fact-retrieval). ([GraphRAG-Bench](https://arxiv.org/pdf/2506.02404), [When to use Graphs in RAG](https://arxiv.org/html/2506.05690v3))

### CORRECTED
- The R-005 phrasing "LazyGraphRAG status — `[needs live verification]`" is now resolvable: **not yet open-sourced as a library, but algorithm + Azure productization is real**. Plan around the OSS drop landing 2026-Q2 if needed.

### NEW 2025-2026 info
- The Kùzu acquisition (covered in R-001) is the biggest unprompted surprise.
- BAML's SAP technique is now broadly cited as the production reliability story vs. server-side JSON modes.
- HNSW-under-writes concern (R-005 item 4) still valid; nightly rebuild from a canonical embedding store remains the recommended pattern.

### VERDICT
**Pick stands.** Reference architecture = LazyGraphRAG ideas applied on top of LightRAG-style local graph construction. When the OSS LazyGraphRAG drops, re-evaluate vs LightRAG/fast-graphrag.

---

## Cross-cutting verdict

The biggest finding is that **Kùzu — the linchpin of R-001 and the vector layer of R-002 — was acquired by Apple in October 2025 and the open-source repo was archived.** That single fact forces ADR-001 and ADR-002 to swap engine names. The cleanest replacement is **LadybugDB** (active MIT fork, same Cypher dialect, same single-file format, ships HNSW vectors, releasing monthly in 2026), with **Postgres + Apache AGE + pgvector** as the sponsor-backed conservative alternative and **FalkorDB / LanceDB** as second-pass options. Pricing seeds for Haiku 4.5 and Sonnet 4.6 are all verified; the only pricing-relevant surprise is Anthropic's silent **5-min default TTL regression in March 2026**, which requires explicit 1-hour pinning in code to preserve the cost math. R-003's hybrid-cascade architecture, the BAML primary / DSPy-later prompt-framework choice, and the LazyGraphRAG reference-architecture posture all survive intact — with the small refresh that **DSPy GEPA**, not MIPROv2, is now the SOTA optimizer; **GLiNER2** with bi-encoder is the NER workhorse to pin; and **XGrammar(-2)** is the default constrained-decoding library for local models. No pricing column moved enough to threaten the ~$25-$75 full-sweep cost envelope.
