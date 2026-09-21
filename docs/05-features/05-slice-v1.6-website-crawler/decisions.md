# Decisions — V1.6a Website-Crawl Ingestion

> Lightweight per-slice decision log. Architectural decisions live in `docs/11-decisions/` as ADRs.

## Architectural decisions (in ADRs)

- **ADR-019** — Website crawler engine: crawl4ai (Apache-2.0, local-first) primary + opt-in ScrapingBee fallback.
- **ADR-020** — Staged website graph: L0 sitemap (free) → L1 entity-tagged (~$0 local NLP) → L2 full GraphRAG (LightRAG-class ~$0.001/page).

## V1.6-R1 locked answers (2026-05-27)

| Question | Answer | Provenance |
|---|---|---|
| Primary engine | crawl4ai | Mahyar V1.6-R1 |
| Proxy | ScrapingBee, opt-in per domain | Mahyar V1.6-R1 |
| Forums in scope? | No | Mahyar V1.6-R1 |
| Social media in scope? | No, hard-blocked | Mahyar V1.6-R1 |
| Cadence | Per-domain cron; default daily 06:00 UTC | Mahyar V1.6-R1 |
| Staging | L0 / L1 / L2 per domain | ADR-020 |
| Asset types | HTML + PDF + xlsx/csv + images + HTML tables | Mahyar V1.6-R1 |
| Budget kill switch | Yes — per-domain pages + USD | Mahyar V1.6-R1 |
| Per-domain default stage | L1 (cheap entity tagging) | Claude proposal pending Mahyar ratification |
| Default L1 OCR | Off (per-domain opt-in) | Claude proposal pending Mahyar ratification |
| ScrapingBee default | Off (per-domain opt-in) | Claude proposal pending Mahyar ratification |
| Default budget | $5/domain/month | Claude proposal pending Mahyar ratification |
| Default concurrency | 4 per domain (hard cap 16) | Politeness default; Claude proposal pending Mahyar |
| Robots.txt | Honored absolutely; no override | Claude proposal pending Mahyar |
| UA string | Honest, env-driven, non-empty enforcement at startup | Politeness default; pending Mahyar |
| Per-page version history in UI? | Yes — bitemporal timeline on page-detail page | Claude proposal pending Mahyar |
| Auto-suggest "you might also want" domains? | No in V1.6a | Claude proposal pending Mahyar |

Items marked "pending Mahyar" need ratification at V1.6a kickoff. If Mahyar disagrees, change here + update `requirements.md` + add a row to `unresolved-questions.md`.

## Implementation-time micro-decisions (free for the implementer)

These don't need ratification — they're under "clean code rules" discretion:

- Module boundaries within `src/ingestion/adapters/crawl4ai_web.py` (single file vs split). Default: single file < 500 LOC, split if it grows.
- Whether to use `pandas.read_html` directly vs `lxml.etree.HTML` + manual table parse for HTML tables. Default: `pandas.read_html`; switch only on perf regression.
- Whether to materialize `pages_index` rows synchronously vs async during L0. Default: sync (simpler).
- Cache eviction strategy for `data/web_cache/`. Default: LRU on disk-size, enforced at adapter startup + once per crawl run.
- Whether to expose `LINKS_TO` adjacency at L0 directly vs only via L1 derived edges. Default: write at L0 — costs nothing, useful for sitemap-only domains.

## Already-rejected ideas (don't reopen without evidence)

| Idea | Why rejected |
|---|---|
| Firecrawl as primary | SaaS-first; recurring per-page cost; we're local. (ADR-019.) |
| Bright Data as primary | $0.75/1000 req + monthly commit; not justified for V1 targets. (ADR-019.) |
| Single-stage "just run V1 Pass 1–5" | Loses the user-controlled cost gate. (ADR-020.) |
| Five-stage 1:1 V1 mapping | UX cost of Pass-2-vs-Pass-3 distinction not worth it. (ADR-020.) |
| Per-page stage selection | UX cost on thousands of pages doesn't pay for itself in V1.6a; per-domain is the right granularity. (ADR-020.) |
| Microsoft GraphRAG full reindex per run | $50–200 / 500-page; > 10× our budget. (ADR-020.) |
| Real-time WebSub / RSS push | V2. V1.6a is polling-on-cron. |
| Forums via crawl path | Wrong fit; Reddit/SDN have dedicated V1 adapters; Discord/Discourse get V1.6b. |
| Social media | Out-of-scope; hard-blocked. |
| Multi-tenant | V2 per ADR-009. |
