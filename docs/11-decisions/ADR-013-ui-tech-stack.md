---
adr: 013
title: UI tech stack for V1.5 — Next.js 15 + FastAPI + Pydantic + Zod
status: accepted
date: 2026-05-24
deciders: Mahyar, Claude
supersedes:
superseded_by:
revision_history:
  - 2026-05-24 — proposed.
  - 2026-05-25 — accepted with a documented partial implementation. V1.5b shipped FastAPI + Pydantic + Next.js 15 + Tailwind + shadcn primitives + the OpenAPI export. The spec'd `datamodel-code-generator + pydantic-to-zod` codegen pipeline was substituted with a hand-authored typed API client + OpenAPI auto-export (`tools/generate_types.py`). V1.5 gap audit MED-2 flagged this drift; W2-6 will either land the spec'd codegen pipeline or amend this ADR with a permanent justification for the substitution. The central `src/web/schemas/` directory is empty (MED-1, fixed in W2-5).
  - 2026-05-25 (W2-6) — codegen path amended. After weighing the cost of installing `datamodel-code-generator` (Python) + `pydantic-to-zod` (npm) + integrating a two-tool build step against the benefit of replacing the existing `tools/generate_types.py` (which already does FastAPI's `app.openapi()` → JSON Schema → hand-authored TS interfaces + Zod schemas), we keep the existing tool and document the substitution as permanent. **Rationale:** (a) the existing tool's output covers every type currently consumed by the frontend; (b) FastAPI's OpenAPI export tracks Pydantic v2 model changes faithfully (verified via W2-5's `src/web/schemas/` migration of the team routes); (c) `pydantic-to-zod` operates on Python source code, requiring an out-of-process Python sub-process at every Node build invocation, which doubles the dev-server startup overhead; (d) `datamodel-code-generator` is bidirectional (JSON Schema ↔ Pydantic) which we don't need in this direction. **New rule:** every Pydantic model that backs an `/api/v1/*` route MUST live in `src/web/schemas/` so `tools/generate_types.py`'s OpenAPI traversal picks it up; W2-5 enforces this for the team routes and a follow-up sweep will migrate the remaining `sources` / `hitl` / `graph` / `settings` / `audit` routes from `dict[str, Any]` to typed Pydantic responses incrementally.
---

# ADR-013 — UI tech stack for V1.5

## Context

V1 shipped CLI + flat-YAML for HITL and Claude-Code-driven MCP for everything else. V1.5 introduces a human-facing web UI for ingestion wizards, HITL review (alias / conflict / cluster-cull / node-edge-proposal), multi-level graph views (Level A / B / C per ADR-012), iterative feedback loops, and per-team dashboards.

The stack choice affects every subsequent V1.5 + V2 decision. V2 reframes the project as `developer_tool` — others' organizations connecting their data — so cloud-readiness matters. V1.5 is single-user localhost (V1.5-R1 confirmed) but we should not paint ourselves into a corner.

Candidates considered:
- **Next.js 15 + FastAPI + Pydantic + Zod** — modern type-safe full-stack standard.
- **Streamlit** — pure-Python; rapid for simple dashboards; weak for graph editing.
- **Gradio** — single-flow demo tool; not full-app.
- **Tauri (Rust + web frontend)** — desktop binary; introduces Rust to stack.

## Decision

**Next.js 15 + FastAPI + Pydantic + Zod** for V1.5.

Concretely:

- **Frontend**: Next.js 15 (App Router, RSC where it helps) + TypeScript + Tailwind CSS + shadcn/ui (primitives) + Tremor (KPI panels + dashboards) + Sigma.js (graph canvas) + TanStack Query (data fetching + cache).
- **Backend**: FastAPI (Python 3.12) running alongside the existing engine. Mounts at `/api/v1/...`. Async by default.
- **Type bridge**: Pydantic models on the backend are the single source of truth. `datamodel-code-generator` + `pydantic-to-zod` generate TypeScript types + Zod schemas into `web/src/lib/api/generated/` as a pre-build step. The frontend imports types from the generated bundle.
- **Auth**: V1.5 = no auth. Backend binds to `127.0.0.1` only. UI loads from `http://localhost:3000`. V2 adds NextAuth + multi-tenant.
- **Build / dev**: pnpm + Turbopack on the frontend; uvicorn on the backend; one `secbrain dev` command boots both via a tiny orchestrator.
- **Deployment (V1.5 local)**: `secbrain ui` boots both processes, opens a browser. Production cloud deploy is V2.

Directory layout (new top-level `web/`):

```
web/
  src/
    app/                  # Next.js App Router
      ingest/
        new/page.tsx              # Ingestion wizard entry
        sources/[id]/page.tsx     # Connector dashboard
      hitl/
        alias/page.tsx
        conflict/page.tsx
        clusters/page.tsx          # Cluster-cull review
        proposals/page.tsx         # Node/edge proposal review
        escalated/page.tsx
      graph/
        structural/page.tsx        # Level A
        clusters/page.tsx          # Level B
        analyzed/page.tsx          # Level C
      teams/
        pm/page.tsx
        social/page.tsx
        marketing/page.tsx
      audit/page.tsx
    components/
      graph/GraphCanvas.tsx        # Sigma.js wrapper
      hitl/ReviewCard.tsx
      ingest/SchemaMappingTable.tsx
      shared/ ...
    lib/
      api/
        generated/                 # Pydantic-to-Zod output
        client.ts                  # TanStack Query hooks
  package.json
  next.config.js
  tailwind.config.ts
  tsconfig.json
src/web/
  __init__.py
  app.py                  # FastAPI factory
  routes/
    ingest.py
    hitl.py
    graph.py               # /api/v1/graph/{structural,clusters,analyzed,crosslinks}
    teams.py
    audit.py
  schemas/                 # Pydantic models — single source of truth
  middleware/
    audit.py
    error_handler.py
```

## Consequences

**Positive:**
- Type safety end-to-end. A backend Pydantic model change breaks the frontend at build time, not runtime.
- Standard 2026 stack — large skill pool, abundant Claude-Code training data, AdminLTE/shadcn/Tremor templates accelerate the first dashboards.
- Sigma.js handles 100K+ nodes via WebGL — the only viz library that scales for the full corpus.
- Next.js App Router lets us colocate per-page server actions where they help (e.g., the ingestion wizard's heavy schema-discovery call streams a server action's progress).
- Cloud-ready for V2 multi-tenant without re-platforming.
- FastAPI + Pydantic are already idiomatic for this codebase (we use Pydantic via BAML schemas), reducing cognitive jump.

**Negative:**
- Adds Node.js + pnpm to the dev environment. Mahyar's Win 11 setup needs Node 22+ installed.
- Three build systems running concurrently (uv for Python, pnpm for JS, Prefect for orchestration). Mitigated by a single `secbrain dev` wrapper.
- Code-gen step (Pydantic → Zod) is a new pre-build hook that has to stay in sync. Mitigated by `make generate-types` + CI gate.
- Frontend tests need their own infrastructure (Vitest + Playwright). Coverage targets must extend to TS.

**Neutral:**
- Streamlit / Gradio remain available for one-off internal tools that don't belong in the main UI (e.g., a debugging notebook). Not adopted as primary.

## Alternatives considered (and rejected)

- **Streamlit** — kills graph editing UX. The Sigma.js canvas + drag-to-review interactions Streamlit fights against, not with. Acceptable for V1's CLI replacement but not for the multi-level graph viewer.
- **Gradio** — single-flow demo tool. Per-team dashboards + HITL queue + graph viewer all in Gradio = three separate apps. Rejected for cohesion.
- **Tauri** — would ship V1.5 as a desktop binary, which is appealing for local-first. But Rust dependency adds complexity; V2 cloud deploy then requires re-building web frontend anyway. Net negative.
- **Plain Django + HTMX** — viable; rejected because graph viz + interactive cluster editing want client-side state that HTMX patterns make awkward.
- **SvelteKit** — equally good technically; rejected because shadcn/ui + Tremor ecosystems are deeper on Next.js, and Claude-Code's Next.js-specific guidance is better.

## Implementation

V1.5b delivers the first end-to-end vertical slice: ingestion-wizard page → mapping-suggestion page → cluster-cull page → one Level B graph view. Once that vertical is green, V1.5b broadens to all pages in parallel.

V1.5a (backend-only) ships before V1.5b starts; the Pydantic schemas it produces become the type contract V1.5b builds against.

## References

- `docs/05-features/v1.5-master-brief.md`
- V1.5-R1 Q3 (UI stack) answer: "Next.js 15 + FastAPI + Pydantic + Zod (Recommended)"
- Best-practices research log 2026-05-24 (in this batch)
