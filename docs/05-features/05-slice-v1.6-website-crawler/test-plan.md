# Test Plan — V1.6a Website-Crawl Ingestion

> TDD per AGENTS.md. Every test below precedes its production code by at least one commit. Coverage gate per NFR-1.6a-3 (≥ 80% line on new code paths).

## Test stacks

| Layer | Tool | Where |
|---|---|---|
| Unit | `pytest` + `pytest-asyncio` | `tests/ingestion/`, `tests/flows/`, `tests/web/`, `tests/integrations/` |
| Mocked HTTP | `httpx-mock` + `respx` | per-adapter unit tests |
| Mocked LLM | V1's `MockGateway` (already exists) + recorded fixture responses | L2 flow tests |
| Mocked Tavily | V1.5c's recorded responses (reused) | L2 conflict-resolution tests |
| Mocked Prefect | `prefect.testing.utilities` | dispatcher tests |
| Property | `hypothesis` | URL parsing, content-hash dedup, cadence parsing |
| Integration | `pytest` against running SQLite + local Prefect + crawl4ai headless | `tests/integration/v1_6a/` |
| Browser (E2E) | Playwright + axe-core | `web/e2e/ingest-web.spec.ts` |
| API contract | Pydantic ↔ Zod parity test (auto-gen) | `tests/web/schemas/test_codegen_parity.py` |
| Performance | `pytest-benchmark` | NFR-1.6a-1 latency gate |
| Coverage | `pytest --cov=src/ingestion --cov=src/web/routes/website_crawl --cov=flows --cov-fail-under=80` | CI |

## Test fixtures

### Synthetic test domains

Located in `tests/fixtures/web/`:

| Fixture domain | Purpose |
|---|---|
| `fixture-clean-html.local` | 25 well-formed HTML pages, sitemap.xml, robots.txt allows all |
| `fixture-pdf-heavy.local` | 10 HTML + 5 PDF (one scanned for OCR test) |
| `fixture-xlsx-tables.local` | 5 HTML pages with `<table>`, plus 2 `.xlsx` downloads |
| `fixture-disallow-private.local` | robots.txt with `Disallow: /private/`; URLs both inside and outside `/private/` |
| `fixture-403-then-recover.local` | first 3 requests 403, 4th returns 200 — used for ScrapingBee fallback gate |
| `fixture-datadome-protected.local` | always 403 + `Server: DataDome` header — triggers ScrapingBee path immediately |
| `fixture-crawl-delay.local` | robots.txt with `Crawl-delay: 2` — used to assert pacing |
| `fixture-l1-clash.local` | a page making the seeded "NYU tuition 2024-25" claim that contradicts V1 ADEA L1 anchor |
| `fixture-bitemporal-changes.local` | versioned HTML; rev1 and rev2 differ in content_hash for the same URL |
| `fixture-oversized.local` | one URL serves a 60 MB body — used for oversized_page skip test |
| `fixture-no-sitemap.local` | robots.txt without sitemap directive; Common Crawl shim fixture returns 5 URLs |

All fixtures served via local httpx-mock router. No real network.

### Recorded LLM responses
- `tests/fixtures/llm/web_l1_entity_match_nyu.json` — GLiNER2 + rapidfuzz output for a page mentioning NYU dentistry.
- `tests/fixtures/llm/web_l2_cluster_summary_*.json` — Gemini Flash-Lite recorded responses for L2 cluster summaries.
- `tests/fixtures/llm/web_l2_extract_claim_nyu_tuition.json` — Haiku 4.5 recorded response for the NYU tuition clash.
- `tests/fixtures/llm/web_l2_tavily_verify_nyu_tuition.json` — V1.5c Tavily QNA/search/extract recordings.

### Recorded ScrapingBee response
- `tests/fixtures/scrapingbee/datadome_recovery.json` — a single successful ScrapingBee call returning the HTML body of `fixture-datadome-protected.local/page1.html`.

## Per-phase coverage map

### Phase 1 — `Crawl4AIAdapter` + robots.txt + cache (`tests/ingestion/adapters/test_crawl4ai_web.py`)

```
test_html_page_round_trip_extracts_title_and_body
test_pdf_via_pdf_strategy_returns_pdf_record
test_xlsx_via_l1_excel_returns_excel_record
test_image_without_ocr_is_mediaasset_only
test_image_with_ocr_extracts_text
test_html_table_becomes_table_node_with_cells
test_robots_disallow_blocks_url
test_robots_absent_treats_as_all_allowed
test_robots_crawl_delay_honored_2_seconds
test_etag_unchanged_returns_cache_hit
test_last_modified_unchanged_returns_cache_hit
test_content_hash_unchanged_returns_cache_hit
test_oversized_page_skipped_emits_audit
test_user_agent_env_required_or_raises
test_adaptive_crawl_off_at_l0_on_at_l2
```

### Phase 2 — `ScrapingBeeFallback` (`tests/ingestion/adapters/test_proxy_scrapingbee.py`)

```
test_fallback_disabled_by_default
test_fallback_invoked_after_three_403s
test_fallback_invoked_on_datadome_detection
test_fallback_invoked_on_perimeterx_detection
test_fallback_invoked_on_cf_challenge_detection
test_scrapingbee_cost_logged_against_budget
test_no_pii_leakage_in_request
test_health_check_succeeds_with_valid_key
test_health_check_fails_with_invalid_key
test_scrapingbee_response_routed_through_trafilatura
```

### Phase 3 — `WebsiteCrawlSource` (`tests/ingestion/sources/test_website_crawl.py`)

```
test_register_domain_valid_writes_row
test_register_domain_blocked_forum_returns_422
test_register_domain_blocked_subdomain_returns_422
test_register_domain_blocked_social_returns_422
test_register_domain_l1_tier_requires_confirm
test_register_domain_unreachable_raises_unreachable
test_register_domain_invalid_cron_raises_invalid_cron
test_discover_uses_sitemap_when_present
test_discover_falls_back_to_cc_when_no_sitemap
test_discover_falls_back_to_homepage_bfs_when_both_absent
test_discover_dedup_across_sources
test_discover_caps_at_max_pages_per_run
test_pull_delta_uses_etag_short_circuit
test_pull_delta_uses_lastmod_short_circuit
test_pull_full_refetches_regardless_of_headers
test_tier_change_l2_to_l1_requires_confirm
test_stage_upgrade_takes_effect_next_run
```

### Phase 4 — L0 sitemap flow (`tests/flows/test_website_l0_sitemap.py`)

```
test_l0_writes_page_nodes_and_links_to_edges
test_l0_writes_sitemap_belongs_edges
test_l0_writes_mediaasset_and_embeds_edges
test_l0_writes_table_and_table_of_edges
test_l0_idempotent_no_change_no_writes
test_l0_content_hash_change_writes_new_version_bitemporal
test_l0_external_link_creates_externalref_placeholder
test_l0_removed_url_after_two_cycles_closes_page
```

### Phase 5 — L1 entity-tagged flow (`tests/flows/test_website_l1_entity_tagged.py`)

```
test_l1_chunking_overlap_64_token
test_l1_bge_embeddings_dim_384
test_l1_gliner_entity_recall_on_gold_set_geq_0_85
test_l1_rapidfuzz_match_geq_095_auto_links_to_l1_anchor
test_l1_rapidfuzz_match_075_to_095_routes_to_hitl
test_l1_rapidfuzz_match_lt_075_leaves_unlinked
test_l1_referenced_topic_assigned_via_nearest_cluster
test_l1_idempotent_no_change_no_writes
test_l1_content_hash_change_tombstones_chunks_and_writes_new
```

### Phase 6 — L2 full GraphRAG flow (`tests/flows/test_website_l2_full_graphrag.py`)

```
test_l2_produces_clusters_and_summaries_within_budget
test_l2_skips_when_projected_cost_exceeds_remaining_budget
test_l2_partial_change_reclusters_only_affected_chunks
test_l2_idempotent_cache_hit_no_llm_call
test_l2_conflict_routes_to_web_verification_agent
test_l2_l1_clash_emits_conflict_candidate_with_provenance
test_l2_utility_filter_drops_short_pages_from_extract
test_l2_summary_includes_chunk_provenance_ge_99_pct
```

### Phase 7 — Dispatcher (`tests/flows/test_website_crawl_dispatcher.py`)

```
test_dispatcher_picks_due_jobs_and_dispatches
test_dispatcher_skips_paused_domains
test_dispatcher_skips_auto_paused_domains
test_dispatcher_quarantines_failed_domain
test_dispatcher_respects_concurrency_cap_16
test_dispatcher_per_domain_concurrency_cap_4
test_dispatcher_exponential_backoff_after_three_failures
test_dispatcher_auto_pauses_after_five_failures
test_dispatcher_cron_parse_failure_emits_hitl
```

### Phase 8 — FastAPI routes (`tests/web/test_website_crawl_routes.py`)

```
test_get_domains_returns_paginated_list
test_post_domains_blocked_returns_422
test_post_domains_invalid_cron_returns_422
test_post_domains_l1_without_confirm_returns_422
test_post_domains_unreachable_returns_422
test_get_domain_status_returns_recent_runs
test_post_run_now_enqueues_within_5_min
test_post_run_now_force_full_refresh_bypasses_etag
test_patch_cadence_updates_and_audits
test_patch_stage_change_l2_to_l1_keeps_existing_data
test_post_pause_resume_round_trip
test_delete_domain_marks_deleted_does_not_remove_history
test_post_purge_stage_l2_removes_clusters_summaries_claims
test_get_budget_returns_current_spend_and_cap
test_post_budget_reset_unfreezes_capped_domain
test_scrapingbee_health_check_round_trip
```

### Phase 9 — Web UI E2E (`web/e2e/ingest-web.spec.ts`)

Playwright specs listed in `ui-flow.md` § "UI test coverage". Includes axe-core a11y assertion on every page load.

### Phase 10 — MCP outbound (`tests/integrations/test_mcp_crawl_tools.py`)

```
test_register_crawl_domain_via_mcp
test_register_crawl_domain_blocked_via_mcp_returns_structured_error
test_list_crawl_domains_via_mcp
test_get_crawl_status_via_mcp
test_trigger_crawl_now_via_mcp
test_pause_crawl_domain_via_mcp
test_update_crawl_cadence_via_mcp
test_every_tool_writes_audit_log
```

## Gold sets

- **`evals/gold/v1.6a-fixture-domains.jsonl`** — expected page-counts + entity-counts + cluster-counts per fixture domain at each stage. Pass criterion: extracted counts within ±5% of gold.
- **`evals/gold/v1.6a-citation-traceability.jsonl`** — sampled L1 + L2 outputs with required citation pointer. Pass criterion: ≥ 99% of outputs carry a resolvable `references` URL.
- **`evals/gold/v1.6a-clash-nyu-tuition.jsonl`** — single L1-vs-L2 clash regenerated; expected verdict via V1.5c `WebVerificationAgent`. Same gold set used by V1.5c.

## Performance benchmarks (`tests/perf/test_v1_6a_perf.py`)

| Benchmark | Target |
|---|---|
| 1000-URL initial sitemap crawl at concurrency=4 | < 30 min wall time |
| L1 per-page extraction (chunk + embed + GLiNER) | < 200 ms/page on GTX 1080 |
| L2 cluster summary per cluster | < 3 s/cluster with Gemini Flash-Lite (network-bound) |
| robots.txt fetch + parse | < 50 ms cold; < 1 ms warm (cache hit) |
| dispatcher cron tick | < 100 ms with 100 registered domains |

Benchmarks run on CI nightly only (not per-PR). Regression beyond 20% blocks the next release.

## Acceptance gate

All of:

1. Every test in this plan passes.
2. Coverage ≥ 80% on new code paths.
3. Mypy + ruff pass on all new modules.
4. Playwright E2E green.
5. axe-core a11y green.
6. Performance benchmarks within target.
7. Acceptance criteria 1–11 from README.md walked manually.
8. Verification Before Completion report filed at `.agent/reports/v1.6a-slice.md`.

Anything red triggers the AGENTS.md repair-budget rule (max 5 unit cycles / 3 E2E cycles / 2 full-suite cycles before stopping and writing a failure report).
