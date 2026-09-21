# Requirements — V1.5c

> Testable; mapping to test cases in `test-plan.md`. Builds on V1 + V1.5a + V1.5b.

## Functional requirements

### FR-1.5c-1 — Web-verification agent (Tavily-only per ADR-016 v2)

- **FR-1.5c-1.1** `src/conflict/web_verify.py::WebVerificationAgent.verify(claim, context) -> VerdictResult` implements the three-signal combine per ADR-016 v2: signal A (Tavily QNA on original), signal B (Tavily search on LLM-rephrased query), signal C (Tavily extract + two-vendor LLM verification on top URLs).
- **FR-1.5c-1.2** Signal combination: ≥ 2-of-3 agreement on the same verdict (`supports` / `refutes`) with confidence ≥ 0.7 → write verdict. Otherwise escalate to HITL (`web_search_disagreement`) or emit `research_need` (if all three return `unknown`).
- **FR-1.5c-1.3** `src/conflict/providers/tavily.py::TavilyProvider` wraps the official Tavily Python SDK. Supports `qna_search`, `search`, and `extract` calls. Reads `TAVILY_API_KEY` from `.env`. Health-check endpoint.
- **FR-1.5c-1.4** Question-generation + paraphrasing: BAML templates `make_question_from_claim` + `paraphrase_question`. Paraphrase must change ≥ 3 content words OR change phrasing structure (validated by edit-distance check).
- **FR-1.5c-1.5** Two-vendor LLM extract-verify: Haiku 4.5 + Gemini Flash via gateway. Both must return same verdict for signal C; else signal C = `disagreement`.
- **FR-1.5c-1.6** Verdict provenance: every verdict stores `web_verification_run` JSON including all three signals, questions used, raw Tavily responses, extracted page contents, per-vendor LLM verdicts, final combine logic. Embedded in the resulting graph claim's `references`.
- **FR-1.5c-1.7** Cost cap: per-corpus cap default $5/sweep, configurable in `/settings/web-search`. Tracked in `web_search_cost` SQLite table. Triggers `cap_hit` audit event + freezes further web-verify calls until window/manual reset.
- **FR-1.5c-1.8** Cache: 7-day TTL keyed on `(claim_hash, context_summary_hash, tavily_model_version, llm_versions)`.
- **FR-1.5c-1.9** Latency budget: 15s hard timeout; per-call timeouts Tavily 8s / LLM verify 6s; typical run 3-5s.
- **FR-1.5c-1.10** Failure modes: Tavily 5xx/rate-limit → exponential backoff (3 tries, 1s/2s/4s); after 3 failures emit `tavily_unavailable` + route to HITL. LLM gateway failure → single-vendor signal C with `low_confidence` flag.
- **FR-1.5c-1.11** Hook into V1's conflict-resolution chain: step 5 of the order (`docs/04-architecture/system-overview.md` §3) now invokes `WebVerificationAgent` instead of just emitting `research_need`. Step 6 (HITL escalation) only fires if web-verify can't reach quorum.

### FR-1.5c-2 — Per-team dashboards (model-swappable per ADR-011)

- **FR-1.5c-2.1** Each dashboard is a Next.js page under `web/src/app/teams/{pm|social|marketing}/`. Backend routes under `src/web/routes/teams.py`.
- **FR-1.5c-2.2** Each dashboard's "suggested angles" content uses the model gateway with task type `team_content_angles`. Default model: **Gemini 2.5 Flash-Lite** per V1.5-R2. Model swap-ability: the per-task matrix in `docs/04-architecture/tech-stack.md` is extended with this task; switching models = editing the matrix, no code change.
- **FR-1.5c-2.3** All three dashboards share `TeamDashboardLayout`, `CitationDrawer`, drill-down to `/graph/analyzed`. Citation traceability ≥ 99%.

### FR-1.5c-2a — PM dashboard

- **FR-1.5c-2a.1** `/teams/pm` shows top pain points aggregated from Pass-4 `conflict_candidate` + `interview_q` + cluster sentiment, ranked by audience segment + volume.
- **FR-1.5c-2a.2** Each pain-point row shows: pain-point label, volume, sentiment ratio, top contributing clusters, source-tier mix, last 30-day trend sparkline.
- **FR-1.5c-2a.3** Per-pain-point drill-down (`/teams/pm/[id]`): source citations (≥ 1 forum post or DB row), proposed feature angles (LLM-generated, ≥ 3 suggestions, draft-only).
- **FR-1.5c-2a.4** Filter: audience segment (all / pre-dental / dental-student / dentist), time range, min volume, sort by volume / sentiment / trend velocity.
- **FR-1.5c-2a.5** Empty state: "Pass 4 hasn't completed for this corpus yet" with CTA "Run Pass 4 now."

### FR-1.5c-2b — Social-media dashboard

- **FR-1.5c-2b.1** `/teams/social` shows trending topics for selected time window (default last 7 days).
- **FR-1.5c-2b.2** Each topic shows: cluster label, current volume, sentiment heat (red/gray/green), trend direction (↑/→/↓), suggested-response-angle preview.
- **FR-1.5c-2b.3** Per-topic drill-down (`/teams/social/topic/[id]`): trend chart (Tremor LineChart, daily volume × sentiment), top recent posts (sorted by recency × engagement), suggested social-post angles (LLM-generated, ≥ 3 angles, draft-only).
- **FR-1.5c-2b.4** Filter: time window (24h / 7d / 30d / 90d), min volume, sentiment band.

### FR-1.5c-2c — Marketing/SEO dashboard

- **FR-1.5c-2c.1** `/teams/marketing` shows content-gap matrix: topic × sentiment cells; "gap" = high volume + no positive consensus (sentiment ratio < 0.5).
- **FR-1.5c-2c.2** Each gap row shows: topic, volume, sentiment ratio, supporting cluster IDs, current source-tier coverage.
- **FR-1.5c-2c.3** Per-gap drill-down (`/teams/marketing/gap/[id]`): supporting data tables, suggested content angles (LLM-generated, ≥ 3 angles, draft-only), competitor coverage stub (V1.6).
- **FR-1.5c-2c.4** Filter: topic category, min volume, sentiment threshold, source-tier mix.

### FR-1.5c-3 — Web-search settings UI

- **FR-1.5c-3.1** `/settings/web-search` shows current providers (Tavily), API-key status (health-check via `tavily.qna_search('ping')`), per-corpus cost cap, last 100 calls' summary (Tremor BarChart: per-day cost).
- **FR-1.5c-3.2** API-key field uses `CredentialField` (plaintext .env per V1.5).
- **FR-1.5c-3.3** Cost-cap editor with confirmation on >$50 (sanity check).

### FR-1.5c-4 — HITL extensions for V1.5c

- **FR-1.5c-4.1** `/hitl/escalated` (existing from V1.5b) gains renderers for new item types: `web_search_disagreement` and `tavily_unavailable`.
- **FR-1.5c-4.2** `web_search_disagreement` body shows all three signals side-by-side with raw Tavily responses; reviewer picks the winning verdict or escalates further.
- **FR-1.5c-4.3** `tavily_unavailable` body shows the original claim + Mahyar's options: retry web-verify, mark as research_need for manual follow-up, accept the L5 / L1 side without web-verification.

### FR-1.5c-5 — Audit + observability

- **FR-1.5c-5.1** New `audit_log.kind` values: `web_search_call`, `web_search_cap_hit`, `web_verify_verdict`, `web_verify_escalated`, `team_dashboard_view`, `team_angles_generated`.
- **FR-1.5c-5.2** Langfuse tagging: web-verify calls tagged `task=web_verify`; team-angles calls tagged `task=team_content_angles, team=<pm|social|marketing>`.
- **FR-1.5c-5.3** SQLite `web_search_cost` table: `(call_id, corpus_id, ts, cost_usd, latency_ms, provider, signal, success_bool)`.

## Non-functional requirements

- **NFR-1.5c-1 Latency** web-verify p95 < 4s (Tavily-bound); team dashboard initial load < 2s.
- **NFR-1.5c-2 Cost** default cap $5 / corpus / sweep; alarm at 80% (audit-log `kind=cap_warning`); freeze at 100%.
- **NFR-1.5c-3 Citation traceability** ≥ 99% across all three dashboards + every web-verify verdict.
- **NFR-1.5c-4 Test coverage** ≥ 80% line on `src/conflict/web_verify.py`, `src/conflict/providers/*`, `src/teams/*`, `src/web/routes/teams.py`.
- **NFR-1.5c-5 Reliability** Tavily failure routes to HITL with structured error; never crashes the resolver.
- **NFR-1.5c-6 Reproducibility** identical claim + identical Tavily index state + identical LLM versions → identical verdict (cache or replay).
- **NFR-1.5c-7 Model swap-ability** changing `team_content_angles` task model in the ADR-003 matrix takes effect on next call; no code change.

## Out of scope (this sub-slice)

- Actual content generation beyond suggested angles. (V2 marketing-content-gen agent.)
- Cross-vendor LLM-as-judge expansion beyond same-tier same-year. (V2.)
- Multi-user dashboard subscriptions / scheduled reports. (V2.)
- Mobile-optimized dashboard layouts. (V2.)
- Real-time dashboard updates (auto-refresh). (V2; V1.5c is manual-refresh.)
- Adding Brave / Firecrawl / Exa as providers. (V1.6.)
- Source-reputation scoring for web-search results. (V1.6 — V1.5c treats Tavily-surfaced URLs equally.)
- Competitor coverage view in marketing dashboard. (V1.6.)

## Open dependencies

1. V1.5b Verification Before Completion report filed.
2. ADR-016 v2 ratified.
3. `TAVILY_API_KEY` in `.env` (Mahyar confirmed V1.5-R2 ✅).
4. Web-search cost cap default ($5/corpus/sweep) confirmed during V1.5c kickoff.
