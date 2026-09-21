# Test Plan — V1.5b

> Maps every AC + FR to concrete tests. Mirrors V1 + V1.5a conventions. Adds frontend testing (Vitest + RTL + Playwright + axe-core).

## Test layers

| Layer | Tool | Scope |
|---|---|---|
| Unit (backend) | pytest | Per-module: `src/web/routes/*`, `src/extraction/feedback_context.py`, `src/extraction/blocklist_filter.py` |
| Unit (frontend) | Vitest + React Testing Library | Per-component: `web/src/components/**/*.tsx` |
| Property | pytest + hypothesis | Feedback-loop scoring determinism, append-only invariant |
| Integration | pytest + TestClient | FastAPI route round-trips |
| Contract | Pydantic → Zod codegen check | `make check-types` CI gate |
| E2E | Playwright | Every page in `page-inventory.md` with E2E-required=Yes |
| Accessibility | axe-core in Playwright | Every page; 0-violations gate |
| Perf | Playwright perf trace | Sigma.js zoom/pan + page load p95 budgets |

## AC mapping

### AC-1: All V1 + V1.5a flows reachable via UI
Per `page-inventory.md`, each E2E-required page gets at least one Playwright smoke. CI gate.

### AC-2: Three-level retrieval contracts
- `tests/web/test_graph_routes.py::test_structural_endpoint_shape` — `GET /api/v1/graph/structural` returns `StructuralResult` with expected fields.
- Same for `clusters` + `analyzed` + `crosslinks`.
- `tests/web/test_graph_routes.py::test_p95_latency_per_level` — latency budgets.

### AC-3: Sigma.js performance
- `tests/web/e2e/test_graph_perf.spec.ts` — load 50K-node structural subgraph; Playwright perf trace asserts frame budgets.

### AC-4: Cluster-cull flow closes a cycle
- `tests/web/e2e/test_cluster_cull_cycle.spec.ts` — seeded Pass-3 output → user marks decisions → commit → assert Pass 4 sees only approved clusters.

### AC-5: Node/edge proposal flow + feedback loop
- `tests/web/e2e/test_proposal_cycle.spec.ts` — full cycle.
- `tests/extraction/test_feedback_context.py::test_top_k_with_diversity` — top-K selection honors diversity constraint.
- `tests/extraction/test_feedback_context.py::test_blocklist_lru_lfu_eviction` — eviction policy correctness.
- `tests/extraction/test_blocklist_filter.py::test_post_hoc_filter_drops_similar` — cosine > 0.92 drops; audit-logged.
- `tests/extraction/test_feedback_context.py::test_few_shot_cap_4` — never returns > 4 examples.
- `tests/extraction/test_feedback_context.py::test_append_only_invariant` — UPDATE / DELETE on feedback_log raises.

### AC-6: Quality non-regression
- `tests/evals/test_post_feedback_precision.py::test_v1_sentiment_gold_no_regression` — run sentiment eval on V1 gold; precision ≥ V1 baseline post-feedback-loop.
- Same for interview-Q gold.
- These tests run in CI on a representative seeded feedback log.

### AC-7: Feedback-loop policy page
- `tests/web/e2e/test_settings_feedback_loop.spec.ts` — edit weights, save, navigate away + back, assert persistence + audit-log row.

### AC-8: Audit log covers every UI action
- `tests/web/test_audit_coverage.py::test_each_route_writes_audit` — fire every route; assert one audit row per invocation.

### AC-9: `secbrain ui` boots dev environment
- `tests/integration/test_dev_orchestrator.py::test_secbrain_ui_boots_two_processes` — spawn `secbrain ui`, poll health endpoints, kill cleanly.

### AC-10: Verification Before Completion
- Manual: `.agent/reports/v1.5b-slice.md`.

## NFR coverage

- **NFR-1 Latency** — `tests/web/perf/test_page_load_p95.py` + Playwright perf traces.
- **NFR-2 Bundle size** — `tests/web/build/test_bundle_size.spec.ts` (Next.js build artifact size assertion).
- **NFR-3 Type safety** — CI gate via `make check-types` (codegen drift check).
- **NFR-4 Coverage** — pytest-cov for `src/web/` ≥ 80%; Vitest --coverage for `web/src/` ≥ 75%.
- **NFR-5 Accessibility** — axe-core in every E2E test; 0 violations.
- **NFR-6 Browser support** — Playwright matrix on Chromium + Firefox + WebKit.
- **NFR-7 Reproducibility** — `tests/extraction/test_pass4_repro.py::test_identical_context_block_identical_output`.
- **NFR-8 Observability** — `tests/observability/test_audit_log_v1.5b.py::test_100pct_route_coverage`.
- **NFR-9 Quality non-regression** — same as AC-6.

## Integration smoke (Phase 7 of plan.md)

`.agent/reports/v1.5b-integration-smoke.md` documents the end-to-end UI walkthrough:
- Open `/` → `/ingest` → connect a Postgres testcontainer.
- Discover, map, commit.
- Pull-delta.
- Open `/graph/structural`, then `/graph/clusters`, then `/graph/analyzed`; selection persists.
- Open `/hitl/clusters`, mark a cull batch.
- Open `/hitl/proposals` post-Pass-4, accept/reject some.
- Open `/settings/feedback-loop`, verify policy + active context block.
- Open `/audit`, verify the full chain of actions logged.

## Fixtures

- `tests/web/fixtures/playwright_setup.ts` — boots `secbrain ui` in test mode (in-memory SQLite + mocked LLM gateway).
- `tests/web/fixtures/seeded_graph.sql` — minimal V1 + V1.5a graph for E2E tests.
- `tests/extraction/fixtures/feedback_log_seeded.jsonl` — known feedback log for scoring tests.

## Coverage budget

| Module | Target |
|---|---|
| `src/web/routes/*` | ≥ 85% |
| `src/web/schemas/*` | ≥ 90% |
| `src/web/middleware/*` | ≥ 85% |
| `src/extraction/feedback_context.py` | ≥ 90% |
| `src/extraction/blocklist_filter.py` | ≥ 90% |
| `src/extraction/cache.py` (additions) | ≥ 95% |
| `src/observability/audit.py` (additions) | ≥ 95% |
| `web/src/components/graph/*` | ≥ 80% |
| `web/src/components/hitl/*` | ≥ 80% |
| `web/src/components/ingest/*` | ≥ 75% |
| `web/src/lib/api/*` | ≥ 85% |
| Overall V1.5b-touched modules (backend) | ≥ 80% |
| Overall V1.5b-touched components (frontend) | ≥ 75% |
