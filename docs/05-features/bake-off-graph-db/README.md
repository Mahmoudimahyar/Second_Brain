# Feature: Graph-DB Bake-Off

**Status:** Proposed — awaiting Mahyar's green light + asset paths (Q-002) + DB engine clarification (Q-020) from round 3.
**Owner:** Mahyar (decisions) + Claude (execution).
**Time budget:** 1-2 days.
**Output:** ADR-001 ratification (which graph DB the V1 product engine uses).

## Why this exists

R-006 invalidated R-001's primary pick: **Kùzu was acquired by Apple and the OSS repo was archived 2025-10-10.** We now have three credible candidates and no clear winner from desk research alone. R-007 surfaced a strong contender (**Graphiti**) that is ~90% of our 3-layer bitemporal architecture out-of-the-box, which complicates "just pick a graph DB" into "pick a graph-DB + library stack."

This bake-off settles the architecture choice with a quantitative test on a representative sample, so ADR-001 can be ratified instead of guessed.

## The three candidates

| | LadybugDB | Graphiti + Neo4j Community | Postgres + Apache AGE + pgvector |
|---|---|---|---|
| Origin | Active MIT fork of Kùzu after Apple acquisition; monthly 2026 releases | MIT temporal-KG engine (arxiv 2501.13956, KGC 2025); rides on Neo4j or FalkorDB | Postgres extensions (AGE for graph + pgvector for embeddings) |
| Storage model | Embedded, columnar, vectorized | Neo4j native graph store | Postgres heap + AGE label tables |
| Vector index | Native HNSW | Neo4j 5.x vector index (HNSW) | pgvector HNSW |
| Bitemporal edges | Property addition | **Native — Graphiti enforces `t_valid_*` + `t_ingest_*`** | Property addition |
| Cypher coverage | Inherits Kùzu's | Full Neo4j Cypher | Partial (AGE narrower) |
| License | MIT | MIT (Graphiti) + GPLv3 (Neo4j Community) | Apache 2.0 + PostgreSQL |
| Ops cost (V1 single-node) | Trivial (embedded) | Medium (JVM, separate process) | Low (Postgres you'd run anyway) |
| Risk | Newer fork — stability, ecosystem | GPLv3 + single-DB Community limit | AGE Cypher gaps, slower 3-hop |

## What the bake-off measures

Five metrics, weighted by impact on V1 (per `docs/04-architecture/system-overview.md` §8):

| Metric | Why it matters | Weight |
|---|---|---|
| Bulk-load time | One-shot extraction → re-import after rerun; cycle latency | High |
| 3-hop traversal latency | The trust-tier-aware retrieval query shape | High |
| HNSW recall@10 | Quality of nearest-neighbor over ~50K embedded chunks | High |
| Bitemporal-edge ergonomics | Native vs property-add; affects every conflict-resolution query | Medium-High |
| Ops complexity | Services / JVMs / schemas / install footprint | Medium |

See `test-plan.md` for the exact methodology + acceptance thresholds.

## Definition of done

- Three candidates installed, sample data loaded, all 5 metrics measured.
- A short comparison table written into `docs/11-decisions/ADR-001-graph-db.md` (created by the bake-off output).
- A justified winner + runner-up + explicit "what would change our mind in V2."
- The graph-DB pick is no longer a blocker for any of: ADR-002 retrieval, ADR-003 extraction, ADR-007+ user-credibility / opinion-consensus / bitemporal-edge implementation, `tools/graphrag/` MCP context server build, V1 vertical-slice TDD.

## Not in scope

- Production hardening of the chosen DB (V1 ships internal, single-node).
- Multi-tenant / cloud / HA evaluation (V2 concern).
- Final tuning of HNSW parameters (round-1 defaults are enough to compare candidates).
- Choice of BM25 backend (Tantivy vs Postgres FTS) — independent decision, ADR-002.
