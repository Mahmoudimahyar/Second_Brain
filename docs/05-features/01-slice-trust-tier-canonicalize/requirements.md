# Requirements

> **Status:** Spec. No code. Requirements are testable; mapping to test cases lives in `test-plan.md`.

## Functional requirements

### FR-1 — Ingestion plane

- **FR-1.1** The system exposes an MCP tool `register_dump(source_tier, manifest, payload_paths)` that validates the manifest, computes content-hashes for each payload file, stores raw payloads in an immutable object store under `data/dumps/<source>/<ingest_date>/`, and emits a `DumpReceipt` containing `dump_id`, `source_tier`, `t_ingest_from`, content-hash list, and pre-extraction validation result.
- **FR-1.2** The L1 Excel adapter accepts ADEA Report 2 files for cycles 2020-21 → 2024-25 and produces canonical `School` + `SchoolYearMetric` rows in the SQLite side store. School names from the L1 source become the canonical alias universe.
- **FR-1.3** The L5 Reddit JSONL adapter accepts `r_DentalSchool_posts.jsonl` + `r_DentalSchool_comments.jsonl`, reconstructs thread structure via `link_id`/`parent_id`, normalizes Unix-epoch `created_utc` to UTC ISO-8601, and emits canonical Post / Comment / User records.
- **FR-1.4** SDN JSONL adapter accepts the SDN `sdn_thread_metadata.jsonl` + per-thread `thread_<id>_posts.jsonl` filtered to `category = "Pre-Dental"` (1K-sample subset for V1) — same canonical output shape as Reddit, with `score`/`ups`/`downs` set to `null`.
- **FR-1.5** Author nodes are namespaced: `reddit:DentalSchool:<author>` and `sdn:<author>`. Same string across sources produces distinct nodes.

### FR-2 — Cascade extraction

- **FR-2.1** Stage 1 (filter) runs spaCy + GLiNER2 + regex on every L5 post + comment. Output: a boolean `mentions_dental_entity` flag + a list of candidate spans.
- **FR-2.2** Stage 2 (local ER) runs GLiNER2 + BGE-small HNSW blocking + DITTO/DistilBERT reranker against the L1 canonical alias universe on Stage-1 survivors. Output per mention: top-K candidate canonical IDs with cosine similarity + reranker score.
- **FR-2.3** Stage 3 (API extraction) runs Claude Haiku 4.5 (batch API + prompt caching with `ttl: 3600` explicit) on Stage-2 residual cases (low-confidence ER, sentiment, interview-Q candidates, conflict candidates). BAML defines the prompts + schemas. Pydantic validates outputs.
- **FR-2.4** Content-addressable extraction cache keyed by `hash(thread_content + prompt_id + prompt_version + schema_hash + model_id + model_version)`. Cache write happens before any API call; cache read happens before extraction is attempted.
- **FR-2.5** Every Anthropic prompt-cache write site uses `ttl: 3600`. A lint / pre-commit check enforces this.

### FR-3 — Entity resolution + canonicalization

- **FR-3.1** Auto-accept threshold ≥ 0.90 (BGE-small cosine similarity after DITTO reranker score).
- **FR-3.2** HITL queue: 0.75 ≤ similarity < 0.90.
- **FR-3.3** Reject (preserve as `Unresolved_Entity`): similarity < 0.75.
- **FR-3.4** Thresholds are ablated on the first 500 HITL decisions and updated via a documented procedure; the initial values are placeholders.
- **FR-3.5** A `MENTIONS_SCHOOL` edge from a Post/Comment to a canonical `School` carries `confidence` (the reranker score), `source_tier`, `rank` (default `normal` for L5), `t_valid_from` (post `created_utc`), `t_ingest_from`, plus a `references` list with the source `post_id` / `comment_id`.

### FR-4 — Trust-tier schema

- **FR-4.1** Every node carries `source_tier` (enum L1..L5).
- **FR-4.2** Every claim edge carries Wikidata-style `rank` (`preferred` / `normal` / `deprecated`), `references` (list of source IDs), `qualifiers` (dict).
- **FR-4.3** L1 nodes are immutable. The system rejects any `UPDATE` operation against an L1 node with `Status: Refused_L1_Immutable`.

### FR-5 — Bitemporal edges

- **FR-5.1** Every edge carries `t_valid_from`, `t_valid_to`, `t_ingest_from`, `t_ingest_to`. `t_valid_to` may be `NULL` (open-ended); `t_ingest_to` may be `NULL` (still ingested).
- **FR-5.2** When a re-ingest produces a conflicting edge for the same (subject, predicate, object), the prior edge's `t_ingest_to` is set to the new ingestion timestamp; the new edge starts with `t_ingest_from = now`.
- **FR-5.3** A `query_graph(..., as_of=<datetime>)` parameter filters edges to those where `t_ingest_from <= as_of AND (t_ingest_to IS NULL OR t_ingest_to > as_of)`.

### FR-6 — Conflict resolution

- **FR-6.1** When a Stage-3 extraction produces a claim about a property that an L1 node owns (e.g., a forum claim says "NYU tuition is $40k" but L1 says $90k for the same year), the system emits an `L1Clash` event, sets the forum claim's `Status: Invalidated_by_Official_Data`, and leaves the L1 node unchanged.
- **FR-6.2** When two non-L1 claims disagree about the same property, the system first attempts temporal disambiguation: if `t_valid_*` differ, the claims are split into year-tagged versions (not flagged conflicts).
- **FR-6.3** If the disagreement persists within the same `(t_valid_year, source_tier)` window, the system applies source-trust weighting via the user-credibility rubric (FR-7), choosing the higher-weight claim as `rank: preferred` and lower-weight as `rank: normal`.
- **FR-6.4** Web-verification trigger: the system emits a `research_need` record to the outbound MCP queue when (a) a non-L1 cluster of claims contradicts an L1 value AND (b) the L1 source's `t_valid_to` is more than 6 months stale. The crawler is responsible for fetching; the engine just queues the request.
- **FR-6.5** Irreducible ambiguity escalates to the HITL queue with a structured reason.
- **FR-6.6** LLM-as-judge is invoked **only** for same-tier same-year tie-breaks per A-031, with cross-vendor calibration (Anthropic + at least one other vendor's agreement check). Disagreements between judges → HITL.

### FR-7 — User-credibility rubric (source-aware)

- **FR-7.1 — Reddit rubric**: 10 features per A-033. Source-tier-aware aggregation.
- **FR-7.2 — SDN rubric**: 7 features (no upvote/karma signal): post count, comment count, account-age proxy via earliest-post timestamp, comment/post ratio, on-topic ratio, megathread participation count, longevity in months.
- **FR-7.3** Each rubric outputs a credibility score in `[0, 1]`. Source-tier weighting (FR-6.3) multiplies tier weight by credibility.
- **FR-7.4** `prescient_correct` count: when a user's L5 claim is later confirmed by an L1/L2 source, increment that user's `prescient_correct` counter. The rubric weights this positively.
- **FR-7.5** Outlier preservation: claims that fall outside the consensus cluster are tagged `Status: Anomaly` (NOT deleted). They remain queryable via `query_graph(..., include_anomalies=True)`.

### FR-8 — Retrieval MCP (inbound)

- **FR-8.1** `query_graph(query, source_tier_min=None, time_range=None, as_of=None, traversal_depth=3)` returns a list of result records, each with `node_id`, `node_type`, `properties`, `references` (citation IDs back to source dumps), `source_tier`, `rank`, `confidence`, and `path_explanation` (which edges were traversed). p95 < 250 ms on V1 sample.
- **FR-8.2** `get_canonical_entity(alias, entity_type)` returns the L1 canonical entity matching the alias plus its alias list. p95 < 50 ms.
- **FR-8.3** Every result carries `references`. **Citation traceability ≥ 99%** on the test set.

### FR-9 — Outbound MCP (to crawler)

- **FR-9.1** `register_dump(...)` per FR-1.1.
- **FR-9.2** `get_gaps()` returns a list of `(topic, source_tier, gap_reason)` tuples — topics where the graph is sparse on a given tier (e.g., "no L2 source for school admissions criteria at NYU").
- **FR-9.3** `get_research_needs()` returns `research_need` records emitted by FR-6.4.
- **FR-9.4** Additional endpoints (`is_url_ingested`, `get_topic_state`, `get_pending_verifications`) pending Q-021.

### FR-10 — HITL queue

- **FR-10.1** `hitl pull` CLI command emits the next pending review item to a flat YAML file under `data/hitl/<item_id>.yml`. Reviewer edits the file (sets decision, optional notes).
- **FR-10.2** `hitl commit <item_id>` reads the YAML, validates the decision, writes the outcome to the graph (e.g., alias accept/reject, conflict-tie-break decision), and logs the decision to `audit_log`.
- **FR-10.3** Queue states: `pending` → `claimed` (reviewer pulled) → `committed` | `escalated`. Re-claiming after timeout is allowed.

### FR-11 — Audit + observability

- **FR-11.1** Every Anthropic API call writes an `audit_log` row with: `thread_content_hash`, `prompt_template_id`, `prompt_version`, `schema_hash`, `model`, `model_version`, `cache_hit`, `cache_key`, `ttl_pinned` (must be `3600`), `input_tokens`, `output_tokens`, `cached_input_tokens`, `cost_usd`, `latency_ms`, `timestamp_utc`.
- **FR-11.2** Every retrieval call writes an audit-log row with: `query_text`, `result_count`, `latency_ms`, `traversal_depth`, `time_range`, `as_of`, `timestamp_utc`.
- **FR-11.3** Every HITL decision writes an `audit_log` row with reviewer, decision, item type, before/after diff.

## Non-functional requirements

- **NFR-1 Latency**: `query_graph` p95 < 250 ms; `get_canonical_entity` p95 < 50 ms on V1 sample.
- **NFR-2 Cost**: V1 slice extraction sweep ≤ **$25** API spend. Pending Mahyar's Q-016 ceiling.
- **NFR-3 Cache efficiency**: warm-sweep cache hit ≥ 80%. Cold-sweep ≥ 0.
- **NFR-4 Accuracy**: alias-resolution F1 ≥ 0.92 on the 200-mention labeled gold set. Citation traceability ≥ 99% on retrieval results.
- **NFR-5 Reliability**: ingestion failures are atomic (partial dumps roll back). Re-running `register_dump` with an identical content-hash is a no-op (idempotent).
- **NFR-6 Observability**: 100% of API calls + retrieval calls + HITL decisions audit-logged.
- **NFR-7 Security**: V1 internal-only. No external network exposure. No PII anonymization required for V1 (V1 retains Reddit / SDN author handles). V2 reopens this.
- **NFR-8 Repro**: identical input + identical prompt-version → identical output (content-addressable cache hit).
- **NFR-9 Test coverage**: ≥ 80% line coverage on the engine's core modules (ingestion, ER, conflict resolution, audit log).

## Out of scope (this slice)

See `docs/01-core/out-of-scope.md` for the global V2 deferral list. Slice-specific deferrals:

- L2 / L3 / L4 source adapters.
- Signed-graph community detection as a retrieval primitive (it runs offline; results land in the graph but `query_graph` doesn't yet rank by them).
- Logistic-regression user-credibility upgrade (V1.1).
- Self-evolving loop (V2).
- HITL web UI (V2).
- Cross-vendor LLM-as-judge calibration (V2 — V1 uses a single-vendor cross-check inside the same Anthropic family).
- Web-verification responder (the engine emits `research_need`; the crawler / responder is a separate system).

## Open dependencies (must be resolved before this slice starts implementation)

1. **Bake-off complete** → ADR-001 ratified → graph DB chosen.
2. **`tools/graphrag/` repo MCP server** implemented or connected + `verification-checklist.md` passing.
3. **Q-016** budget ceiling answered (drives the auto-accept threshold ablation budget).
4. **Q-021** crawler MCP endpoints confirmed.
5. **Q-026** Reddit/SDN credibility split confirmed (default: two parallel rubrics).
6. **GraphRAG MCP infrastructure code go-ahead** from Mahyar (asked in main thread).
