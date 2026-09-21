# ADR-025: GraphRAG Engine Evaluation (LightRAG / Graphiti vs Custom 5-Pass) — SPIKE

Status: **proposed** (2026-05-29) — **decision deferred to a spike.** Do NOT rip out the
custom pipeline on the strength of this ADR. This ADR authorizes a measured evaluation and
defines the decision criteria; a successor ADR (or an amendment flipping this to `accepted`)
records the outcome.

## Context

The 2026-05-29 SOTA review (R-010) found that two premises behind the custom 5-pass engine
are stale or partly redundant in 2026:

- **"Microsoft GraphRAG is too expensive at 500K-thread scale" is a 2024 fact.** Indexing/
  query cost fell ~100–1000× via **LazyGraphRAG** (defers LLM work to query time; ~0.1%
  indexing cost) and **LightRAG** (~1/100 cost, native incremental insert), and MS GraphRAG
  itself added incremental indexing + DRIFT search. (LazyGraphRAG is **not** open-source —
  Azure-only — so it is a benchmark, not an adoptable dependency.)
- **Temporal + provenance + incremental updates are largely solved by existing systems.**
  **Zep/Graphiti** (arXiv 2501.13956) is a bitemporal KG with recency-native, incremental,
  hybrid retrieval — i.e. much of what our custom Pass 1–5 + bitemporal machinery rebuilds.
  **HippoRAG 2** and **LightRAG** give incremental graph memory.
- The **genuinely novel** SecBrain surface is the **L1–L5 trust-tier weighting + conflict
  resolution** (ADR-021/006/026), which **none** of these frameworks ship.

So the open question: should the trust-tier layer sit **on top of LightRAG/Graphiti** (less
infra to own, incremental + recency for free) or stay on the **custom 5-pass + Kùzu** stack?

## Spike (what to actually do — this is the "decision")

Run a 1-week bounded evaluation, harness reusable like the graph-DB bake-off:

1. **Candidates:** (a) keep custom (Kùzu + Pass 1–5), (b) LightRAG as the graph/retrieval
   substrate + our trust-tier layer on top, (c) Graphiti(+Neo4j) as substrate + our layer.
2. **Sample:** the same real `External Data/` subgraph used for the graph-DB bake-off
   (ADEA L1 + r/DentalSchool L5).
3. **Metrics (decision rubric, pre-registered):**
   - Can the trust-tier prior + bitemporal `as_of` + conflict hooks be expressed on the
     substrate **without forking it**? (yes/partial/no — gating)
   - Incremental re-ingest cost + wall-clock (daily-update cadence is a V1 requirement).
   - Retrieval quality on a small cited-QA set vs the custom path.
   - Ops complexity on the single Windows workstation (Neo4j = Docker+JVM; LightRAG = Python).
   - Migration cost from the current Kùzu schema.
4. **Decision criterion:** adopt a framework only if it expresses the trust-tier + bitemporal
   + conflict surface without a fork **and** beats custom on incremental cost or retrieval
   quality without losing the L1-immutability guarantees. Otherwise keep custom and merely
   **re-baseline the cost claims** in the docs and adopt the cheap *ideas* (lazy/query-time
   summarization, incremental insert).

## Measured outcome — bounded spike (V1.7, 2026-05-30)

Ran the store-layer bake-off (`tools/graph_engine_bakeoff/`) on the real residency
graph (1,214 nodes / 1,634 edges) — custom **Kùzu vs Neo4j 5.26** (loaded natively),
five matched Cypher queries, 60 iters; report `.agent/reports/v1.7-wp5-adr025-graphrag-engine-spike.md`.

| | point-lookup | 1-hop | 2-hop | aggregation | 3-hop |
|---|---|---|---|---|---|
| Kùzu p50 | **0.21 ms** | **0.97 ms** | 6.02 ms | 5.04 ms | 14.19 ms |
| Neo4j p50 | 3.28 ms | 5.12 ms | **2.80 ms** | **2.70 ms** | **2.36 ms** |

Crossover ≈ 2 hops: embedded Kùzu wins shallow (5–15×, no Bolt hop), Neo4j's
native typed adjacency wins deep multi-hop (2–6×). **Both 16× under the NFR-1
< 250 ms budget — performance does not force a migration.** Kùzu's multi-hop cost
is largely the **single-table `label`-as-property schema** (each hop filters
`e.label=…`); the high-leverage fix is a **native typed Kùzu schema**, not a DB
migration (keeps embedded speed, no new ops). **LightRAG / Graphiti** both require
an LLM client + embedder for ingest (verified: `Graphiti(…, llm_client, embedder)`,
`LightRAG(…, llm_model_func, embedding_func)`) — they are LLM graph-**construction**
frameworks that would replace our deterministic, L1-grounded construction (the
differentiator), so **not adopted** as the engine.

**Decision (resolving the spike): keep the custom Kùzu engine for V1**; refactor
to a native typed schema if/when deep multi-hop dominates; reconsider Neo4j only
then, as a human-approval migration. ADR stays `proposed` pending that trigger;
no production change made.

## Consequences (either branch)

- **Re-baseline now regardless:** the "GraphRAG too expensive" framing in
  `product-vision.md` / `system-overview.md` is corrected to cite LazyGraphRAG/LightRAG 2025
  (done in V1.7 doc edits) — this is independent of the spike outcome.
- If "adopt": a migration ADR + a new `DataSource`/store adapter; trust-tier layer becomes a
  thin layer over the framework. If "keep": custom stays, with the lazy/incremental ideas
  folded into Pass 3–5.
- Risk of *not* doing the spike: continuing to hand-build (and hand-maintain) incremental +
  recency machinery that a maintained OSS framework already provides.

## Related docs
- `docs/03-research/R-010-sota-review-2026-05.md` (LazyGraphRAG; LightRAG; Zep/Graphiti arXiv 2501.13956; HippoRAG 2; GraphRAG-Bench)
- `docs/04-architecture/system-overview.md` (cost framing), `docs/05-features/bake-off-graph-db/` (harness pattern to reuse)
- `docs/00-bootstrap/implementation-status.md` (SOTA spike row)

## Related code (spike harness)
- `tools/graph_engine_bakeoff/` — Kùzu-vs-Neo4j store bake-off + LightRAG/Graphiti fit probe
