# Plan — V1.5c

> TDD per AGENTS.md. Web-search agent first (because it's the riskiest unknown), then per-team dashboards build on top.

## Phase 0 — Prereqs

| # | Item | Owner | Status |
|---|---|---|---|
| 0.1 | V1.5b Verification Before Completion report | Claude | Pending V1.5b |
| 0.2 | ADR-016 v2 ratified | Mahyar | Drafted; pending |
| 0.3 | `TAVILY_API_KEY` in `.env` | Mahyar | ✅ V1.5-R2 |
| 0.4 | Cost-cap default ($5/corpus/sweep) confirmed | Mahyar | Pending V1.5c kickoff |

## Phase 1 — Tavily provider + question/paraphrase BAML templates

1. **Failing-first test**: `tests/conflict/providers/test_tavily.py::test_qna_search_returns_answer_and_urls` — uses respx to mock Tavily API; assert response shape; assert key passed correctly; assert timeout honored.
2. **Code**:
   - `src/conflict/providers/base.py` — `SearchProvider` Protocol (qna_search, search, extract methods + result schemas).
   - `src/conflict/providers/tavily.py` — `TavilyProvider` wrapping `tavily-python` SDK. Reads `TAVILY_API_KEY`.
   - `src/conflict/baml/make_question_from_claim.baml`.
   - `src/conflict/baml/paraphrase_question.baml`.
   - `src/conflict/baml/verify_claim_from_evidence.baml`.
3. **Tests**:
   - Health-check (qna_search 'ping').
   - Backoff + retry behavior (respx mock 5xx, then 200).
   - Cost-tracking write to `web_search_cost` table.
   - Per-call audit log.

## Phase 2 — Three-signal `WebVerificationAgent`

1. **Failing-first test**: `tests/conflict/test_web_verify.py::test_three_signals_majority_writes_verdict` — given a synthetic claim ("NYU dental tuition was $87k in 2024-25"), pre-recorded Tavily responses + mocked LLM verify; assert signal A + B + C aggregate to a `supports` verdict with citations.
2. **Code**:
   - `src/conflict/web_verify.py::WebVerificationAgent` — parallel async signals A/B/C, combine logic.
   - `src/conflict/signal_combine.py` — 2-of-3 majority logic + escalation to HITL on disagreement.
3. **Tests**:
   - 5 hand-crafted L1-vs-L5 clashes (V1.5c gold set in `evals/gold/v1.5c-web-verify.jsonl`).
   - All-disagree → escalation; all-unknown → research_need.
   - Cost-cap freeze blocks further calls.
   - 15s hard-timeout enforced.
   - Cache hit on identical (claim, context) repeat.

## Phase 3 — Hook into V1 conflict-resolution chain

1. **Failing-first test**: `tests/conflict/test_resolver_step5.py::test_step5_invokes_web_verify_before_hitl` — synthetic conflict reaches resolver step 5; assert `WebVerificationAgent` called; assert HITL only fires if web-verify fails.
2. **Code**:
   - `src/conflict/resolver.py` — step 5 invocation point; failure → step 6 (HITL).
   - Backwards compatibility: V1 resolver tests keep passing (web-verify can be disabled via config flag for V1 corpus tests).
3. **Acceptance**: 5 V1 seeded clashes pre-existing → all resolve through web-verify post-V1.5c.

## Phase 4 — Per-team aggregation backends

1. **Tests** per dashboard endpoint:
   - PM: aggregation correctness on a seeded corpus with known pain-point counts.
   - Social: trending-topic computation matches a hand-calculated baseline.
   - Marketing: gap detection produces expected gaps for a contrived sentiment/volume scenario.
2. **Code**:
   - `src/teams/__init__.py`
   - `src/teams/pm.py` — `compute_pain_points(corpus_id, filters) -> list[PainPoint]`.
   - `src/teams/social.py` — `compute_trending_topics(corpus_id, window, filters) -> list[TrendingTopic]`.
   - `src/teams/marketing.py` — `compute_content_gaps(corpus_id, filters) -> list[ContentGap]`.
   - `src/teams/angles.py` — `suggest_angles(team, item_id, k=3) -> list[str]` — single entry-point that routes through gateway with task `team_content_angles`.
   - `src/web/routes/teams.py` — REST endpoints.
3. **Acceptance**: each dashboard's backend returns the AC-counts specified in `README.md` (PM ≥ 10, Social ≥ 5, Marketing ≥ 5).

## Phase 5 — Team dashboard UIs

1. **Tests** (Playwright per dashboard):
   - Renders without errors on V1 seed corpus.
   - Filters work + persist via URL.
   - Drill-down opens `/graph/analyzed` with the right entity centered + citation drawer expanded.
2. **Code**:
   - `web/src/app/teams/pm/page.tsx` + `[id]/page.tsx`.
   - `web/src/app/teams/social/page.tsx` + `topic/[id]/page.tsx`.
   - `web/src/app/teams/marketing/page.tsx` + `gap/[id]/page.tsx`.
   - `web/src/components/team/{PainPointTable, TrendingTopicCarousel, ContentGapMatrix, SuggestedAnglesPanel, TeamDashboardLayout}.tsx`.

## Phase 6 — `/settings/web-search` UI + HITL extensions

1. **Tests**:
   - Settings page renders provider list + cost summary.
   - Health-check button works (mocked).
   - Cost-cap editor with >$50 confirmation modal.
   - `/hitl/escalated` renders `web_search_disagreement` + `tavily_unavailable` items.
2. **Code**:
   - `web/src/app/settings/web-search/page.tsx`.
   - `web/src/components/hitl/WebSearchDisagreementBody.tsx`.
   - `web/src/components/hitl/TavilyUnavailableBody.tsx`.

## Phase 7 — Verification Before Completion + integration smoke

1. End-to-end smoke: 5 seeded conflicts → web-verify resolves → results flow into PM dashboard → drill-down opens correct entity in Level C.
2. `.agent/reports/v1.5c-slice.md` + `.agent/reports/v1.5c-integration-smoke.md`.

## Provisional time estimate

| Phase | Hours |
|---:|---|
| 1 — Tavily provider + BAML templates | 18 |
| 2 — WebVerificationAgent + signal combine | 22 |
| 3 — Hook into V1 conflict resolver | 12 |
| 4 — Per-team aggregation backends | 28 |
| 5 — Three team dashboard UIs | 32 |
| 6 — Settings page + HITL extensions | 14 |
| 7 — Integration smoke + verification | 10 |
| **Total** | **~136 hours** (4 focused weeks) |

## Risk register

| Risk | Mitigation |
|---|---|
| Tavily reliability post-Nebius acquisition | `SearchProvider` Protocol allows swapping providers; V1.6 candidate to add Brave/Firecrawl as fallback |
| Three-signal latency creep past 4s budget | Per-signal timeouts + parallel async; cache hits dominate after warm-up |
| Cost cap hit prematurely | $5 default; configurable; alarm at 80%; UI banner clearly shows current spend |
| LLM-generated angles hallucinate | Always citation-backed; `draft-only` watermark; user must approve before any external use |
| Few-shot collapse on PM angles | ADR-018 cap (4) applies to `team_content_angles` BAML template too |
| Aggregation perf at scale | Pre-computed daily roll-up table refreshed by Prefect flow; UI reads roll-up not raw scan |
