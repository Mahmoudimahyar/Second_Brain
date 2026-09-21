# Context — V1.5b

## Upstream

V1 + V1.5a deliverables. V1.5 master brief.

## Directly applicable ADRs

- **ADR-012** multi-level graph views — three retrieval contracts that V1.5b's UI consumes.
- **ADR-013** UI tech stack — Next.js + FastAPI + Pydantic + Zod foundation.
- **ADR-017** feedback loop via BAML prompt context (amended by ADR-018).
- **ADR-018** feedback log retention + active-learning context curation.

## Upstream code (do-not-break)

- `src/retrieval/api.py::RetrievalService.query_graph` — gets extended with three level-typed methods but the V1 surface is preserved (aliased to `query_graph_analyzed`).
- `src/hitl/queue.py::HITLQueue` — UI consumes; CLI stays functional.
- `src/extraction/pass4_*` — gain `context_block` parameter in BAML templates.
- `src/extraction/cache.py` — cache-key extended with `feedback_context_hash`.
- `src/observability/audit.py` — `kind` enum extended.

## Downstream consumers (what V1.5b unlocks)

- V1.5c per-team dashboards build on the same UI stack.
- V2 multi-tenant inherits the stack with minimal refactoring (per-tenant route prefix + auth wrapper).

## External research informing this slice

- Few-shot collapse (2026) — drives ADR-018's K=4 hard cap.
- Active learning for in-context examples — drives hybrid scoring function in ADR-018.
- A2UI / agent-graph reasoning surface — informs the integration of HITL into the graph viewer.
- Sigma.js benchmarks for 100K+ node WebGL rendering.
- shadcn/ui + Tremor patterns for internal-tool dashboards.

## Memory

See V1.5 master brief + assumptions.md V1.5-R1 / V1.5-R2 entries.
