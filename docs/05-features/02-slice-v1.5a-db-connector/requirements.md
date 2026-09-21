# Requirements — V1.5a

> Testable; mapping to test cases lives in `test-plan.md`. Same conventions as V1 slice 01.

## Functional requirements

### FR-1.5a-1 — DataSource Protocol

- **FR-1.5a-1.1** `src/ingestion/sources/base.py` defines a `DataSource` Protocol with at minimum: `open()`, `close()`, `discover_schema() -> SchemaSnapshot`, `sample_rows(table_or_label, n) -> list[dict]`, `pull_delta(cursor) -> Iterable[CanonicalRecord]`, `tier: SourceTier`, `source_id: str`, `manifest() -> SourceManifest`. Resource lifecycle is context-manager safe.
- **FR-1.5a-1.2** The existing V1 `SourceAdapter` instances (L1 Excel, L1 PDF, L2 HTML, L5 Reddit, L5 SDN) are wrapped by `LocalFileDataSource` which satisfies the new `DataSource` Protocol without behavior change. V1 callers route through the new abstraction.
- **FR-1.5a-1.3** A `DataSource` can be paused, resumed, and reconfigured (mapping change, projection change, tier change) without re-ingesting from scratch unless the user explicitly requests it.

### FR-1.5a-2 — Engine implementations

- **FR-1.5a-2.1 — Postgres** `PostgresDataSource` reads connection params from `.env`-loaded config (host, port, db, user, password, optional ssl_mode). Uses `psycopg[binary]`. Schema discovery via `information_schema.tables` + `information_schema.columns` + foreign-key introspection. Row sampling honors row-level security if configured.
- **FR-1.5a-2.2 — MySQL** `MySQLDataSource` mirrors Postgres but uses `mysql-connector-python`. Schema discovery via `INFORMATION_SCHEMA.TABLES` + `KEY_COLUMN_USAGE`.
- **FR-1.5a-2.3 — SQLite** `SQLiteDataSource` accepts a file path. Schema discovery via `sqlite_master` + `PRAGMA table_info` + `PRAGMA foreign_key_list`. (This engine also supports re-ingesting our own L1 side-store as a self-test fixture.)
- **FR-1.5a-2.4 — Neo4j** `Neo4jDataSource` uses the official `neo4j` driver, Cypher queries against `db.schema.visualization()` for labels + relationship types, samples nodes via `MATCH (n:Label) RETURN n LIMIT 100`. Treats Neo4j label nodes as candidate node types and relationship types as candidate edge types.
- **FR-1.5a-2.5 — Credentials** stored in plaintext `.env` per V1.5-R1. UI surfaces (V1.5b) display a banner on every credential-entry field stating "V1.5 stores this in plaintext on this machine; V2 migrates to OS keychain." See `docs/12-security/v1.5-credentials.md`.

### FR-1.5a-3 — Schema discovery + auto-suggest mapping

- **FR-1.5a-3.1** `SchemaSnapshot` is a Pydantic model containing per-table: `name`, `column_specs` (name + type + nullable + sample values), `primary_key`, `foreign_keys`, `row_count_estimate`, `sample_rows` (default N=100).
- **FR-1.5a-3.2** `MappingSuggester.suggest(snapshot) -> MappingProposal` returns a per-table verdict: `node_type` (proposed name + properties), `edge_type` (if the table is a join/bridge), `skip` (no plausible mapping). Reasoning chain attached for HITL display.
- **FR-1.5a-3.3** Suggestion heuristics: (a) embed each column-name + first 5 distinct sample values via BGE-small; (b) cosine-similarity against an internal "node-property dictionary" seeded from V1's data dictionary; (c) tables with > 50% non-null FKs → edge candidate; (d) tables with all-pk-only structure (join tables) → edge candidate; (e) tables with sample values matching known canonical entity aliases (school names, program names) get auto-bound to existing node types.
- **FR-1.5a-3.4** Per-suggestion confidence in `[0, 1]`. Auto-accept ≥ 0.90; HITL review 0.75–0.90; reject < 0.75. Same thresholds as V1 alias resolution per FR-3.
- **FR-1.5a-3.5** `MappingProposal` is editable: the user (or a CLI override) can override `node_type`, rename properties, drop columns, change cardinality of an edge type. Edits are persisted in `mapping_decisions` SQLite table.
- **FR-1.5a-3.6** `MappingSuggester` honors **prior decisions**: if the user previously mapped `users.email` → `User.email` in a similar Postgres schema, that decision shows up as a stronger seed in the next discovery.

### FR-1.5a-4 — User-declared tiering

- **FR-1.5a-4.1** `DataSource.tier` is set at connect-time. Default = `L2`. Valid values: `L1` (immutable ground truth — gated), `L2` (verifiable secondary), `L3` (community-curated), `L4` (raw web), `L5` (forum / social).
- **FR-1.5a-4.2** Setting `tier=L1` requires an explicit `--confirm-l1-immutable` CLI flag (or UI confirmation checkbox in V1.5b). Without the flag, the connector rejects the configuration with `L1_UPGRADE_REQUIRES_CONFIRMATION`.
- **FR-1.5a-4.3** Tier choice is stamped on every node + edge the connector materializes. Re-tiering a connector requires re-ingesting (the bitemporal `t_ingest_to` of the old-tier edges is closed; new edges start with the new tier).
- **FR-1.5a-4.4** An L2 connector that conflicts with an existing L1 node flags the L2 claim `invalidated_by_official_data` per V1 FR-6.1. The L1 node is unchanged. **An L1 connector that conflicts with an existing L1 node** is a configuration error (`MULTIPLE_L1_CLAIMS`) — only one L1 source per `(subject, predicate, t_valid_year)`.

### FR-1.5a-5 — Cross-graph entity mapping

- **FR-1.5a-5.1** When a connector materializes a node that may correspond to an existing canonical entity (heuristic: same node-type, name/alias overlap), `CrossGraphLinker.link(new_node) -> list[CrossGraphLinkCandidate]` runs. Reuses V1's `Pass1MentionExtractor` + BGE/HNSW blocking + DITTO reranker pipeline in cross-source mode (no Pass-1 mention parsing — the entity is already structured).
- **FR-1.5a-5.2** Per-candidate confidence in `[0, 1]`. Auto-accept ≥ 0.90 → write `SAME_AS` edge with `confidence`, `references`, both `source_tier` values (one per node). HITL ≥ 0.75 → enqueue. Reject < 0.75 → no edge; new node stands as its own canonical (becomes a new alias group if other entities then match it).
- **FR-1.5a-5.3** `SAME_AS` edges are bidirectional in semantics (auto-mirrored) and bitemporal like all other edges.
- **FR-1.5a-5.4** Cross-graph match F1 ≥ 0.92 on a 100-pair gold set covering: (a) ADEA L1 ↔ external-Postgres school table; (b) ADEA L1 ↔ Reddit alias mentions (regression on V1 alias gold); (c) external-Postgres ↔ Reddit (the new cross-source direction).
- **FR-1.5a-5.5** When V1.5b ships, `CrossGraphLink` candidates feed the same HITL queue as alias-match items. Item type = `cross_graph_link`.

### FR-1.5a-6 — Re-pull cadence

- **FR-1.5a-6.1** Each `DataSource` persists a `cursor` in `data_source_state` SQLite table. Default cursor for SQL engines: `max(updated_at)` if present, else `max(created_at)`, else `max(pk)`. Neo4j cursor: `max(node.modified)` if present, else last sync timestamp.
- **FR-1.5a-6.2** `pull_delta(cursor)` returns only rows / nodes modified after `cursor`. Idempotent on identical deltas (content-hash check before write).
- **FR-1.5a-6.3** A `--full-resync` flag bypasses the cursor and re-ingests everything. Old `t_ingest_to` is closed; new `t_ingest_from` opens. No data loss.
- **FR-1.5a-6.4** Prefect 3 flow `flows/data_source_pull.py` schedules per-connector pull cadence (daily default, configurable). Integrates with V1's `flows/full_sweep.py`.

### FR-1.5a-7 — Outbound MCP additions

- **FR-1.5a-7.1** `connect_data_source(engine, config, tier) -> ConnectorReceipt`
- **FR-1.5a-7.2** `discover_schema(source_id) -> SchemaSnapshot`
- **FR-1.5a-7.3** `suggest_mapping(source_id) -> MappingProposal`
- **FR-1.5a-7.4** `commit_mapping(source_id, mapping_decisions) -> MappingCommitReceipt`
- **FR-1.5a-7.5** `pull_delta(source_id, since=None) -> PullReceipt`
- **FR-1.5a-7.6** `list_connectors() -> list[ConnectorSummary]`
- **FR-1.5a-7.7** `disconnect_data_source(source_id, retain_graph=True) -> DisconnectReceipt` — retains materialized nodes by default; `retain_graph=False` soft-deletes per bitemporal `t_ingest_to` closure.

All seven tools registered on the existing `secbrain-v1` MCP server (Tier 1 per ADR-011).

### FR-1.5a-8 — Audit + observability

- **FR-1.5a-8.1** `audit_log.kind` enum extended with `connector_connect`, `connector_discover`, `connector_map_suggest`, `connector_map_commit`, `connector_pull`, `connector_crosslink`, `connector_disconnect`, `connector_tier_upgrade_attempt`.
- **FR-1.5a-8.2** Each connector action writes an audit row including `source_id`, `engine`, `tier`, `actor`, `before_state`, `after_state`, `ts`. Secrets never logged.
- **FR-1.5a-8.3** Langfuse tagging extended with `source_id` so per-connector cost is attributable.

## Non-functional requirements

- **NFR-1.5a-1 Latency** Pull-delta on 100K-row table < 90s on Mahyar's workstation.
- **NFR-1.5a-2 Schema discovery** < 10s on a 200-table Postgres DB.
- **NFR-1.5a-3 Cross-graph match** p95 < 30ms per mention (excluding embedding step).
- **NFR-1.5a-4 Idempotency** under hypothesis with ≥ 500 random source-state trajectories.
- **NFR-1.5a-5 Reproducibility** identical source state + config → identical graph state.
- **NFR-1.5a-6 Test coverage** ≥ 80% line on `src/ingestion/sources/*` + `src/er/cross_graph.py` + `src/extraction/mapping_suggester.py`.
- **NFR-1.5a-7 Security** plaintext `.env` for credentials is a V1.5-only allowance. No credential ever appears in audit log, structlog, or Langfuse events. Connector code includes a redaction filter on logs.
- **NFR-1.5a-8 Observability** 100% audit-log coverage for connector actions; Langfuse cost attribution per `source_id`.
- **NFR-1.5a-9 Documentation** every new MCP tool documented in `docs/06-api/v1.5-connectors.md` with request/response schemas + an example.

## Out of scope (this sub-slice)

- Web UI for any of the above. CLI + Python API only. V1.5b adds UI.
- Slack / Notion / website-crawler engines. V1.6.
- OS-keychain or Vault-backed credentials. V2.
- Live-streaming change-data-capture (CDC). V2. V1.5a uses periodic delta pull.
- Cross-graph link types beyond `SAME_AS` (e.g., `PARTIALLY_OVERLAPS`, `SUCCEEDED_BY`). V1.6.
- Auto-discovery of a Neo4j graph's full Cypher schema beyond labels + rel types. V1.6.
- Real Snowflake / BigQuery / MS SQL / Oracle engines. V1.6.

## Open dependencies

1. ADR-012 (multi-level graph views) ratified.
2. ADR-013 (UI tech stack) ratified — even though V1.5a is headless, ADR-013 fixes the Pydantic/Zod boundary that V1.5a's API surface honors.
3. ADR-014 (external DB tiering) ratified.
4. ADR-015 (cross-graph mapping) ratified.
5. Mahyar provides at least one test Postgres connection for E2E validation (can be a local Docker instance pre-seeded with synthetic ADEA-shaped data).
