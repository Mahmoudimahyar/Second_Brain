# Context — V1.6a Website-Crawl Ingestion

> Lightweight pointer file so future agents don't re-derive the dependency map.

## What this slice is

V1.6a turns the V1's deferred "Crawler (separate system, separate repo)" line into a built-in scheduled multi-domain website-crawl ingestion. Mahyar requested it on 2026-05-27 (V1.6-R1 prompt). It opens the V1.6 batch of work that also covers V1.6b (forum types) and V1.6c (Slack / Notion) in later briefs.

## Read these first

1. **`docs/05-features/v1.6-master-brief.md`** — sub-slice sequencing + locked scope + architecture deltas.
2. **`docs/05-features/05-slice-v1.6-website-crawler/README.md`** — this packet's intent + acceptance criteria.
3. **`docs/11-decisions/ADR-019-website-crawler-engine.md`** — engine pick (crawl4ai + opt-in ScrapingBee).
4. **`docs/11-decisions/ADR-020-staged-website-graph.md`** — L0 / L1 / L2 stage definitions.
5. **`docs/05-features/05-slice-v1.6-website-crawler/requirements.md`** — testable FR + NFR.
6. **`docs/05-features/05-slice-v1.6-website-crawler/data.md`** — SQLite + graph schema additions.
7. **`docs/05-features/05-slice-v1.6-website-crawler/state-machine.md`** — domain + crawl-job + per-page lifecycles.

## Prior-art pointers (reused, not re-built)

| Reused from | What we reuse | Where |
|---|---|---|
| V1 | `L2HtmlAdapter` regex strip + canonical-url extraction | `src/ingestion/adapters/l2_html.py` |
| V1 | `L1PdfAdapter` | `src/ingestion/adapters/l1_pdf.py` |
| V1 | `L1ExcelAdapter` | `src/ingestion/adapters/l1_excel.py` |
| V1 | Pass 1 structural-graph writers | `src/extraction/pass1_structural.py` |
| V1 | Pass 3 BGE-small chunking + signed-graph clustering | `src/embeddings/`, `src/extraction/pass3_clustering.py` |
| V1 | Pass 4 sentiment / claim / utility filter | `src/extraction/pass4_runners.py`, `utility_filter.py` |
| V1 | Conflict resolver 6-step chain | `src/conflict/` |
| V1 | Content-addressable extraction cache | `src/extraction/cache.py` |
| V1 | Bitemporal edge schema | per ADR-005 |
| V1.5a | `DataSource` Protocol + tier declaration + MappingSuggester | `src/ingestion/sources/base.py`, `src/extraction/mapping_suggester.py` |
| V1.5b | HITL queue + `/hitl/escalated` UI | `src/hitl/`, `web/src/app/hitl/` |
| V1.5b | `IngestionLayout`, `CronPicker`, `AuditTimeline` UI components | `web/src/components/` |
| V1.5c | `WebVerificationAgent` for L2 conflict resolution | `src/conflict/web_verify.py` |
| V1.5c | Tavily provider | `src/conflict/providers/tavily.py` |
| V1.5c | Model gateway routing (Gemini Flash-Lite / Haiku 4.5) | `src/gateway/` |
| V1.5c | Langfuse cost telemetry | `src/observability/` |

## New external dependencies (V1.6a)

Added to `pyproject.toml` (versions pinned at adoption time):

| Dep | Why | License | Optional? |
|---|---|---|---|
| `crawl4ai>=0.8,<0.9` | Primary crawl engine | Apache-2.0 (attribution required) | No |
| `playwright` (Chromium only) | Backs crawl4ai's JS rendering | Apache-2.0 | No (installed via `crawl4ai-setup`) |
| `trafilatura>=2.0,<3.0` | Main-content extraction fallback | GPL-3.0+ → **see ADR-019 license note**; used as a separate process subcall to avoid linking concerns OR replace with `readability-lxml` if license concern surfaces | No |
| `pikepdf>=8` | PDF metadata + repair | MPL-2.0 | No |
| `tabula-py>=2.9` | Robust HTML/PDF table extraction | MIT | No |
| `pandas>=2.2` | Already present; reused for `read_html` | BSD-3-Clause | — |
| `easyocr>=1.7` | OCR for images when enabled | Apache-2.0 | Yes (extras: `secbrain[ocr]`) |
| `croniter>=2` | Cadence parsing + next-run preview | MIT | No |
| `scrapingbee>=1.2` | Opt-in proxy fallback | MIT | Yes (extras: `secbrain[proxy]`) |
| `httpx-mock`, `respx` | Testing | BSD-3-Clause | dev only |

## .env additions (already in `data.md` § ".env additions")

`CRAWL4AI_USER_AGENT`, `CRAWL4AI_CONTACT_EMAIL`, `CRAWL4AI_MAX_CONCURRENCY`, `SCRAPINGBEE_API_KEY` (optional), `WEBSITE_CRAWL_DEFAULT_BUDGET_USD`, `WEBSITE_CRAWL_DEFAULT_BUDGET_PAGES`, `WEB_CACHE_DIR`, `WEB_CACHE_MAX_BYTES`. Documented in `.env.example`.

## Boundary checklist (for the agent picking this up)

Before writing any code, verify:

- [ ] V1.5c Verification Before Completion report exists at `.agent/reports/v1.5c-slice.md`. If not, stop and write to `docs/00-bootstrap/unresolved-questions.md` instead.
- [ ] ADR-019 and ADR-020 carry `status: accepted` (currently `proposed`). If still `proposed`, wait for Mahyar's ratification.
- [ ] `.env` has `CRAWL4AI_USER_AGENT` set to a non-empty honest string. Without it the adapter must refuse to start.
- [ ] The fixture domains in `tests/fixtures/web/` are present (they ship with this packet via a one-time scaffolding script).
- [ ] `data/web_cache/` exists and is writable; cap from `WEB_CACHE_MAX_BYTES` enforced via LRU on startup.
- [ ] `blocked_domains.py` has been reviewed by Mahyar — additions / removals are a security-relevant action per AGENTS.md "Human approval required".

## Out-of-scope confirmations

- Forums (Reddit / SDN / Discord / Discourse / Stack Exchange) are handled separately. Reddit + SDN have V1 adapters; Discord / Discourse / Stack Exchange come in V1.6b. The blocklist enforces this.
- Social media (Twitter/X, Instagram, LinkedIn, TikTok, Facebook, Bluesky, Mastodon, Threads, YouTube, Pinterest) are blocklisted with no V1.x roadmap path.
- Slack / Notion connectors are V1.6c.
- Multi-tenant + auth + cloud deploy are V2.
- Per-page stage selection (instead of per-domain) is V1.7.

## Why this is a slice and not just a new adapter

The naïve framing would be "add a `WebsiteCrawlAdapter`". That misses three things:

1. **Cadence + budget**: a crawl is a recurring event, not a one-shot dump. We need a scheduler row, dispatcher flow, and budget tracking.
2. **Staged ingestion**: the user wants cost control via L0/L1/L2 gating per ADR-020. That's a state machine, not just an adapter.
3. **UI**: this is the first ingestion path that doesn't make sense as a CLI-only feature — users want to see "what's getting crawled, when, for how much". So we need pages.

The slice format (this packet) is the same one V1.5 used for each sub-slice. Don't shortcut it.
