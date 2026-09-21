# Context — V1.5a

## Upstream

V1 ratified architecture (`docs/04-architecture/system-overview.md` §1–§10), V1 feature packet (`docs/05-features/01-slice-trust-tier-canonicalize/`), V1.5 master brief (`docs/05-features/v1.5-master-brief.md`).

## Directly applicable ADRs

- ADR-005 trust-tier schema + bitemporal edges — V1.5a inherits unchanged; tier-stamping per node + edge.
- ADR-009 two-MCP framing + SQLite side store — the new connector tools register on `secbrain-v1` Tier 1.
- ADR-010 Prefect 3 orchestrator — `flows/data_source_pull.py` adopts the same patterns as `flows/full_sweep.py`.
- ADR-011 model gateway + MCP three-tier policy — `MappingSuggester` LLM calls + cross-graph match LLM rerank route through the gateway.
- **ADR-012** multi-level graph views — V1.5a's outputs land in Level C (analyzed) primarily; Level A (structural) picks up new User/Post-shaped nodes from non-forum sources only if they exist; Level B (clusters) unaffected.
- **ADR-013** UI tech stack — V1.5a is headless but Pydantic schemas it ships become the V1.5b type contract.
- **ADR-014** external DB connector tiering — the L1/L2/etc. declaration policy.
- **ADR-015** cross-graph entity mapping — auto-suggest + HITL pattern.

## Upstream code (do-not-break)

- `src/ingestion/api.py::IngestionService` — V1.5a refactors to route through `DataSource`. Public API surface preserved (V1 callers unaffected).
- `src/ingestion/adapters/base.py::SourceAdapter` — wrapped, not replaced. The existing adapters keep working.
- `src/er/` — V1 alias-resolution pipeline is reused by `src/er/cross_graph.py` in cross-source mode.
- `src/graph/client.py::GraphClient` — adds `SAME_AS` edge type but preserves all existing edge writers.
- `src/observability/audit.py` — extends `kind` enum.

## Downstream consumers (what V1.5a unlocks)

- V1.5b web UI consumes the seven new connector MCP tools through its FastAPI surface.
- V1.5b cross-link HITL page consumes `cross_graph_link` items.
- V1.5c PM/Social/Marketing dashboards rely on the cleaner cross-graph anchors V1.5a provides.

## External research that informed this slice

- Airbyte/Singer connector framework (2026) — Pydantic-validated config + capability discovery is the standard.
- PuppyGraph (2026) — evolutionary graph-schema modeling pattern: per-table mapping decisions can produce both node and edge types.
- Subgraph-network entity alignment (arxiv) — informed the cross-graph approach but we use the simpler DITTO+BGE pipeline V1 already validated.

## Memory

See `assumptions.md` V1.5-R1 + V1.5-R2 entries (post-this-batch).
