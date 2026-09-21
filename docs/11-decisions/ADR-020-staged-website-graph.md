---
adr: 020
title: Staged website graph — L0 sitemap → L1 entity → L2 full GraphRAG
status: accepted
date: 2026-05-27
deciders: Mahyar, Claude
supersedes:
superseded_by:
revision_history:
  - 2026-05-27 v1 — drafted by Claude during V1.6a kick-off research per Mahyar's V1.6-R1 prompt. Pending Mahyar ratification.
  - 2026-05-27 — accepted. Mahyar ratified at V1.6a kickoff. L0/L1/L2 stage semantics + incrementality contract + budget gating (3-point: project / cumulative / dispatcher-boot) approved as written. Per-page version history visible in UI via bitemporal timeline. Per-domain stage selection (not per-page) is the V1.6a granularity; per-page is V1.7. V1.6a implementation cleared to proceed under this ADR.
---

# ADR-020 — Staged website graph

## Context

Mahyar's V1.6-R1 prompt asks for a staged ingestion: "first version just make a graph of the overall site map, then we go one level deeper and extract information using the entity extractor which is cheap to run and then we go for the full GraphRAG solution like before this method has intermediate too."

The V1 5-pass extraction architecture (`docs/04-architecture/system-overview.md` §2) already maps cleanly onto this. We don't need a new architecture, just to organize it per-domain so the user can buy in at any stage.

Cost-modelling against published 2026 GraphRAG benchmarks:
- **Microsoft GraphRAG**: $50–200 to index a 500-page corpus; $33K reported for large enterprise sets. Unaffordable for V1's $5/domain/month default budget.
- **LightRAG**: $0.50 to index a 500-page corpus, ~70–90% of Microsoft GraphRAG quality. Affordable.
- **Fast GraphRAG / nano-graphrag**: roughly LightRAG-class cost with different trade-offs.
- **Heuristic content extractors** (Trafilatura): SIGIR'23 benchmark winner; F1 = 0.883 mean / 0.970 median across 8 datasets. Effectively free.

We need a structure that:
1. Lets the user stop at any stage they're willing to pay for.
2. Lets each higher stage incrementally build on lower stages without re-doing work.
3. Reuses V1's Pass 1–5 architecture so we don't reinvent ER, conflict resolution, or retrieval.
4. Stays incremental on re-crawl: new pages add nodes; changed pages re-trigger only their downstream re-extraction; unchanged pages cost $0.

## Decision

**Three-stage website graph, opt-in per domain, each stage idempotent and incremental.**

```
                          ┌─────────────────────────────────────┐
                          │ Crawl4AIAdapter pull (sitemap.xml + │
                          │ ETag/Last-Modified + content hash)  │
                          └────────────────┬────────────────────┘
                                           │ raw pages + assets (cache-keyed)
                                           ▼
   Stage L0 ─►     ┌──────────────────────────────────────────────────────┐
   sitemap         │ Structural site-map graph (deterministic, $0)        │
   graph           │ Page / Sitemap / MediaAsset / Table nodes            │
                   │ + LINKS_TO / BELONGS_TO_SITEMAP / EMBEDS / TABLE_OF  │
                   │ + content_hash + ETag + crawl_run_id on every node   │
                   └────────────────┬─────────────────────────────────────┘
                                    │ unchanged? skip downstream stages
                                    ▼
   Stage L1 ─►     ┌──────────────────────────────────────────────────────┐
   entity-tagged   │ Local NLP entity tagging (~$0; runs on workstation)  │
   graph           │ Trafilatura main-content extraction + GLiNER2 +      │
                   │ spaCy + rapidfuzz canonical-match against V1 L1 anchors│
                   │ + BGE-small embeddings on chunks                     │
                   │ Adds Entity nodes + MENTIONS / REFERENCES_TOPIC edges│
                   └────────────────┬─────────────────────────────────────┘
                                    │ chunk-embeddings → vector index hot
                                    ▼
   Stage L2 ─►     ┌──────────────────────────────────────────────────────┐
   full web        │ LightRAG-style community detection + per-cluster     │
   GraphRAG        │ summarization + Pass-4-style sentiment / claim /     │
                   │ relationship extraction via the existing model       │
                   │ gateway (Haiku 4.5 default; tiered per ADR-003)      │
                   │ Adds Claim / Cluster / Summary nodes + SUPPORTS /    │
                   │ CONTRADICTS / SUMMARIZES edges                       │
                   └──────────────────────────────────────────────────────┘
```

### Stage definitions

**L0 — sitemap graph (always on; no user opt-in needed)**

- Cost: $0 (no LLM, no embedding, no external API).
- Latency: O(pages) — ~50 pages/sec on a local workstation.
- Inputs: crawl4ai output for a domain (URL list + per-URL HTML/PDF/asset).
- Outputs:
  - `Page` node per URL with `title`, `url`, `mime`, `content_hash`, `etag`, `last_modified`, `bytes`, `crawled_at`, `tier`, `domain_id`.
  - `Sitemap` node per discovered sitemap.xml index.
  - `MediaAsset` node per discovered image / video / non-textual asset; URL + alt text + mime + bytes.
  - `Table` node per `<table>` block; serialized cells + row/col counts.
  - `LINKS_TO` edge for every `<a href>` in body (deduplicated; out-of-domain links target a `ExternalRef` placeholder node).
  - `BELONGS_TO_SITEMAP` edges.
  - `EMBEDS` edges (Page → MediaAsset).
  - `TABLE_OF` edges (Page → Table).
- Idempotent: a re-crawl with no `content_hash` change → no-op on the graph; only `crawled_at` is bumped via a bitemporal write.
- Equivalent V1 pass: **Pass 1 (structural graph)** — same deterministic-no-LLM character.

**L1 — entity-tagged graph (opt-in per domain; default off in V1.6a)**

- Cost: ~$0 on a local workstation. GLiNER2 + spaCy + BGE-small all run on CPU or the local GPU. No external API calls.
- Latency: ~5–20 pages/sec depending on GPU.
- Inputs: L0 graph + raw HTML/PDF/Excel from the per-page cache.
- Outputs:
  - Main-content extraction via Trafilatura (F1 0.883 mean per SIGIR'23) → per-page `content_md` cached.
  - Chunking: 512-token chunks with 64-token overlap (matches V1 Pass 3 chunking).
  - BGE-small embedding per chunk (384-d) → vector index entry keyed on `chunk_id`.
  - GLiNER2 entity extraction over chunks → `Entity` nodes (Person / Organization / Place / Date / Money / Program / School-or-Institution / Procedure / etc.).
  - rapidfuzz canonical-match against V1 L1 anchors (ADEA + CODA Excel-derived nodes) → `MENTIONS` edge with fuzzy-match score; ≥ 0.95 auto-link, 0.75–0.95 HITL via `entity_link_ambiguous`, < 0.75 leave unlinked.
  - `REFERENCES_TOPIC` edges from `Page` nodes to existing `Topic` nodes via Pass-3-clustering-style nearest-cluster lookup.
- Idempotent: `content_hash` unchanged → no-op. Changed hash → re-extract only that page; old chunks tombstoned (bitemporal); new chunks linked.
- Equivalent V1 passes: **Pass 2 (cheap labels)** + **Pass 3 (semantic clustering)** with no top-down cluster construction (that lives in L2).

**L2 — full web GraphRAG (opt-in per domain; pay-per-page LLM cost)**

- Cost: target ≤ $0.001 per page / per pass at default ADR-003 routing (Gemini Flash-Lite for cluster summaries; Haiku 4.5 for selective claim / sentiment extraction). 500 pages ≈ $0.50; matches LightRAG-class numbers.
- Latency: O(pages) × per-call latency; backgrounded via Prefect flow.
- Inputs: L1 entity-tagged graph + chunk embeddings.
- Outputs:
  - Community detection on the chunk-embedding graph (signed-graph clustering per V1 Pass 3, same algorithm).
  - Per-cluster summary via Gemini 2.5 Flash-Lite (one LLM call per cluster) → `Cluster` + `Summary` nodes + `SUMMARIZES` edges.
  - Selective Pass-4-style extractions: sentiment, claim atomization, conflict-candidate proposals on chunks flagged as high-value (utility filter applies — same as V1 Pass 4).
  - `SUPPORTS` / `CONTRADICTS` edges between `Claim` nodes per V1 ADR-006 conflict-chain machinery.
  - L1-vs-L2 conflict propagation: if a page makes a claim about an L1 anchor entity, it routes through the V1 6-step conflict-resolution chain. Step 5 hits V1.5c's `WebVerificationAgent` (Tavily) — note this is the same Tavily integration; we don't re-build it.
- Idempotent: chunk-level. Re-running L2 on unchanged chunks is a no-op via the content-addressable extraction cache.
- Equivalent V1 passes: **Pass 4 (selective deep extraction)** + **Pass 5 (knowledge surfacing)**.

### Cross-stage incrementality contract

Re-crawl of a domain after the cadence elapses:

1. `Crawl4AIAdapter.pull(delta=True)` fetches only URLs with newer `lastmod` OR ETag/Last-Modified change. Other URLs not refetched. Bandwidth and ScrapingBee cost stay near zero on a no-change run.
2. For URLs with new `content_hash`:
   - L0: existing `Page` node bitemporally updated (`t_valid_to` closed on old version, new version opened); `LINKS_TO` etc. re-computed.
   - L1: existing chunks tombstoned; new chunks embedded + entity-tagged.
   - L2 (if domain opted in): clusters touching changed chunks are recomputed; downstream summaries + claims regenerated; conflicts re-evaluated.
3. For removed URLs: `Page.t_valid_to` set to now; downstream chunks/claims tombstoned but preserved per V1's "graph keeps every node" invariant (R5).

### Per-domain stage gating

- `WebsiteCrawlSource.stage` (user-set; default `"L0"`) — one of `"L0"`, `"L1"`, `"L2"`.
- Upgrades take effect on the next scheduled run. Downgrades pause higher-stage outputs but do **not** delete already-extracted data — the user can `purge_stage(level)` from the settings page if they want to delete and re-run.
- Budget gating: if `max_usd_per_month` would be exceeded by running L2 on the queued pages, the run fires L0 + L1 only and emits a `budget_capped` HITL item with a "Buy more budget?" CTA.

## Consequences

**Positive:**
- Aligns one-to-one with V1's 5-pass architecture. Reuses Pass 1 (structural) machinery for L0, Pass 2/3 for L1, Pass 4/5 for L2. No new core code paths.
- Cost-per-page at L2 is bounded to LightRAG levels (~$0.001/page at default routing) — fits SecBrain's $5/domain/month default budget for ~5000 L2 pages.
- L0 alone is genuinely useful — the user can answer "what's on this domain?" and "what does X page link to?" without paying any LLM cost. Many domains will never need L1+.
- Incremental on re-crawl by design — unchanged pages contribute zero LLM cost. This is the key differentiator over Microsoft-GraphRAG-style full-reindex pipelines.
- Conflict resolution piggy-backs on V1.5c's Tavily `WebVerificationAgent`. No new web-verification infrastructure.
- Bitemporal semantics preserved — historical versions of every page are retrievable per V1 ADR-005.

**Negative:**
- Three stages = more state machine surface area. State diagram lives in `state-machine.md`; gated by tests.
- L2 cost-bounding depends on accurate per-page cost estimation pre-run. We use V1.5c's `web_search_cost` style projection (recent-page avg × queued pages), with 20% safety margin. May under-estimate on long-tail pages.
- Cluster-recomputation on partial change is heuristic: we re-cluster only chunks within 2 hops of changed chunks in the embedding graph, not the whole domain. Acceptable trade-off; documented as a known issue.
- GLiNER2 inference on every crawled page burns ~50 ms each on a Pascal GPU. 5000 pages/run = ~4 minutes of L1 work. Fine; not a tight loop.

**Neutral:**
- We deliberately don't implement Microsoft GraphRAG's full hierarchical community summarization (the $50–200/500-page step). LightRAG-style flat community detection plus per-cluster Flash-Lite summary is sufficient at V1.6a budget. Re-open in V2 if quality lags.
- nano-graphrag / FastGraphRAG were evaluated; rejected for V1.6a because (a) we already have V1's clustering implementation, (b) integrating a parallel graph engine doubles maintenance, (c) LightRAG-style hand-rolled stages give us more control over the cost cap.

## Alternatives considered (and rejected)

**Full Microsoft GraphRAG every run** — Too expensive; $50+ per 500-page indexing pass. Rejected.

**Single-stage "just run V1 Pass 1–5 on web pages"** — Doesn't expose the user-controlled cost gate. Rejected.

**Two stages (skip L1)** — Considered. Rejected because L1 is genuinely cheap and lets the user search-by-entity without paying for L2; cutting it would push more users into the L2 budget.

**Five stages (mirror V1's Pass 1–5 1:1)** — Considered. Rejected because Passes 2 and 3 collapse cleanly to one user-facing L1 stage with no UX value lost.

**Per-page user-selectable stage** (vs per-domain) — Considered. Rejected for V1.6a because the UX cost (a per-page setting on potentially thousands of pages) doesn't pay for itself; per-domain is the right granularity for V1.6a. Per-page becomes a power-user feature in V1.7.

## Related docs
- `docs/05-features/v1.6-master-brief.md`
- `docs/05-features/05-slice-v1.6-website-crawler/`
- `docs/04-architecture/system-overview.md` (§2 V1 5-pass; §14 to be added)
- `docs/11-decisions/ADR-003-extraction-stack.md` (per-task model matrix reused)
- `docs/11-decisions/ADR-005-trust-tier-schema-and-bitemporal-edges.md` (bitemporal write semantics)
- `docs/11-decisions/ADR-006-conflict-resolution-and-llm-judge.md` (conflict chain reused at L2)
- `docs/11-decisions/ADR-016-web-search-conflict-resolution.md` (Tavily reused at L2 step 5)

## Related code
- `src/ingestion/sources/website_crawl.py` (new — stage state lives here)
- `flows/website_l0_sitemap.py` (new)
- `flows/website_l1_entity_tagged.py` (new)
- `flows/website_l2_full_graphrag.py` (new — delegates to existing Pass 4+5 flows)
- `src/graph/web_node_types.py` (new — `Page`, `Sitemap`, `MediaAsset`, `Table`, `Entity` subtype registrations)
