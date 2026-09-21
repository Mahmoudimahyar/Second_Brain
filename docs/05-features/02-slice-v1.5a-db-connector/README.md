# Feature: V1.5a — External Data Source Connector + Cross-Graph Mapping + User-Declared Tiering

**Status:** Spec only. Implementation blocked on: V1 final verdict filed (✅ 2026-05-21) + ADR-012/-013/-014/-015 ratified (pending) + Mahyar's go-ahead.
**Sub-slice ratified:** V1.5-R1 (2026-05-24).
**Owner:** Mahyar (decisions) + Claude (implementation, post-ADRs).
**Time budget:** 4–5 weeks of focused work after ADRs land.
**Acceptance level:** end-to-end DB connect → schema discovery → mapping wizard → graph materialization → cross-graph link to V1 forum graph. Headless API surface (CLI / Python) only — UI lands in V1.5b.

## What this sub-slice proves

The generalization step from V1's hard-coded ADEA Excel + Reddit JSONL ingest to a **plug-in data source** model where the user brings their own database and the system absorbs it into the trust-tier graph correctly.

1. **DataSource Protocol** — a new abstraction above `SourceAdapter`. Wraps connection lifecycle, schema discovery, user-driven projection, tier declaration, and re-pull cadence. The four V1.5a engines (Postgres / MySQL / SQLite / Neo4j) implement this Protocol; the existing V1 adapters get wrapped to satisfy it without behavior change.
2. **Schema discovery + auto-suggest mapping** — connect to a DB, system reads table/column metadata, samples N rows per table, embeds column-name + value samples via BGE-small, suggests a `table → node-type` or `FK → edge-type` mapping per table. User accepts/edits each suggestion.
3. **User-declared source tier** — at connect time the user picks the tier (default L2). L1 upgrade is gated behind a confirmation dialog stating "this data is immutable ground truth for my domain; existing L1 nodes will not be overwritten." Tier choice is stored on every node + edge produced by this connector.
4. **Cross-graph entity mapping** — entities produced by the new connector are auto-matched against entities already in the graph (e.g., school names from the connected DB match school names already in ADEA L1 + Reddit mentions). Same DITTO + BGE pipeline as V1's alias resolution, run in cross-source mode. F1 ≥ 0.92 on a new 100-pair gold set.
5. **Re-pull cadence** — connector remembers its last-pull cursor (max `updated_at` per table, or `created_utc` for forums). Re-running the connector pulls only deltas. Idempotent on identical deltas.
6. **L1 immutability holds across new ground** — an L2 connector that produces a `school:nyu_dental` entity does NOT overwrite the L1 ADEA node; instead it creates a cross-graph `SAME_AS` edge with `confidence` + `references`.

## What this sub-slice does NOT prove (deferred to V1.5b / V1.5c / V2)

- Web UI for the connect-DB wizard or the mapping-approval flow. V1.5a ships a headless API + a thin CLI (`secbrain connect db ...`, `secbrain map suggest ...`). V1.5b builds the UI on top.
- The iterative cluster-cull + node/edge proposal loop. That's V1.5b.
- Web-search-grounded conflict resolution. V1.5c.
- Per-team dashboards. V1.5c.
- Slack / Notion / website-crawler data sources. V1.6.
- Multi-tenant credentials / OS-keychain. V2.

## Why this sub-slice first

- It's pure backend — the engine grows a new capability without depending on the UI. Lets us nail the abstraction before any rendering decisions lock us in.
- It removes the largest hardcode in V1 (the assumption that data sources are local files in `External Data/`).
- It produces the new MCP surfaces (`connect_data_source`, `discover_schema`, `suggest_mapping`, `commit_mapping`, `pull_delta`, `crosslink_entities`) that V1.5b's UI consumes directly.
- It's the smallest end-to-end demo of the V2 `developer_tool` posture — "bring your own data."

## Acceptance criteria (testable, blocking)

1. **DataSource Protocol implemented + tested** — `src/ingestion/sources/base.py` defines `DataSource`. The four engines + a wrapped-V1 adapter (`ReSourceAdapterDataSource`) all satisfy it. Hypothesis test asserts every `DataSource` round-trips the lifecycle states without resource leaks.
2. **All four engines pass connect + discover + dry-run** — Postgres / MySQL / SQLite / Neo4j each: connect using `.env`-loaded credentials → list tables (SQL) or labels (Neo4j) → sample 100 rows → return a `SchemaSnapshot`. Tests use ephemeral local containers (`testcontainers-python`).
3. **Auto-suggest mapping F1 ≥ 0.85 on a hand-labeled 50-pair gold set** — `MappingSuggester` produces `(table → node-type | edge-type | skip)` decisions for a seeded ADEA-shaped Postgres dump. Gold set in `evals/gold/v1.5a-mapping-suggestions.jsonl`.
4. **Tier declaration enforcement** — attempt to mark a connector L1 without the confirmation flag returns `INVALID_TIER_UPGRADE`. Tier-stamped on every materialized node + edge.
5. **Cross-graph entity match F1 ≥ 0.92** — on a 100-pair gold set in `evals/gold/v1.5a-cross-graph.jsonl` covering ADEA school names ↔ Reddit mentions ↔ an external Postgres dump's school table. Reuses the V1 DITTO + BGE pipeline in cross-source mode.
6. **L1 immutability preserved** — a connector declared L2 that produces a conflicting metric for an L1 school flags the L2 claim `invalidated_by_official_data` (per V1 FR-6.1) and leaves the L1 node unchanged.
7. **Re-pull idempotency** — running the same connector twice in a row with no source-side changes is a no-op. Hypothesis property: re-pulls are commutative with no-op-stamping on unchanged rows.
8. **Citation traceability ≥ 99%** — every node + edge produced by the connector carries `references` pointing to the source table + primary-key value.
9. **Audit log covers every connector action** — `audit_log` kind enum extended with `connector_*` (connect, discover, map_suggest, map_commit, pull_delta, crosslink). 100% coverage tested.
10. **Verification Before Completion report** in `.agent/reports/v1.5a-slice.md` per AGENTS.md.

Non-functional:

- **NFR-1** Pull-delta on a 100K-row table completes in < 90s on Mahyar's workstation (GTX 1080, 64GB RAM).
- **NFR-2** Schema discovery on a 200-table Postgres DB completes in < 10s.
- **NFR-3** Cross-graph match latency for a single mention p95 < 30ms (excluding the embedding step, which is amortized).
- **NFR-4** Audit log + idempotency invariants hold under hypothesis property-based tests with ≥ 500 random source-state trajectories.
- **NFR-5** Repro: identical source state + identical config → identical graph state (content-hash idempotency).
- **NFR-6** Test coverage ≥ 80% line on `src/ingestion/sources/*` + `src/er/cross_graph.py`.

## Sub-files in this packet

- `README.md` — this file
- `requirements.md` — functional + non-functional requirements
- `context.md` — links to upstream V1 architecture + relevant ADRs + V1.5 master brief
- `plan.md` — phased implementation plan
- `data.md` — V1.5a data model additions (`DataSource` schema, `CrossGraphLink` edge type, tier-declaration table)
- `api.md` — new MCP + Python API signatures
- `state-machine.md` — connector lifecycle + mapping-approval state machine
- `test-plan.md` — test matrix mapping ACs to test cases
- `decisions.md` — slice-local decisions (extends ADRs 012-017)
- `known-issues.md` — discovered during implementation
- `changelog.md` — slice-local change log

## Open questions (must resolve before implementation starts)

None — V1.5-R1 closed scope. Anything new that surfaces during implementation gets logged in `known-issues.md` per the bootstrap discipline.
