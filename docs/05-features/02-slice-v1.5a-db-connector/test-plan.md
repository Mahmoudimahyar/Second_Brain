# Test Plan — V1.5a

> Maps every acceptance criterion + functional requirement to concrete test cases. Mirrors the V1 slice-01 test-plan convention.

## Test layers

| Layer | Tool | Scope |
|---|---|---|
| Unit | pytest | Per-module: `src/ingestion/sources/*`, `src/extraction/mapping_suggester.py`, `src/er/cross_graph.py` |
| Property | pytest + hypothesis | Idempotency, lifecycle, audit-log invariants |
| Integration | pytest + testcontainers-python | End-to-end connect → discover → suggest → commit → pull → crosslink |
| Eval (gold-set) | pytest + custom harness | F1 on mapping-suggestion + cross-graph match gold sets |
| Contract | pytest + MCP test client | Each new MCP tool's request/response shape |
| Flow | Prefect test client | `flows/data_source_pull.py` |

## Acceptance-criteria mapping

### AC-1: DataSource Protocol implemented + tested
- `tests/ingestion/sources/test_protocol.py::test_protocol_signature` — pyright + `typing.runtime_checkable` assertion.
- `tests/ingestion/sources/test_protocol.py::test_lifecycle_round_trip_property` — hypothesis: any `DataSource` survives a random sequence of (open/discover/sample/pull/close/re-open) without leaks. Asserted via `tracemalloc`.
- `tests/ingestion/sources/test_local_file_wrapper.py::test_existing_v1_adapters_wrapped` — wrapping each V1 adapter (L1 Excel / L1 PDF / L2 HTML / L5 Reddit / L5 SDN) yields canonical records bit-identical to V1's direct call.

### AC-2: All four engines pass connect + discover + dry-run
- `tests/ingestion/sources/test_postgres.py::test_postgres_lifecycle` — testcontainers Postgres; create 3-table schema with FKs; assert SchemaSnapshot.
- `tests/ingestion/sources/test_postgres.py::test_pull_delta_on_updated_at_cursor` — incremental pull writes only new rows.
- `tests/ingestion/sources/test_postgres.py::test_pull_delta_idempotent` — running twice in a row writes 0 nodes/edges on second call.
- `tests/ingestion/sources/test_postgres.py::test_ssl_mode_passthrough` — `ssl_mode='require'` honored.
- `tests/ingestion/sources/test_mysql.py::*` — same coverage for MySQL.
- `tests/ingestion/sources/test_sqlite.py::*` — same coverage for SQLite.
- `tests/ingestion/sources/test_sqlite.py::test_reingest_own_l1_sidestore_round_trip` — pointing at V1's L1 SQLite file as a SQLiteDataSource produces the original L1 graph.
- `tests/ingestion/sources/test_neo4j.py::*` — testcontainers Neo4j; assert labels + rel types discovered; sample per label; cursor on `node.modified`.
- `tests/ingestion/sources/test_neo4j.py::test_apoc_optional` — Neo4j without APOC still works (fallback discovery).
- `tests/ingestion/sources/test_engine_extras_optional.py::test_install_without_postgres_extra` — core install (without `[postgres]`) still imports cleanly; running Postgres tests with extra missing raises a structured error.

### AC-3: Auto-suggest mapping F1 ≥ 0.85
- `evals/gold/v1.5a-mapping-suggestions.jsonl` — 50 pairs covering ADEA-shaped Postgres + Reddit-shaped SQLite + a synthetic edge table.
- `tests/extraction/test_mapping_suggester.py::test_suggest_school_node` — `schools(id,name,city,state)` → `node_type=School` confidence ≥ 0.90.
- `tests/extraction/test_mapping_suggester.py::test_suggest_join_table_as_edge` — `enrollments(user_id, school_id)` → `edge_type=ENROLLED_IN`.
- `tests/extraction/test_mapping_suggester.py::test_skip_audit_table` — `audit_log(*)` table proposes `skip` because internal-operational.
- `tests/extraction/test_mapping_suggester.py::test_overall_f1_meets_gate` — full gold set; F1 ≥ 0.85 required to pass.
- `tests/extraction/test_mapping_suggester.py::test_prior_decision_boost` — committing a decision raises confidence on a similar-shape table on the next run.
- `tests/extraction/test_mapping_suggester.py::test_no_llm_pollution` — suggestion logic uses BGE embeddings only; no LLM call. Property-tested by mocking the gateway and asserting it's never invoked.

### AC-4: Tier declaration enforcement
- `tests/ingestion/sources/test_tier_enforcement.py::test_l1_without_confirmation_rejected` — `tier='L1', confirm_l1_immutable=False` → `INVALID_TIER_UPGRADE`.
- `tests/ingestion/sources/test_tier_enforcement.py::test_l1_with_confirmation_accepted` — confirmed L1 connector accepted.
- `tests/ingestion/sources/test_tier_enforcement.py::test_tier_stamped_on_materialized_nodes` — every node/edge written by the connector carries the declared tier.
- `tests/ingestion/sources/test_tier_enforcement.py::test_retier_closes_old_tingest_to` — re-tiering closes prior bitemporal range.

### AC-5: Cross-graph match F1 ≥ 0.92
- `evals/gold/v1.5a-cross-graph.jsonl` — 100 pairs across (ADEA L1 ↔ external Postgres ~40) + (ADEA L1 ↔ Reddit ~30, regression) + (external Postgres ↔ Reddit ~30).
- `tests/er/test_cross_graph.py::test_link_adea_to_partner_postgres_school` — F1 ≥ 0.92 on the ADEA↔partner subset.
- `tests/er/test_cross_graph.py::test_regression_on_v1_alias_gold` — V1 alias resolution F1 ≥ 0.92 unchanged after `cross_source_mode=True`.
- `tests/er/test_cross_graph.py::test_overall_f1_meets_gate` — full 100-pair set.
- `tests/er/test_cross_graph.py::test_autoaccept_at_0_90_threshold` — confidence ≥ 0.90 auto-writes `SAME_AS`.
- `tests/er/test_cross_graph.py::test_hitl_routing_at_borderline` — 0.75 ≤ conf < 0.90 enqueues `cross_graph_link` item.
- `tests/er/test_cross_graph.py::test_no_link_below_threshold` — conf < 0.75 writes nothing.
- `tests/er/test_cross_graph.py::test_bidirectional_query` — querying either endpoint returns the edge.

### AC-6: L1 immutability preserved
- `tests/ingestion/sources/test_l1_immutability.py::test_l2_connector_l1_clash_flags_l2_claim` — known L1 metric (`nyu_dental:2024-25:tuition_resident=87000`) + L2 connector claiming `=99999` → L2 claim status `invalidated_by_official_data`. L1 node + metric value unchanged.
- `tests/ingestion/sources/test_l1_immutability.py::test_multi_l1_collision_escalates` — two L1 connectors both claim conflicting values → `multi_l1_claims` HITL item created; neither side modified.

### AC-7: Re-pull idempotency
- `tests/ingestion/sources/test_pull_idempotency.py::test_no_changes_writes_zero` — idempotent pull.
- `tests/ingestion/sources/test_pull_idempotency.py::test_full_resync_closes_old_tingest_to` — full-resync semantics.
- `tests/ingestion/sources/test_pull_idempotency.py::test_property_500_random_trajectories` — hypothesis: random sequence of (add row / update row / delete row / pull) maintains the invariant that "current materialized graph == replay of pulls".

### AC-8: Citation traceability ≥ 99%
- `tests/retrieval/test_citation_traceability_v1.5a.py::test_every_connector_node_has_references` — every node produced by a connector has `references` linking to source table + primary-key value.
- `tests/retrieval/test_citation_traceability_v1.5a.py::test_99pct_on_full_corpus_smoke` — end-to-end smoke; 200-query sample; ≥ 99% carry `references`.

### AC-9: Audit log covers every connector action
- `tests/observability/test_audit_log_v1.5a.py::test_every_mcp_tool_writes_audit_row` — invoke each of the seven MCP tools; assert one row per call with the correct `kind`.
- `tests/observability/test_audit_log_v1.5a.py::test_secrets_never_logged` — assert credentials never appear in any audit row, structlog event, or Langfuse trace. Regex grep on synthetic credentials.

### AC-10: Verification Before Completion report
- Manual: write `.agent/reports/v1.5a-slice.md` per AGENTS.md.

## Non-functional test coverage

### NFR-1.5a-1 — Pull-delta latency
- `tests/integration/perf/test_pull_delta_perf.py::test_100k_row_table_under_90s` — synthetic 100K-row Postgres table; assert wall-clock < 90s on Mahyar's workstation profile.

### NFR-1.5a-2 — Schema discovery latency
- `tests/integration/perf/test_discover_perf.py::test_200_table_under_10s` — synthetic 200-table Postgres schema.

### NFR-1.5a-3 — Cross-graph match latency
- `tests/er/perf/test_cross_graph_perf.py::test_p95_under_30ms` — 1000-mention batch; p95 latency.

### NFR-1.5a-4 — Idempotency property
- See AC-7's 500-trajectory hypothesis test.

### NFR-1.5a-5 — Reproducibility
- `tests/integration/test_reproducibility.py::test_identical_input_identical_output` — content-hash idempotency end-to-end.

### NFR-1.5a-6 — Coverage
- CI gate: `pytest --cov=src/ingestion/sources --cov=src/er/cross_graph --cov=src/extraction/mapping_suggester --cov-fail-under=80`.

### NFR-1.5a-7 — Security (no credential leakage)
- See AC-9's secrets-never-logged test.
- `tests/security/test_credential_redaction.py::test_structlog_redacts_known_secret_keys` — structlog config strips `password`, `token`, `api_key`, `secret` fields.

### NFR-1.5a-8 — Observability
- `tests/observability/test_langfuse_attribution.py::test_per_source_id_tagging` — Langfuse trace carries `source_id`.

### NFR-1.5a-9 — Documentation
- `tests/docs/test_v1_5a_api_docs_exist.py` — for each MCP tool, `docs/06-api/v1.5-connectors.md` has a section with a request example + response example.

## Integration smoke (Phase 8 of plan.md)

`.agent/reports/v1.5a-integration-smoke.md` documents an end-to-end run:
- Connect testcontainers Postgres pre-seeded with ADEA-shaped data.
- Discover schema (5 tables).
- Suggest mapping (5 auto-accepts).
- Commit mapping.
- Pull delta (~1000 rows).
- CrossGraphLinker produces ~5 SAME_AS edges to V1's existing ADEA L1.
- Query the merged graph via `query_graph_analyzed` (Level C, ADR-012) — assert results include both V1 ADEA nodes and V1.5a-connected Postgres nodes connected via SAME_AS.

## Test data + fixtures

- `tests/fixtures/v1.5a-postgres-init.sql` — ADEA-shaped schema for testcontainers.
- `tests/fixtures/v1.5a-mysql-init.sql` — MySQL equivalent.
- `tests/fixtures/v1.5a-neo4j-init.cypher` — Neo4j label fixture.
- `tests/fixtures/v1.5a-mapping-decisions.yaml` — committed mapping for the integration smoke.
- `evals/gold/v1.5a-mapping-suggestions.jsonl` — 50 pairs.
- `evals/gold/v1.5a-cross-graph.jsonl` — 100 pairs.

## Coverage budget

| Module | Target |
|---|---|
| `src/ingestion/sources/base.py` | ≥ 90% |
| `src/ingestion/sources/postgres.py` | ≥ 85% |
| `src/ingestion/sources/mysql.py` | ≥ 85% |
| `src/ingestion/sources/sqlite.py` | ≥ 90% |
| `src/ingestion/sources/neo4j.py` | ≥ 80% |
| `src/extraction/mapping_suggester.py` | ≥ 85% |
| `src/er/cross_graph.py` | ≥ 85% |
| `src/observability/audit.py` (additions) | ≥ 95% |
| Overall V1.5a-touched modules | ≥ 80% |
