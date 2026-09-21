# Requirements — V1.6a

> Testable; mapping to test cases in `test-plan.md`. Builds on V1 + V1.5a + V1.5b + V1.5c.

## Functional requirements

### FR-1.6a-1 — `WebsiteCrawlSource` (DataSource implementation)

- **FR-1.6a-1.1** `src/ingestion/sources/website_crawl.py::WebsiteCrawlSource` implements the V1.5a `DataSource` Protocol. Required methods: `connect`, `disconnect`, `health_check`, `discover`, `suggest_mapping`, `pull(delta: bool = True)`, `tier`, `id`.
- **FR-1.6a-1.2** Domain registration requires: `domain` (FQDN string), `tier` (one of `L1`/`L2`, default `L2`, `L1` requires `confirm_l1_immutable=True`), `cadence` (cron string; default `0 6 * * *`), `stage` (`L0` / `L1` / `L2`; default `L1`), `max_pages_per_run` (default 500), `max_pages_per_month` (default 5000), `max_usd_per_month` (default 5.00), `concurrency` (default 4, max 16), `enable_ocr` (default False), `enable_scrapingbee_fallback` (default False).
- **FR-1.6a-1.3** `register_domain` validates the FQDN against `blocked_domains.FORUM_DOMAINS` ∪ `blocked_domains.SOCIAL_DOMAINS`. A match raises `StructuredError(ErrorCode.DOMAIN_BLOCKED)` with a `suggestion` field pointing to the V1 Reddit adapter (for Reddit-family) or "no path — out of scope" (for social media).
- **FR-1.6a-1.4** `connect()` fetches `https://<domain>/robots.txt` once and caches it in `robots_cache` (TTL = `max-age` directive or 24h). On 404, treats domain as "all allowed" per RFC 9309. On other failure, raises `StructuredError(ErrorCode.UNREACHABLE_DOMAIN)`.
- **FR-1.6a-1.5** `discover()` returns the URL set by combining: (a) `robots.txt`'s `Sitemap:` directives → fetch sitemap.xml + sub-sitemaps recursively; (b) crawl4ai's `cc` source for Common-Crawl-known URLs if sitemap is absent; (c) homepage BFS depth=2 only if both (a) and (b) yield < 10 URLs. Returns deduplicated list capped at `max_pages_per_run`.
- **FR-1.6a-1.6** `pull(delta=True)` fetches only URLs whose `lastmod` (from sitemap.xml) is newer than `last_crawled_at` for that URL, OR whose previous `ETag` / `Last-Modified` headers don't match the current `HEAD` response. Falls back to GET-with-content-hash if HEAD is not supported.
- **FR-1.6a-1.7** `pull(delta=False)` re-fetches every URL regardless of headers. Used only on manual "Force full refresh" UI action.
- **FR-1.6a-1.8** Tier upgrade L2 → L1 requires `confirm_l1_immutable=True`. L1 → L2 is freely allowed (downgrade). Audit-log each tier change.
- **FR-1.6a-1.9** All operations write `audit_log` rows with `kind` ∈ {`domain_registered`, `domain_paused`, `domain_resumed`, `domain_deleted`, `cadence_changed`, `stage_changed`, `tier_changed`, `crawl_started`, `crawl_succeeded`, `crawl_failed`, `crawl_cap_hit`, `robots_disallow`, `scrapingbee_invoked`}.

### FR-1.6a-2 — `Crawl4AIAdapter` (SourceAdapter implementation)

- **FR-1.6a-2.1** `src/ingestion/adapters/crawl4ai_web.py::Crawl4AIAdapter` wraps `crawl4ai.AsyncWebCrawler` behind the V1 `SourceAdapter` Protocol (`source_tier`, `parse(payload_paths) -> IngestResult`).
- **FR-1.6a-2.2** `BrowserConfig` defaults: headless Chromium, viewport 1280×720, user-agent from `CRAWL4AI_USER_AGENT` env (required non-empty; format `SecBrain/1.6 (+<email>)`).
- **FR-1.6a-2.3** `CrawlerRunConfig` defaults: `check_robots_txt=True`, `prefetch=True`, `resume_state=True`, `max_depth=2` (page-graph depth from a sitemap URL), per-page hard timeout 30s, retry 3 with exponential backoff (1s/2s/4s).
- **FR-1.6a-2.4** Content-type dispatch: `text/html` → `L2HtmlAdapter` + Trafilatura main-content fallback; `application/pdf` → `L1PdfAdapter`; `application/vnd.*spreadsheet`/`text/csv` → `L1ExcelAdapter`; `image/*` → store as `MediaAsset` + optional `easyocr` OCR if `enable_ocr=True` AND adjacent body text < 50 words.
- **FR-1.6a-2.5** HTML `<table>` extraction via `pandas.read_html` → one `Table` node per table; cells stored as JSON `[[row0col0, row0col1, ...], ...]`; `TABLE_OF` edge from parent `Page`.
- **FR-1.6a-2.6** Adaptive depth: pass crawl4ai's adaptive-information-foraging knob via `CrawlerRunConfig.adaptive=True` when `stage=L2` (L2 cares about content saturation); off at L0 (sitemap-only).
- **FR-1.6a-2.7** On 403 / 429 / 503 ≥ 3 consecutive retries OR detection of DataDome / PerimeterX / Cloudflare-challenge markers (`Cf-Mitigated`, `Server: DataDome`, `cf-chl-bypass`, `_pxhd` cookie), if `enable_scrapingbee_fallback=True` route the URL to `ScrapingBeeFallback`; else mark URL as `blocked` and emit `crawl_blocked` HITL item.
- **FR-1.6a-2.8** Per-page payload stored under `data/web_cache/<domain>/<sha256-16-of-url>.<ext>` with content-hash sidecar `<sha256-16>.meta.json` containing `url`, `etag`, `last_modified`, `content_hash`, `bytes`, `mime`, `fetched_at`.
- **FR-1.6a-2.9** Cache hit semantics: if `content_hash` unchanged AND ETag / Last-Modified unchanged AND `mime` unchanged → adapter returns the cached normalized record without re-running extraction.
- **FR-1.6a-2.10** `parse()` aggregates all per-page normalized records into one `IngestResult` per crawl run.

### FR-1.6a-3 — `ScrapingBeeFallback` (opt-in proxy adapter)

- **FR-1.6a-3.1** `src/ingestion/adapters/proxy_scrapingbee.py::ScrapingBeeFallback` wraps the ScrapingBee API behind a thin async client. Reads `SCRAPINGBEE_API_KEY` from `.env`.
- **FR-1.6a-3.2** Domain opts in via `enable_scrapingbee_fallback=True`. Domains without opt-in never reach ScrapingBee.
- **FR-1.6a-3.3** Invocation triggers (FR-1.6a-2.7) only. ScrapingBee is **never** the primary path.
- **FR-1.6a-3.4** Calls `GET https://app.scrapingbee.com/api/v1/?api_key=<key>&url=<encoded>&render_js=true&premium_proxy=true&country_code=us` by default; flag overrides exposed in `BrowserConfig`.
- **FR-1.6a-3.5** Returns raw HTML. SecBrain still runs its own extraction locally (Trafilatura → `L2HtmlAdapter`) — ScrapingBee is treated as an opaque HTML provider.
- **FR-1.6a-3.6** Per-call cost logged to `crawl_cost` table; counts against the per-domain `max_usd_per_month` budget.
- **FR-1.6a-3.7** Health-check (`POST /api/v1/ingest/web/settings/scrapingbee/health`) runs a low-cost test request (`render_js=false`).
- **FR-1.6a-3.8** No user PII (chat history, prompts, identity) is forwarded to ScrapingBee. Only the URL + UA + (optional) referer is sent.

### FR-1.6a-4 — Staged graph ingestion (L0 / L1 / L2)

- **FR-1.6a-4.1** `flows/website_l0_sitemap.py` runs unconditionally after each crawl. Writes `Page`, `Sitemap`, `MediaAsset`, `Table` nodes + `LINKS_TO`, `BELONGS_TO_SITEMAP`, `EMBEDS`, `TABLE_OF` edges. Deterministic, no LLM.
- **FR-1.6a-4.2** `flows/website_l1_entity_tagged.py` runs only when `domain.stage >= L1`. Runs Trafilatura main-content extraction + 512-token chunking with 64-token overlap + BGE-small embedding + GLiNER2 entity tagging + rapidfuzz canonical-match against existing V1 L1 anchors. Writes `Entity` nodes + `MENTIONS`, `REFERENCES_TOPIC` edges. No external API.
- **FR-1.6a-4.3** `flows/website_l2_full_graphrag.py` runs only when `domain.stage = L2` AND budget remains. Runs signed-graph clustering on chunks + per-cluster Gemini Flash-Lite summary (one call per cluster) + selective Pass-4 sentiment / claim / relationship extraction on chunks passing the utility filter. Writes `Cluster`, `Summary`, `Claim` nodes + `SUMMARIZES`, `SUPPORTS`, `CONTRADICTS` edges.
- **FR-1.6a-4.4** All three stages are idempotent. Re-running on an unchanged corpus is a no-op via the content-addressable extraction cache (V1 invariant preserved).
- **FR-1.6a-4.5** Partial-change recomputation at L2: only chunks within 2 hops of changed chunks in the embedding graph trigger re-clustering / re-summarization. Documented as known issue (clustering precision can drift with very-large rewrite events).
- **FR-1.6a-4.6** Stage downgrade does **not** delete already-written rows. Explicit `purge_stage(level)` API + UI action does.
- **FR-1.6a-4.7** Budget projection before L2 run: `projected_cost = avg_cost_per_recent_l2_page × queued_pages × 1.2`. If `projected_cost + spent_month > max_usd_per_month`, fire L0 + L1 only; emit `budget_capped` HITL item.

### FR-1.6a-5 — Scheduler (Prefect)

- **FR-1.6a-5.1** `flows/website_crawl_dispatcher.py` runs as a Prefect cron flow every 5 minutes. Queries `crawl_jobs` for due rows, marks them `running`, dispatches one Prefect task per due domain. Failed tasks don't block other domains (FR-NFR-1.6a-5).
- **FR-1.6a-5.2** Cadence: per-domain cron string; default `0 6 * * *`. Validate via `croniter` at registration time.
- **FR-1.6a-5.3** Concurrency budget: max 16 domains running simultaneously across the workstation. Per-domain max 16 page-fetches in flight (default 4).
- **FR-1.6a-5.4** `trigger_crawl_now(domain)` API + UI action enqueues a `crawl_jobs` row with `scheduled_at = now()`; dispatcher picks it up within 5 minutes.
- **FR-1.6a-5.5** `pause_crawl_domain(domain)` sets `status='paused'`; resume with `resume_crawl_domain(domain)`.
- **FR-1.6a-5.6** Per-run failure backoff: 3 failed runs in a row → exponential pause (1h, 4h, 24h); 5 failures → auto-pause + HITL `crawl_chronic_failure` item.

### FR-1.6a-6 — Web UI `/ingest/web`

- **FR-1.6a-6.1** `web/src/app/ingest/web/page.tsx` — list of registered domains with: domain, tier, stage, cadence (humanized), last-crawled-at, next-run-at, status pill, budget-used bar, action buttons (Run now, Pause, Edit, Delete).
- **FR-1.6a-6.2** `web/src/app/ingest/web/register/page.tsx` — wizard:
  1. Enter URL → backend validates: FQDN parseable, not in blocklist, reachable, robots.txt fetched OK.
  2. Pick tier (L1 / L2 with L1 gating per FR-1.6a-1.8).
  3. Pick stage (L0 / L1 / L2 with cost preview for L2).
  4. Pick cadence (preset hourly / daily 06:00 / weekly Mon 06:00 / monthly 1st 06:00 / custom cron with `croniter` validator).
  5. Configure budget (pages + USD + concurrency + OCR + ScrapingBee opt-in).
  6. Review + confirm → POST `/api/v1/ingest/web/domains`.
- **FR-1.6a-6.3** `web/src/app/ingest/web/[domain]/page.tsx` — domain detail. Shows: settings summary, recent run history table (last 50), `crawl_cost` chart (last 30 days), page count by mime, list of top entities extracted at L1, list of clusters at L2.
- **FR-1.6a-6.4** `web/src/app/ingest/web/[domain]/page/[id]/page.tsx` — single-page detail. Shows: rendered Markdown content, bitemporal version timeline, `LINKS_TO` targets, mentioned entities, source URL with "Open in browser" link.
- **FR-1.6a-6.5** Pagination on history table (50/page). Filter on status.
- **FR-1.6a-6.6** Toast notifications on successful registration / pause / resume / run trigger. Confirmation modal on Delete and on Force-full-refresh.
- **FR-1.6a-6.7** Empty states for: no domains registered, domain with zero runs, domain at L0 with no L1 entities yet (CTA "Upgrade to L1").

### FR-1.6a-7 — MCP outbound surface

- **FR-1.6a-7.1** `mcp__secbrain__register_crawl_domain(domain, tier, stage, cadence, max_pages_per_run, max_pages_per_month, max_usd_per_month, concurrency, enable_ocr, enable_scrapingbee_fallback, confirm_l1_immutable)`.
- **FR-1.6a-7.2** `mcp__secbrain__list_crawl_domains() -> list[CrawlDomain]`.
- **FR-1.6a-7.3** `mcp__secbrain__get_crawl_status(domain) -> CrawlStatus`.
- **FR-1.6a-7.4** `mcp__secbrain__trigger_crawl_now(domain) -> CrawlJob`.
- **FR-1.6a-7.5** `mcp__secbrain__pause_crawl_domain(domain) -> CrawlDomain`.
- **FR-1.6a-7.6** `mcp__secbrain__update_crawl_cadence(domain, cadence) -> CrawlDomain`.
- **FR-1.6a-7.7** Every MCP tool writes an `audit_log` row with the calling actor.

## Non-functional requirements

- **NFR-1.6a-1** Latency: sitemap-only first crawl on ≤ 1000 URLs completes < 30 min at default concurrency=4. (NFR-1.6a-1 in README.)
- **NFR-1.6a-2** Cost: default per-domain budget $5/month enforced; alarm at 80%; hard stop at 100%. (NFR-1.6a-2.)
- **NFR-1.6a-3** Test coverage ≥ 80% line on the new code paths. (NFR-1.6a-3.)
- **NFR-1.6a-4** Citation traceability ≥ 99% across web-sourced retrieval. (NFR-1.6a-4.)
- **NFR-1.6a-5** Single-domain failure quarantine. (NFR-1.6a-5.)
- **NFR-1.6a-6** Politeness defaults — robots.txt + Crawl-delay + honest UA + concurrency ≤ 4 default / ≤ 16 hard. (NFR-1.6a-6.)
- **NFR-1.6a-7** Storage cap: 5 GB local cache LRU. (NFR-1.6a-7.)
- **NFR-1.6a-8** No PII leakage to ScrapingBee. (NFR-1.6a-8.)
- **NFR-1.6a-9** Crash recovery: a workstation reboot during a crawl resumes from `resume_state` checkpoint within 60 s of Prefect worker restart.
- **NFR-1.6a-10** Observability: every fetch + extraction stage emits a structlog event + Langfuse cost row (L2 only) + Prefect task state.

## Out of scope (V1.6a)

- Per-page user-selectable stage (per-domain only in V1.6a).
- RSS / Atom feed ingestion (V1.7).
- Browser-based SSO / login flows (V2).
- Automatic suggested-domain recommendations (V1.7).
- Multi-tenant access control (V2).
- Cross-workstation distributed crawling (V2).
- Push-notification of new pages (V2 via WebSub or polling-shorter-cadence in V1.6a).
- Forum types — handled by V1 (Reddit/SDN) and V1.6b (Discord/Discourse/StackEx).
