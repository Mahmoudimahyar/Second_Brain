# User Journeys

> Light per `ai_agent_system` mode. Three V1 journeys mapping to the three V1 user types. Each journey calls out the exact MCP / CLI / file touchpoints.

## Journey 1: Ingestion operator drops a new dump and gets a clean graph

### User goal
Mahyar has a new ADEA Excel file (or a new month of r/DentalSchool dump). He wants it ingested, conflict-resolved, and queryable, within hours.

### Entry point
`mcp call register_dump source_tier=L1 manifest=<adea_report2_2024_25.json> payload_paths=<paths.json>`
(equivalent Python `IngestionService.register_dump(...)`).

### Happy path
1. **Validate manifest** — schema-locked manifest check passes; content-hashes computed; immutable raw stored under `data/dumps/L1/2026-05-20/`.
2. **Normalize** — L1 Excel adapter loads sheets via pandas/openpyxl; emits canonical `School` + `SchoolYearMetric` records.
3. **Extract** — for L1 dumps, extraction is trivial (table rows → typed records). For L5 dumps, the cascade runs Stage 1 → 2 → 3 with cost cascade observability shown in the operator's terminal.
4. **Resolve** — for L5, BGE + DITTO snap mentions to canonical L1 entities. Auto-accepts go to the graph; borderline cases land in the HITL queue.
5. **Reconcile** — conflict resolver applies the 6-step order; L1 wins on clash; bitemporal `t_ingest_from` set.
6. **Commit** — graph writes flush; `audit_log` rows appended; Langfuse dashboard updates cost + latency + cache-hit per call.
7. **Receipt** — operator gets a `DumpReceipt` with counts (nodes added, edges added, HITL items queued, research needs emitted, total cost).

### Error paths
- **Manifest invalid** → `VALIDATION_FAILED` error, raw payload not stored, no graph writes.
- **Duplicate content-hash** → idempotent no-op; receipt returns prior `dump_id`.
- **Stage-3 vendor API outage** → fallback chain kicks in per per-task matrix; if all vendors fail, partial dump rolls back, `dump.status = failed`, operator sees a clear error in CLI.
- **Auto-accept threshold ablation reveals drift** → operator gets a warning in CLI to re-tune SD-005 thresholds.

### Edge cases
- L1 file with new column the adapter doesn't recognize → adapter logs unknown columns, ingests known ones, emits a `propose_new_metric` HITL item.
- Posts referencing schools not in the L1 canonical universe (e.g., a foreign dental school) → `Unresolved_Entity` marker node + HITL queue.

### Success metric
- Dump ingest end-to-end < 2 hours for a single subreddit slice (~274K records).
- Cost < $25 first sweep; < $5 warm rerun.
- Audit log shows complete trace.

### Related features
- `docs/05-features/01-slice-trust-tier-canonicalize/` (V1 slice)
- ADR-003 (extraction stack)
- ADR-011 (gateway + MCP policy)

---

## Journey 2: HITL reviewer arbitrates a borderline alias

### User goal
Mahyar (V1) or contracted reviewer (V1.x) sees 50+ items in `hitl_queue` and wants to clear the queue in a focused session.

### Entry point
`hitl pull` (typer CLI).

### Happy path
1. **Pull next item** — `hitl pull` writes `data/hitl/<item_id>.yml`. YAML includes: mention text, originating post excerpt (with thread context), top-5 candidate canonical entities + ER scores, alias-history for those canonicals, the timestamp.
2. **Review** — reviewer reads the YAML in their editor; decides accept (which canonical) / reject / propose-new-alias / propose-new-node-type.
3. **Edit** — reviewer fills the `decision` field of the YAML.
4. **Commit** — `hitl commit <item_id>` reads YAML, validates the decision schema, writes:
   - If accept: `HAS_ALIAS` edge from chosen canonical to alias-string + `MENTIONS_*` edge from host post/comment.
   - If reject: `UnresolvedEntity` node preserved.
   - If propose-new-alias: new entry in `alias` table with `alias_source = 'hitl'`.
   - If propose-new-node-type: a separate HITL flow (out-of-V1, deferred).
5. **Audit-log row** appended.
6. **Queue advances** to next pending item.

### Error paths
- **Reviewer claims item but doesn't commit within 24h** → timeout reverts item to `pending`, preserving the draft as a comment.
- **Schema-invalid YAML** → `hitl commit` rejects with a clear error, reviewer fixes.
- **Decision conflicts with existing state** (e.g., proposing an alias that's already declared elsewhere) → rejected with conflict reason.

### Edge cases
- A reviewer claims an item already claimed by another reviewer → `ALREADY_CLAIMED` error; allow `--force` flag to re-claim if the prior claim is stale > 24h.
- A reviewer escalates → item goes to `escalated` sub-queue; Mahyar reviews these.

### Success metric
- ≤ 1 minute per item median review time (V1 with familiar reviewer).
- 100% of `hitl commit` decisions have a corresponding audit-log row.
- Zero decisions lost across reviewer-restart / claim-timeout / re-claim.

### Related features
- HITL CLI module (Phase 8 of slice plan).
- ADR-008 (user-credibility — informs which mention-claims the rubric currently has low confidence about).

---

## Journey 3: Downstream consumer queries the graph

### User goal
A product manager (eventual DentistJourney team) asks: "What were the top 5 applicant pain points about UCSF dental over the last 3 cycles?"

### Entry point
MCP call: `query_graph(query="top applicant pain points UCSF dental 2022-2024", source_tier_min="L5", time_range=("2022-07-01", "2024-12-31"), traversal_depth=3)`.

### Happy path
1. **Parse + route** — query passes through retrieval-router: identifies `UCSF` as a canonical entity (via `get_canonical_entity`), maps "pain points" to topic clusters + opinion-layer claims.
2. **Traversal** — graph traversal finds `Post`/`Comment` nodes that `MENTIONS_SCHOOL → UCSF` within the time range, hops to `Topic` and `Claim` nodes, filters by `source_tier ∈ {L5}` and `t_valid_*` overlap.
3. **Rank** — results ranked by `tier_weight × rank_weight × decay(now, t_valid_from) × user_credibility(source)`. Outliers (`Status: Anomaly`) excluded unless `include_anomalies=True`.
4. **Aggregate** — top 5 pain-point clusters returned with: representative claim text, count of supporting posts, time-span, citation list (post IDs), and confidence.
5. **Cite** — every result has `references` linking to source posts; PM can drill down by opening Reddit URLs.

### Error paths
- **No canonical for "UCSF"** → returns `get_canonical_entity` failure suggestion + offers to search by alias.
- **No L5 posts in time range** → returns empty list with a hint about the temporal filter; PM can widen.
- **Query times out** (> 250 ms p95 target) → partial results + warning; logged for optimization.

### Edge cases
- PM asks about a topic that has both L1 and L5 evidence with different valence → results include both with `source_tier` distinction in the response shape; PM can see L1 says X, L5 cluster says Y, and the L1 wins by `rank: preferred`.
- PM asks an "as of past date" question (e.g., "what did the community think in 2022?") → uses `as_of` parameter to reconstruct the bitemporal snapshot.

### Success metric
- p95 query latency < 250 ms.
- Citation traceability 100% on every result.
- Zero hallucinated entities or claims (because retrieval is graph-bounded, not LLM-generative).

### Related features
- `api.md` — `query_graph` signature.
- ADR-002 (hybrid retrieval).
- ADR-005 (trust-tier schema).
- ADR-007 (HALO decay).
