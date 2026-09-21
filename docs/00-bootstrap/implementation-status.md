# Implementation Status — Single Source of Truth

> **Why this file exists.** The review of 2026-05-29 found capabilities documented as
> "Locked"/"accepted" that were never wired into the running pipeline (root cause:
> `why-drift-happened.md`). "Locked" and ADR-`accepted` mean **a decision was made**, not
> **code runs**. This file is the one place that tracks *what actually runs*. Any doc that
> claims a capability is done must agree with this table. CI doc-lint enforces it.

## Status vocabulary (use these exact words everywhere)

| Status | Meaning | Bar to claim it |
|---|---|---|
| **Decided** | An ADR chose this. No code obligation yet. | ADR exists. ("Locked"/"accepted" = this and only this.) |
| **Built** | Module exists and passes unit tests **in isolation**. | Tests green in `tests/`. |
| **Wired** | Reachable from the real end-to-end entrypoint (CLI / flow / API), not just tests. | A non-test call site exists — cite `file:line`. |
| **Validated** | Wired **and** exercised on real `External Data/` corpus with a saved report. | `.agent/reports/*` with real-data evidence. |

A capability is **not "done" below `Wired`.** `Built`-but-not-`Wired` is a gap, logged in
`gap-register.md` — never closed as complete.

## Current status (2026-05-29, pre-V1.7-patch)

| Capability | ADR | Doc says | **Actual** | Wiring site / gap |
|---|---|---|---|---|
| Graph store = Kùzu | ADR-001 | "pending bake-off" ❌ | **Validated** | `src/graph/kuzu_client.py`; bake-off `tools/bake_off/`. *(Docs stale — fixed in V1.7.)* |
| Vendor-lock gateway (no SDK imports outside `src/gateway/`) | ADR-011 | enforced | **Validated** | `src/gateway/*`; rule holds in code. ✅ |
| L1 gold ingest from DJ-Backup DB dump (schools + alias backbone) | ADR-014 | — | **Validated** | `src/ingestion/adapters/l1_db.py` → `src/cli.py:175` `ingest l1-db`; no-server `pg_restore --data-only` COPY parse → 78 L1 `School` nodes (gold facts as props) + 505 canonical aliases; idempotent re-run (counts stable); `.agent/reports/v1.7-l1-db-ingest-validated.md`. Cleaner than ADEA Excel (no aggregate-row artifacts — GAP-056). |
| L1 gold ingest from DJ-Backup DB dump (residency: specialties/institutions/programs) | ADR-014 | — | **Validated** | `src/ingestion/adapters/l1_residency.py` → `src/cli.py` `ingest l1-residency`; same no-server COPY parse → 30 `Specialty` + 289 `Institution` + 817 `Program` L1 nodes + 1634 edges (817 `OFFERED_BY` + 817 `IN_SPECIALTY`, 100% linkage); specialty aliases (OMFS/Perio/Endo …) extend the canonical ER backbone (1097 aliases total); idempotent; additive (78 schools untouched). `.agent/reports/v1.7-l1-residency-ingest-validated.md`. |
| 5-pass structural ingest (Pass 1–2) | — | done | **Validated** | `src/extraction/pass1_structural.py`, `pass2_*`; `real-data-smoke-2026-05-21.md`. |
| Pass 3 semantic clustering | ADR-006 | "signed-graph community detection" ❌ | **Built** (`MiniBatchKMeans` + `signed_spectral`) | `src/extraction/pass3_clustering.py`. Signed-spectral **Built 2026-06-17** → `method="signed_spectral"`, BNC-style signed Laplacian + scipy eigenvectors + KMeans; falls back to plain KMeans when no opinion labels; 5 tests green (`tests/extraction/test_pass3_clustering.py`). GAP-049 closed. |
| Pass 4 selective extraction (sentiment/Q/claims) | ADR-003 | done | **Validated** (single sweep) | `src/extraction/pass4_*`; `pass4-live-smoke-2026-05-21.md`. |
| Trust-tier-aware retrieval ranking (`w_tier×w_rank×decay×cred×consistency`) | ADR-021/007 | "Locked" | **Wired** | `src/retrieval/ranking.py` (scorer) + `src/retrieval/consistency.py`; wired in `src/retrieval/api.py` `query_graph` via `rank_query_results`. Minority-correct fixture in `tests/retrieval/test_ranking.py`. GAP-048. |
| HALO temporal decay | ADR-007 | "accepted" | **Wired** | `src/conflict/halo_table.py` `decay()`, consumed by `src/retrieval/ranking.py`. Tests `tests/conflict/test_halo.py`. GAP-050. |
| Hybrid retrieval (BM25+HNSW+RRF) | ADR-002 | "Locked architecture" | **Wired** | `HybridIndex` (`src/retrieval/index.py`) built from `graph.all_nodes()` + passed to `RetrievalService(hybrid_index=)` in `src/cli.py` `query`; `_seed_lookup` consumes it. Tests `tests/retrieval/test_hybrid_wiring.py`. GAP-051. |
| Conflict cascade steps 1–3 (L1 / temporal / credibility) | ADR-006 | done | **Wired** | `src/conflict/resolver.py`; `src/cli.py:899`. ✅ |
| 3-vendor LLM-as-judge tie-break (family-exclusion + independent vote) | ADR-006/024 | "Locked" | **Wired** | `src/conflict/judge.py`; built via `src/conflict/factory.py` `build_three_vendor_judge`; passed to `ConflictResolver` in `src/cli.py` (`reconcile_demo`, `resolve`) + `flows/pass4_llm.py`. Resolves real Claim ties via `src/conflict/pass4_resolution.py`. GAP-052. *(Wired; real-data 3-vendor validation awaits a corpus with actual same-tier ties.)* |
| Web-verification (Tavily 3-signal) | ADR-016 | "shipped" | **Wired** into resolver | `src/conflict/web_verify.py`; `build_web_verifier` passes it to `ConflictResolver` in `src/cli.py` + `flows/pass4_llm.py`. GAP-052. |
| Bitemporal supersede (atomic `t_ingest` close/open) | ADR-005 | non-negotiable #3 | **Wired** | `src/graph/kuzu_client.py` `supersede_edge` (edge primitive; `tests/graph/test_supersede_edge.py`). GAP-053 caller **Wired 2026-06-17**: `src/conflict/l1_claims.py` `supersede_l1_claim_if_changed()` — archives old L1 Claim node under timestamped id, tags new node with `supersedes` back-ref; wired into `build_db_fact_claims(check_supersede=True)` → `cloud/tier1_l1_claims.py`. 10 tests green (`tests/conflict/test_l1_supersede.py`). |
| User credibility (Reddit/SDN split rubric) | ADR-008 | done | **Built/Wired** | `src/credibility/*`; computed in Pass 1. |
| External DB connectors (PG/MySQL/SQLite/Neo4j) | ADR-014 | shipped | **Built** | `src/ingestion/sources/*`; needs Docker for full validation (Q-027). |
| Cross-graph entity mapping | ADR-015 | shipped | **Built** | `src/er/cross_graph.py`. |
| Feedback loop (feedback_log + context loader) | ADR-017/018 | shipped | **Built** | `src/extraction/feedback_context.py`; live quality-lift unvalidated (W1-7). |
| Website crawler (L0/L1/L2 staged) | ADR-019/020 | shipped | **Built** | `src/ingestion/` web + flows; not run on a real domain at scale. |
| Web UI (`/ingest/web/*`, graph views) | ADR-012/013 | shipped | **Built** | `web/`; Playwright/axe present. |
| V1 core slice (ADEA L1 + r/DentalSchool L5 → Pass 1–4 → cited retrieval) | — | target | **Validated** (bounded sample) | `.agent/reports/v1.7-wp2-core-slice-validated.md` — 8403 nodes / 16663 edges on real data; cited `query`; idempotent re-run (counts stable); ~$0.003; CPU-only (GAP-054); Q-028 did not recur. Full-volume ingest = scaling run. **WP3 gate re-run (2026-05-29) green:** tier-as-prior ranking (WP3.2) + hybrid seed lookup (WP3.3) + conflict `resolve` (WP3.4) now live on this path; `query` returns cited results. |
| CI doc-lint (doc↔code truth guard) | — | new (V1.7 WP1) | **Validated** | `tools/doc_lint/check_status_truth.py` + `tests/doc_lint/*` (32 tests). Checks A (ADR related-code existence), B (no stale Locked/done claim for a below-Wired capability), C (ConflictResolver stub-wiring) — all green on the real repo; wired into `pytest`. |

## SOTA adoption status (from R-010, decided 2026-05-29)

| SOTA item | ADR | Status |
|---|---|---|
| Tier-as-prior scoring + RA-RAG cross-source consistency | ADR-021 | **Decided** → V1.7 |
| Embedder swap → Qwen3-Embedding-0.6B (blocking) | ADR-022 | **Wired** — `src/embeddings/qwen_embedder.py` behind `EmbeddingService` + `--embedder qwen`; A/B recall ≥ BGE (`.agent/reports/v1.7-wp4.2-embedder-ab.md`). **LLM-matcher fallback Wired** (`src/er/llm_matcher.py`; `ingest l5-reddit --llm-matcher`; gateway `ENTITY_MATCH_HARD`). **NER A/B done → NuNER-Zero adopted** (bake-off F1 1.00/type 0.91 vs GLiNER-v2.1 0.97/0.82 vs rapidfuzz 0.77; `tools/ner_bakeoff/`, `.agent/reports/v1.7-wp4.2-ner-bakeoff.md`); `src/extraction/ner_mention_extractor.py` **Built** (optional, gliner lazy import) — not yet wired into the ingest CLI. |
| LLM-matcher fallback for low-confidence ER | ADR-022 | **Decided** → V1.7 |
| Calibrated cascade routing + learned first-hop router | ADR-023 | **Wired (default off)** — `src/gateway/routing.py` `CalibratedCascade` + `calibration.py`; `default_gateway()` registers it for Pass-4 conflict/interview tasks under `SECBRAIN_CASCADE=1`. Identity calibrator + router off until a trace set exists → cost-regression safe. Q-031 → option a (built the in-task cascade). |
| LLM-judge family-exclusion + independent-vote hardening | ADR-024 | **Decided** → V1.7 |
| GraphRAG engine evaluation (LightRAG/Graphiti vs custom) | ADR-025 | **Spike run (bounded)** — store bake-off on real data (`tools/graph_engine_bakeoff/`): embedded Kùzu wins shallow (point-lookup 0.21 ms vs Neo4j 3.28 ms), Neo4j wins deep multi-hop (3-hop 2.36 ms vs Kùzu 14.19 ms); both 16× under the 250 ms budget. LightRAG/Graphiti need an LLM for graph construction → would replace our deterministic L1-grounded pipeline. **Recommendation: keep Kùzu** (refactor to native typed schema if multi-hop dominates; Neo4j migration only then, human-approval). Stays `proposed`. `.agent/reports/v1.7-wp5-adr025-graphrag-engine-spike.md`. |
| Learned/probabilistic truth-discovery vs deterministic cascade | ADR-026 | **Hybrid Built + Wired (default off)** — the bake-off recommendation is now real: `src/conflict/joint_resolver.py` `L1AnchoredJointResolver` (current-L1 immutability + HALO-decayed joint-confidence mass + abstain band). Bake-off candidate (c) = (b)'s accuracy 0.88 + minority recall 1.00 **and** fixes C3 (current L1 protected) + abstains on C8. Wired into `resolve_pass4_conflicts` / `src/cli.py:986` / `flows/pass4_llm.py` via `build_joint_resolver_if_enabled()` under `SECBRAIN_JOINT_RESOLVER=1`. Validated end-to-end on the real CLI over the 78-school L1 graph (`.agent/reports/v1.7-wp5-adr026-joint-resolver-wired.md`). ADR-026 stays `proposed`; default stays off pending real HITL labels. |

## Update (2026-06-09 — full-corpus runs + resolution layer)

Evidence: `.agent/reports/v1.7-full-corpus-runs-2026-06-09.md`. Rows here supersede the
2026-05-29 table where they overlap.

| Capability | **Actual** | Wiring site / evidence |
|---|---|---|
| Pass-1 structural ingest, full corpus (Reddit + 5 SDN forums) | **Validated** | VM runners `cloud/run_pass1_vm.sh`, `cloud/ingest_sdn_batched.py` → 1,371,415 Post / 1,953,599 Comment / 288,294 User nodes (877,128 posts with text). |
| Pass-4 selective extraction, full corpus | **Validated** | `cloud/pass4_run.py` + gateway `oss` variant (`src/gateway/api.py` `_wire_extraction_models` Plan-B block) → 496,665 Sentiment / 51,673 Claim / 7,138 InterviewQuestion; $119.34; 1 failed post. |
| Pass-3 clustering, full corpus | **Validated** | `cloud/pass3_run.py` (source=all) → 99 Cluster nodes + 877,188 IN_CLUSTER edges; $0.0057. KMeans method used for corpus run; `signed_spectral` method now Built (GAP-049 closed 2026-06-17). |
| Pass-4 model selection benchmark (cheap-model sweep vs gpt-5.4 gold) | **Validated** | `cloud/bench/` (sweep/score/prompts); winner gpt-oss-20b bulk + Llama-3.3-70B conflict; leaderboard in report. |
| Gateway request timeout/retry hardening | **Wired** | `src/gateway/openai_adapter.py` (`timeout`, `max_retries` on `OpenAIAdapter`). |
| Predicate normalization + per-school ForumConsensus layer | **Validated** | `cloud/resolve_and_persist.py`, `cloud/resolve_l1_cleanup.py` → 40,606 Claims tagged `predicate_canonical`/`resolved_school_id`; 432 ForumConsensus nodes + CONSENSUS_FOR edges (ADEA Table-1 agreement on tuition/fees). |
| L1 gold facts as Claim nodes (ADR-026 anchor on organic conflicts) | **Validated** | `cloud/tier1_l1_claims.py` (uses `src/conflict/l1_claims.py` predicate maps) → 4,750 L1-tier Claim nodes in-graph. |
| Entity dedup bridging (School↔School + Institution↔School) | **Validated** | `cloud/merge_schools.py` + `cloud/tier1_l1_claims.py` → 274 SAME_AS edges (51 school dup groups + 48 institutions). |
| Pass-4 edge dedup (killed-run overlap) | **Validated** | `cloud/tier1_dedup_edges.py` → 8,752 dup edges removed; ANNOTATES/REPORTED_AT/EXTRACTED_FROM each exactly equal node counts. |
| InterviewQuestion→School linkage | **Validated** | `cloud/tier1_iq_links.py` → 1,951 ASKED_AT edges (83% of school-tagged questions). |
| Cluster hygiene (junk flags + label dedup) | **Validated** | `cloud/tier1_clusters.py` → 10 `is_junk` flags; 0 duplicate labels. |
| Kùzu compaction recipe (update-bloat) | **Validated** | `cloud/compact_graph.py` / `cloud/compact_local.py` — EXPORT→IMPORT, counts verified (182→5.3 GB VM; 13.25→5.87 GB local). |
| KB ask agent (NL question → grounded, cited answer) | **Wired + smoke-validated** | `src/retrieval/kb_agent.py` (productionized); CLI `src/cli.py` `ask`; API `src/web/routes/ask.py` `POST /api/v1/ask` (+ `/ask/health`), registered in `src/web/app.py`. Smoke on the full graph: CLI Columbia GPA/DAT answer; API affordability + sentiment answers grounded with ADEA labels. |
| Web app + ask agent share one Kùzu handle | **Wired** | Kùzu locks the DB file per `Database` handle → `src/web/graph_db.py` `shared_database()` + `KuzuGraphClient(database=)` injection (`src/graph/kuzu_client.py`); `/api/v1/graph/*` + `/api/v1/ask` coexist in one process. |
| Graph-route seed search at full-corpus scale | **Wired (fixed)** | `src/retrieval/api.py` `_seed_lookup`: substring predicate pushed into Kùzu (a bare `LIMIT` scan only ever read the first rows — all empty-props Posts → 0 hits) + per-level label filter so Level B Cluster seeds aren't crowded out. `/graph/structural|clusters|analyzed` verified returning real results. |
| Web console frontend on the real graph | **Runs (graph canvas = pre-existing stub)** | Next.js console boots clean (0 console errors), proxies to the API via `NEXT_PUBLIC_API_BASE`; HITL/ingest/audit pages render. The graph results canvas/table is an explicit V1.5b Phase-3 stub ("Sigma.js ships in Phase 3"; `// TODO: redesign-W3-2`) — backend payloads verified by API instead. |
| Hybrid retrieval at full-corpus scale | **Gap closed (semantic path Validated)** | Persisted embeddings replace embed-at-query-time: `cloud/embed_posts.py` → 18 fp32 shards (877,188 vectors, 1.27 GB, BGE-small, 130.9 m CPU) + `post_text.db` sidecar (0.51 GB) → `src/retrieval/semantic_index.py` `SemanticIndex` (top-k cosine + quotable snippets; **34 ms warm query**), consumed by `KBAgent` (`evidence_posts` on school profiles + `semantic_posts` fallback). Legacy `HybridIndex.build()` path remains sample-only. |
| Pass-4 over comments — Plan D (junk rules + task gating + thread context) | **Validated (2026-06-10)** | `cloud/pass4_comments.py` (+ measured design `cloud/comment_cost_analysis.py`). 1,953,599 comments → 311,420 processed (junk 579,370; no-signal 821,876; no-author/bot 166,994; no-text 73,939); 366,212 LLM calls (93% of brute-force eliminated). **Result: +171,508 artifacts — 143,779 comment SentimentAnnotations (ANNOTATES→Comment), 26,869 Claims, 860 InterviewQuestions — for $34.05 in 3.5 h** (vs ~$146 unfiltered). Totals now: sentiment 640,444 / claims 83,292 / interview-Qs 7,998. Counts re-query-verified to the unit; graph recompacted. |
| L1 official-source registry (which publishers qualify as ground truth) | **Validated (2026-06-11)** | `docs/07-data/l1-official-source-registry.md` — 20 domains; rounds 1–2 via 3-vote adversarial deep-research (49 surviving claims, 1 refuted), round 3 via direct primary-source fetches. Explicit "no single authoritative source" list (per-school ground-truth pockets). |
| L1 official-source crawl — full corpus in canonical graph | **Validated (2026-06-12)** | 10 registry domains crawled (8 local + ada.org/adea.org on EC2 after local-PC freezes), merged + compacted on the VM, swapped local. Final canonical graph: **4,558,352 nodes / 13,103,287 edges / 6,866 Page** (5,203 open-version crawl pages + 1,663 bitemporally-closed ada.org duplicates from a killed run) **+ 13,570 Chunk + 21,455 MENTIONS**, all `source_tier=L1`; counts verified identically on VM pre-compact, post-compact, and locally post-swap. 15.2→6.6 GB. Evidence: `.agent/reports/v1.7-l1-crawl-batch-2026-06-11.md`. Deferred: cdac-cadc.ca + HRSA (honest-UA 403), programs.adea.org (JS SPA). |
| Website crawler — production wiring (was Built-not-Wired) | **Wired + smoke-validated (2026-06-11)** | The V1.6a parts existed but nothing composed them (dispatcher's worker was test-only; "Run now" enqueued rows nothing consumed; no URL discovery). NEW `flows/website_crawl_worker.py` (`crawl_domain_once`/`make_worker`: robots-sitemap discovery → BFS fallback → `Crawl4AIAdapter` fetch → L0 → L1 → optional L2 + fetch-log/pages_index/jobs bookkeeping); CLI `src/cli.py` `crawl register|run|tick`; UI path `src/web/routes/website_crawl.py` `run_now` → BackgroundTasks → `_execute_due_jobs` (dispatcher tick with real worker on the shared Kùzu handle). Smoke on real domain natmatch.com (sandbox graph): 23 Page + 38 Chunk + 74 MediaAsset + 47 ExternalRef nodes, 345 LINKS_TO edges, tier=L1, 0 errors; re-run idempotent (23 unchanged, 0 rewrites); real NMS stats PDF text-extracted (2,965 chars). |
| Crawler bug fixes (would have corrupted the graph) | **Fixed (2026-06-11)** | (1) `flows/website_l1_entity_tagged.py` wrote Entity *stubs* at canonical ids unconditionally — `KuzuClient.upsert_node` is full-overwrite ⇒ first crawl mentioning a school would have **clobbered the real L1 School node**; now guarded by `get_node` (stub only when absent). (2) `flows/website_l0_sitemap.py` per-record `nodes_of_label` scan (O(N·P) + silent 10K cap) → single prebuilt url→open-page map (cap 1M). (3) `crawl4ai_web.py` PDFs/XLSX produced empty bodies → pypdf text extraction (300-page cap) + pandas sheet→TableRecord parsing (XLSX/CSV; 5K-row cap) — official PDFs/spreadsheets ARE the L1 payload. (4) `?status=deleted` filter always empty (filtered `list_active()`); (5) `CanonicalIndex.reload` crashed on fresh DBs without anchor tables. |

## Update (2026-06-17 — V1-June12 bundle + Evidence Answer Engine design)

### V1-June12 portable data bundle

| Capability | **Actual** | Wiring site / evidence |
|---|---|---|
| documents.sqlite (thread-complete raw store) | **Validated** | `cloud/build_documents_sqlite.py` → 3,325,014 docs (877,128 posts + 1,953,599 comments + 288,294 SDN entries); indexed on thread_id/parent_id/doc_type; tolerant JSON parse on empty/malformed props; 1.79 GB. |
| Parquet graph export (engine-independent) | **Validated** | `cloud/export_graph_parquet.py` → `graph/nodes.parquet` (4,558,352 rows) + `graph/edges.parquet` (13,103,287 rows); `graph/kuzu_export/` schema.cypher + per-label parquet. Counts verified on VM and locally post-swap. |
| Self-contained MCP server (bundle-local) | **Validated** | `cloud/bundle_assets/mcp_server.py` → tools: `search_corpus` (LIKE scan), `get_document`, `get_thread`, `list_l1_sources`, `corpus_stats`; resolves bundle root from `SECBRAIN_BUNDLE` env or parent-dir walk; no graph engine required. |
| DuckDB query layer (Parquet) | **Validated** | `cloud/bundle_assets/load_duckdb.py` → `CREATE VIEW nodes/edges AS read_parquet(...)`, label counts + ForumConsensus queries demo. |
| V1-June12 zip bundle | **Validated** | `cloud/assemble_bundle_vm.py` → MANIFEST.json (per-file sha256 + counts, 54 files, 5.1 GB assembled); final download `secbrain-corpus-V1-June12.zip` (3.27 GB, md5 a5a2abf4893d56a26cf57e7204d82f36). |
| Bundle documentation (README / DATASET_CARD / LICENSING / data-dictionary) | **Validated** | `cloud/bundle_assets/README.md` (3-way quickstart: MCP, DuckDB, SQLite), `DATASET_CARD.md` (Datasheet-for-Datasets), `LICENSING_AND_USE.md` (per-source licensing + PII), `data-dictionary.md` (field-level schema), `.mcp.json.example` (copy-paste MCP connector). |

### Evidence Answer Engine (EAE) — **Wired 2026-06-17**

All 7 EAE steps implemented in `src/retrieval/kb_agent.py` `evidence_answer()`, exposed at
`POST /api/v1/evidence` (`src/web/routes/evidence.py`). 24/24 unit tests green (`tests/retrieval/test_eae.py`).
FTS5 comment-recall scripts ready for EC2 VM (`cloud/add_fts5_documents.py`).

| EAE step | **Actual** | Wiring site |
|---|---|---|
| R1 — Source-typed evidence counts | **Wired** | `src/retrieval/kb_agent.py` `_typed_counts()` + `evidence_answer()` → `typed_counts` field. GAP-057 closed. |
| R2 — Tier-weighted reliability (most_reliable surfacing) | **Wired** | `_score_evidence_items()` applies `ranking_score()` with `EAE_TIER_WEIGHTS={L1:1.0,…,L5:0.4}` (GAP-058 fix); `evidence_answer()` → `most_reliable` = top-3 L1 + top-3 L5. |
| R3 — Popular-vs-correct adjudication | **Wired** | `_popular_vs_correct()` compares L5 majority vs L1 Claim snippets (number-overlap heuristic); verdict: `"agrees" \| "contradicts" \| "no_l1_data" \| "insufficient_evidence"`. `consistency()` from `src/retrieval/consistency.py` (RA-RAG) used in `_score_evidence_items()`. GAP-058 closed. |
| R4 — KPA-lite stance clustering | **Wired** | `_kpa_stance()`: LLM-powered when key present; polarity-keyword fallback always available. `opinion_distribution` from `_opinion_distribution()` (SentimentAnnotation counters per school). GAP-059 closed (KPA-lite). |
| R5 — Popular-vs-correct verdict + citation | **Wired** | `evidence_answer()` emits `popular_answer`, `authoritative_answer`, `verdict`. |
| R6 — Drill-down to individual sources | **Wired** | Every `EvidenceItem` carries `doc_id + url + snippet`; `sources` list in response (up to `max_sources`). `EvidenceItemOut` schema in `src/web/schemas/evidence.py`. GAP-060 closed. |
| R7 — Comment recall (FTS5 / LIKE) + calibrated abstention | **Validated** | `_comment_recall()` uses FTS5 when available (`_check_fts5()`), LIKE-scan fallback otherwise. `_abstain_check()` fires when `n < 3` or max opinion fraction < 40%. FTS5 index built on VM 2026-06-17 via `cloud/add_fts5_documents.py`: **3,325,014 rows indexed in 0.7 min**; smoke: `docs_fts MATCH 'NYU tuition'` → 3 reddit_comment hits. GAP-061 closed. |

**Tests**: `tests/retrieval/test_eae.py` — 24 tests, 0 failures, no Kùzu required (mock graph client).
**Route**: `GET /api/v1/evidence/health` reports FTS5 availability + corpus sizes.
**Smoke (2026-06-17)**: `scripts/smoke_eae.py` PASS — all 3 questions returned correct schema (missing_keys=[] each); evidence sparse on local pre-ForumConsensus snapshot (124 schools, 0 consensus nodes); FTS5 path validated on VM (3,325,014 rows indexed). Report: `.agent/reports/smoke-eae-20260617-211119.json`.

## Update (2026-06-20 — Evidence Dossier Engine, ED-1 … ED-8)

The EAE v2 "Evidence Dossier": every answer is an adjudicated breakdown — typed evidence
counts, most-reliable official sources (L1 facts + article prose w/ URLs), a **counted**
opinion distribution, a popular-vs-correct verdict, drill-down sources, calibrated abstention.
Bundle-artifact-backed (parquet + embeddings + documents.sqlite + reddit_school_link.sqlite),
runs on the VM/bundle (never local Kùzu). Decisions: broad-then-filter, always-counted stance,
L1-trusted adjudication (`project_evidence_dossier`). Brief: `docs/05-features/v1.7-evidence-dossier-brief.md`.

| Step | **Actual** | Wiring site / evidence |
|---|---|---|
| ED-1 comment embeddings | **Validated** | `cloud/embed_comments.py` → 1.95M comment vectors (18 shards) + `comment_text.db`; 274 min on VM. |
| ED-2/2b recall (census + graph-anchored) | **Validated** | `src/retrieval/evidence_census.py`, `graph_recall.py` (`ParquetGraphReader`, SAME_AS union + `BELONGS_TO_THREAD`). NYU: 154,479 SDN structurally linked (~4× over keyword). |
| ED-3 unified recall + filter | **Validated** | `src/retrieval/evidence_recall.py` (school∩topic, exact counts) + `embedding_store.py` floor. Reddit scoped via precomputed `cloud/reddit_school_link.py` → `reddit_school_link.sqlite` (57,913 links, 18s/$0). Perf 20min→11-17s. |
| ED-4 official L1 article retrieval | **Validated** | `src/retrieval/l1_retrieval.py` (13,570 Chunk / 6,866 Page; domain-authority + school-mention). compact→aadbcompact, DAT→cda/ada, NYU+loans→ADA/ADEA. |
| ED-5 counted stance clustering | **Validated** | `src/retrieval/stance.py` (LLM names positions; full set classified by embedding-cosine + counted). Validated on a single-school cost question over ~12.5 K documents (every document classified and counted). |
| ED-6 L1-anchored adjudicator | **Built** | `src/retrieval/adjudicator.py` — verdict ∈ {popular_confirmed, popular_is_wrong, combination, no_official_source, needs_research}; L1-trusted, abstains w/o anchor. 16 unit tests `tests/retrieval/test_dossier_components.py`. |
| ED-7 thread-aware drill-down | **Built** | `dossier.py` `_source_items` (thread_id/parent_id/url/score per source); full relevant id list for pagination. |
| ED-8 engine + route + eval | **Validated** | `src/retrieval/dossier.py` `EvidenceDossierEngine` → `POST /api/v1/dossier` (`src/web/routes/dossier.py`, registered `src/web/app.py:75`; gated on `$SECBRAIN_BUNDLE`). Calibrated abstention (insufficient/no-majority/no-L1/unknown-school). **Eval `scripts/eval_dossier.py` → 6/6 matrix PASS on VM** (school-stat/opinion/process, no-school process, edge unknown-school abstains): a school-level cost question recalls ~15 K forum documents plus L1 facts and articles, verdict `popular_confirmed`, L1-grounded answer; a fictitious school → abstains. Report `.agent/reports/dossier-eval.json`. Live-path LLM gate off (counts exact). |

**Tests**: `tests/retrieval/test_dossier_components.py` — 23 unit tests (FTS query, alias derivation, topic separation, adjudicator verdicts, stance parse/retry/temperature, L1 snippet hygiene), 0 failures, no artifacts required; run on the **EC2 VM** (the full local suite opens Kùzu and crashes the workstation — `project-crawl-ops`).

**Robustness fixes (2026-06-20, found via 10 out-of-domain business questions + run-to-run variance):**
- Out-of-domain over-answering → **semantic L1 relevance floor** (cosine 0.73 vs precomputed chunk embeddings, `cloud/embed_l1_chunks.py`); keyword matching pulled spurious chunks. 10/10 business Qs now abstain.
- Stance/verdict run-to-run flakiness → **`temperature=0`** (gateway `complete(temperature=)`) + retry-on-empty + tolerant JSON parse in `stance.derive_positions`; adjudicator at temp 0.
- Abstain/verdict mixed signal → explicit **`answered`** flag; confident answer suppressed when abstaining.
- Duplicate L1 facts (SAME_AS dupes) → dedup by `(predicate, value)`; nav boilerplate stripped from snippets.
- **End-to-end re-validated on VM: 10/10 fix checks + 6/6 eval + 10/10 out-of-domain abstain.**

**Known follow-ups**: no-school questions are L1-driven (forum opinion needs a school); engine requires the bundle artifacts (`$SECBRAIN_BUNDLE`).

## Update (2026-06-21 — Provenance + SOTA fixes, PV-1 … PV-5)

Five fixes from the 17-question eval (compositional/faceted/faithfulness/provenance/
hydration gaps). All wired into `EvidenceDossierEngine` + route; validated on the VM.

| Step | **Actual** | Wiring site / evidence |
|---|---|---|
| PV-1 per-statistic provenance | **Validated** | `src/retrieval/provenance.py` (`ProvenancedStat` + bounded `ProvenanceStore` + `build_distribution`); `graph_recall.sentiment_for` (verdict→exact ids); `stance.py` retains full per-position ids; `dossier.answer` emits provenanced opinion+sentiment; `dossier.sources()` + `GET /api/v1/dossier/sources?stat_id=` drill-down hydrates url+snippet (reddit comment permalinks rebuilt from parent post). Validated: a sentiment split over ~6 K comments drills down to the exact id set behind each bucket. 8 tests. |
| PV-2 deterministic render + entailment guard | **Validated** | `src/retrieval/rendering.py` (`render_grounded_answer` counted-only; `guard_narration` drops verdict sentences with unsupported %/numbers → `filtered_claims`). Fixes #20 reorder/invented-stats. Guard passes real L1 numbers and drops fabricated stats. 9 tests. |
| PV-3 snippet/quote hydration | **Validated** | `src/retrieval/semantic_index.py` now hydrates from `raw/documents.sqlite` (sidecars optional) + `rendering.best_sentence` extractive quote. Fixes #30: "shadowing tips" → 5/5 post + 5/5 comment snippets (was 0/0 → abstain). |
| PV-4 compositional query planner | **Validated** | `src/retrieval/planner.py` (typed ops rank_tuition/rank_sentiment/combine; heuristic floor + LLM enricher) over `cloud/build_school_metrics.py` → `school_metrics.sqlite` (119 schools). `dossier` ranking branch + lazy per-row drill-down (`sources(school,label)`). Fixes #35: "cheapest schools applicants also like" → true intersect; #20 ranking queries → deterministic ordering, junk-free. 9 tests. |
| PV-5 query-scoped sub-topic clustering | **Validated** | `src/retrieval/facets.py` (`is_facet_query`, `facet_terms`, `facet_distribution`) reusing `stance.classify_counted` (extracted kernel); `dossier` facet branch (school→recall, no-school→FTS5) + provenance per sub-topic + `render_facets`. Fixes #36: "interview topics" → 5 counted sub-topics over 3,000 query-relevant docs (not global clusters), each drill-down-able. |

**Tests**: `tests/retrieval/{test_provenance,test_rendering,test_planner,test_facets}.py` +
existing `test_dossier_components.py` — **56 retrieval tests pass on the EC2 VM** (no
regression from the `stance.classify_counted` refactor). All five validated end-to-end on
real NYU/East-Carolina/interview data; every statistic carries a `stat_id` + drill-down to
the exact posts/comments.

**Provenance principle**: counted statistics are a data-lineage problem, not LLM citation —
the number is a deterministic function over a retained id set, and that set *is* the
citation (100% faithful by construction, fully auditable).

## Update (2026-06-21 — Research Protocol, RP-1 … RP-7)

Every answer now routes through `EvidenceDossierEngine.research()` → an enforced
experimental protocol (`src/research/`): estimand + denominator → retrieve → classify →
enrich (thread/author/year/cohort) → proportion **+ Wilson + thread-clustered bootstrap
CI + effective N** → consensus / EB shrinkage → measurement-error band → robustness →
temporal trend → cohort split → bias label → provenance. No number is LLM-produced.
Spec: `docs/05-features/research-protocol.md`.

| Step | **Actual** | Wiring / evidence |
|---|---|---|
| RP-1 statistics | **Validated** | `src/research/stats.py` (Wilson, cluster bootstrap +deff/n_eff, beta-binomial shrinkage, Rogan-Gladen+band, consensus, weighted trend). numpy-only, seeded. |
| RP-2 enrichment | **Validated** | `src/research/enrich.py` — year (real, created_iso), subreddit→cohort + price (proxy). |
| RP-3 protocol runner | **Validated** | `src/research/protocol.py` `ResearchProtocol` + 9-estimand router; `engine.research()`. |
| RP-4 quality assessor | **Validated** | `src/research/quality.py` — 10 criteria; 2 (accuracy calibration, spot-check) **gated**, not silently passed. |
| RP-5 panel + runner | **Validated** | `cloud/run_research_panel.py` + `scripts/research_questions.jsonl` (53 Qs / 10 roles). |
| RP-7 panel run | **Validated** | EC2 run: **51/53 answered, 2 honest abstains**, process-score **1.0** (8/10 auto criteria pass; temporal trend on 45, cohort split on 7, 0 robustness failures, median n_eff/n=0.89). Report `.agent/reports/research_panel/`. |

**Tests**: `tests/research/` — 46 unit tests pass on EC2.

**Follow-on fixes (RB-1, RB-2, RA-1):**
- RB-1 **reproducible labels** (`positions.py`): `PositionCache` + `stable_positions`
  (derive-once-and-cache) — "Is NYU worth it?" now returns identical 4-bucket labels across
  runs (closes honest limit #2). Cross-run embedding ensemble tried + rejected (short
  in-domain labels cosine-collapse).
- RB-2 **compound routing**: new `contrast` estimand (praise-vs-criticize → sentiment-split
  then topic-cluster each side, with provenance); price routes on magnitude only (closes #3).
- RA-1 **calibration** (`calibration.py` + `cloud/build_gold_sentiment.py`): silver gold
  set (Llama-3.3-70B reference, n=320) → per-class sens/spec → Rogan-Gladen corrected
  prevalence with Youden-J **low-reliability flag**. Finding: bulk sentiment classifier is
  weak (κ=0.36 vs reference, sens 0.44–0.62), so neutral can't be corrected precisely — the
  dossier says so instead of asserting a number. Gate effect: `calibrated_corrected`
  gated→**partial**; only `human_spotcheck` remains gated; sentiment dossier score 0.944.
- MH-1 **concept-grounded hybrid (M3)** (`criteria.py` + `signals.py` + protocol `_concept`):
  ranks topics by an externally-researched concept (virality), not raw demand. Deep research
  is an offline refresh → cited criteria artifact (Berger/STEPPS + 2025-26 platform signals);
  the engine intent-corrects retrieval, scores each topic by weighted corpus signals (emotion/
  engagement/advice/story/social-currency), and **flags demand-vs-viral-fit divergence**.
  Validated: pre-dental "viral topics" → Forum Navigation 75% demand but #4 fit; UConn
  Admissions 11% demand but #1 fit. Honest proxy caveat (no platform reach). 51 tests.
- MH-2 **finer topic granularity** (`clustering.py`): replaced LLM-names-few-then-assign
  (75% catch-all) with **spherical k-means over embeddings + batch cluster labeling**
  (numpy, seeded, cached). Concept path k=12, topic/pain k=10 with seed-perturbation
  robustness; stance keeps LLM viewpoints. Validated: "viral topics" → 11 balanced topics,
  junk catch-all ("Resource Redirection" 40%) isolated + buried at viral-fit #11;
  "interview topics" → 10 specific sub-topics. 54 tests.
- MH-3 **cohort-scoped retrieval + junk filtering** (`enrich.is_junk`, protocol
  `_target_cohorts`/`_clean_pool`): no-school queries retrieve a 2x pool, drop automod/
  removed/junk docs, and scope to applicant cohorts {pre-dental, dental student, sdn}
  (professional/clinical questions keep everything). Fixes the retrieval-precision
  bottleneck. Validated: Q1 pain → applicant unmet needs (School Selection, DAT, Apps,
  GPA) with patient/clinical content removed; Q2 SEO junk automod cluster gone; Q3 advising
  clean 36% positive / 62% negative. 56 tests.
- Also added 'seo' concept + `recency` signal (concept path generalizes to a 2nd concept).
- Still open: (4) price regex proxy noise; (5) forum self-selection bias quantification;
  human-gold upgrade (partial→pass); residual SDN process/meta clusters; k-means cluster-
  size mild seed-sensitivity (flagged).

## Update (2026-06-23 — Product: offline Insights Pack, SHIP-1 … SHIP-4)

Productized as a **downloadable, no-key, cross-OS ZIP** a customer attaches to their own
agent (the host agent is the brain; the pack = data + deterministic tools + methodology).
Layout + EULA + attach docs under `pack/`.

| Step | **Actual** | Wiring / evidence |
|---|---|---|
| SHIP-1 no-key tools | **Validated** | `pack/tools/insights_tools.py` `InsightsTools` — LLM-free retrieve/cluster/classify/sentiment/signals/stats/temporal/sources/rank/l1_facts/thread; doc-sets pass as tokens; every stat → exact source ids. Smoke-tested full flow on VM. |
| SHIP-2 MCP server | **Validated** | `pack/tools/mcp_server.py` FastMCP stdio — 11 tools registered; offline-by-default (HF_HUB_OFFLINE, shipped BGE weights). Token flow validated through MCP layer on VM. |
| SHIP-3 packaging | **Validated** | `pack/tools/pyproject.toml` + `pack/run.sh`/`run.ps1` (`uv run` self-bootstrap, cross-OS); `pack/LICENSE.txt` EULA; `pack/skills/dental-applicant-insights/SKILL.md` (the research playbook) + `TOOLS.md`; `pack/README.md` (attach in ~2 min). |
| SHIP-4 assemble | **Validated** | `cloud/build_pack.py` — PII scrub (234,012 authors pseudonymized in the packed documents.sqlite), vendor engine (retrieval/research/er/embeddings) into tools/src, copy BGE model, MANIFEST(sha256), zip → `dental-applicant-insights-2026Q2.zip` on the VM. |

**Honest gate:** author-field PII is scrubbed; **free-text PII (names, body u/mentions) needs
a dedicated pass + legal review before any commercial copy ships** (stated in LICENSE).
Skill-pack model = host agent does planning/clarify/deep-research/labeling/narration/review;
pack tools are pure computation. Commits 5a13b3b, 1230143, 0d70105.

## 2026-09-20 — public-readiness pass (repo hygiene; no new capabilities)

| Item | Status | Evidence |
|---|---|---|
| Clean install is runnable | **Validated** | New py3.12 venv → `pip install -e ".[dev]"` → **1,224 passed** on Windows and on Ubuntu (WSL). Before: collection failed — `numpy`, `fastapi`, `scikit-learn`, `scipy`, `croniter`, `pandas`, `lxml` were imported but undeclared, and unbounded `mcp>=1.0` resolved to 2.x (breaking Server API). Fixed in `pyproject.toml` (`mcp<2`; extras `web` / `analysis` / `embeddings`). |
| Suite needs no keys / corpus | **Validated** | Same result in a detached worktree with no `.env`, no `data/`, vendor keys unset. |
| CI | **Built** (not yet run) | `.github/workflows/ci.yml`: pytest (3.12/3.13 × ubuntu/windows), `ruff --select F,E9`, doc-lint, web typecheck + vitest — blocking. Full ruff + `mypy --strict` — non-blocking ratchet. |
| Measured quality baseline | — | Line coverage **71.6 %** (`src` + `tools`; target 80 %). `ruff` full rule set: 277 findings (120 are `PLC0415` on deliberate lazy imports). `mypy --strict`: 238 errors / 38 files. Pyflakes-level findings in `src`/`flows`/`tools`: 0. |
| `graphrag-index` console script | **Wired** (was broken) | `pyproject.toml` pointed at nonexistent `tools.graphrag.cli`; now `tools.graphrag.index:index_command`. Verified: `--full` indexes this repo (1,742 files → 6,514 nodes / 6,725 edges, 23 s). |
| Alias gold set (public) | **Replaced** | The tracked gold held 277 verbatim forum posts. Now hand-written + synthetic carriers around observed alias surface forms (`evals/build_public_alias_gold.py`); real-text gold is git-ignored. Same matcher: private 326 entries F1 **0.884** → public 264 entries F1 **0.946** — **not comparable**; earlier alias figures in reports refer to the private set. See `evals/README.md`. |
| Research-panel full report | **Withheld** | `.agent/reports/research_panel/report.md` untracked (licensed per-school figures, named-school rankings). Aggregate + calibration JSON and a README with one sample answer remain. |
| Doc reconciliation | — | `gap-register.md` GAP-048…053 and `system-overview.md` brought in line with this file; five pre-implementation docs carry dated *Historical* banners. |

## 2026-09-21 — documentation made executable (no new engine capabilities)

| Item | Status | Evidence |
|---|---|---|
| Keyless quickstart on fictional data | **Validated** (by test) | `examples/quickstart/` — L1 sheet + L5 forum through the real CLI (`ingest l1-adea`, `ingest l5-reddit`, `stats`, `canonical`, `query --no-hybrid`) and the production `ConflictResolver` (4 cascade outcomes). Replayed by `tests/examples/test_quickstart.py`. |
| Generated CLI + REST reference | **Wired** | `tools/docs/gen_reference.py` → `docs/guide/reference/`; `tests/docs/test_reference_docs.py` fails when stale or when a command is undocumented. |
| Env-var truth | **Validated** (by test) | `.env.example` previously offered ~30 variables nothing read and omitted ~17 that are read. Rewritten; `tests/docs/test_env_vars_documented.py` enforces both directions against `docs/guide/configuration.md`. |
| CLI `--help` on non-UTF-8 consoles | **Fixed** | `src/cli.py` `cli()` forces UTF-8 on its own streams; console script is now `src.cli:cli`. `tests/test_cli_console_encoding.py` (2 of 5 cases failed before). |
| Known limitation surfaced by the quickstart | — | With the dependency-free `hash` embedder, hybrid `query` ranking is not semantic (noisy on small graphs); entity-seeded `--no-hybrid` is the keyless path. Six crawl MCP tools in `src/integrations/mcp_crawl_tools.py` are **Built, not Wired** into `src/retrieval/mcp_server.py`. |
| Suite | — | 1,235 tests. |

## Rule

When you finish a capability, **move its row here first**, citing the non-test wiring site,
*then* update the ADR / tech-stack / system-overview. If those disagree with this table,
**this table wins** and the others are the bug.
