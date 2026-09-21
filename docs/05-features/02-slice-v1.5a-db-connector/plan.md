# Plan — V1.5a

> Sequencing rule (per AGENTS.md): every phase uses TDD — failing test first, smallest correct change, targeted tests, broader tests, docs updated, then move on.

## Phase 0 — Prereqs (gating)

| # | Item | Owner | Status |
|---|---|---|---|
| 0.1 | V1 final verdict filed | Claude | ✅ 2026-05-21 |
| 0.2 | V1.5 master brief ratified | Mahyar | ✅ 2026-05-24 |
| 0.3 | ADR-012 multi-level graph views | Claude (this batch) | Drafted |
| 0.4 | ADR-013 UI tech stack | Claude (this batch) | Drafted |
| 0.5 | ADR-014 external DB connector tiering | Claude (this batch) | Drafted |
| 0.6 | ADR-015 cross-graph entity mapping | Claude (V1.5a kickoff) | Pending |
| 0.7 | Mahyar provides test Postgres connection | Mahyar | Pending |
| 0.8 | `testcontainers-python` added to dev deps | Claude (Phase 1) | Pending |

## Phase 1 — DataSource Protocol + LocalFileDataSource wrapper

1. **Failing-first test**: `test_data_source_protocol.py::test_local_file_round_trip` — wrap existing L5 Reddit adapter as `LocalFileDataSource`; assert lifecycle (open → discover → pull_delta → close) returns identical canonical records to V1's direct adapter call.
2. **Smallest code**:
   - `src/ingestion/sources/base.py` — `DataSource` Protocol, `SchemaSnapshot` Pydantic model, `SourceManifest`, `CursorState`.
   - `src/ingestion/sources/local_file.py` — wraps `SourceAdapter` instances; cursor = last-ingested file content-hash.
   - `src/ingestion/api.py` updated — `IngestionService` routes through `DataSource` instead of `SourceAdapter` directly. V1 callsites unaffected (wrapper preserves semantics).
3. **Targeted tests**: lifecycle property tests; resource-leak hypothesis; cursor stability across restarts.
4. **Acceptance**: V1 test suite passes unchanged; new `DataSource` tests pass.

## Phase 2 — Engine implementations

Per engine: failing connect test → connect impl → failing discover test → discover impl → failing sample test → sample impl → failing delta test → delta impl. Use `testcontainers-python` for ephemeral Postgres + MySQL + Neo4j; SQLite uses temp files.

### 2a — Postgres
1. Failing test: `tests/ingestion/sources/test_postgres.py::test_connect_and_discover_basic_schema` — spins up Postgres container, creates 3 tables with FKs, asserts `SchemaSnapshot` contains all tables + columns + FK relationships.
2. Code: `src/ingestion/sources/postgres.py` using `psycopg[binary]`. Connection pool via `psycopg_pool`.
3. Tests: schema discovery; row sampling honors row-level security; pull_delta on `updated_at` cursor; SSL mode passthrough.

### 2b — MySQL
Same shape using `mysql-connector-python` + `INFORMATION_SCHEMA` queries.

### 2c — SQLite
Same shape using stdlib `sqlite3` + `sqlite_master` + `PRAGMA` calls. Also doubles as a self-test fixture: connector points at V1's own L1 side-store and re-ingests it, verifying the round-trip.

### 2d — Neo4j
Uses official `neo4j` driver + Cypher introspection. Labels → candidate node types; relationship types → candidate edge types; sample-node call per label.

**Acceptance phase 2**: all four engines pass connect + discover + sample + delta + close on container fixtures + on a synthetic Postgres dump shaped like ADEA Report 2.

## Phase 3 — MappingSuggester

1. **Failing-first test**: `tests/extraction/test_mapping_suggester.py::test_suggests_schools_table_as_school_node` — given a `SchemaSnapshot` of a Postgres table named `schools` with columns `(id, name, city, state)`, the suggester returns `node_type=School` with confidence ≥ 0.90.
2. **Smallest code**:
   - `src/extraction/mapping_suggester.py` — `MappingSuggester` class. Loads V1 data-dictionary entries from `docs/07-data/data-dictionary.md` as the "node-property dictionary."
   - Column-name embedding cache (content-hash keyed).
   - Heuristics per FR-1.5a-3.3.
3. **Tests**:
   - F1 ≥ 0.85 on a 50-pair seed gold set (`evals/gold/v1.5a-mapping-suggestions.jsonl`).
   - Join-table detection (table with 2 PKs that are both FKs → edge candidate).
   - Prior-decision boost (decision logged in `mapping_decisions` increases similar-table confidence on subsequent runs).
4. **Acceptance**: F1 ≥ 0.85; suggestions produce a coherent mapping for the V1 SQLite side store re-ingested through the SQLite engine.

## Phase 4 — Tier declaration + L1 immutability enforcement

1. **Failing-first test**: `tests/ingestion/sources/test_tier_enforcement.py::test_l1_without_confirmation_rejected` — `connect_data_source(engine='postgres', tier='L1')` without `confirm_l1_immutable=True` returns `INVALID_TIER_UPGRADE`.
2. **Smallest code**: tier-validation hook in `IngestionService.connect`; persistence in `data_sources` SQLite table with `tier` + `l1_confirmed_at` columns.
3. **Tests**: L1 upgrade requires confirmation; L2 default; tier stamping on every materialized node + edge; multiple-L1-claims-detected; re-tiering closes old `t_ingest_to`.
4. **Acceptance**: ACs 4 + 6 from README pass.

## Phase 5 — Cross-graph entity mapping

1. **Failing-first test**: `tests/er/test_cross_graph.py::test_matches_adea_school_to_external_postgres_school` — given V1's existing graph + a new Postgres connector materializing a school table, `CrossGraphLinker.link()` produces `SAME_AS` edges between matching schools at confidence ≥ 0.90.
2. **Smallest code**:
   - `src/er/cross_graph.py` — `CrossGraphLinker`, reuses V1's `Pass1MentionExtractor` blocking + DITTO reranker; new `cross_source_mode=True` flag.
   - `SAME_AS` edge type added to `src/graph/schema.py` + bitemporal-edge writer.
3. **Tests**:
   - F1 ≥ 0.92 on the 100-pair v1.5a cross-graph gold set.
   - Auto-accept / HITL / reject routing matches V1 alias thresholds.
   - Bidirectional semantic mirroring (querying either side returns both).
4. **Acceptance**: AC-5 from README passes.

## Phase 6 — Re-pull cadence + Prefect flow

1. **Failing-first test**: `tests/ingestion/flows/test_data_source_pull.py::test_pull_delta_idempotent` — pull twice in a row with no source changes; second pull writes 0 nodes / 0 edges.
2. **Smallest code**:
   - `src/ingestion/sources/state.py` — `data_source_state` SQLite table + cursor read/write API.
   - `flows/data_source_pull.py` — Prefect flow.
3. **Tests**: cursor persistence; idempotent re-pull; `--full-resync` closes old `t_ingest_to`; daily schedule wired in Prefect.
4. **Acceptance**: AC-7 passes; hypothesis property test passes 500 random trajectories.

## Phase 7 — Outbound MCP tools + audit log + Verification Before Completion

1. **Tests**: contract tests on each of the seven new MCP tools (FR-1.5a-7.*); audit-log coverage tests.
2. **Code**: `src/mcp/outbound.py` extended with the seven new tool handlers; audit-log enum extended.
3. **Verification**: `.agent/reports/v1.5a-slice.md` written per AGENTS.md.

## Phase 8 — Integration smoke

End-to-end: connect to test Postgres → discover → suggest mapping → user edits one suggestion → commit → pull-delta → cross-graph link to existing V1 ADEA graph → query the merged graph via Level A / B / C surfaces.

Smoke goes into `.agent/reports/v1.5a-integration-smoke.md`.

## Risk register

| Risk | Mitigation |
|---|---|
| `testcontainers-python` flakes in CI | Pin image SHAs; fallback to skipped-with-warning in CI, full run on Mahyar's workstation |
| Mapping suggester confidence calibration off | Phase 3 gates on gold-set F1 ≥ 0.85 before merging; calibration audit after first 50 real decisions |
| Cross-graph F1 < 0.92 | Reuse V1 alias-resolution stack; fail-loud test gate; back off to HITL-heavy if needed |
| Neo4j engine complexity (different mental model) | Phase 2d limited to label-and-rel-type introspection; full Cypher schema discovery is V1.6 |
| Plaintext credentials in `.env` exposes risk | UI banner (V1.5b); restrict `.env` mode 0600; add lint that rejects committed `.env` content |
| Cursor logic gets wrong on tables with no `updated_at` | Documented fallback chain (`created_at` → `pk`); audit-log warns when fallback engaged |
| Postgres + MySQL drivers add too many transitive deps | Optional extras: `pip install secbrain[postgres,mysql,neo4j]`; core install stays slim |

## Provisional time estimate (after Phase 0 gates pass)

| Phase | Hours |
|---:|---|
| 1 — DataSource Protocol + LocalFile wrapper | 14 |
| 2 — Four engine implementations | 32 (8 × 4) |
| 3 — MappingSuggester + gold set | 22 |
| 4 — Tier declaration + L1 enforcement | 10 |
| 5 — Cross-graph entity mapping + gold set | 24 |
| 6 — Re-pull cadence + Prefect flow | 14 |
| 7 — MCP tools + audit log + verification | 16 |
| 8 — Integration smoke | 8 |
| **Total** | **~140 hours** (4 focused weeks) |
