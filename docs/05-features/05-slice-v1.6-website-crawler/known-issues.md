# Known Issues — V1.6a Website-Crawl Ingestion

> Open at packet creation time (2026-05-27). Move to `docs/00-bootstrap/gap-register.md` if any of these block implementation.

## High-priority (likely to bite during implementation)

1. **crawl4ai Trafilatura license interaction.** Trafilatura is GPL-3.0+. If we link it in-process, our distribution may pick up GPL terms for the parts of SecBrain that touch it. Mitigation: invoke Trafilatura as a subprocess (CLI mode) rather than as an imported Python module. Alternative: swap to `readability-lxml` (Apache-2.0). Resolution required before Phase 1 commit. Track in `docs/00-bootstrap/unresolved-questions.md`.

2. **L2 partial-change cluster recomputation is heuristic.** ADR-020 specifies "re-cluster only chunks within 2 hops of changed chunks". On large rewrite events (e.g., a domain rewrites half its pages in one run), this can drift cluster boundaries vs a full recluster. We accept the trade-off; if drift exceeds 10% per V1.6a-perf-clustering eval, we add a "force full recluster" admin action. Tracked.

3. **Common Crawl fallback for sitemap-less domains** can return stale URLs (Common Crawl indexes lag by weeks-to-months). For a brand-new domain without sitemap.xml, the first crawl may return zero useful URLs. Mitigation: homepage BFS depth=2 as the third fallback. Documented in FR-1.6a-1.5.

4. **Pascal-era GPU OCR throughput.** `easyocr` on a GTX 1080 does ~1 page/s. If a domain has many scanned PDFs and OCR is enabled, a single run can wall-clock past NFR-1.6a-1's 30-min budget. Mitigation: OCR runs asynchronously (separate Prefect flow) and doesn't block the rest of L1. The PDF is still ingested at L0 + L1 sans OCR text; OCR fills in on the next pass.

5. **ScrapingBee responses are decoded HTML, not rendered Markdown.** crawl4ai's local path returns Markdown directly; the proxy path returns raw HTML and we then re-extract via Trafilatura locally. This means the two paths can produce slightly different Markdown for the same URL. Mitigation: extract always uses the same Trafilatura settings; verified by a `tests/ingestion/adapters/test_crawl_path_vs_proxy_parity.py` test.

## Medium-priority

6. **`pages_index` can grow large** on big domains (e.g., 100k pages). Query cost on the domain detail page could degrade. Mitigation: indexes per `data.md` § "Index recommendations"; if the list view degrades past 100 ms p95, we paginate further.

7. **`audit_log` write amplification.** Every fetch + every robots-disallow-hit + every cache-hit + every ScrapingBee call writes a row. On a 5000-page run, that's ~10k rows. SQLite is fine with that, but the `audit_log` viewer in V1.5b may need a date-range default of "last 24 hours" to avoid loading every-row history.

8. **Per-domain budget projection can under-estimate.** We multiply the recent average page cost by 1.2 safety margin. Long-tail expensive pages (very long body → bigger summary → more Gemini calls) can blow past projection mid-run. We catch this with a hard stop at run-time once `spent_month >= max_usd_per_month`, which fires `crawl_cap_hit` HITL.

9. **No deduplication across domains.** If two domains both index the same external PDF (e.g., a school's tuition PDF mirrored on both `school.edu` and `adea.org`), we'll have two `MediaAsset` nodes pointing to two cached copies. Acceptable for V1.6a; cross-domain dedup is V1.7.

10. **Sitemap.xml `<changefreq>` ignored.** Per 2026 best-practice, most modern crawlers (Google included) ignore `<changefreq>`. We follow suit and rely on `<lastmod>` + ETag + content-hash.

## Low-priority

11. **No GraphQL / JSON-LD structured-data extraction in V1.6a.** Many official sites publish schema.org markup; we don't parse it specially yet. V1.7 candidate.

12. **No `<noindex>` meta-tag respect.** Robots.txt is enough for V1.6a; per-page `<meta name="robots" content="noindex">` is V1.7.

13. **No PDF form-field extraction.** PDFs are extracted as text only. Form fields are V1.7.

14. **No video / audio transcription.** `MediaAsset` nodes carry URL + alt + mime + bytes only; no audio→text. V1.7.

15. **No JS-rendered SPA support beyond crawl4ai's default Playwright Chromium**. Heavy SPAs (e.g., framework-routed dashboards behind login) may not render properly; user can opt into `enable_scrapingbee_fallback` which renders with a different headless stack. Beyond that, V2.

## Carry-over from V1 / V1.5 still relevant

16. **HNSW rebuild nightly** (V1 known issue) — applies to the L1 chunk-embedding index as it does to all V1 vector data.
17. **LiteLLM SDK-mode fallback chain** must include OpenAI as a layer (V1 ADR-011) — we don't change that; L2 cluster summaries get the same fallback chain.
18. **Langfuse cost-attribution dashboards** need a new tag `corpus=website-crawl:<domain>` so per-domain L2 spend rolls up correctly. Add at Phase 6.

## Resolved before packet creation (for the record)

- ~Should crawl4ai be a hard dep or extra?~ → Hard dep. The slice exists for it.
- ~ScrapingBee vs Bright Data?~ → ScrapingBee (ADR-019; cleanest pay-as-you-go).
- ~LightRAG vs Microsoft GraphRAG?~ → LightRAG-style staged (ADR-020).
- ~Per-domain vs per-page staging?~ → Per-domain (ADR-020).
- ~Forums in crawl path?~ → No (blocklist + V1.6b).
- ~Social media in crawl path?~ → No (permanent blocklist).
