# Plan

> **Sequencing rule:** Every phase below uses TDD per AGENTS.md — failing test first, smallest correct change, targeted tests, broader tests, docs updated, then move on.
>
> **R5 revision** (2026-05-20): replaces the previous 11-phase linear plan with a **5-pass architecture**. Each pass is a Prefect 3 flow per ADR-010.
>
> **Implementation blocked until**: bake-off ADR-001 ratified, `tools/graphrag/` repo MCP server verified, Mahyar's go-ahead.

## Phase 0 — Prereqs (gating)

| # | Item | Owner | Status |
|---|---|---|---|
| 0.1 | Graph-DB bake-off complete + ADR-001 ratified | Claude + Mahyar | Unblocked R5; execution pending |
| 0.2 | `tools/graphrag/` repo MCP server up + verification checklist passing | Claude (R5 OK'd) | In progress |
| 0.3 | ADR-003 (5-pass extraction) + ADR-010 (Prefect 3) + ADR-011 (gateway + MCP policy) landed | Claude | **Done** R5 |
| 0.4 | Q-016 budget — replaced by R5 "cost-efficient by design, no cap" | Mahyar | **Closed** R5 |
| 0.5 | Q-021 outbound MCP endpoints | Mahyar | **Closed** R5 (all 6 endpoints OK'd) |
| 0.6 | Q-026 Reddit/SDN credibility split | Mahyar | **Closed** R3 (two parallel rubrics per ADR-008) |
| 0.7 | `.env.example` complete | Claude | **Done** R4 |
| 0.8 | Prefect 3 installed + local server running | Claude (Phase 1 setup) | Pending |

## Pass 1 — Structural graph (deterministic, $0)

Implements FR-1.1 / FR-1.2 / FR-1.3 / FR-1.4 / FR-1.5 + the rapidfuzz canonical match + user-credibility computation (ADR-008).

1. **Failing-first test**: `test_pass1_idempotent.py::test_register_dump_then_pass1_idempotent` — same input + content-hash → identical Pass-1 outputs (nodes + edges + credibility scores).
2. **Smallest code**:
   - `src/ingestion/api.py` `register_dump(...)` validates manifest, content-hashes, stores raw.
   - `src/ingestion/adapters/l1_excel.py` — ADEA Report 2 (5 yearly files) → `l1_school` + `l1_school_year_metric` in SQLite.
   - `src/ingestion/adapters/l5_reddit.py` — r/DentalSchool posts + comments → canonical Posts/Comments/Users with bitemporal 4-tuple.
   - `src/ingestion/adapters/l5_sdn.py` — Pre-Dental category subset (1K threads).
   - `src/extraction/pass1_structural.py` — assembles structural edges (AUTHORED, REPLIED_TO, BELONGS_TO_THREAD, POSTED_IN_FORUM, UPVOTED).
   - `src/extraction/pass1_fuzzy_match.py` — `rapidfuzz` `token_set_ratio` against canonical school + program list (derived from ADEA + CODA Excel, or Mahyar's curated list if provided). Threshold ≥ 95.
   - `src/credibility/api.py` + `reddit_rubric.py` + `sdn_rubric.py` — per ADR-008 source-aware split.
   - `flows/pass1_structural.py` — Prefect flow orchestrating the above.
3. **Targeted tests**: per-adapter unit tests; idempotency; bitemporal correctness; fuzzy-match precision + recall on a 50-mention seed gold set.
4. **Acceptance**: 274K Reddit + 1K SDN + 5 ADEA years ingested; `l1_school` ≥ 56 schools; every node + edge has full property convention.

## Pass 2 — Cheap labels ($0)

Implements A-065. Promotes Reddit `link_flair_text` + SDN `category` to `Topic` nodes.

1. **Failing-first test**: `test_pass2_labels.py::test_reddit_flair_promoted_to_topic` — given a post with `link_flair_text = "Acceptance"`, a `Topic:acceptance` node materializes + `REFERENCES_TOPIC` edge.
2. **Smallest code**:
   - `src/extraction/pass2_labels.py` — read each Post node's metadata, emit `Topic` + `REFERENCES_TOPIC` edges. Null-safe (some Reddit dumps may lack flair fields per GAP-037).
   - `flows/pass2_labels.py` — Prefect flow; runs after Pass 1 in the daily DAG.
3. **Tests**: null-handling on missing flair; SDN-category-to-Topic mapping; idempotency.
4. **Acceptance**: ~20-50 `Topic` nodes (depending on flair distribution); every Post in a flaired thread has at least one `REFERENCES_TOPIC` edge.

## Pass 3 — Semantic clustering (~$0 local GPU)

Local embeddings + signed-graph community detection.

1. **Failing-first test**: `test_pass3_clustering.py::test_cluster_dental_school_selection_topic` — fixture of 100 posts about school-selection produces a coherent cluster (silhouette > 0.4 + cluster summary mentions "school selection").
2. **Smallest code**:
   - `src/extraction/pass3_embeddings.py` — BGE-small embeddings on post + comment bodies; SQLite + Parquet embedding store (content-hash keyed).
   - `src/extraction/pass3_clustering.py` — HNSW + signed-graph community detection per ADR-006.
   - `src/extraction/pass3_summarize.py` — per-cluster summary call via Gemini Flash-Lite (one call per cluster).
   - `flows/pass3_clustering.py` — Prefect flow; runs after Pass 2; weekly full rebuild + daily incremental.
3. **Tests**: cluster-summary call goes through gateway (no direct vendor SDK); idempotent re-embedding via content-hash; SUPPORTS/CONTRADICTS detection accuracy.
4. **Acceptance**: cluster count in expected range (50-200 for V1 slice corpus); cluster summaries match topic content qualitatively.

## Pass 4 — Selective deep extraction ($35-50 est. full sweep)

LLM tier. Implements FR-2 + utility filter (A-057) + per-task model matrix (A-056).

1. **Failing-first test**: `test_pass4_utility_filter.py::test_filter_drops_bots_keeps_lowkarma_with_entity` — synthetic post mix; filter drops AutoModerator + deleted but keeps a `score=-3` post that mentions "NYU" (prescient_correct candidate).
2. **Smallest code**:
   - `src/extraction/utility_filter.py` — A-057 heuristics.
   - `src/extraction/pass4_routing.py` — confidence-gated routing to Stage 3a / 3b / 3c.
   - `src/extraction/pass4_sentiment.py` — Gemini Flash-Lite via gateway; BAML prompts; Pydantic schema.
   - `src/extraction/pass4_interview_q.py` — Haiku 4.5 via gateway.
   - `src/extraction/pass4_conflict_candidates.py` — Haiku 4.5; escalates to Sonnet 4.6 if confidence < 0.7.
   - `src/extraction/cache.py` — content-addressable (R-008 §1.8).
   - `flows/pass4_llm.py` — Prefect flow; orchestrates filter → routing → 3a/3b/3c → cache write.
3. **Tests**:
   - Cache idempotency: identical input → cache hit on second call.
   - `ttl: 3600` pinned (`lint_ttl_pinning.py` + runtime check).
   - Vendor failover: Gemini Flash-Lite 5xx → Haiku 4.5 fallback.
   - Filter doesn't drop posts containing entities (`prescient_correct` preservation).
4. **Acceptance**: F1 ≥ 0.85 on sentiment gold; F1 ≥ 0.90 on interview-Q precision; cache hit ≥ 80% on warm sweep; V1 slice cost well under $25.

## Pass 5 — Knowledge surfacing ($0 retrieval)

Implements FR-8. Inbound MCP tools + bitemporal `as_of` retrieval.

1. **Failing-first test**: `test_pass5_query_graph.py::test_citation_traceability_99pct` — runs 200 representative queries; ≥ 99% of results carry `references`.
2. **Smallest code**:
   - `src/retrieval/api.py` — `RetrievalService.query_graph(...)`.
   - `src/retrieval/ranking.py` — `tier × rank × HALO decay × credibility` weight per ADR-007.
   - `src/retrieval/rrf.py` — HNSW + BM25 + RRF per ADR-002.
   - `src/retrieval/mcp/inbound.py` — wrap `query_graph` + `get_canonical_entity` as MCP tools.
   - `src/mcp/outbound.py` — `register_dump`, `get_gaps`, `get_research_needs`, `is_url_ingested`, `get_topic_state`, `get_pending_verifications`.
3. **Tests**: p95 latency < 250 ms; bitemporal `as_of` reconstructs past snapshot; MCP contract tests for all tools.
4. **Acceptance**: V1 retrieval MCP callable from Claude Code; all 200 representative queries return expected shapes; AC-5 + AC-6 + NFR-1 pass.

## Phase 6 — Conflict resolver + HITL + audit + verification

These cut across Pass 1-5 and are integrated as the passes land.

1. **Conflict resolver** (`src/conflict/resolver.py`) — 6-step order per ADR-006; runs at the end of Pass 4.
2. **HITL CLI** (`src/hitl/cli.py`) — `hitl pull` + `hitl commit`; ties into the borderline outputs of Pass 1 (fuzzy 70-94%), Pass 4 (low confidence), and conflict resolver (irreducible).
3. **Audit log** (`src/observability/audit.py`) + `lint_ttl_pinning.py` — all from R4; verified at Pass 1 + 4.
4. **Verification Before Completion** report → `/.agent/reports/v1-slice-01.md`.

## Risk register (R5-updated)

| Risk | Mitigation |
|---|---|
| Bake-off slips → blocks Phase 0.1 | All Pass 1-5 code is graph-DB-agnostic via `GraphClient` Protocol; swap adapters when ADR-001 lands |
| Utility filter over-aggressive → drops `prescient_correct` candidates | Audit 1% sample post-Pass 4 weekly (GAP-035); tune filter |
| Pass 3 cluster naming churns across sweeps | Document in `known-issues.md` (GAP-039); revisit in V1.x with deterministic-seed clustering |
| Reddit dump lacks `link_flair_text` on older posts (GAP-037) | Adapter null-handles; older posts get clusters from Pass 3 only |
| Prefect on Windows daemon model (GAP-040) | Verify during Phase 0.8; fallback = manual `prefect server start` + Task Scheduler trigger |
| F1 below targets | Threshold-ablate auto-accept; expand HITL routing; per-task model tier escalation |
| Daily cadence creates audit-log growth | Archive policy: monthly partition; retain 12 months in primary SQLite, older to Parquet cold-store |

## Provisional time estimate (after Phase 0 gates pass)

| Pass / Phase | Hours |
|---:|---|
| 1 — Structural graph + fuzzy + credibility | 28 |
| 2 — Cheap labels | 8 |
| 3 — Semantic clustering | 20 |
| 4 — Selective deep extraction (filter + routing + 3a/3b/3c) | 24 |
| 5 — Retrieval MCP | 16 |
| 6 — Conflict + HITL + audit + verification | 16 |
| **Total** | **~112 hours** (3 focused weeks) |

(Down from prior 120-hr estimate; Pass 2 + Pass 3 simplifications + Prefect taking care of orchestration.)
