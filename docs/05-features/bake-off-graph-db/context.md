# Context

## Why we're here

`docs/04-architecture/system-overview.md` (§4 multi-layer graph store, §8 bake-off) locked the architecture *except* for the underlying graph store. This packet is the experiment that settles that single decision.

## Prior research feeding this

- `docs/03-research/research-log.md` — **R-001** (original Kùzu-primary recommendation, no live web).
- `docs/03-research/R-006-live-verification.md` — invalidated R-001 (Kùzu→Apple acquisition, OSS archived 2025-10-10); surfaced LadybugDB + Graphiti + Postgres-AGE candidates; confirmed Memgraph rejection (enterprise paywall $25k/yr/16GB).
- `docs/03-research/R-007-multi-source-kg.md` — surfaced **Graphiti/Zep** (arxiv 2501.13956, KGC 2025) as a near-fit OSS reference for our 3-layer bitemporal architecture. Independent of graph-DB pick, Graphiti's bitemporal edge schema is what we'd build anyway, so this is partly "do we let Graphiti own the schema for us?"
- `docs/03-research/R-008-cost-accuracy.md` — extraction-side levers; orthogonal to graph-DB pick but informs the sample-data preparation (content-addressable cache lives outside the graph DB).

## What the graph DB has to support

From `system-overview.md` §4:

1. **Multi-layer logical model over one physical store**: user/actor + post/document + opinion/advice graphs.
2. **L1 immutable anchor nodes** (`Trust_Score = 1.0`, `rank: preferred`, never overwritten).
3. **Per-node + per-edge properties**: `source_tier` (L1..L5), Wikidata-style `rank`, `references` array, `qualifiers`, `t_valid_from/to`, `t_ingest_from/to`, `created_utc`.
4. **HNSW vector index** for hybrid retrieval (native or sidecar; this bake-off prefers native).
5. **1-3 hop traversal at low latency** on trust-tier + temporal filter queries.
6. **Bulk-load throughput** for re-imports after extraction reruns (R-008 §1.8 content-addressable cache enables many reruns).
7. **Single-node, single-writer is fine** for V1 internal use.

## What stays out of scope of this bake-off

- BM25 / FTS engine pick — independent ADR-002 decision.
- Embedding-model pick (BGE-small confirmed by R-007 + R-008).
- Extraction stack — R-003 + R-006 picks stand.
- Conflict-resolution algorithm — R-007b picks stand.
- HITL UX — Q-015 R4.

## Related files

- `docs/04-architecture/system-overview.md` — the architecture this fits into.
- `docs/00-bootstrap/assumptions.md` (A-026, A-027) — explicit assumptions on the Kùzu invalidation + bitemporal edge model.
- `docs/00-bootstrap/gap-register.md` (GAP-027) — the gap this packet closes.
- `tools/graphrag/schema.md` — generic GraphRAG schema scaffold to be specialized after this bake-off lands.
- `memory/project_dentistjourney.md` — durable project context.

## Stakeholders + decision owner

- **Decision owner**: Mahyar.
- **Execution**: Claude (writes the test harness, runs the candidates, fills `decisions.md` + ADR-001).
- **Affects**: every architecture decision downstream (ADR-002 retrieval, ADR-003 extraction integration, ADR-007+ data-model ADRs), the `tools/graphrag/` MCP server build (because the repo MCP server may reuse the chosen graph-DB engine), and the V1 vertical-slice feature packet.
