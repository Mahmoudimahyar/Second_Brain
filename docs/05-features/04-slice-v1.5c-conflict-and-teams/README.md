# Feature: V1.5c — Web-Search Conflict Resolution + PM / Social / Marketing Dashboards

**Status:** Spec only. Implementation blocked on V1.5b Verification Before Completion report filed + ADR-016 ratified + Mahyar's go-ahead.
**Sub-slice ratified:** V1.5-R1 (2026-05-24).
**Owner:** Mahyar (decisions) + Claude (implementation, post-V1.5b).
**Time budget:** 3–5 weeks of focused work after V1.5b gate passes.
**Acceptance level:** the conflict resolver reaches a sourced verdict on 5 seeded clashes via web search; each per-team dashboard returns at least 10 sourced insights for the V1 seed corpus.

## What this sub-slice proves

The closing payoff of V1.5: the system becomes useful to people other than the operator. PMs, social media strategists, and marketing teams open a dashboard and see decision-grade outputs with full citation provenance.

1. **Web-search-grounded conflict resolution** — step 5 of the V1 conflict-resolution chain ("emit `research_need`") becomes step 5 active: the resolver invokes a web-search agent that runs Brave Search + Tavily in parallel, requires 2-of-2 agreement on at least one supporting citation, and writes the resolved verdict to the graph with `references` pointing to both providers' URLs. Per ADR-016.
2. **PM dashboard** — `/teams/pm` surfaces top pain points aggregated from Pass-4 conflict-candidate + interview-Q + cluster sentiment, ranked by audience segment + volume. Each pain point drill-down (`/teams/pm/[id]`) shows source citations + proposed feature angles (LLM-generated, draft-only).
3. **Social-media dashboard** — `/teams/social` shows trending topics by time window with sentiment heat. Each topic drill-down shows trend chart + suggested social-post angles.
4. **Marketing/SEO dashboard** — `/teams/marketing` shows content-gap matrix (topic × sentiment cells with gap detection — high volume + no positive consensus = opportunity). Each gap drill-down shows supporting data + suggested content angles.
5. **All three dashboards share** a `TeamDashboardLayout` chrome, the citation drawer, audit-log integration, drill-down to `/graph/analyzed` for full evidence.

## What this sub-slice does NOT prove (deferred to V1.6 / V2)

- Actual content generation (the marketing-content-gen agent writing full blog posts). Suggested angles only.
- Cross-vendor LLM-as-judge expansion beyond same-tier same-year. V2.
- Multi-user dashboard subscriptions / scheduled reports. V2.
- Mobile-optimized dashboard layouts. V2.
- Real-time dashboard updates (auto-refresh). V2 — V1.5c is manual-refresh.

## Why this sub-slice last

- It depends on every prior layer: clean V1.5a connectors for external data anchors; V1.5b graph + feedback loop for the cleaned graph foundation.
- It's the proof that the V1+V1.5 architecture actually serves humans, not just agents. Without it, V1.5 is "better internals, same surface as V1."
- The web-search conflict step is the riskiest unknown (cost, latency, provider reliability) — pushing it to last lets V1.5a + V1.5b stay simple.

## Acceptance criteria (testable, blocking)

1. **Web-search agent reaches verdict on 5 seeded clashes** — 5 hand-crafted L1-vs-L5 clashes in the V1 corpus where the resolver previously emitted `research_need`. After V1.5c lands, all 5 resolve to a verdict with citations from at least one of Brave + Tavily, with 2-of-2 agreement on the relevant fact.
2. **Brave + Tavily 2-of-2 enforcement** — both providers must return at least one URL that mentions the resolved fact within the top 5 results. If only one provider returns evidence, the verdict escalates to HITL (`web_search_disagreement`).
3. **Web-search cost cap honored** — per-corpus cap (default $5 per full sweep, configurable in `/settings/web-search`). Once hit, further `research_need` items wait until next sweep window or manual override.
4. **PM dashboard returns ≥ 10 sourced pain points** for the V1 seed corpus (r/DentalSchool + SDN Pre-Dental + ADEA). Each carries `references` ≥ 1.
5. **Social dashboard returns ≥ 5 trending topics with trend charts** for the last 12 months of the V1 seed corpus.
6. **Marketing dashboard returns ≥ 5 content gaps** with supporting data + suggested angles for the V1 seed corpus.
7. **Drill-down chain works end-to-end** — clicking any insight on any team dashboard opens `/graph/analyzed` centered on the relevant anchor with citation drawer pre-expanded.
8. **Web-search audit + cost telemetry** — every web-search call writes an audit-log row (kind `web_search`) and a Langfuse event with provider + latency + cost.
9. **Settings page for web-search providers** — `/settings/web-search` shows current providers, API-key status (health-check), per-corpus cap, last 100 calls' cost summary.
10. **Verification Before Completion report** in `.agent/reports/v1.5c-slice.md`.

Non-functional:

- **NFR-1.5c-1 Latency** web-search call p95 < 4s (Brave + Tavily parallel; Brave ~700ms, Tavily ~2s).
- **NFR-1.5c-2 Cost** default cap $5 per corpus per sweep; alarm at 80%.
- **NFR-1.5c-3 Test coverage** ≥ 80% line on `src/conflict/web_verify.py` + `src/teams/*` + `web/src/app/teams/*`.
- **NFR-1.5c-4 Citation traceability** ≥ 99% across all three dashboards. Same gate as V1 FR-8.3.
- **NFR-1.5c-5 Reliability** web-search provider failure (5xx, rate-limit) routes to a single-provider fallback with `low_confidence` flag; never crashes the resolver.

## Sub-files in this packet

- `README.md` — this file
- `requirements.md` — functional + non-functional requirements
- `context.md` — links to V1.5 master brief + ADR-016 + V1.5b deliverables
- `plan.md` — phased implementation plan
- `data.md` — `web_search_log` schema, per-team aggregation table specs, dashboard query patterns
- `api.md` — `/api/v1/teams/*` FastAPI routes + Pydantic models
- `state-machine.md` — web-verify lifecycle + per-team-insight lifecycle
- `test-plan.md` — Playwright + Vitest + pytest + web-search mock stack
- `decisions.md`
- `known-issues.md`
- `changelog.md`

## Open questions (pending V1.5c kickoff)

- LLM model for "suggested feature angles" / "suggested social post angles" — default Gemini Flash-Lite per ADR-003 cost matrix, but Mahyar may want Haiku for nuance.
- Whether team-specific insights should also surface in the HITL queue for refinement, or stay read-only V1.5c (default: read-only, with "Refine this" CTA logging a refinement request to V1.6 backlog).
- Brave + Tavily API-key procurement (Mahyar action).
