# Test Plan — V1.5c

> Maps every AC + FR to test cases. Tavily mocked via respx with pre-recorded fixtures.

## Test layers

| Layer | Tool | Scope |
|---|---|---|
| Unit (backend) | pytest | `src/conflict/web_verify.py`, `src/conflict/providers/tavily.py`, `src/conflict/signal_combine.py`, `src/teams/*` |
| Unit (frontend) | Vitest + RTL | `web/src/components/team/*`, `web/src/components/hitl/{WebSearchDisagreementBody,TavilyUnavailableBody}.tsx` |
| Integration | pytest + TestClient + respx | Resolver step 5 invokes web-verify; Tavily mocked |
| Eval (gold-set) | pytest | 5 seeded clashes resolve to verdict |
| E2E | Playwright | `/teams/*` pages, `/settings/web-search`, `/hitl/escalated` web-verify item bodies |
| Cost | pytest | Cap-hit / cap-warning thresholds |

## AC mapping

### AC-1: 5 seeded clashes reach verdict via web-verify
- `evals/gold/v1.5c-web-verify.jsonl` — 5 hand-crafted L1-vs-L5 clashes with known correct verdicts.
- `tests/conflict/test_web_verify_gold.py::test_all_5_clashes_reach_verdict` — runs the agent (Tavily mocked with pre-recorded responses); asserts each reaches a verdict that matches the gold.

### AC-2: 2-of-3 signal agreement enforced
- `tests/conflict/test_signal_combine.py::test_two_of_three_agreement_writes_verdict` — synthetic signal combinations.
- `tests/conflict/test_signal_combine.py::test_one_signal_only_escalates` — only signal A succeeded → escalation.
- `tests/conflict/test_signal_combine.py::test_all_unknown_emits_research_need` — all three return unknown.
- `tests/conflict/test_signal_combine.py::test_provider_failure_routes_to_tavily_unavailable` — 3 retries failed.

### AC-3: Cost cap honored
- `tests/conflict/test_cost_cap.py::test_cap_warning_at_80pct` — fires `cap_warning` audit event.
- `tests/conflict/test_cost_cap.py::test_cap_hit_freezes_further_calls` — 100% cap; subsequent calls return `WEB_SEARCH_CAP_HIT`.
- `tests/conflict/test_cost_cap.py::test_manual_reset_unfreezes` — admin reset re-enables.

### AC-4: PM dashboard ≥ 10 sourced pain points
- `tests/teams/test_pm_aggregation.py::test_minimum_10_pain_points_on_v1_corpus` — runs aggregation on V1 seed corpus.
- `tests/teams/test_pm_aggregation.py::test_every_pain_point_has_citation` — `references` ≥ 1.

### AC-5: Social dashboard ≥ 5 trending topics with charts
- `tests/teams/test_social_aggregation.py::test_minimum_5_trending` — V1 seed corpus, 12-month window.
- `tests/teams/test_social_aggregation.py::test_trend_chart_has_daily_buckets` — daily volume + sentiment buckets.

### AC-6: Marketing dashboard ≥ 5 content gaps
- `tests/teams/test_marketing_aggregation.py::test_minimum_5_gaps` — V1 seed corpus.
- `tests/teams/test_marketing_aggregation.py::test_gap_detection_threshold` — gap = high volume + sentiment < 0.5.

### AC-7: Drill-down chain end-to-end
- `tests/web/e2e/test_team_drilldown.spec.ts` — click on a PM pain point → `/graph/analyzed` opens centered on the anchor with citation drawer expanded.

### AC-8: Web-search audit + cost telemetry
- `tests/observability/test_web_search_audit.py::test_every_tavily_call_audit_logged` — fire calls; assert audit rows.
- `tests/observability/test_langfuse_attribution.py::test_web_verify_tagged` — Langfuse trace carries `task=web_verify`.

### AC-9: Settings page for web-search providers
- `tests/web/e2e/test_settings_web_search.spec.ts` — health-check, cap-edit with confirmation modal, last-100 summary.

### AC-10: Verification Before Completion
- Manual: `.agent/reports/v1.5c-slice.md`.

## NFR coverage

- **NFR-1 Latency** — `tests/conflict/perf/test_web_verify_latency.py::test_p95_under_4s` (Tavily mocked at realistic latencies).
- **NFR-2 Cost** — see AC-3.
- **NFR-3 Citation traceability** — `tests/retrieval/test_citation_traceability_v1.5c.py::test_99pct_on_dashboards` across all three dashboards + verdict writes.
- **NFR-4 Coverage** — pytest-cov + Vitest --coverage targets.
- **NFR-5 Reliability** — `tests/conflict/test_failure_modes.py::test_tavily_5xx_routes_to_hitl`.
- **NFR-6 Reproducibility** — `tests/conflict/test_repro.py::test_identical_input_identical_verdict`.
- **NFR-7 Model swap-ability** — `tests/teams/test_model_swap.py::test_changing_team_content_angles_in_matrix_takes_effect` (edit matrix → next call uses new model; assert via Langfuse trace).

## Integration smoke (Phase 7 of plan.md)

`.agent/reports/v1.5c-integration-smoke.md` documents:
- 5 seeded conflicts → web-verify resolves each (4 supports, 1 refutes).
- Outputs flow into PM dashboard.
- Drill-down opens correct entity in Level C with full citations.
- `/settings/web-search` shows the 5 calls' cost summary.

## Fixtures

- `tests/fixtures/v1.5c-tavily-responses/` — pre-recorded Tavily responses for the 5 gold clashes + additional edge cases.
- `tests/fixtures/v1.5c-llm-verify-responses.json` — mocked LLM verify outputs.
- `evals/gold/v1.5c-web-verify.jsonl` — the 5 clashes with expected verdicts.
- `evals/gold/v1.5c-pm-pain-points.jsonl` — expected pain-point counts + content.

## Coverage budget

| Module | Target |
|---|---|
| `src/conflict/web_verify.py` | ≥ 85% |
| `src/conflict/providers/*` | ≥ 85% |
| `src/conflict/signal_combine.py` | ≥ 90% |
| `src/teams/pm.py` | ≥ 80% |
| `src/teams/social.py` | ≥ 80% |
| `src/teams/marketing.py` | ≥ 80% |
| `src/teams/angles.py` | ≥ 85% |
| `src/web/routes/teams.py` | ≥ 85% |
| `web/src/components/team/*` | ≥ 75% |
| Overall V1.5c-touched modules | ≥ 80% |
