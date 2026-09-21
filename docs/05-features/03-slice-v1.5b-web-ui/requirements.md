# Requirements — V1.5b

> Testable; mapping to test cases in `test-plan.md`. Same conventions as V1 slice-01.

## Functional requirements

### FR-1.5b-1 — Web-app shell

- **FR-1.5b-1.1** Next.js 15 app under `web/` per ADR-013. App Router with route groups for `(public)` (none in V1.5) + `(operator)` (everything). Tailwind + shadcn/ui + Tremor + Sigma.js installed.
- **FR-1.5b-1.2** FastAPI backend under `src/web/` exposing `/api/v1/*`. Pydantic schemas are the type source-of-truth; Zod schemas auto-generated via pre-build `make generate-types`.
- **FR-1.5b-1.3** `secbrain ui` CLI command boots both processes via a tiny Python orchestrator (`src/web/dev_orchestrator.py`), opens browser to `http://localhost:3000`. Health-check + graceful shutdown.
- **FR-1.5b-1.4** Sidebar + breadcrumbs + top-bar + command-palette (Cmd-K) chrome on every page (per `docs/08-ui/site-map.md`).
- **FR-1.5b-1.5** Localhost-only binding. Backend `127.0.0.1`, frontend pinned. No CORS surface to the public internet (V2 adds CORS for cloud).

### FR-1.5b-2 — Ingestion UI (consumes V1.5a backend)

- **FR-1.5b-2.1** `/ingest` lists all connectors with status + last-pull summary (Tremor `KpiCard` + `BarList`).
- **FR-1.5b-2.2** `/ingest/new` is an `EnginePickerGrid` tile UI.
- **FR-1.5b-2.3** Per-engine config pages (`/ingest/new/postgres`, etc.) render the engine-specific `ConnectionConfigForm` with health-check button. `CredentialField` shows a V1.5-plaintext banner on every credential input.
- **FR-1.5b-2.4** `/ingest/new/[engine]/discover` streams schema-discovery progress; renders `SchemaTree` with sampled rows visible per table.
- **FR-1.5b-2.5** `/ingest/new/[engine]/mapping` renders the `MappingSuggester` output as a `SchemaMappingTable`. Per-row edit, bulk-accept, bulk-skip. Tier selection (`TierSelector`) with L1 confirmation modal per ADR-014.
- **FR-1.5b-2.6** `/ingest/sources/[id]` is the connector dashboard. Pulls now, edits cursor + mapping, opens detail on cross-graph link items in HITL.
- **FR-1.5b-2.7** Mapping wizard preserves user edits across page reloads (URL-encoded state + localStorage; cleared on commit).

### FR-1.5b-3 — Multi-level graph viewer (per ADR-012 + `docs/08-ui/graph-level-views.md`)

- **FR-1.5b-3.1** Three independent routes: `/graph/structural` (Level A), `/graph/clusters` (Level B), `/graph/analyzed` (Level C). Each calls its dedicated retrieval endpoint.
- **FR-1.5b-3.2** Sigma.js canvas with ForceAtlas2 worker layout. Force-directed default. Render budget per AC-3 of `README.md`.
- **FR-1.5b-3.3** Common chrome: top bar (corpus + time-range + as-of pickers), right `GraphSelectionPanel`, bottom `CitationDrawer`, zoom + reset controls.
- **FR-1.5b-3.4** Per-level styling per `graph-level-views.md` (node shapes, sizes, colors, edge styles).
- **FR-1.5b-3.5** Selection state persists across view switches via URL params (Cmd-1/2/3 keyboard shortcut to switch).
- **FR-1.5b-3.6** Reduced-motion preference snaps to final positions (no ForceAtlas2 animation).
- **FR-1.5b-3.7** "View as table" fallback link on every view (paginated DataTable with the same data) — accessibility requirement per `docs/08-ui/accessibility.md`.

### FR-1.5b-4 — HITL review UI

- **FR-1.5b-4.1** `/hitl` is the inbox showing item counts per type (alias, conflict, cluster_review, node_edge_proposal, multi_l1_claims, cross_graph_link, judge_disagreement, escalated). Bulk-mode toggle.
- **FR-1.5b-4.2** Per-type pages: `/hitl/alias`, `/hitl/conflict`, `/hitl/clusters`, `/hitl/proposals`, `/hitl/multi-l1`, `/hitl/crosslinks`, `/hitl/judge`, `/hitl/escalated`, `/hitl/history`.
- **FR-1.5b-4.3** Each page uses the shared `ReviewCard` with item-type-specific body components per `docs/08-ui/hitl-flows.md`.
- **FR-1.5b-4.4** `VerdictPicker` enforces correct verdict vocabulary per item type. `BulkActionToolbar` exposes "apply same verdict to N selected" for batchable types.
- **FR-1.5b-4.5** Commit writes the decision via FastAPI → V1 / V1.5a queue APIs; audit-logged; UI shows toast + advances to next item.
- **FR-1.5b-4.6** Power-user keyboard shortcuts per page: `J/K` next/previous; `A` accept; `R` reject; `E` escalate; `D` defer; `?` shortcut help.
- **FR-1.5b-4.7** `/hitl/history` is read-only — past decisions with replay capability ("show what the system would have done without this decision").

### FR-1.5b-5 — Cluster-cull HITL flow

- **FR-1.5b-5.1** `/hitl/clusters` renders the Pass-3 cluster landscape (default to the Level B Sigma.js view; user can toggle to list-view).
- **FR-1.5b-5.2** Per-cluster card shows label + description + member count + sentiment ratio (if Pass-4 has touched it) + sample posts (top 5 by representative score) + status chip.
- **FR-1.5b-5.3** Verdict vocabulary: `keep`, `cull`, `merge_into:<target_id>`, `split:<n_target_clusters>`, `mark_anomaly`, `defer`. Bulk-action toolbar for multi-select.
- **FR-1.5b-5.4** Cluster review is **manual-trigger** (per V1.5-R1 Q14): user opens the page when ready. Pass 4 is gated on cluster review status (`approved`).
- **FR-1.5b-5.5** "Submit review batch" commits all pending decisions atomically; triggers the next Pass 4 sweep on approved clusters only.

### FR-1.5b-6 — Node/edge proposal review flow

- **FR-1.5b-6.1** `/hitl/proposals` lists Pass-4 proposed node/edge types grouped by type. Per-proposal card shows the type name + sample extractions + confidence + sample source posts.
- **FR-1.5b-6.2** Verdict vocabulary: `accept`, `reject`, `refine:<notes>`, `defer`.
- **FR-1.5b-6.3** Decision writes to `feedback_log` per ADR-018. Audit row written.
- **FR-1.5b-6.4** Rejection adds the pattern to the active blocklist (within the 50-cap LFU+LRU policy per ADR-018).

### FR-1.5b-7 — Feedback loop machinery

- **FR-1.5b-7.1** `feedback_log` table created per ADR-018 schema. Append-only enforced at DB level (no UPDATE / DELETE statements; only INSERT).
- **FR-1.5b-7.2** `FeedbackContextLoader.build(corpus_id, prompt_template_id)` implements the active-learning hybrid scoring + diversity-constrained top-K selection (K=4) + blocklist eviction (cap=50, LFU+LRU).
- **FR-1.5b-7.3** Each Pass-4 BAML template gains a `context_block` parameter; templates renders examples + blocklist sections.
- **FR-1.5b-7.4** `BlocklistFilter.apply(extractions, blocklist)` is the post-hoc safety net. Drops extractions with exact pattern match OR cosine similarity > 0.92 to a blocklisted pattern. Dropped items write `audit_log` with `kind=blocklist_filtered`.
- **FR-1.5b-7.5** Pass-4 content cache key includes `feedback_context_hash` per ADR-018; invalidates affected template's cache when context changes.
- **FR-1.5b-7.6** `/settings/feedback-loop` exposes active context block + blocklist + scoring-weight inputs. Edits write back to `feedback_log` with `decided_by='settings_override'`.
- **FR-1.5b-7.7** Measured quality lift: post-feedback-loop precision on V1 sentiment + interview-Q gold sets must be ≥ V1 baseline (no regression). Improvement is celebrated but not gated; regression is blocking.

### FR-1.5b-8 — Audit-log UI

- **FR-1.5b-8.1** `/audit` shows filterable log: time range, kind, actor, source_id, item type. Tremor DataTable with virtual scroll.
- **FR-1.5b-8.2** `/audit/[id]` shows entry detail with linked entities (clickable to graph view if applicable).
- **FR-1.5b-8.3** UI-action audit coverage: every page view, selection, filter change, review commit writes a row. `kind` enum extended: `ui_view`, `ui_select`, `ui_filter_change`, `ui_review_commit`, `ui_batch_commit`, `ui_settings_update`. 100% coverage tested.

### FR-1.5b-9 — Settings UI

- **FR-1.5b-9.1** `/settings/corpora` lists corpora with quick switch.
- **FR-1.5b-9.2** `/settings/extraction` exposes per-pass config (read-only V1.5b; editable V1.6).
- **FR-1.5b-9.3** `/settings/feedback-loop` per FR-1.5b-7.6.
- **FR-1.5b-9.4** `/settings/web-search` exists in V1.5c (not V1.5b).

## Non-functional requirements

- **NFR-1.5b-1 Latency** p95 page load < 1.5s (full-corpus Level B); Sigma.js 60fps zoom/pan.
- **NFR-1.5b-2 Bundle size** < 350 kB gzipped per route (Next.js route-splitting).
- **NFR-1.5b-3 Type safety** Pydantic-to-Zod generation enforced by CI; build fails on schema drift.
- **NFR-1.5b-4 Test coverage** ≥ 80% line on `src/web/`; ≥ 75% line on `web/src/`. Playwright E2E covers every page with E2E-required=Yes (per page-inventory.md).
- **NFR-1.5b-5 Accessibility** WCAG 2.1 AA per `docs/08-ui/accessibility.md`. axe-core in every Playwright test; 0 violations gate.
- **NFR-1.5b-6 Browser support** Chrome / Firefox / Safari current.
- **NFR-1.5b-7 Reproducibility** Pass-4 with identical `feedback_context_hash` produces identical output (content-hash idempotency, ADR-018).
- **NFR-1.5b-8 Observability** 100% audit-log coverage on UI actions + backend route invocations. Langfuse traces per LLM call; structlog JSON on FastAPI events.
- **NFR-1.5b-9 Quality non-regression** post-feedback-loop extraction precision ≥ V1 baseline on V1 sentiment + interview-Q gold sets.

## Out of scope (this sub-slice)

- Per-team dashboards (PM / Social / Marketing) → V1.5c.
- Web-search-grounded conflict resolution → V1.5c.
- Multi-user / auth → V2.
- Mobile-responsive design beyond Tailwind defaults → V2.
- Direct-canvas graph editing → V2.

## Open dependencies

1. V1.5a Verification Before Completion report filed in `.agent/reports/v1.5a-slice.md`.
2. ADR-012/-013/-017/-018 ratified.
3. Mahyar provides shadcn theme decision (V1.5-R2: stay on shadcn defaults — confirmed).
4. Node.js 22+ installed on Mahyar's workstation.
