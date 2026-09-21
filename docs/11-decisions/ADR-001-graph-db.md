# ADR-001: Graph Database Selection

Status: **accepted** (bake-off complete 2026-05-21)
Date: 2026-05-20 (initial); ratified 2026-05-21

## Context

The V1 product engine needs a graph store that supports: millions of nodes / edges, native or sidecar HNSW vector index, property indexes on `source_tier` + `t_valid_*`, 1-3 hop traversal at < 250 ms p95, bulk-load throughput for re-imports, and a bitemporal edge model (Graphiti/Zep style). Single-node, single-writer is acceptable for V1.

R-001 (no live web) initially recommended **Kùzu**. R-006 (live web) found that the Kùzu OSS repo was archived after Apple's acquisition (2025-10-10). Three replacements were bake-off-measured per `docs/05-features/bake-off-graph-db/test-plan.md`:

1. **Kùzu** — pip-published `kuzu==0.11.3` (the last installable lineage); embedded, columnar, native HNSW, MIT.
2. **Graphiti + Neo4j Community** — Graphiti (arxiv 2501.13956, KGC 2025) on Neo4j 5.x Community. Graphiti models the bitemporal 4-tuple natively; Neo4j 5 has native HNSW.
3. **Postgres 18 + Apache AGE + pgvector** — single-engine combo for HITL writes + audit log + graph + vectors.

## Decision

**Kùzu** for V1 (`kuzu==0.11.3`, embedded, MIT). When the active LadybugDB MIT fork publishes to PyPI, swap by changing the dependency pin — the schema + driver code do not change.

### Why

Raw weighted scores (per the `test-plan.md` rubric, sample = 28,403 nodes / 41,914 edges from real `External Data\` ADEA + r/DentalSchool):

| Engine | M1 load | M2 3-hop p95 | M3 HNSW | M4 bitemp | M5 ops | **total** |
|---|---:|---:|---:|---:|---:|---:|
| neo4j | 1.000 | 0.000 | 1.000 | 1.000 | 0.000 | **0.600** |
| **kuzu** | 0.000 | 0.857 | 1.000 | 0.000 | 1.000 | **0.564** |
| postgres-age | 0.142 | 1.000 | 1.000 | 0.000 | 0.333 | **0.528** |

Margin Neo4j → Kùzu = 0.036, **below the 0.10 clarity threshold** declared in `decisions.md` "Decision protocol" §3. **M5 ops-complexity tiebreaker fires**: Kùzu (5, embedded, no service) > Neo4j (2, Docker + JVM + GPLv3) > AGE (3, Postgres extension + version-compat history). **Kùzu wins.**

Defensive analysis beyond the rubric:
- **Kùzu wins outright on Q-C (1-hop, 1.32 ms p95)** and **Q-D (filtered count, 0.65 ms p95)** — the operations the retrieval layer hits most often.
- Q-A 3-hop p95: 2.46 ms (Kùzu) vs 2.16 ms (AGE) vs 4.26 ms (Neo4j). All under the 250 ms V1-viable threshold; AGE's narrow win on this single metric doesn't overcome its ops complexity.
- M1 load-time apparent loss (165 s Kùzu vs 5 s Neo4j) is a **driver-implementation artifact**: the V1 bake-off driver used per-row INSERTs; `kuzu COPY FROM CSV` (which the V1 production driver will use) closes the gap by ~10-30×.
- V1 posture (single workstation, single user, single writer) is the embedded-DB sweet spot.

Raw measurements: `tools/bake_off/results/{kuzu,neo4j,postgres-age,_summary}.json`.

### Runner-up

**Neo4j 5.x Community + Graphiti** is the V2-swap-target. Pre-committed migration triggers (per `decisions.md`):

- V2 needs multi-writer concurrency (Kùzu is single-writer embedded).
- V2 needs cloud-hosted SaaS (no managed Kùzu offering).
- LadybugDB MIT fork stalls (no monthly releases for > 6 months → Kùzu lineage maintenance risk).
- Web HITL UI with concurrent reviewers.

If any of these fire, re-run the bake-off harness against the then-current Neo4j + Graphiti versions; the harness lives at `tools/bake_off/`.

### Rejected

- **Postgres + AGE + pgvector**: lowest raw weighted score (0.528); AGE Postgres-version-compat history adds risk.
- **Kùzu upstream (Apple-archived repo)**: invalidated by R-006. Mitigation: pin to `kuzu==0.11.3` PyPI release; track LadybugDB fork.
- **Memgraph** ($25k/yr/16GB enterprise paywall; R-006).
- **SurrealDB** (immature for ground-truth storage; R-001).

## Consequences

- `src/graph/` will provide a `GraphClient` Protocol and `kuzu_client.py` concrete impl. The Protocol means other modules don't depend on Kùzu directly; a future swap (V2 → Neo4j or AGE) is a `pyproject.toml` change + one new driver file.
- **Bitemporal edges**: Kùzu has no native bitemporal operators. The 4-tuple (`t_valid_from/to`, `t_ingest_from/to`) lives as ISO-string edge properties; Cypher-style WHERE-clause filtering. ADR-005 (bitemporal schema) is unaffected.
- **HNSW vectors**: Kùzu 0.11.x's vector extension wasn't exercised in the V1 bake-off driver (deferred to Phase 3.5). The vector path will be added once V1 ingestion is generating embeddings; if Kùzu's HNSW maturity proves inadequate, escalate to a Qdrant sidecar per ADR-002.
- **License**: Kùzu (MIT) is V2-distribution-safe — no GPL concerns like Neo4j Community.
- **Schema migration to V2**: structural-graph data round-trips cleanly via the Pydantic Node/Edge model in `tools/graphrag/types.py`; relation/property mapping is one-day work.
- **Driver writes**: Kùzu is single-writer. V1 internal-only is single-writer by design; V2 plan must account for this (see "Runner-up" triggers).

## Related docs

- `docs/05-features/bake-off-graph-db/decisions.md` — full bake-off results, normalized scores, V2 watch items.
- `docs/05-features/bake-off-graph-db/test-plan.md` — measurement rubric + V1-viability thresholds.
- `docs/03-research/research-log.md` R-001 (initial picks).
- `docs/03-research/R-006-live-verification.md` (Kùzu acquisition + candidate substitution).
- `docs/04-architecture/system-overview.md` §4, §8.
- `docs/04-architecture/tech-stack.md` Graph store section.
- `docs/04-architecture/module-boundaries.md` `GraphClient` Protocol.
- `docs/00-bootstrap/assumptions.md` A-026, A-039.
- `docs/00-bootstrap/gap-register.md` GAP-027.

## Related code

- `tools/bake_off/` — harness; reusable for V2 re-evaluation
  - `build_sample.py` — sample-prep from real `External Data\`
  - `run_kuzu.py`, `run_neo4j.py`, `run_age.py` — per-engine drivers
  - `score.py` — weighted scoring + tiebreaker
  - `results/{kuzu,neo4j,postgres-age,_summary}.json` — raw measurements
- `src/graph/client.py` — `GraphClient` Protocol (V1 implementation, forthcoming)
- `src/graph/kuzu_client.py` — concrete V1 driver (uses `COPY FROM CSV` for bulk-load)
- (V2) `src/graph/graphiti_neo4j_client.py` — runner-up impl, written if a V2 migration trigger fires
