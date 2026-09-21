# Decisions — V1.5b

> Extends V1 + V1.5a ADRs. Cross-cutting decisions live in `docs/11-decisions/ADR-*`.

| ID | Decision | Rationale | Status |
|---|---|---|---|
| D-1.5b-1 | Next.js 15 App Router (not Pages Router) | RSC where it helps; future-proof for V2 | Locked ADR-013 |
| D-1.5b-2 | Sigma.js for graph canvas (not Cytoscape/vis-network/Reagraph) | WebGL handles 100K+ nodes; corpus size demands it | Locked ADR-013 |
| D-1.5b-3 | Tremor for KPI/charts + shadcn/ui for primitives | Best-in-class for the respective domain | Locked ADR-013 |
| D-1.5b-4 | Three separate graph views (not single-canvas LOD) | V1.5-R1 user choice; simpler to build + tune per-level | Locked ADR-012 |
| D-1.5b-5 | Manual cluster-review trigger (not auto after Pass 3) | V1.5-R1 user choice; matches operator workflow | Locked |
| D-1.5b-6 | Cluster input = posts + comments together (V1 behavior) | V1.5-R1 user choice; configurable per-sweep if needed | Locked |
| D-1.5b-7 | Hybrid LRU+LFU eviction on blocklist (cap 50) | Research-driven; standard pattern for mixed access | Locked ADR-018 |
| D-1.5b-8 | K=4 hard cap on positive examples per template | Research-driven; few-shot collapse 2026 | Locked ADR-018 |
| D-1.5b-9 | Append-only feedback_log (no eviction) | Replay + future fine-tuning; cheap to store | Locked ADR-018 |
| D-1.5b-10 | `secbrain ui` CLI boots both Next.js + FastAPI + Prefect | Single dev command; matches V1's ergonomics | Locked |
| D-1.5b-11 | Stay on shadcn defaults for theming | V1.5-R2 user choice; revisit in V2 | Locked V1.5-R2 |
| D-1.5b-12 | Pydantic→Zod codegen via `make generate-types` + CI gate | Prevents schema drift between frontend + backend | Locked |
| D-1.5b-13 | "View as table" fallback link on every graph view | WCAG AA accommodation for the Sigma.js canvas | Locked accessibility.md |
| D-1.5b-14 | Audit log captures every UI action (view, select, filter, commit) | Compliance + replay + analytics | Locked |
