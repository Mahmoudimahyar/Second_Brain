# Changelog — V1.6a Website-Crawl Ingestion

## 2026-05-27 — packet seeded

- Drafted by Claude during V1.6-R1 kick-off research, in response to Mahyar's prompt requesting a website-crawl ingestion patch.
- Created `docs/05-features/v1.6-master-brief.md` + this packet (`README`, `requirements`, `plan`, `data`, `api`, `state-machine`, `ui-flow`, `test-plan`, `context`, `decisions`, `known-issues`, this file).
- Drafted `docs/11-decisions/ADR-019-website-crawler-engine.md` (crawl4ai + opt-in ScrapingBee).
- Drafted `docs/11-decisions/ADR-020-staged-website-graph.md` (L0 / L1 / L2 staging).
- Status across both ADRs: `proposed`. Awaiting Mahyar ratification at V1.6a kickoff.

## 2026-06-11 — V1.6a slice COMPLETED (Validated on real data)

- `flows/website_crawl_worker.py` landed: `crawl_domain_once` + `make_worker` (robots-sitemap discovery → BFS fallback → Crawl4AI fetch → L0 → L1 entity tagging → optional L2 + bookkeeping).
- CLI `src/cli.py crawl register|run|tick` wired.
- UI `src/web/routes/website_crawl.py` `run_now` → BackgroundTasks → real dispatcher tick wired (was a silent no-op).
- 5 crawler bugs fixed: Entity stub clobber; O(N·P) sitemap scan; PDF/XLSX empty bodies; `?status=deleted` filter; `CanonicalIndex.reload` crash on fresh DB.
- Smoke on natmatch.com sandbox: 23 Page + 38 Chunk + 74 MediaAsset + 47 ExternalRef nodes, 345 LINKS_TO edges, 0 errors; re-run idempotent.
- Full L1 batch: 10 registry domains crawled (8 local + ada.org/adea.org on EC2 VM), merged + compacted. Final: **4,558,352 nodes / 13,103,287 edges / 6,866 Page / 13,570 Chunk**.
- Deferred: cdac-cadc.ca + HRSA (honest-UA 403), programs.adea.org (JS SPA).

## Pending (this slice will update on each implementation phase)

| Phase | Expected entry shape |
|---|---|
| Phase 1 | "`Crawl4AIAdapter` + robots.txt + cache landed. Coverage X%. NFRs Y/Z pass." |
| Phase 2 | "`ScrapingBeeFallback` opt-in shipped. Disabled by default. Cost logging verified." |
| Phase 3 | "`WebsiteCrawlSource` + blocklist + SQLite migrations landed." |
| Phase 4 | "L0 sitemap flow landed; 3 fixture domains complete L0 in <fixture-perf>." |
| Phase 5 | "L1 entity-tagged flow landed; NYU canonical-match auto-link verified." |
| Phase 6 | "L2 full GraphRAG flow landed; first L2 run on fixture domain came in at $<cost>." |
| Phase 7 | "Dispatcher landed; 3 seed domains crawl on schedule." |
| Phase 8 | "FastAPI routes + Zod codegen + audit shipped." |
| Phase 9 | "Web UI shipped; Playwright + axe green." |
| Phase 10 | "MCP outbound surface shipped." |
| Phase 11 | "Verification Before Completion report filed at `.agent/reports/v1.6a-slice.md`. Slice gate passed." |
