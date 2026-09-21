# Feature: V1.5b — Web UI + Multi-level Graph Views + Cluster-Cull / Propose Loop + Feedback Context

**Status:** Spec only. Implementation blocked on V1.5a Verification Before Completion report filed + ADR-012/-013/-017 ratified + Mahyar's go-ahead.
**Sub-slice ratified:** V1.5-R1 (2026-05-24).
**Owner:** Mahyar (decisions) + Claude (implementation, post-V1.5a).
**Time budget:** 5–6 weeks of focused work after V1.5a gate passes.
**Acceptance level:** every V1 + V1.5a flow reachable through the web UI; the cluster-cull → propose-review → next-sweep feedback loop closes a complete cycle with measured extraction-quality lift.

## What this sub-slice proves

The V1.5 product becomes a **person-driven web application**, not a CLI tool. The graph stops being an abstract MCP surface and becomes a thing the user can see, click, and edit.

1. **Three-level graph viewer** — three independent routes (`/graph/structural`, `/graph/clusters`, `/graph/analyzed`) each backed by a level-typed retrieval contract per ADR-012. Sigma.js + WebGL canvas. ForceAtlas2 layout with worker offload. Selection persists across view switches.
2. **Full web HITL UI** — every V1 + V1.5a HITL flow has a web review page: alias, conflict, cluster-cull, node/edge proposal, multi-L1, cross-link, judge-disagreement, escalation. CLI stays as a power-user fallback.
3. **Cluster-cull review** — `/hitl/clusters` is the operational entry to the iterative loop. User opens the page when ready (manual trigger per V1.5-R1 Q14); sees the Pass-3 cluster landscape; marks clusters keep / cull / merge / split / mark-anomaly via bulk-action toolbar; commits the batch.
4. **Node/edge proposal review** — `/hitl/proposals` shows Pass-4 outputs from approved clusters, grouped by proposed node-type / edge-type. User accepts, rejects, or refines per proposal. Decisions write to `feedback_log`.
5. **BAML feedback loop** — Pass 4's prompt context block loads (a) previously-accepted node/edge types as `examples`, (b) rejected patterns as `blocklist`. The blocklist is enforced both in prompt and via post-hoc filter. Per ADR-017.
6. **Measured quality lift** — the loop runs at least one full cycle on a corpus subset; before/after extraction precision is measured against the V1 sentiment + interview-Q gold sets; quality lift > 0 verified.
7. **End-to-end ingestion through UI** — the V1.5a connector wizard pages (engine pick → config → discover → mapping → connector dashboard) are reachable as a connected flow.

## What this sub-slice does NOT prove (deferred to V1.5c / V1.6 / V2)

- Per-team dashboards (PM / Social / Marketing). V1.5c.
- Web-search-grounded conflict resolution. V1.5c.
- Multi-tenant auth or per-user attribution. V2.
- Real-time collaborative editing. V2.
- Mobile / responsive design beyond Tailwind defaults. V2.
- Direct-canvas graph editing (drag-to-merge etc.). V2.
- Production cloud deployment. V2.

## Why this sub-slice second

- V1.5a delivers the new backend surfaces (the seven new MCP tools + the cross-graph + tier system). V1.5b puts a face on them and on V1's existing surfaces.
- The cluster-cull + propose loop is the highest-impact human workflow we can ship — it directly attacks the "Pass 4 wastes tokens on bad clusters" failure mode the user named.
- It locks the UI tech stack contracts (ADR-013) so V1.5c can build per-team dashboards on the same foundation without re-platforming.
- The loop's measured quality lift becomes the V1.5 success story.

## Acceptance criteria (testable, blocking)

1. **All V1 + V1.5a flows reachable via UI** — every page in `docs/08-ui/page-inventory.md` rows where E2E test required = Yes ships with a passing Playwright smoke test.
2. **Three-level retrieval contracts** (`query_graph_structural`, `query_graph_clusters`, `query_graph_analyzed`) — implemented per ADR-012; tested with Pydantic schema round-trip + p95 latency budgets in `docs/08-ui/graph-level-views.md`.
3. **Sigma.js renders 50K-node structural subgraph at 60fps zoom/pan** on Mahyar's GTX 1080. Measured via Playwright performance trace.
4. **Cluster-cull flow closes a cycle** — given a corpus where Pass 3 has run, the user opens `/hitl/clusters`, marks 5 cull + 2 merge + 1 split, commits. Result: cull → status `culled`, merge target updated, split produces N new clusters. All audit-logged.
5. **Node/edge proposal flow closes a cycle** — Pass 4 runs on approved clusters from AC-4; proposals appear in `/hitl/proposals`; user accepts 3 + rejects 2; next Pass 4 sweep on same input no longer extracts the rejected patterns AND surfaces the accepted patterns as examples in the BAML context block. Verified by inspecting the prompt content + the cache-hit shape.
6. **Quality lift measured** — extraction precision on the V1 sentiment gold + interview-Q gold improves (or holds) post-feedback-loop vs pre-feedback. Regression gated: post-loop precision must be ≥ V1 baseline.
7. **Feedback-loop policy page** — `/settings/feedback-loop` shows the active context block + blocklist; user can edit the blocklist and rebuild the prompt context.
8. **Audit log covers every UI action** — `kind` enum extended with `ui_view`, `ui_select`, `ui_filter_change`, `ui_review_commit`, `ui_batch_commit`, `ui_settings_update`. 100% coverage tested.
9. **`secbrain ui` boots the dev environment** — one command spawns Next.js dev server + FastAPI + Prefect server; opens browser. Verified in onboarding doc.
10. **Verification Before Completion report** in `.agent/reports/v1.5b-slice.md`.

Non-functional:

- **NFR-1.5b-1 Latency** p95 page load (full-corpus level B): < 1.5s. p95 graph-canvas interactivity: 60fps.
- **NFR-1.5b-2 Bundle size** initial JS payload < 350 kB gzipped per page (Next.js per-route splitting).
- **NFR-1.5b-3 Type safety** Pydantic-to-Zod generation is enforced via `make generate-types` + CI gate; PRs that drift fail.
- **NFR-1.5b-4 Test coverage** ≥ 80% line on `src/web/` (FastAPI) + ≥ 75% on `web/src/` (Vitest unit + RTL component). Playwright E2E covers every AC-1 page.
- **NFR-1.5b-5 Accessibility** WCAG 2.1 AA per `docs/08-ui/accessibility.md` (which V1.5b also rewrites from TBD scaffolding).
- **NFR-1.5b-6 Browser support** Chrome / Firefox / Safari current; no IE/Edge-Legacy.
- **NFR-1.5b-7 Reproducibility** identical feedback-loop state + identical Pass-4 input → identical extraction output (content-hash idempotency preserved).

## Sub-files in this packet

- `README.md` — this file
- `requirements.md` — functional + non-functional requirements (FR-1.5b-* + NFR-1.5b-*)
- `context.md` — links to V1.5 master brief + ADR-012/-013/-017 + V1.5a deliverables
- `plan.md` — phased implementation plan (vertical-slice-first)
- `data.md` — `feedback_log` schema, `ui_event` audit kinds, cluster-cull state machine persistence
- `api.md` — `/api/v1/*` FastAPI routes + Pydantic models
- `state-machine.md` — cluster-review lifecycle + proposal-review lifecycle + feedback-loop state
- `test-plan.md` — Playwright + Vitest + pytest mapping
- `decisions.md` — slice-local decisions
- `known-issues.md`
- `changelog.md`

## Open questions (pending V1.5b kickoff)

- Color palette + brand-system finalization (currently shadcn defaults; Mahyar may want a custom theme).
- Whether `/hitl/clusters` shows the Sigma.js cluster map by default or a list-view by default (V1.5-R1 implied map-first; confirm during kickoff).
- Whether feedback-loop blocklist edits should require a confirmation step or apply immediately (default: confirm).
