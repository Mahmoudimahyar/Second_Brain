# Context

## Where this slice fits

This is the **first vertical slice** for the V1 product engine — the trust-tier knowledge-graph engine that ingests dental data dumps. It is downstream of:

- All bootstrap docs (`docs/00-bootstrap/*`).
- The system architecture (`docs/04-architecture/system-overview.md`).
- The tech stack picks (`docs/04-architecture/tech-stack.md`).
- The graph-DB bake-off (`docs/05-features/bake-off-graph-db/`) → ADR-001.
- The `tools/graphrag/` repo MCP context server (gate #6 from CLAUDE.md).

It is upstream of:

- L2 / L3 / L4 source-tier adapters (later slices).
- Web-verification agent integration (V1.5+).
- HITL web UI (V2).
- Downstream PM / marketing / analyst agents (V2 — `docs/01-core/out-of-scope.md`).

## Source material

### Prior research feeding this slice

- `docs/03-research/research-log.md` — R-001..R-005 (pre-web-verify).
- `docs/03-research/R-006-live-verification.md` — Kùzu acquisition, GLiNER2, XGrammar, DSPy GEPA, Anthropic TTL change.
- `docs/03-research/R-007-multi-source-kg.md` — Graphiti/Zep as ~90% architecture match, Wikidata-rank trust schema, BGE→DITTO ER pipeline, HALO per-edge half-life, signed-graph community detection, LLM-as-judge restrictions, outlier preservation.
- `docs/03-research/R-008-cost-accuracy.md` — top 5 cost/accuracy levers, V1 budget projection.

### Data (`External Data\`)

- **L1**: ADEA Report 2 (Tuition, Admission, Attrition), 5 most-recent yearly files (`2020-21` → `2024-25`) under `External Data\Official Dental School Data\Report 2_ Tuition, Admission, and Attrition\`. Excel format; loaded via openpyxl/pandas into the V1 SQLite side store as `l1_school`, `l1_school_year_metric`.
- **L5**: `r/DentalSchool` — `External Data\Forum\Reddit\r_DentalSchool_posts.jsonl` (34,771 posts) + `r_DentalSchool_comments.jsonl` (239,426 comments). Full Reddit schema (`created_utc`, `author`, `score`, `ups`, `downs`, `num_comments`, `selftext`, `title`, `body`, `parent_id`, `link_id`).
- 1K SDN "Pre-Dental" posts for schema-cross-validation (Reddit has karma, SDN doesn't — A-043 confirms the user-credibility rubric is source-aware). Filtered from `External Data\Forum\sdn_llm\sdn_thread_metadata.jsonl` where `category = "Pre-Dental"`.

### Canonical entity universe

The L1 dataset declares the closed-set of US dental schools (~56 accredited US dental schools per the most recent ADEA report). Loaded once at ingestion start; the BGE-small + DITTO ER pipeline snaps L5 mentions to this set. Any L5 mention that fails to snap (similarity < 0.75) is preserved as `Unresolved_Entity` for review.

## Architectural surfaces this slice exercises

| Surface | This slice | Deferred |
|---|---|---|
| Ingestion plane (`register_dump`) | L1 Excel adapter + L5 Reddit JSONL adapter | L2 HTML, L3 CSV, L4 PDF, L5 SDN JSONL (added soon after) |
| Cascade extraction (Stage 1-3) | Full cascade: spaCy + GLiNER2 + BGE+DITTO + Haiku 4.5 (BAML) | XGrammar local-LLM path only as fallback (Pascal-GPU throughput too low for production) |
| Conflict resolution | L1 clash, temporal disambig, source-trust weighting, HITL escalation | Web-verification crawler trigger (emits `research_need` but no responder yet), full signed-graph community detection (computed nightly but not yet retrieval-primitive) |
| Trust-tier schema | `source_tier` L1+L5, Wikidata `rank`, `references`, `qualifiers` | L2/L3/L4 tiers |
| Bitemporal edges | Full `t_valid_*` + `t_ingest_*` on every edge | "as of past date" reconstruction is tested but not yet a first-class MCP tool |
| Multi-layer graph (3 layers) | User layer (with V1 hand-weighted source-aware rubric), Post layer, Opinion layer (claims/recs computed but signed-graph clustering is offline) | Logistic-regression credibility (V1.1) |
| Retrieval MCP (inbound) | `query_graph`, `get_canonical_entity` | `search_by_topic`, `get_user_credibility`, `get_topic_consensus` (added in later slices) |
| Outbound crawler MCP | `register_dump`, `get_gaps()`, `get_research_needs()` | `is_url_ingested`, `get_topic_state`, `get_pending_verifications` (pending Q-021) |
| HITL queue | CLI + flat YAML review file + `commit` command | Web UI |
| Audit + observability | Full per-call structured logs, prompt-cache TTL lint | OpenTelemetry trace propagation (V2) |
| Cost cascade | Content-addressable cache + prompt-cache + batch + snap-to-canonical | Distillation (V2) |

## Stakeholders

- **Decision owner**: Mahyar.
- **Implementer**: Claude, post-gates, under TDD discipline.
- **Reviewer (HITL)**: Mahyar (V1); contracted dental-admissions expert (V1.x+).
- **Downstream consumers**: PM / marketing humans + (V2) downstream agents.

## Related files

- `docs/01-core/product-vision.md` — the product principles this slice instantiates.
- `docs/01-core/out-of-scope.md` — deferral list this slice respects.
- `docs/04-architecture/system-overview.md` — the architecture this slice implements.
- `docs/04-architecture/tech-stack.md` — the version-pinned tool list this slice consumes.
- `docs/05-features/bake-off-graph-db/` — the prerequisite bake-off.
- `tools/graphrag/IMPLEMENTATION_PLAN.md` + `MCP_SERVER_REQUIREMENTS.md` + `verification-checklist.md` — the repo MCP server gate.
- `docs/00-bootstrap/assumptions.md` — A-001..A-045 (assumptions this slice depends on).
- `docs/00-bootstrap/gap-register.md` — gaps this slice closes (GAP-002 confirmed-by-execution, GAP-007 cost-confirmed, GAP-019 source-aware rubric exercised, GAP-020 HALO decay exercised).
- `memory/project_dentistjourney.md` — durable project context.
