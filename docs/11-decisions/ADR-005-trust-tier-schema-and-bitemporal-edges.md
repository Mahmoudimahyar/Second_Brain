# ADR-005: Trust-Tier Schema (Wikidata-style) + Bitemporal Edges (Graphiti-style)

Status: **accepted**
Date: 2026-05-20

## Context

The engine has to represent claims from a mix of authoritative (L1) + community (L5) sources with explicit trust tiers, citation traceability, and temporal validity. The graph also has to answer "as of past date" queries to reconstruct historical state.

R-007a found that no off-the-shelf GraphRAG library models multi-tier source trust as a first-class concept — Wikidata is the closest reference. R-007b found that Graphiti / Zep (arxiv 2501.13956, KGC 2025) is ~90% of our 3-layer bitemporal architecture and validates bitemporal edges as the right primitive.

## Decision

### Trust-tier schema (Wikidata-style)

Every claim edge carries:

- **`source_tier`** enum `L1` / `L2` / `L3` / `L4` / `L5`. Required on every node + edge.
- **`rank`** enum `preferred` / `normal` / `deprecated`. Required on every claim edge. L1 = `preferred` by default; conflict-resolution can downgrade non-L1 claims to `normal` or `deprecated`.
- **`references`** list of source `dump_id` + `post_id` (≥ 1 required on every claim edge). Drives the ≥ 99% citation traceability requirement.
- **`qualifiers`** dict — free-form context (e.g., `{"out_of_state": true}` on a tuition claim).

L1 nodes are **immutable**. Any code path attempting to mutate them raises `L1_IMMUTABLE_REJECT`.

### Bitemporal edges (Graphiti-style)

Every edge carries:

- **`t_valid_from`** datetime UTC. Wall-clock start of asserted validity.
- **`t_valid_to`** datetime UTC \| NULL. End of validity (NULL = open-ended).
- **`t_ingest_from`** datetime UTC. When the graph first held this version.
- **`t_ingest_to`** datetime UTC \| NULL. NULL = still current.

When a re-ingest produces a conflicting edge for the same (subject, predicate, object), the prior edge's `t_ingest_to` is set to the new ingestion timestamp; the new edge starts with `t_ingest_from = now`. **The prior edge is preserved, not deleted** — enables `query_graph(..., as_of=<past>)` to reconstruct any historical snapshot.

The 4-tuple is portable as edge properties regardless of which graph DB wins ADR-001.

## Consequences

- Every ingestion adapter must compute `t_valid_*` from its source (e.g., ADEA cycle year for L1; Reddit `created_utc` for L5).
- Every conflict-resolution path (ADR-006) interacts with bitemporal correctness: superseding sets `t_ingest_to` atomically.
- Retrieval ranking includes `t_valid_*` decay (ADR-007 HALO half-life table).
- Wikidata-rank conflict resolution gives a uniform semantic across L1 ↔ L5 disputes: `preferred` wins; ties resolved by source-trust then user-credibility (ADR-008).
- L1 immutability enforced at the graph-client level (`src/graph/client.py`), not in business logic — non-negotiable.
- Schema is `extra="forbid"` on Pydantic models — unknown properties on edges are rejected to prevent ontology sprawl.

## Alternatives considered

- **Single timestamp** (just `created_at`): can't reconstruct "as of past date" after re-ingests. Rejected.
- **`rank` as a plain integer 0-100**: loses Wikidata interoperability + the explicit "preferred / normal / deprecated" semantic. Rejected.
- **No `references` array** (just a string source ID): loses multi-source claim aggregation. Rejected.
- **`source_tier` as a float (0.0-1.0 trust score)**: loses the discrete-tier ordering that drives conflict resolution. Rejected.
- **Adopting Graphiti as the engine** (not just the schema): Graphiti's MIT-licensed but ties us to its lifecycle. Schema is portable; framework is not. We borrow the bitemporal model; we keep the option to swap implementations.

## Related docs

- `docs/03-research/R-007-multi-source-kg.md` R-007a (trust-tier modeling) + R-007b (bitemporal)
- `docs/04-architecture/system-overview.md` §4 multi-layer graph store
- `docs/07-data/data-dictionary.md` — full property convention + ID conventions
- `docs/00-bootstrap/assumptions.md` A-014, A-027, A-028
- `docs/00-bootstrap/gap-register.md` GAP-008 (schema lockdown), GAP-016 (trust ladder as schema)

## Related code

- `src/graph/client.py` — `Node`/`Edge` dataclasses: the bitemporal 4-tuple + full property convention (`source_tier` / `rank` / `references` / `qualifiers` / `t_valid_*` / `t_ingest_*`)
- `src/graph/kuzu_client.py` — persists the 4-tuple; `supersede_edge` (atomic `t_ingest` close/open) — to be created in V1.7 (GAP-053)
- L1-immutability check enforced in the data layer (`src/graph/client.py` / `src/conflict/resolver.py` step 1)
