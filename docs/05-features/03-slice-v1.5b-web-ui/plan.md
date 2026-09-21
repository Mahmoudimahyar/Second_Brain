# Plan — V1.5b

> TDD per AGENTS.md. Vertical-slice-first: one end-to-end page wired before broad expansion.

## Phase 0 — Prereqs

| # | Item | Owner | Status |
|---|---|---|---|
| 0.1 | V1.5a Verification Before Completion report | Claude | Pending V1.5a |
| 0.2 | ADR-012/-013/-017/-018 ratified | Mahyar | Pending |
| 0.3 | Node.js 22+ on workstation | Mahyar | Pending |
| 0.4 | pnpm installed | Claude (Phase 1) | Pending |
| 0.5 | shadcn theme decision | Mahyar | ✅ V1.5-R2: shadcn defaults |

## Phase 1 — App shell + vertical slice (one route wired end-to-end)

1. **Failing-first test**: `tests/web/e2e/test_smoke_postgres_connector.spec.ts` (Playwright) — boot `secbrain ui`, navigate `/ingest/new/postgres`, fill the form with testcontainers Postgres creds, click Connect, assert `/ingest/new/postgres/discover` renders the schema tree.
2. **Smallest code**:
   - `web/` Next.js 15 + Tailwind + shadcn/ui + Tremor + Sigma.js scaffolded via `pnpm create next-app`.
   - `src/web/app.py` — FastAPI factory. CORS off. Mount `/api/v1`.
   - `src/web/routes/sources.py` — three endpoints (`POST /sources`, `GET /sources/{id}`, `POST /sources/{id}/discover`) wired to V1.5a `IngestionService`.
   - `src/web/dev_orchestrator.py` — boots uvicorn + pnpm dev together; `secbrain ui` CLI entry.
   - `web/src/app/ingest/new/postgres/page.tsx` — connection form using shadcn `Form` + `Input` + `Button`.
   - `web/src/app/ingest/new/postgres/discover/page.tsx` — schema tree rendering via TanStack Query + `SchemaTree` component.
   - `web/src/lib/api/client.ts` — generated TS types + TanStack Query hooks.
   - `Makefile` — `make generate-types` runs Pydantic→Zod codegen.
3. **Targeted tests**:
   - Playwright smoke for the route chain.
   - Vitest unit on `SchemaTree` (renders, expands, sample-row preview).
   - pytest backend unit on the three FastAPI routes.
4. **Acceptance**: `secbrain ui` boots; user can connect a Postgres testcontainer + see its schema in the browser. Audit log records `ui_view` + `ui_form_submit` + backend `connector_connect` + `connector_discover`.

## Phase 2 — Ingestion UI (full)

Broaden from the Phase-1 vertical to all ingestion pages. Per-engine config forms (MySQL / SQLite / Neo4j / Upload). Mapping wizard. Connector dashboard. Source-edit + disconnect.

1. **Tests** (Playwright + Vitest + pytest):
   - Each engine config form's happy + error paths.
   - Mapping wizard: render `SchemaMappingTable`, edit a row's target_type, bulk-accept, commit.
   - Tier selector + L1 confirmation modal.
   - Connector dashboard pull-now button.
2. **Code**:
   - `web/src/components/ingest/*` (SchemaMappingTable, TierSelector, ConnectorHealthCard, CursorEditor).
   - `web/src/app/ingest/sources/[id]/page.tsx` + `/edit` + `/disconnect`.
   - Backend endpoints from `02-slice-v1.5a-db-connector/api.md` FastAPI routes list, all wired.
3. **Acceptance**: all V1.5a-flagged pages in `page-inventory.md` pass E2E smoke.

## Phase 3 — Multi-level graph viewer

1. **Failing-first test**: `tests/web/e2e/test_graph_structural.spec.ts` — load `/graph/structural?corpus=v1_seed`, assert ≥ 1000 nodes rendered, click a User node, assert `GraphSelectionPanel` shows credibility breakdown.
2. **Code**:
   - `src/retrieval/api.py` extended with `query_graph_structural`, `query_graph_clusters`, `query_graph_analyzed`, `query_graph_crosslinks` per ADR-012.
   - `src/retrieval/level_filters.py` — subgraph selectors.
   - `src/web/routes/graph.py` — four endpoints.
   - `web/src/components/graph/GraphCanvas.tsx` — Sigma.js wrapper.
   - `web/src/app/graph/structural/page.tsx`, `clusters/page.tsx`, `analyzed/page.tsx`.
   - Selection state persistence via URL params; Cmd-1/2/3 hotkeys.
3. **Acceptance**: all three views render; cross-view selection persists; perf budgets met.

## Phase 4 — HITL inbox + per-type review pages

1. **Tests** (per item type): render item from queue, fill verdict, commit, assert next item loads.
2. **Code**:
   - `web/src/app/hitl/*` pages.
   - `web/src/components/hitl/*` components (ReviewCard, VerdictPicker, BulkActionToolbar, per-type bodies).
   - `src/web/routes/hitl.py` — list / claim / commit endpoints wrapping V1 + V1.5a HITL queue.
   - Keyboard shortcuts hook.
3. **Acceptance**: every V1 + V1.5a HITL flow has a working web page.

## Phase 5 — Cluster-cull + node/edge proposal flows

1. **Tests**: end-to-end:
   - Pass 3 runs on a seeded corpus.
   - `/hitl/clusters` shows the clusters.
   - User marks 5 cull + 2 merge + 1 split + commits.
   - Pass 4 runs on the survivors.
   - `/hitl/proposals` shows the new proposals.
   - User accepts 3 + rejects 2 + commits.
   - Re-run Pass 4 on identical input — assert the rejected patterns no longer appear AND the accepted patterns appear as examples in the BAML context.
2. **Code**:
   - `web/src/app/hitl/clusters/page.tsx` — Sigma.js Level B canvas in review mode.
   - `web/src/app/hitl/proposals/page.tsx`.
   - `src/web/routes/hitl.py` — cluster + proposal verdict endpoints.
   - `src/extraction/feedback_context.py` — `FeedbackContextLoader` + active-learning scoring + blocklist eviction.
   - `src/extraction/blocklist_filter.py` — post-hoc safety net.
   - Pass-4 BAML templates extended with `context_block`.
   - `src/extraction/cache.py` — extended cache key.
3. **Acceptance**:
   - End-to-end flow completes.
   - Measured precision on V1 gold sets ≥ V1 baseline.
   - Audit-log + Langfuse traces show context-block hash + cache invalidation behavior.

## Phase 6 — Feedback-loop policy page + audit-log UI + settings

1. **Tests**:
   - `/settings/feedback-loop` renders active context + blocklist; weight edits persist.
   - `/audit` filtering by kind / source_id / time range.
2. **Code**:
   - `web/src/app/settings/feedback-loop/page.tsx`.
   - `web/src/app/audit/page.tsx` + `[id]/page.tsx`.
   - `src/web/routes/settings.py`, `audit.py`.
3. **Acceptance**: all V1.5b pages ship.

## Phase 7 — Accessibility + browser-validation + Verification Before Completion

1. **Tests**:
   - axe-core integration in every Playwright test.
   - Keyboard-only walkthrough manually documented in `.agent/reports/v1.5b-a11y-walkthrough.md`.
   - NVDA screen-reader walkthrough of 4 primary flows.
2. **Acceptance**: 0 axe violations across all pages. WCAG 2.1 AA committed.
3. Write `.agent/reports/v1.5b-slice.md` per AGENTS.md.

## Provisional time estimate

| Phase | Hours |
|---:|---|
| 1 — App shell + vertical slice | 26 |
| 2 — Ingestion UI (full) | 30 |
| 3 — Multi-level graph viewer | 36 |
| 4 — HITL inbox + per-type pages | 32 |
| 5 — Cluster-cull + proposal flows + feedback loop | 34 |
| 6 — Settings + audit-log UI | 14 |
| 7 — Accessibility + verification | 12 |
| **Total** | **~184 hours** (5.5 focused weeks) |

## Risk register

| Risk | Mitigation |
|---|---|
| Sigma.js perf below budget on 50K-node Level A | Phase 3 includes a perf gate test before broader work; fallback = node decimation + zoom-load |
| Pydantic-to-Zod codegen breaks on union types | Validate codegen via Phase 1 vertical; CI gate catches drift |
| Few-shot collapse regression on V1 gold sets | ADR-018's 4-cap + diversity constraint mitigates; gate test in Phase 5 |
| `secbrain ui` boot complexity (two processes) | Single command wraps subprocess management; dev-mode hot-reload |
| WCAG AA on Sigma.js canvas is hard | Off-screen aria-live region + "view as table" fallback per `graph-level-views.md` |
| Bundle-size budget overrun | Tremor + Sigma.js are heavy; lazy-load per-route via Next.js dynamic imports |
