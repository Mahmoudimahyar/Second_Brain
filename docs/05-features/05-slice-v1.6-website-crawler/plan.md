# Plan — V1.6a Website-Crawl Ingestion

> TDD per AGENTS.md. Crawler + adapter first (riskiest unknown), staged graph next, scheduler + UI last. Each phase ships a failing test before any production code.

## Phase 0 — Prereqs

| # | Item | Owner | Status |
|---|---|---|---|
| 0.1 | V1.5c Verification Before Completion report | Claude | Pending V1.5c |
| 0.2 | ADR-019 ratified | Mahyar | Drafted; pending |
| 0.3 | ADR-020 ratified | Mahyar | Drafted; pending |
| 0.4 | `CRAWL4AI_USER_AGENT` + `CRAWL4AI_CONTACT_EMAIL` in `.env` | Mahyar | Pending kickoff |
| 0.5 | (Optional) `SCRAPINGBEE_API_KEY` in `.env` | Mahyar | Optional |
| 0.6 | `crawl4ai`, `trafilatura`, `pikepdf`, `tabula-py`, `easyocr`, `croniter` pinned in `pyproject.toml` extras | Claude | Pending |
| 0.7 | `crawl4ai-setup` post-install Playwright Chromium installed | Claude | Pending |
| 0.8 | Default per-domain budget ($5/month) confirmed | Mahyar | Pending kickoff |

## Phase 1 — `Crawl4AIAdapter` + cache + robots.txt

1. **Failing-first test**: `tests/ingestion/adapters/test_crawl4ai_web.py::test_html_page_round_trip_extracts_title_and_body` — uses `httpx-mock` + a fixture HTML file to assert: title extracted, body matches Trafilatura output, content-hash stable, `Page` candidate record carries all required fields.
2. **Code**:
   - `src/ingestion/adapters/crawl4ai_web.py::Crawl4AIAdapter` (`BrowserConfig`, `CrawlerRunConfig` wiring, content-type dispatch, cache layer).
   - `src/ingestion/adapters/_robots_cache.py` (RFC 9309 parser; TTL'd SQLite-backed cache).
   - `src/ingestion/adapters/_content_hash_cache.py` (per-page hash + sidecar `.meta.json`).
3. **Tests**:
   - `test_pdf_via_pdf_strategy_returns_pdf_record` — `application/pdf` mock → `L1PdfAdapter` invoked → body chunks present.
   - `test_xlsx_via_l1_excel_returns_excel_record`.
   - `test_image_without_ocr_is_mediaasset_only` and `test_image_with_ocr_extracts_text`.
   - `test_html_table_becomes_table_node_with_cells`.
   - `test_robots_disallow_blocks_url` — synthetic robots.txt with `Disallow: /private/` → URL `/private/foo` never fetched.
   - `test_crawl_delay_honored` — `Crawl-delay: 2` → minimum 2s between fetches to that domain.
   - `test_etag_unchanged_returns_cache_hit` — second fetch with same ETag returns cached normalized record; no second HTTP call.
   - `test_oversized_page_skipped` — > 50 MB page → `oversized_page` audit row, not stored.

## Phase 2 — `ScrapingBeeFallback` (opt-in)

1. **Failing-first test**: `tests/ingestion/adapters/test_proxy_scrapingbee.py::test_fallback_invoked_after_three_403s` — domain configured `enable_scrapingbee_fallback=True`; mocked target returns 403 three times; assert ScrapingBee called on 4th attempt; assert response routed through `Trafilatura` extraction; assert `via_proxy=1` recorded.
2. **Code**:
   - `src/ingestion/adapters/proxy_scrapingbee.py::ScrapingBeeFallback`.
   - Trigger detection helpers (`detect_datadome`, `detect_perimeterx`, `detect_cf_challenge`).
3. **Tests**:
   - `test_fallback_disabled_by_default` — without `enable_scrapingbee_fallback`, ScrapingBee never invoked even on persistent 403.
   - `test_scrapingbee_cost_logged_against_budget` — every ScrapingBee call writes to `crawl_cost`.
   - `test_health_check_endpoint_succeeds_with_valid_key`.
   - `test_health_check_endpoint_fails_with_invalid_key`.
   - `test_no_pii_leakage` — request payload to ScrapingBee never contains anything other than URL + UA + (optional) referer.

## Phase 3 — `WebsiteCrawlSource` (DataSource)

1. **Failing-first test**: `tests/ingestion/sources/test_website_crawl.py::test_register_domain_blocked_returns_422` — attempt to register `reddit.com` raises `StructuredError(DOMAIN_BLOCKED)`.
2. **Code**:
   - `src/ingestion/sources/website_crawl.py::WebsiteCrawlSource`.
   - `src/ingestion/sources/blocked_domains.py` (FORUM_DOMAINS, SOCIAL_DOMAINS, matcher).
   - SQLite migrations: `crawl_domains`, `crawl_jobs`, `crawl_fetch_log`, `crawl_cost`, `robots_cache`, `pages_index`.
3. **Tests**:
   - `test_register_domain_valid_writes_row`.
   - `test_register_domain_subdomain_of_blocked_blocks_too` — `old.reddit.com` blocked.
   - `test_register_domain_with_l1_tier_requires_confirm`.
   - `test_register_domain_unreachable_raises_unreachable_domain`.
   - `test_discover_uses_sitemap_xml_when_present`.
   - `test_discover_falls_back_to_cc_when_no_sitemap`.
   - `test_discover_falls_back_to_homepage_bfs_when_both_absent`.
   - `test_pull_delta_uses_etag_short_circuit`.
   - `test_tier_change_l2_to_l1_requires_confirm`.

## Phase 4 — L0 sitemap flow

1. **Failing-first test**: `tests/flows/test_website_l0_sitemap.py::test_l0_writes_page_nodes_and_links_to_edges` — fixture URL set with 3 pages cross-linking; assert all 3 `Page` nodes + correct `LINKS_TO` adjacency.
2. **Code**:
   - `flows/website_l0_sitemap.py`.
   - `src/graph/web_node_types.py` (Page, Sitemap, MediaAsset, Table, ExternalRef registrations).
3. **Tests**:
   - `test_l0_idempotent_no_change_no_writes`.
   - `test_l0_content_hash_change_writes_new_version` — bitemporal `t_valid_to` close + new node open.
   - `test_l0_external_link_creates_externalref_placeholder`.
   - `test_l0_writes_sitemap_belongs_edges`.

## Phase 5 — L1 entity-tagged flow

1. **Failing-first test**: `tests/flows/test_website_l1_entity_tagged.py::test_l1_extracts_school_entity_and_links_to_l1_anchor` — fixture page mentions "New York University College of Dentistry"; assert `Entity` node created, `MENTIONS` edge written, rapidfuzz score ≥ 0.95 → auto-linked to existing V1 L1 NYU canonical node.
2. **Code**:
   - `flows/website_l1_entity_tagged.py`.
   - Reuse V1 `src/extraction/pass1_mention_extractor.py` for entity tagging.
   - Reuse V1 `src/embeddings/` for BGE-small.
3. **Tests**:
   - `test_l1_ambiguous_mention_routes_to_hitl` — score 0.80 → `entity_link_ambiguous` HITL item.
   - `test_l1_no_l1_anchor_match_leaves_entity_unlinked`.
   - `test_l1_chunking_overlap_64_token`.
   - `test_l1_idempotent_no_change_no_writes`.
   - `test_l1_referenced_topic_assigned_via_nearest_cluster`.

## Phase 6 — L2 full GraphRAG flow

1. **Failing-first test**: `tests/flows/test_website_l2_full_graphrag.py::test_l2_produces_clusters_and_summaries_within_budget` — fixture corpus of 20 pages with known topic clusters; assert ≥ 2 `Cluster` nodes + `SUMMARIZES` edges; total cost recorded ≤ projected cap.
2. **Code**:
   - `flows/website_l2_full_graphrag.py` (delegates to existing V1 Pass 4 + Pass 5 with web-corpus-scoped chunks).
   - Budget projector in `src/ingestion/sources/website_crawl.py::_project_l2_cost`.
3. **Tests**:
   - `test_l2_skips_when_budget_would_be_exceeded` — pre-computed projection > remaining budget → emits `budget_capped` HITL; L2 not run; L0 + L1 still run.
   - `test_l2_partial_change_reclusters_only_affected_chunks` — change 1 chunk; assert only the affected cluster recomputes.
   - `test_l2_conflict_routes_to_web_verification_agent` — claim contradicting L1 anchor → V1.5c `WebVerificationAgent` invoked.
   - `test_l2_idempotent_cache_hit_no_llm_call` — re-run on unchanged corpus → 0 LLM calls.

## Phase 7 — `website_crawl_dispatcher` (Prefect cron)

1. **Failing-first test**: `tests/flows/test_website_crawl_dispatcher.py::test_dispatcher_picks_due_jobs_and_dispatches` — seed `crawl_jobs` with 3 due rows; assert dispatcher transitions all to `running` and spawns 3 worker tasks.
2. **Code**:
   - `flows/website_crawl_dispatcher.py`.
   - `_schedule_due_jobs(now)` helper using `croniter`.
3. **Tests**:
   - `test_dispatcher_quarantines_failed_domain` — domain A worker raises; assert domain B and C unaffected.
   - `test_dispatcher_respects_concurrency_cap_16_domains`.
   - `test_dispatcher_exponential_backoff_after_three_failures`.
   - `test_dispatcher_auto_pauses_after_five_failures`.

## Phase 8 — FastAPI routes `/api/v1/ingest/web/*`

1. **Failing-first test**: `tests/web/test_website_crawl_routes.py::test_post_domains_blocked_returns_422` — POST `/api/v1/ingest/web/domains` with `domain=reddit.com` → 422 + `DOMAIN_BLOCKED`.
2. **Code**:
   - `src/web/routes/website_crawl.py` (all routes per `api.md`).
   - Pydantic models for request/response.
   - Zod codegen run.
3. **Tests**:
   - `test_get_domains_returns_paginated_list`.
   - `test_get_domain_status_returns_recent_runs`.
   - `test_post_trigger_now_enqueues_within_5_minutes`.
   - `test_patch_cadence_updates_and_audits`.
   - `test_post_pause_resume_round_trip`.
   - `test_delete_domain_marks_deleted_does_not_remove_history`.

## Phase 9 — Web UI `/ingest/web/*`

1. **Failing-first test**: `web/e2e/ingest-web.spec.ts::registration wizard happy path` — Playwright walks through: navigate, click "Register domain", fill `https://www.adea.org/`, pick L2/L1 stage daily 06:00, submit, see domain in list, click "Run now", wait, see successful run.
2. **Code**:
   - `web/src/app/ingest/web/page.tsx` (list).
   - `web/src/app/ingest/web/register/page.tsx` (wizard).
   - `web/src/app/ingest/web/[domain]/page.tsx` (detail).
   - `web/src/app/ingest/web/[domain]/page/[id]/page.tsx` (page detail).
   - `web/src/components/ingest-web/*` (DomainsTable, RegisterWizard, CronPicker, BudgetEditor, RunHistory, PageDetail).
   - TanStack Query hooks for backend integration.
3. **Tests**:
   - Vitest unit tests on each component.
   - Playwright E2E: registration / pause / resume / delete / force-full-refresh / cap-hit-banner / page-detail-version-timeline.
   - axe-core accessibility audit on every new page.

## Phase 10 — MCP outbound surface

1. **Failing-first test**: `tests/integrations/test_mcp_crawl_tools.py::test_register_crawl_domain_via_mcp` — MCP stdio call → domain registered → audit row written.
2. **Code**: `src/integrations/mcp_crawl_tools.py` exposing the 6 tools from FR-1.6a-7.
3. **Tests**: round-trip for each MCP tool + error paths (DOMAIN_BLOCKED returned over MCP wire).

## Phase 11 — Verification Before Completion

- Acceptance criteria 1–11 walked manually.
- Validation commands:
  ```
  uv run pytest -m "v1_6a"
  uv run pytest tests/ingestion/adapters/test_crawl4ai_web.py tests/ingestion/adapters/test_proxy_scrapingbee.py
  uv run pytest tests/ingestion/sources/test_website_crawl.py
  uv run pytest tests/flows/test_website_*.py
  uv run pytest tests/web/test_website_crawl_routes.py
  uv run mypy src/ingestion/adapters/crawl4ai_web.py src/ingestion/adapters/proxy_scrapingbee.py src/ingestion/sources/website_crawl.py
  uv run ruff check src/ingestion/adapters/crawl4ai_web.py src/ingestion/adapters/proxy_scrapingbee.py src/ingestion/sources/website_crawl.py
  cd web && pnpm test
  cd web && pnpm playwright test ingest-web.spec.ts
  cd web && pnpm axe-core
  ```
- Browser validation per CLAUDE.md.
- Final report → `.agent/reports/v1.6a-slice.md`.

## Scope

### In
- Website-crawl `DataSource` + `Crawl4AIAdapter` + opt-in `ScrapingBeeFallback`.
- Staged ingestion flows (L0 / L1 / L2).
- Prefect cron dispatcher.
- FastAPI routes + Pydantic models + Zod codegen.
- Next.js wizard + list + detail pages.
- MCP outbound tool surface.
- robots.txt + per-domain budget + blocklist enforcement.
- Tests + docs + audit + browser-validation.

### Out
- Forums (V1.6b).
- Slack / Notion (V1.6c).
- Push / RSS / WebSub (V2).
- Multi-tenant / auth (V2).
- Per-page stage selection (V1.7).

## Validation commands
- See Phase 11.
