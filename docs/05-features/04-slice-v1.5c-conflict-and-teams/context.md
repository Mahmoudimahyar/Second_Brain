# Context — V1.5c

## Upstream

V1 + V1.5a + V1.5b deliverables. V1.5 master brief.

## Directly applicable ADRs

- **ADR-006** — conflict-resolution order (step 5 now active per V1.5c).
- **ADR-011** — model gateway (V1.5c registers `team_content_angles`, `make_question_from_claim`, `paraphrase_question`, `verify_claim_from_evidence` tasks).
- **ADR-016 v2** — Tavily-only web-verify with query-rephrase + 3-judge cross-check.
- **ADR-013** — UI tech stack (V1.5c builds dashboards on V1.5b's foundation).

## Upstream code (do-not-break)

- `src/conflict/resolver.py` — gains web-verify invocation at step 5.
- `src/gateway/api.py` — model gateway is the boundary V1.5c relies on for swap-ability.
- `src/web/routes/` — V1.5b's route layout; V1.5c adds `teams.py` + `web_verify.py` + `settings_web_search.py`.
- `src/observability/audit.py` — `kind` enum extended.

## Downstream consumers (what V1.5c unlocks)

- V2 marketing-content-gen agent — V1.5c's "suggested angles" surface is the natural ancestor of an autonomous content writer.
- V2 search-verification autonomous agent — V1.5c's WebVerificationAgent is the kernel.
- V1.6 multi-provider web search — V1.5c's `SearchProvider` Protocol is the plug-in surface.

## External research informing this slice

- Tavily SDK capabilities (qna_search, search, extract; search_depth modes).
- 2026 agentic search API benchmarks — Tavily ranked 5th overall agent score (13.67); ~1s latency.
- TruthfulRAG + hybrid fact-checking — informed the three-signal majority pattern.
- Microsoft killed Bing API in March 2025; Brave + Tavily + Firecrawl + Exa are the V1.5+ choices.
- DSPy GEPA + active-learning content selection (V2 candidate).

## Memory

See V1.5 master brief + assumptions.md V1.5-R1 / V1.5-R2 entries — especially A-081 (Tavily-only) and A-083 (model-swappable team content angles).
