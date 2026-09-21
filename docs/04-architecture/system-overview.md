# System Overview

> **Status**: V1 seed updated 2026-05-20 (R-006…R-009/R5); **graph-DB bake-off complete 2026-05-21 → Kùzu (ADR-001 accepted)**; **SOTA re-verified 2026-05-29 (R-010 → ADR-021…026)**. **Reconciled 2026-09-20** against `implementation-status.md`: HALO/tier ranking, hybrid retrieval, the 3-vendor judge + web-verifier, and bitemporal supersede are now **Wired** (V1.7 WP3); signed-spectral clustering is **Built**. ⚠️ This doc still describes the architecture as designed through V1.5 and does not yet cover the V1.7 evidence engine, dossier, research protocol, or Insights Pack — for what actually runs today, `docs/00-bootstrap/implementation-status.md` is the single source of truth.

## Summary

A generic, self-correcting, self-evolving **knowledge-graph engine + retrieval layer**. Ingests heterogeneous data dumps (structured DBs, official websites, scraped forums, technical docs), anchors them against authoritative ground truth, resolves conflicts in a tier-aware temporal-first order using bitemporal edges + signed-graph clustering, and exposes a queryable graph with MCP tools.

V1 anchor domain = US dental school + residency applications (Mahyar's DentistJourney use case). V1 internal-only. V2 generalizes the source-handler interface to other companies' data dumps (`developer_tool` posture).

**Versatile by design** (R5): the retrieval surface serves PMs, marketers, sales reps, and downstream agents — not over-specialized for one question type.

## Two distinct GraphRAG deployments (DO NOT confuse)

1. **`tools/graphrag/` — Repo MCP context server.** Indexes the SecBrain repo itself (docs, code, tests, feature packets). Per CLAUDE.md, implemented before V1 product code starts. Verified against `tools/graphrag/verification-checklist.md`. Reindex trigger: git-hook (opt-in) + manual `index.py --incremental` per R5.
2. **V1 product engine (under `src/`, name TBD).** Indexes ingested dental data (ADEA SQL + Reddit + SDN + future sources) and emits the trust-tier-aware GraphRAG. **This is what V1 builds.**

These may share a core library (design opportunity).

## Main components (V1 product engine)

### 1. Ingestion plane
- **Data dump receiver** — API endpoint + MCP tool `register_dump(source_tier, manifest, payload)`. Validates manifest, content-hashes payloads, stores immutable raw.
- **Source-type adapters** (per source-type, plug-in pattern). L1 Excel / L2 HTML / L5 Reddit JSONL / L5 SDN JSONL. Each implements `SourceAdapter` Protocol.
- **Normalizer** — canonical document/post records with provenance + timestamps + license + content-hash.

### 2. Extraction — 5-pass architecture (R5)

**The graph preserves every post.** Utility filter ONLY avoids LLM token spend at Pass 4.

| Pass | Cost | Inputs | Outputs | Filter? |
|---|---|---|---|---|
| **1 — Structural graph** | $0 | Raw dumps (ADEA Excel, Reddit JSONL, SDN JSONL) | Users / Posts / Comments / Threads / Subreddits / SDNCategories + edges (AUTHORED, REPLIED_TO, BELONGS_TO_THREAD, POSTED_IN_FORUM, UPVOTED) + user-credibility scores + `rapidfuzz`-matched school/program entities | None |
| **2 — Cheap labels** | $0 | Post metadata | `Topic` nodes from Reddit `link_flair_text` + SDN `category` + REFERENCES_TOPIC edges | None |
| **3 — Semantic clustering** | ~$0 (local GPU) | BGE-small embeddings (post + comment bodies) | Mid-level Topic groupings via signed-graph community detection; per-cluster summary via Gemini 2.5 Flash-Lite (one call per cluster) | None |
| **4 — Selective deep extraction** | $35-50 est. full sweep | Pass 3 + utility filter | Sentiment (broad), interview-Q harvest, conflict candidates, claim atomization | **Yes — utility filter applies here** |
| **5 — Knowledge surfacing** | $0 retrieval | Cleaned graph | MCP retrieval primitives + convenience tools | None |

**Utility filter (Pass 4 only)** drops a post from LLM processing if ANY of:
- `[deleted]` / `[removed]` / AutoModerator / known-bot patterns,
- `<3 words` AND not a reply to a question,
- no entity-mention AND no question/answer structure AND no sentiment marker,
- crosspost-duplicate of an already-processed post.

The filter is reversible: the `Post`/`Comment` node stays in the graph; only the `LLMExtraction` edge is skipped. Marketers can ask "what's the vibe in r/predental during exam season?" later by clearing the filter for that topic and rerunning sentiment.

**Pass 4 model tiering** (per ADR-003):

| Stage | Model | When |
|---|---|---|
| 3a | **Gemini 2.5 Flash-Lite** ($0.10/$0.40, batch+cache further) | Default workhorse: sentiment + cluster-summary refinement + initial Q-candidates |
| 3b | **Claude Haiku 4.5** ($0.50/$2.50 batch + 90% cache-read, `ttl: 3600`) | When 3a confidence < 0.9 OR nuanced extraction (multi-part interview Q, conflict candidate paired with L1) |
| 3c | **Claude Sonnet 4.6** ($1.50/$7.50 batch) | Hardest ~2%: Haiku confidence < 0.7 AND high downstream impact |

**Constrained decoding (local)**: XGrammar / XGrammar-2.
**Content-addressable extraction cache**: keys = `hash(post + prompt_id + prompt_version + schema_hash + model + model_version)`. 90-99% off reruns.

### 3. Conflict resolution (order per A-011, R-007b)

1. **L1 clash** — forum claim conflicting with L1 → flagged `Status: Invalidated_by_Official_Data`. L1 unmodified.
2. **Temporal disambiguation** — bitemporal `t_valid_*` check; if different years, split into year-tagged versions (not conflict).
3. **Source-trust weighting** — Wikidata `rank` × tier × intra-tier user-credibility.
4. **Signed-graph community detection** on opinion-layer SUPPORTS / CONTRADICTS edges. ⚠️ **Corrected per R-010 / ADR-026:** (a) signed-spectral clustering is **Built** (`method="signed_spectral"`, GAP-049, 2026-06-17) but the default and the full-corpus run still use k-means; (b) **cluster size ≠ truth.** Community detection *detects disagreement*; it does not *adjudicate* it. Consensus is decided by **source-trust-weighted stance aggregation** (ADR-021 `consistency`), and a minority is **routed to web-verification, not auto-tagged `Status: Anomaly`** (majority≠correct is a documented failure mode — dangerous here, since a correct policy change often starts as a small minority cluster). Anomalies are still preserved (A-032), just not by majority vote alone.
5. **Web-verification trigger** — emit `research_need` via outbound MCP → crawler fetches → re-extraction.
6. **HITL escalation** — irreducible ambiguity.

**LLM-as-judge restricted** to same-tier same-year tie-breaks with three-vendor calibration (Sonnet 4.6 + Gemini 2.5 Flash + GPT-4.1-mini; ≥2/3 agreement). Outside that window: HITL.

### 4. Multi-layer graph store (V1 = all 3 layers, bitemporal edges, Wikidata-rank trust)

Underlying store = **Kùzu (ADR-001 accepted)**. All edges carry: `source_tier`, `rank`, `references`, `qualifiers`, `t_valid_from/to`, `t_ingest_from/to`. L1 anchors immutable. The 4-tuple is stored, `as_of` reads work, and **bitemporal supersede (atomic close/open) is Wired**: `supersede_edge` in `src/graph/kuzu_client.py`, called from `src/conflict/l1_claims.py` (GAP-053 closed).

- **User/actor layer** — derived properties: source-aware credibility rubric (Reddit 10-feature + SDN 7-feature per ADR-008); `prescient_correct` counter (low-karma claims later confirmed).
- **Post/document layer** — classified by Pass 2 flair/category + Pass 3 emergent clusters + Pass 4 sentiment.
- **Opinion/advice layer** — SUPPORTS / CONTRADICTS edges; signed-graph community detection.

L1 nodes (Universities, Programs, Cycle years, ADEA cost/admission stats) sit above all three layers as immutable canonical anchors with `rank: preferred`.

### 5. Temporal-decay model (HALO per-edge-type half-life — ADR-007)

Each edge type has its own half-life. V1 hand-set table; V1.1 may learn from data.

Retrieval ranking weight (per Pass 5) — per ADR-021, **Wired** in `src/retrieval/ranking.py` via `query_graph` (GAP-048 closed):
```
ranking_score = w_tier × w_rank × decay(now, t_valid_from, half_life) × user_credibility(source) × consistency(claim)
```
`w_tier` is a **prior/weight, not a hard pre-sort** (a fresh, corroborated, high-credibility L5 claim can outrank a stale L1 record). `consistency` = RA-RAG-style cross-source agreement (ADR-021). HALO `decay` per ADR-007 (`src/conflict/halo_table.py`, Wired — GAP-050 closed).

### 6. Retrieval / MCP plane (Pass 5)

**Inbound MCP tools** (Tier 1, V1):
- `query_graph(query, source_tier_min, time_range, as_of, traversal_depth, include_anomalies)`
- `get_canonical_entity(alias, entity_type)`

**Inbound MCP tools** (Tier 1, V1.x — convenience for marketers / PMs / sales / agents):
- `search_by_topic(topic, source_tier_min, time_range)`
- `get_user_credibility(user_id, topic)`
- `get_topic_consensus(topic, time_range)`
- `get_top_concerns_by_audience(audience_filter, time_range)` *(new R5)*
- `get_sentiment_distribution(topic, time_range)` *(new R5)*

**Outbound MCP tools** (Tier 1, V1 — to the crawler):
- `register_dump(source_tier, manifest, payload)`
- `get_gaps()` / `get_research_needs()`
- `is_url_ingested(url)` *(R5 confirmed)*
- `get_topic_state(topic)` *(R5 confirmed)*
- `get_pending_verifications()` *(R5 confirmed)*

### 7. HITL queue

V1 = CLI + flat YAML files; V2 = web UI. Items queued: borderline alias matches (Pass 1 fuzzy < 95 routed to Pass 2/3/4; some land in HITL), conflict-resolution ambiguity outside the LLM-as-judge tie-break window, new node/edge type proposals.

### 8. Graph DB bake-off (COMPLETE 2026-05-21 → Kùzu; ADR-001 accepted)

Ran on a 28,403-node real-data sample; 5 metrics (bulk-load, 3-hop p95, HNSW recall@10, bitemporal ergonomics, ops complexity). Scores: Neo4j 0.600 / Kùzu 0.564 / AGE 0.528 (margin < 0.10 → M5 ops-complexity tiebreak → **Kùzu** `0.11.3`). Runner-up + V2 swap-target: **Graphiti + Neo4j Community**. Code runs on `src/graph/kuzu_client.py`; harness `tools/bake_off/`.

### 9. Observability + audit

- Every extraction / retrieval / HITL decision / ingestion event audit-logged (SQLite `audit_log`, append-only).
- Per-call LLM telemetry → Langfuse (per ADR-011).
- structlog JSON app logs.
- Prefect 3 task / flow dashboards (per ADR-010).

### 10. Orchestration (R5 — ADR-010 decided)

**Prefect 3** as V1 orchestrator. Daily incremental re-ingest cadence (R5) drove the decision from "deferred" to "decided." Each pass is a Prefect flow; per-task retries + backoff + observability dashboards. SQLite-backed state store (`.prefect/`).

## Data flow (R5 5-pass)

```
                       ┌──────────────────────┐
                       │  External crawler    │
                       │  (separate system)   │
                       └──────────┬───────────┘
                                  │ register_dump(source_tier, manifest, payload)
                                  ▼
                       ┌──────────────────────┐
                       │  Ingestion plane     │
                       │  (Tier 1 MCP)        │
                       └──────────┬───────────┘
                                  │ canonical records
                                  ▼
              Pass 1 ─►  ┌─────────────────────────────────┐
                         │  Structural graph (deterministic)│
                         │  Users / Posts / Comments       │
                         │  + AUTHORED / REPLIED_TO        │
                         │  + rapidfuzz canonical match    │
                         │  + user-credibility scores      │
                         └──────────────┬──────────────────┘
                                        │ (NO FILTER — every post in graph)
                                        ▼
              Pass 2 ─►  ┌─────────────────────────────────┐
                         │  Cheap labels (no LLM)          │
                         │  Reddit flair / SDN category    │
                         │  → Topic nodes                  │
                         └──────────────┬──────────────────┘
                                        │
                                        ▼
              Pass 3 ─►  ┌─────────────────────────────────┐
                         │  Semantic clustering (local GPU)│
                         │  BGE-small + signed-graph       │
                         │  → mid-level Topic clusters     │
                         │  + per-cluster summary (Flash-Lite)│
                         └──────────────┬──────────────────┘
                                        │ (still NO FILTER on the graph)
                                        ▼
              Pass 4 ─►  ┌─────────────────────────────────┐
                         │  Selective deep extraction      │
                         │  ┌─ Utility filter ──────┐      │
                         │  │ drop deleted/bots/    │      │
                         │  │ ultra-short/generic   │      │
                         │  │ (filters LLM input    │      │
                         │  │  ONLY — graph keeps   │      │
                         │  │  every node)          │      │
                         │  └─────┬─────────────────┘      │
                         │        ▼                         │
                         │  Stage 3a Gemini Flash-Lite      │
                         │  Stage 3b Haiku 4.5              │
                         │  Stage 3c Sonnet 4.6 (rare)      │
                         │  + content-addressable cache     │
                         │  + ttl:3600 prompt cache         │
                         └──────────────┬──────────────────┘
                                        │ sentiment + interview-Q + claims
                                        ▼
                         ┌─────────────────────────────────┐
                         │  Conflict resolver (6 steps)    │
                         │  + bitemporal write             │
                         │  ↳ web-verification ─►          │ outbound MCP
                         │  ↳ HITL escalation ─►           │ HITL queue
                         └──────────────┬──────────────────┘
                                        ▼
                         ┌─────────────────────────────────┐
                         │  Multi-layer graph (Kùzu, ADR-001)│
                         │  · L1 immutable anchors         │
                         │  · User/actor (credibility)     │
                         │  · Post/document (clusters)     │
                         │  · Opinion/advice (signed graph)│
                         │  Bitemporal + rank + tier       │
                         └──────────────┬──────────────────┘
                                        ▼
              Pass 5 ─►  ┌─────────────────────────────────┐
                         │  Retrieval MCP plane            │
                         │  Versatile: PMs / marketers /   │
                         │  sales / agents                 │
                         │  query_graph / topic / etc.     │
                         └─────────────────────────────────┘

Prefect 3 orchestrates the passes (daily incremental + ad-hoc full sweeps).
```

## External integrations

- **Crawler (separate system)** — talks to outbound MCP, submits dumps via `register_dump`.
- **Anthropic API** — Haiku 4.5 + Sonnet 4.6 via gateway. Cross-vendor failover.
- **OpenAI API** — GPT-4o-mini / GPT-4.1-mini via gateway. Used in LLM-as-judge.
- **Google API** — Gemini 2.5 Flash-Lite / 2.5 Flash via gateway. Pass 3a/4 workhorse + LLM-as-judge.
- **Local models** — spaCy, GLiNER2, BGE-small (embeddings), DITTO/DistilBERT (ER reranker), XGrammar (constrained decoding).
- **HITL reviewer** — Mahyar (V1); contracted dental-admissions expert (V1.x+).

## Deployment overview (V1)

- Single workstation. Process layout:
  - **Graph DB** — **Kùzu** (embedded, `kuzu==0.11.3`; ADR-001).
  - **Side store** — SQLite for L1 + HITL + extraction-cache + audit log.
  - **Prefect 3** — `prefect server start` + `prefect worker start` for scheduled flows.
  - **Object store** — local filesystem (`/data/dumps/`).
  - **Extraction pipeline** — Prefect flows (`flows/pass1..pass5.py`).
  - **MCP servers** — `mcp` Python SDK over stdio.
  - **HITL CLI** — Python click/typer.

## Key risks

- Kùzu upstream archived post-Apple-acquisition; mitigated by pinning the `kuzu==0.11.3` PyPI release + tracking the LadybugDB MIT fork (ADR-001 / tech-stack).
- Pascal-era GPU is fine for GLiNER + embeddings + DITTO; local 8B LLM = fallback.
- Prompt-cache TTL pinning enforced via lint (GAP-031).
- HNSW under continuous deletion → rebuild nightly.
- Trust-tier retrieval under-published — we are inventing this layer.
- LadybugDB stability — newer fork; need bake-off + 6-month monitoring.
- Utility-filter calibration on real data (GAP-035) — must not over-filter `prescient_correct` candidates.

## 11. Cross-graph entity mapping (V1.5a addition — ADR-015)

V1's entity-resolution stack snaps L5 mentions to L1 canonical entities within a single ingest's universe. V1.5a generalizes this to cross-source entity mapping across the multi-source graph.

**`DataSource` Protocol** (V1.5a) — wraps each connector (Postgres / MySQL / SQLite / Neo4j / wrapped V1 local-file adapters) with lifecycle + schema-discovery + sample + delta-pull + tier declaration.

**`MappingSuggester`** (V1.5a) — reads a `SchemaSnapshot` and proposes `(table → node_type | edge_type | skip)` per table. BGE-small embeddings on column names + sample values; auto-accept ≥ 0.90, HITL 0.75–0.90, reject < 0.75.

**User-declared tier** (ADR-014) — connector tier is declared at connect-time; default L2. L1 requires explicit `confirm_l1_immutable=True`. L1 connectors that conflict with existing L1 produce a `multiple_l1_claims` HITL item (rather than auto-merge).

**`CrossGraphLinker`** (ADR-015) — reuses the V1 BGE + DITTO pipeline in cross-source mode. Same auto-accept ≥ 0.90 / HITL 0.75–0.90 / reject < 0.75 thresholds. Writes `SAME_AS` bitemporal edges. Bidirectional read semantics; canonical-ordered storage.

```
        External Postgres / MySQL / SQLite / Neo4j
                     │
                     │ connect_data_source + discover + suggest_mapping + commit + pull
                     ▼
                 ┌─────────────────────────┐
                 │  Connector engine       │
                 │  (per-source DataSource)│
                 └────────────┬────────────┘
                              │ materializes nodes + edges (tier-stamped)
                              ▼
                 ┌─────────────────────────┐
                 │  CrossGraphLinker       │  ← matches against existing canonical universe
                 │  (BGE blocking +        │  ← (V1 ADEA L1 + V1.5a Postgres L2 + V1 Reddit L5)
                 │   DITTO reranker)       │
                 └────────────┬────────────┘
                              │
              ┌───────────────┼────────────────┐
              ▼               ▼                ▼
        conf ≥ 0.90      0.75-0.90          < 0.75
              │               │                │
              ▼               ▼                ▼
        SAME_AS edge      HITL queue        no link
        written           (cross_graph_link)
```

## 12. Iterative feedback loop (V1.5b addition — ADR-017 + ADR-018)

V1 produces Pass-4 extractions and writes them. V1.5b adds a human-in-the-loop iterative refinement layer where user decisions feed back into the next sweep.

**`feedback_log`** (append-only, immutable) — every HITL decision on a cluster, node-edge proposal, alias, conflict, cross-graph link is permanently recorded with full provenance + BGE embedding.

**`FeedbackContextLoader`** (ADR-018) — at Pass-4 init, queries `feedback_log` for the corpus + template, runs active-learning hybrid scoring (relevance + recency + diversity + frequency), selects top-K=4 positive examples + ≤50 blocklist entries.

**Few-shot collapse mitigation** (ADR-018) — hard cap K=4 examples per few-shot-collapse 2026 research. Blocklist eviction LFU+LRU at cap=50.

**`BlocklistFilter`** — post-hoc cosine-similarity safety net (drops extractions with similarity > 0.92 to a blocklisted pattern). Filtered items audit-logged (not silently dropped).

**Cache integration** — Pass-4 content-addressable cache key includes `feedback_context_hash`. Changing feedback affects only the affected template's cache entries.

```
       (Pass 3 outputs clusters)
                │
                ▼
       ┌─────────────────┐
       │  Cluster cull   │ ← user reviews + culls / merges / splits
       │  HITL flow      │
       └────────┬────────┘
                │ approved clusters only
                ▼
       ┌─────────────────┐    ┌──────────────────────────────┐
       │  Pass 4         │ ◄──│  FeedbackContextLoader       │
       │  (with context  │    │  - load feedback_log         │
       │   block injected│    │  - active-learning score     │
       │   into BAML)    │    │  - top-K=4 + blocklist=50    │
       └────────┬────────┘    └──────────────────────────────┘
                │ extractions
                ▼
       ┌─────────────────┐
       │  BlocklistFilter│ (safety net)
       └────────┬────────┘
                │
                ▼
       ┌─────────────────┐
       │  Node/edge      │ ← user reviews + accepts / rejects / refines
       │  proposal HITL  │
       └────────┬────────┘
                │ decisions write to feedback_log → next sweep picks them up
                └─────────────────────────────────────────────────────────►
```

## 13. Web-search-grounded conflict resolution (V1.5c addition — ADR-016 v2)

V1's conflict-resolution chain (§3 above) has step 5 "emit research_need" — V1 only queues; nothing fetches. V1.5c activates step 5 via Tavily-only verification with internal cross-check.

**`WebVerificationAgent`** runs three parallel signals before writing a verdict:
- **Signal A** — Tavily QNA on the original claim (LLM-rephrased as a question).
- **Signal B** — Tavily search on an LLM-paraphrased version of the question.
- **Signal C** — Tavily extract on top URLs from A+B + two-vendor LLM verify (Haiku 4.5 + Gemini Flash, both must agree).

**Combine**: ≥ 2-of-3 agreement (confidence ≥ 0.7) → verdict written with full provenance (`web_verification_run` JSON). Otherwise escalate to HITL or emit `research_need`.

**Cost cap**: $5 default per corpus per sweep, configurable.

**Provider abstraction**: `SearchProvider` Protocol — V1.5c ships Tavily only; V1.6 candidates include Brave / Firecrawl / Exa as configurable additions.

## 14. Website-crawl ingestion (V1.6a addition — ADR-019 + ADR-020)

V1.6a turns the long-deferred "Crawler (separate system)" placeholder into an in-house scheduled multi-domain website-crawl ingestion. **Forums and social media are hard-blocked at registration time**; V1 (Reddit/SDN) and V1.6b (Discord/Discourse/Stack Exchange) handle those separately.

**`WebsiteCrawlSource`** — implements V1.5a's `DataSource` Protocol; one instance per user-registered domain. Tier defaults to L2; L1 requires explicit confirmation matching ADR-014's L1 gating.

**`Crawl4AIAdapter`** — wraps `crawl4ai.AsyncWebCrawler` behind the V1 `SourceAdapter` Protocol. Honors robots.txt absolutely (no override), sends an env-driven non-empty UA string (`SecBrain/1.6 (+<contact_email>)`), uses ETag / Last-Modified / content-hash for incremental dedup, handles HTML / PDF / xlsx / image / `<table>` in one pass.

**`ScrapingBeeFallback`** — opt-in per domain (default off). Activates only after 3 consecutive 403/429/503 OR DataDome / PerimeterX / Cloudflare-challenge detection. ScrapingBee sees only URL + UA + (optional) referer — no PII (NFR-1.6a-8).

**Staged graph ingestion** (ADR-020) — three opt-in levels per domain:

| Stage | Cost | Equivalent V1 pass |
|---|---|---|
| **L0** sitemap graph | $0 (deterministic) | Pass 1 (structural) |
| **L1** entity-tagged graph | ~$0 (local GLiNER2 + BGE + rapidfuzz canonical match) | Passes 2 + 3 |
| **L2** full web GraphRAG | LightRAG-class ~$0.001/page | Passes 4 + 5 |

L2 budget gating fires at 3 points: pre-run projection (`avg × queued × 1.2`), cumulative inside the run, and dispatcher boot. L1 conflicts route through the existing V1 6-step conflict chain (step 5 hits V1.5c's `WebVerificationAgent` — no new web-verification infrastructure).

**New graph node types** (all bitemporal per ADR-005): `Page`, `Sitemap`, `MediaAsset`, `Table`, `ExternalRef`. New edges: `LINKS_TO`, `BELONGS_TO_SITEMAP`, `EMBEDS`, `TABLE_OF`, `HAS_CHUNK`, `MENTIONS` (extension to web pages), `REFERENCES_TOPIC`, `IN_CLUSTER`, `SUMMARIZES`, `CLAIMS_FROM`, `SUPPORTS`/`CONTRADICTS`.

**Scheduler** — `flows/website_crawl_dispatcher.py` runs as a Prefect cron every 5 minutes, picks up due `crawl_jobs` rows, dispatches per-domain workers. Single-domain failures don't block other domains (NFR-1.6a-5). Per-domain max 16 simultaneous fetches (default 4); workstation max 16 domains running at once.

**Budget + blocklist** — every registered domain carries pages/USD caps; cap hit auto-pauses the domain + emits `crawl_cap_hit` HITL item. `src/ingestion/sources/blocked_domains.py` carries the seed forum/social blocklist; modifications require Mahyar sign-off per AGENTS.md "Human approval required".

**UI** — five pages under `/ingest/web/*`: domain list, register wizard (6 steps), domain detail (Overview/History/Pages/Entities/Clusters tabs), single-page detail (with bitemporal version timeline), per-domain settings. `/settings/web-search` gains a "Crawl proxy" tab for ScrapingBee health check.

**MCP outbound surface** — 6 tools: `register_crawl_domain`, `list_crawl_domains`, `get_crawl_status`, `trigger_crawl_now`, `pause_crawl_domain`, `update_crawl_cadence`. Every call writes an `audit_log` row.

## Not in V1 (explicit deferrals)

- Crawler (separate system, separate repo).
- Downstream PM / marketing / SEO / search-verification / analyst agents — V2 (V1.5c adds PM/Social/Marketing as dashboards, NOT autonomous agents).
- Web HITL UI — moved to V1.5b.
- Multi-tenant + external use — V2.
- Real-time / streaming ingestion — V2 (V1.5 uses daily batch).
- All 5 trust tiers active — V1 demonstrates L1 + L5; L2 added in V1.5a via connector tiering; L3+L4 plugins V1.6 or V2.
- V1.1 logistic-regression user-credibility upgrade (gold-set dependent).
- Cross-vendor LLM-as-judge calibration set (V2 if judge moves beyond same-tier same-year).
- Distillation pipeline (V2; R-008's V2 projection).
- Convenience MCP tools (`get_top_concerns_by_audience`, `get_sentiment_distribution`) — folded into V1.5c per-team dashboards.
