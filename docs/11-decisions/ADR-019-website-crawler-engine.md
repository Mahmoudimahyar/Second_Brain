---
adr: 019
title: Website crawler engine — crawl4ai with opt-in ScrapingBee fallback
status: accepted
date: 2026-05-27
deciders: Mahyar, Claude
supersedes:
superseded_by:
revision_history:
  - 2026-05-27 v1 — drafted by Claude during V1.6a kick-off research per Mahyar's V1.6-R1 prompt. Pending Mahyar ratification.
  - 2026-05-27 — accepted. Mahyar ratified at V1.6a kickoff. Seed blocklist (FORUM_DOMAINS + SOCIAL_DOMAINS as listed in this ADR) approved. Default per-domain settings ratified: stage L1, OCR off, ScrapingBee off, $5/month budget, concurrency 4 (hard cap 16). robots.txt honored absolutely (no override exposed in UI). UA string env-driven non-empty enforcement at startup. Trafilatura invoked as subprocess (per known-issues.md §1) to keep SecBrain's process boundary free of GPL linkage. V1.6a implementation cleared to proceed under this ADR.
---

# ADR-019 — Website crawler engine

## Context

V1's `docs/04-architecture/system-overview.md` "External integrations" line names a "Crawler (separate system, separate repo)" as a deferred component. V1.5 didn't move it; V1.5c shipped Tavily web-search but only for conflict-resolution lookups, not for owning a corpus of pages.

V1.6a brings the crawler in-house for a constrained scope: **user-declared official-source domains** (school admissions pages, professional-association sites, government health pages, regulatory bodies). Forums and social media are explicitly out — V1 already has SourceAdapter implementations for those (Reddit/SDN), and the V1.6b sub-slice will add Discord/Discourse/Stack Exchange.

We need a crawler that:
1. Runs locally (single-workstation V1 deployment per ADR-009).
2. Outputs Markdown / structured JSON ready for SecBrain's existing extraction pipeline.
3. Speaks sitemap.xml + robots.txt + ETag / Last-Modified.
4. Handles JS-rendered pages without a separate browser farm.
5. Extracts PDFs, spreadsheets, images, and HTML tables inside the same pass.
6. Has crash-recovery for long crawls.
7. Is permissively licensed (engine code distributed inside the SecBrain repo as a dependency only — no AGPL-style copyleft).
8. Has an optional escape hatch for sites that bounce local IPs (Cloudflare, DataDome, PerimeterX).

## Decision

**Primary engine: [`crawl4ai` (unclecode)](https://github.com/unclecode/crawl4ai) v0.8.x, Apache-2.0 with attribution, used as a Python library via `AsyncWebCrawler`.**
**Fallback: opt-in `ScrapingBee` HTTP API behind a per-domain feature flag. Default off. ScrapingBee credentials are user-supplied per ADR-009 plaintext-env policy.**

Specifically:

1. **`src/ingestion/adapters/crawl4ai_web.py`** wraps `AsyncWebCrawler` behind the V1 `SourceAdapter` Protocol. Configuration mirrors crawl4ai's `BrowserConfig` + `CrawlerRunConfig`:
   - `check_robots_txt=True` (non-overridable in V1.6a).
   - Honest UA string: `SecBrain/1.6 (+<CRAWL4AI_CONTACT_EMAIL>)` — env-driven, must be non-empty.
   - URL seeding from `sitemap+cc` (sitemap.xml + Common Crawl fallback per `docs.crawl4ai.com/core/url-seeding/`).
   - `prefetch=True` for 5–10× faster URL discovery on initial crawl.
   - `resume_state=True` + on-state-change callback wired to Prefect for crash recovery.
   - PDF handling via `PDFContentScrapingStrategy`.
   - Adaptive-crawl knob exposed (`max_depth`, `max_pages`) — defaults per-domain budget.

2. **`src/ingestion/sources/website_crawl.py::WebsiteCrawlSource`** implements V1.5a's `DataSource` Protocol. Each registered domain produces one `DataSource` instance with:
   - `connect()` — health-check sitemap + robots.txt, store rotating ETag cache.
   - `discover()` — list URLs from sitemap.xml (+ Common Crawl on first run).
   - `suggest_mapping()` — delegates to the V1.5a `MappingSuggester` adapter for any HTML tables found (BGE-small embeddings + 0.90/0.75 thresholds).
   - `pull(delta=True)` — fetch only URLs with newer `lastmod` or changed ETag/Last-Modified; content-hash dedupe.
   - `tier` — user-declared, default L2.

3. **`src/ingestion/adapters/proxy_scrapingbee.py::ScrapingBeeFallback`** is opt-in per domain. Activates only when crawl4ai returns 403/429/503 ≥ 3 times in a row, OR when `Cf-Mitigated`, `Server: DataDome`, `cf-chl-bypass`, or `_pxhd` cookies appear in responses. When enabled, ScrapingBee is invoked with the same URL set but receives only HTML; SecBrain still does its own extraction (Trafilatura main-content pass) so we don't pay ScrapingBee for processing we already do locally. ScrapingBee call cost is logged to `crawl_cost` SQLite table and counts against the per-domain budget.

4. **Domain blocklist** — hard-coded list of forum / social-media / chat domains that cannot be registered as a website-crawl source. The list lives in `src/ingestion/sources/blocked_domains.py` and is enforced at `register_domain()` call time. V1.6a seed list:
   ```
   FORUM_DOMAINS = {
       "reddit.com", "old.reddit.com", "studentdoctor.net", "sdn.net",
       "stackoverflow.com", "stackexchange.com",
       "discord.com", "discord.gg",
       "discourse.org", "discoursehosting.com",
   }
   SOCIAL_DOMAINS = {
       "twitter.com", "x.com", "instagram.com", "facebook.com",
       "linkedin.com", "tiktok.com", "snapchat.com", "youtube.com",
       "bsky.app", "mastodon.social", "threads.net", "pinterest.com",
   }
   ```
   Attempting to register a blocked domain returns `DOMAIN_BLOCKED` (HTTP 422) with a pointer to the dedicated forum/social path. Subdomains are matched. Override requires an explicit `confirm_block_override=True` flag (intentionally undocumented in the UI — backend escape hatch for V2).

5. **Per-domain budget** — every registered domain carries:
   - `max_pages_per_run` (default 500),
   - `max_pages_per_month` (default 5000),
   - `max_usd_per_month` (default $5 — counts ScrapingBee + LLM extraction stages),
   - `cadence` (cron expression; default `0 6 * * *` — daily 06:00 UTC),
   - `concurrency` (default 4 concurrent fetches; hard-capped at 16).
   Cap-hit pauses the domain and emits a HITL `crawl_cap_hit` item.

6. **MIME / asset handling** — single pass over crawl4ai's discovered URLs routes by content-type:
   - `text/html` → `Crawl4AIAdapter` → `L2HtmlAdapter` extraction (reused from V1) + Trafilatura fallback if `l2_html.py`'s pure-regex stripping under-fills.
   - `application/pdf` → `L1PdfAdapter` (already present in V1) via crawl4ai's `PDFContentScrapingStrategy`.
   - `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`, `text/csv`, `application/vnd.ms-excel` → `L1ExcelAdapter` (already present in V1).
   - `image/*` → stored as `MediaAsset` node; OCR'd via `easyocr` (local, GPU-friendly) only at L1 stage and only when adjacent text is short (< 50 words) — heuristic to avoid running OCR on every banner image.
   - HTML `<table>` blocks → extracted via `pandas.read_html` → `Table` node + `TABLE_OF` edge.

7. **robots.txt** — fetched once per crawl run, cached in `robots_cache` SQLite table (TTL = `max-age` directive or 24h, whichever is shorter). Disallow rules respected absolutely; `Crawl-delay` honored if present (clamped to 0.5–10s). Sitemap directives parsed and added to the URL-seed candidate set.

8. **Failure modes**:
   - sitemap.xml absent → fall back to Common Crawl URL list (crawl4ai supports `cc` source) + homepage BFS at depth 2.
   - robots.txt absent → treated as "all allowed" per RFC 9309 default; logged.
   - All 3 ScrapingBee retries fail → emit `crawl_blocked` HITL item with the URL + last response code + suggestion text.
   - Page > 50 MB → skip with `oversized_page` audit row.
   - PDF > 100 MB → skip with same.

9. **Provenance** — every fetched URL writes a `crawl_fetch_log` row with `url`, `status_code`, `etag`, `last_modified`, `content_hash`, `bytes`, `fetched_at`, `crawl_run_id`, `via_proxy` (bool), `cost_usd`. Every resulting graph node carries `references[]` entries with the URL + fetch timestamp.

10. **Cache** — content-addressable on `hash(url + etag + content_hash)`. Cache hit replays the prior extraction; no re-fetch unless `delta=False` (full refresh) is requested.

## Consequences

**Positive:**
- crawl4ai's local-first + Apache-2.0 + Markdown-first design fits SecBrain's posture (single-workstation, internal-only V1). No SaaS dependency for the default path.
- crawl4ai already implements the four hardest pieces (anti-bot tiering, sitemap/Common-Crawl seeding, deep-crawl crash recovery, PDF extraction). We don't write any of that ourselves.
- Reusing V1's `L2HtmlAdapter`, `L1PdfAdapter`, `L1ExcelAdapter` means crawled content lands in the same canonical record shape as V1's manual uploads — Pass 1/2/3/4/5 work unchanged.
- ScrapingBee fallback is optional; users who only crawl ADEA / ADA / school pages never pay for it. Users with a Cloudflare-protected target pay only for failing-locally pages.
- Domain blocklist + budget + robots.txt make this a polite crawler by default; the user can't accidentally hammer a forum or burn through a budget.
- crawl4ai's adaptive-crawl mode (knows when enough information is gathered) cuts the L2 GraphRAG token bill substantially vs naive deep-crawling.

**Negative:**
- crawl4ai is one project, one maintainer's repo. If it goes unmaintained, we'd need to swap. Mitigated by the `SourceAdapter` Protocol — swapping engines is mechanical.
- crawl4ai requires Playwright Chromium installed (`crawl4ai-setup` post-install step). Adds ~500 MB to the workstation image. Acceptable.
- The opt-in ScrapingBee path requires a paid plan ($49/mo entry tier or pay-as-you-go). User-controlled.
- We're now running an outbound crawler from the user's workstation — different threat model than V1's "data lands via manual dumps". The blocklist + budget + UA-honesty + robots.txt compliance are mitigations, but operational discipline matters more than before.
- The two extraction paths (V1 `L2HtmlAdapter` regex strip vs Trafilatura fallback) duplicate work — kept simple in V1.6a; one is the V1-default and the other is the better-on-non-articles fallback. May be consolidated in V1.7.

**Neutral:**
- We picked crawl4ai over Firecrawl (SaaS-first; cost spike for our volume), Scrapy (no LLM-Markdown out of box; would need to wire Trafilatura ourselves anyway), and fastCRW (faster but very new — not yet battle-tested at 2026-05-27). Re-evaluate in V2 when fastCRW's stability profile is known.
- ScrapingBee picked over Bright Data + Zyte because Bright Data is a heavy contract ($0.75/1000 req with min plan), Zyte is more expensive per-request, and ScrapingBee has the cleanest pay-as-you-go + simplest API + sufficient anti-bot for the V1 target sites. If a registered domain needs Bright-Data-grade anti-bot, we re-open this ADR.

## Alternatives considered (and rejected)

**Firecrawl** — SaaS-first. Same Markdown output, similar feature surface. Rejected because (a) ongoing per-page cost, (b) SecBrain's V1 deployment is single-workstation local, (c) we already pay Tavily for V1.5c — adding a second SaaS isn't justified by capability gain.

**Scrapy + Trafilatura DIY** — Most flexible. Rejected because crawl4ai already wraps roughly the same composition with better-defaults for LLM ingestion (Markdown output, anti-bot tiering, adaptive depth). DIY would cost ~2 weeks of work to match.

**fastCRW** — 5× faster than crawl4ai, 75× less RAM per published benchmark. Rejected for V1.6a because it's < 1 year old (2026-05), no PDF extraction yet, no anti-bot tiering. Strong V2 re-evaluation candidate.

**Apify open-source (Crawlee)** — Excellent production crawler. Rejected because TypeScript-first; integration with our Python stack adds friction. Re-evaluate if we ever add a Node service.

**Bright Data Web Scraper API as primary** — Bypasses crawl4ai entirely. Rejected because ~$0.75/1000 req with min monthly commit; we'd pay even when local crawling works.

**Zyte Smart Proxy Manager as primary** — Similar reasoning to Bright Data; better suited as a paid escape hatch on specific protected sites.

**ScrapingBee as primary** — Considered but rejected for the same SaaS-cost reasoning as Firecrawl. Kept as opt-in fallback only.

## Related docs
- `docs/05-features/v1.6-master-brief.md`
- `docs/05-features/05-slice-v1.6-website-crawler/`
- `docs/11-decisions/ADR-009-mcp-deployments-and-side-store.md` (deployment posture)
- `docs/11-decisions/ADR-014-external-db-tiering.md` (tier-declaration pattern reused here)
- `docs/04-architecture/system-overview.md` (§14 to be added)
- `docs/04-architecture/tech-stack.md`
- `.env.example` (entries added per master brief)

## Related code
- `src/ingestion/adapters/crawl4ai_web.py` (new)
- `src/ingestion/adapters/proxy_scrapingbee.py` (new, optional)
- `src/ingestion/sources/website_crawl.py` (new)
- `src/ingestion/sources/blocked_domains.py` (new)
- `src/ingestion/adapters/l2_html.py` (existing — reused)
- `src/ingestion/adapters/l1_pdf.py` (existing — reused)
- `src/ingestion/adapters/l1_excel.py` (existing — reused)
- `flows/website_crawl_dispatcher.py` (new — Prefect cron flow)
