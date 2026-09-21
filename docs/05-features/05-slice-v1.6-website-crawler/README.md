---
type: feature
feature: v1.6a-website-crawler
status: planned
related_code:
  - /src/ingestion/sources/website_crawl.py
  - /src/ingestion/adapters/crawl4ai_web.py
  - /src/ingestion/adapters/proxy_scrapingbee.py
  - /src/ingestion/sources/blocked_domains.py
  - /src/graph/web_node_types.py
  - /src/web/routes/website_crawl.py
  - /web/src/app/ingest/web
  - /flows/website_crawl_dispatcher.py
  - /flows/website_l0_sitemap.py
  - /flows/website_l1_entity_tagged.py
  - /flows/website_l2_full_graphrag.py
related_tests:
  - /tests/ingestion/sources/test_website_crawl.py
  - /tests/ingestion/adapters/test_crawl4ai_web.py
  - /tests/ingestion/adapters/test_proxy_scrapingbee.py
  - /tests/flows/test_website_crawl_dispatcher.py
  - /tests/flows/test_website_l0_sitemap.py
  - /tests/flows/test_website_l1_entity_tagged.py
  - /tests/flows/test_website_l2_full_graphrag.py
  - /tests/web/test_website_crawl_routes.py
  - /web/e2e/ingest-web.spec.ts
---

# Feature: V1.6a — Website-Crawl Ingestion + Staged Web Graph

**Status:** Spec only. Implementation blocked on V1.5c Verification Before Completion report filed + ADR-019 + ADR-020 ratified + Mahyar's go-ahead.
**Sub-slice ratified:** V1.6-R1 (2026-05-27).
**Owner:** Mahyar (decisions) + Claude (implementation, post-V1.5c).
**Time budget:** 4–6 weeks of focused work after V1.5c gate passes.
**Acceptance level:** 3 user-registered seed domains crawl on schedule, stage to L0 / L1 / L2 per user setting, citations resolve, robots.txt + per-domain budget honored every run.

## Purpose

Turn SecBrain from a "manual-upload + database-connector" system into one that **keeps up with official websites on its own**. The user names domains they care about (school admissions pages, professional bodies, regulators, official news), picks a cadence, and the system handles fetch → extract → stage into the graph without further babysitting.

## User value

A second-year dental-school applicant cares about ADEA + ADA + ASDA + every individual school's admissions page. Today (V1.5) those have to be downloaded by hand and registered as L2 dumps. V1.6a means the user clicks "Register ADEA.org", picks "Daily", and the next morning the ADEA changes are reflected in the graph with citations.

The same pattern serves every downstream consumer V1.5c introduced — the PM dashboard sees ADEA's authoritative numbers move; the marketing dashboard sees content-gap changes when official messaging shifts; the conflict resolver gets a richer L1/L2 corpus to argue against forum claims.

## What this sub-slice proves

1. **End-to-end scheduled crawl** — register a domain via UI, set cadence "every day at 06:00 UTC", come back the next day and see fresh L0 nodes with current `lastmod` timestamps.
2. **Staged ingestion** — same domain at stage L0 stays cheap forever; user upgrades to L1 and entity tags appear; upgrades to L2 and clusters / claims appear within budget cap.
3. **Politeness defaults** — robots.txt fetched, honored, cached; per-domain budget enforced; UA string honest; forum / social-media domains hard-blocked at registration.
4. **Asset coverage** — PDFs (`.pdf`), spreadsheets (`.xlsx` / `.csv`), images (with optional OCR), and HTML tables are extracted on the same pass.
5. **Incremental refresh** — a re-crawl with no source changes costs $0 and writes no new graph rows; a re-crawl with partial changes only re-processes changed pages.
6. **Proxy escape hatch** — opt-in `SCRAPINGBEE_API_KEY` per domain; default off. When a domain bounces local requests 3× in a row, ScrapingBee covers it transparently and the cost is logged against the per-domain budget.

## Acceptance criteria (testable, blocking)

1. **Register + schedule + run** — UI flow `/ingest/web` → "Register domain" → enter `https://www.adea.org/`, declare tier `L2`, cadence `daily 06:00 UTC`, stage `L1`. Domain appears in the list. Next scheduled run fires within the window; `crawl_jobs` row reaches `succeeded`; ≥ 10 `Page` nodes land in the graph with citations.
2. **Three seed domains land** — ADEA + ADA + ASDA all register successfully, run through their first crawl, and produce a non-empty `domain_summary` view at L1.
3. **Staged budget cap honored** — domain with `max_usd_per_month = $0.50` and L2 enabled hits cap mid-run, emits a HITL `crawl_cap_hit` item, pauses the domain. Next manual refresh after cap reset resumes from the queued URL.
4. **Robots.txt honored** — synthetic test domain with `Disallow: /private/` confirms that pages under `/private/` are skipped at the adapter level (not fetched, not stored, not graphed). Audit log shows `robots_disallow` rows.
5. **Domain blocklist** — attempt to register `reddit.com` returns HTTP 422 `DOMAIN_BLOCKED` with pointer to V1 Reddit adapter. Attempt to register `twitter.com` same.
6. **Asset coverage** — seed domain ADEA: at least one `.pdf` page registers as a `Page` node with `mime = application/pdf` and its extracted body chunked at L1. At least one `<table>` block on the ADEA cost-of-attendance page becomes a `Table` node with row/col counts ≥ (1, 2).
7. **Incremental refresh** — re-crawl ADEA the same day with no source change: `crawl_jobs.pages_fetched` counts new pages discovered, `pages_unchanged` counts the rest. Zero new `Page` versions are written for unchanged pages. Total cost row in `crawl_cost` shows ≤ $0 for the rerun.
8. **ScrapingBee fallback** — synthetic test domain that returns 403 to local UA flips to ScrapingBee on the 4th retry, succeeds, and the resulting fetch row carries `via_proxy=1`.
9. **Bitemporal page versioning** — change a page's `content_hash` via test fixture and re-crawl: prior `Page` version closes (`t_valid_to` = run time), new version opens; `query_page_at(url, t_valid)` returns the right one.
10. **Conflict resolution wired** — a crawled L2 page making a claim that contradicts an L1 anchor reaches step 5 (`WebVerificationAgent`) of the existing V1 conflict chain. Run the seeded "NYU tuition 2024-25" clash scenario; verdict written with citations.
11. **MCP outbound surface** — `register_crawl_domain`, `list_crawl_domains`, `get_crawl_status`, `trigger_crawl_now`, `pause_crawl_domain`, `update_crawl_cadence` all callable via MCP stdio + via FastAPI.
12. **Verification Before Completion report** in `.agent/reports/v1.6a-slice.md`.

Non-functional:

- **NFR-1.6a-1 Latency** — initial sitemap crawl (≤ 1000 URLs) completes < 30 minutes wall time on a single workstation with default concurrency=4.
- **NFR-1.6a-2 Cost** — L2 default budget cap $5/domain/month enforced; alarm at 80%.
- **NFR-1.6a-3 Test coverage** — ≥ 80% line coverage on `src/ingestion/sources/website_crawl.py`, `src/ingestion/adapters/crawl4ai_web.py`, `src/ingestion/adapters/proxy_scrapingbee.py`, `flows/website_*.py`.
- **NFR-1.6a-4 Citation traceability** — ≥ 99% on every retrieval surface that returns web-sourced data. Same gate as V1 FR-8.3 and V1.5c.
- **NFR-1.6a-5 Reliability** — single domain failure must not block other domains' scheduled runs. Crawl run failures are quarantined to that domain.
- **NFR-1.6a-6 Politeness** — robots.txt + `Crawl-delay` respected absolutely; UA string env-driven and non-empty; default concurrency ≤ 4 per domain; per-domain max 16.
- **NFR-1.6a-7 Storage** — raw fetched pages cached under `data/web_cache/<domain>/<sha256-16>.html` with hard-link dedup across runs; cache size capped at 5 GB workstation-wide with LRU eviction.
- **NFR-1.6a-8 Privacy / safety** — never crawl forums or social media regardless of override flag absent in UI; user PII never sent to ScrapingBee fallback (only URL + UA + optional referer).

## Sub-files in this packet

- `README.md` — this file
- `requirements.md` — functional + non-functional requirements
- `context.md` — links to V1.6 master brief + ADR-019 / ADR-020 + V1.5c deliverables
- `plan.md` — phased TDD implementation plan
- `data.md` — SQLite + graph schema additions
- `api.md` — `/api/v1/ingest/web/*` FastAPI routes + Pydantic models + MCP tool surface
- `state-machine.md` — crawl-job lifecycle + per-domain stage transitions
- `ui-flow.md` — register / list / detail / schedule wizard
- `test-plan.md` — unit + integration + E2E + mocked-network test stacks
- `decisions.md`
- `known-issues.md`
- `changelog.md`

## Open questions (pending V1.6a kickoff)

- Default L0/L1/L2 setting for new domains — proposed: `L1` (gives entity-tagged graph at no LLM cost). Confirm with Mahyar at kickoff.
- Image OCR default — proposed: off; user enables per-domain when needed (some ADEA PDFs are scanned, so this might be worth turning on for them by default).
- Whether to expose the per-page version history in the UI in V1.6a — proposed: yes via `/ingest/web/[domain]/page/[id]` with bitemporal timeline. Confirm scope.
- Auto-onboarding flow: when the user registers their first domain, do we auto-suggest a few "you might also want" domains (e.g., they pick ADEA → we suggest ADA + ASDA + CODA)? Proposed: no in V1.6a; revisit V1.7.
