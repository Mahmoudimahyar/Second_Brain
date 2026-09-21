# Data Model — V1.5a

> V1.5a slice subset. Extends V1's data model. Full schema lives in `docs/07-data/data-dictionary.md` (updated post-V1.5a).

## New SQLite tables

### `data_sources`
```
source_id              TEXT  PRIMARY KEY        -- e.g., "ds:postgres:adea_partner_2026_03"
engine                 TEXT  NOT NULL           -- "postgres" / "mysql" / "sqlite" / "neo4j" / "local_file"
display_name           TEXT  NOT NULL
config_json            TEXT  NOT NULL           -- engine-specific; NEVER contains plaintext creds
credential_ref         TEXT                     -- env-var name (e.g., "PARTNER_DB_PASSWORD")
tier                   TEXT  NOT NULL           -- "L1" / "L2" / "L3" / "L4" / "L5"
l1_confirmed_at        DATETIME                 -- nullable; set iff tier=L1
status                 TEXT  NOT NULL           -- "active" / "paused" / "errored" / "disconnected"
created_at             DATETIME NOT NULL
created_by             TEXT  NOT NULL
last_pull_at           DATETIME
last_pull_status       TEXT
notes                  TEXT
```

### `mapping_decisions`
```
decision_id            TEXT  PRIMARY KEY
source_id              TEXT  NOT NULL REFERENCES data_sources(source_id)
table_or_label         TEXT  NOT NULL           -- SQL table name OR Neo4j label
mapping_type           TEXT  NOT NULL           -- "node" / "edge" / "skip"
target_type            TEXT                     -- e.g., "School" / "AUTHORED" / NULL on skip
target_properties_json TEXT                     -- per-column property mapping
edge_endpoints_json    TEXT                     -- iff mapping_type=edge
suggested_confidence   REAL                     -- the MappingSuggester output
decided_by             TEXT  NOT NULL
decided_at             DATETIME NOT NULL
applied_in_pull_id     TEXT
notes                  TEXT
```

### `data_source_state` (per-source cursor)
```
source_id              TEXT  PRIMARY KEY REFERENCES data_sources(source_id)
cursor_table           TEXT                     -- which table the cursor applies to (multi-table case)
cursor_column          TEXT                     -- the column we track (e.g., "updated_at")
cursor_value           TEXT                     -- serialized; type-aware on read
last_full_resync_at    DATETIME
schema_snapshot_hash   TEXT                     -- fingerprint of the last-discovered schema; drift detection
```

### `pulls` (audit of each pull-delta operation)
```
pull_id                TEXT  PRIMARY KEY
source_id              TEXT  NOT NULL
mode                   TEXT  NOT NULL           -- "delta" / "full_resync"
started_at             DATETIME NOT NULL
finished_at            DATETIME
status                 TEXT                     -- "running" / "ok" / "errored" / "cap_hit"
rows_pulled            INTEGER
nodes_written          INTEGER
edges_written          INTEGER
crosslinks_proposed    INTEGER
crosslinks_auto_linked INTEGER
crosslinks_hitl        INTEGER
error_excerpt          TEXT
audit_log_ref          TEXT
```

## New graph edge types

### `SAME_AS` (cross-graph equivalence — ADR-015)
Standard property convention (per ADR-005):
```
edge_id                TEXT  PRIMARY KEY
subject_id             TEXT  NOT NULL           -- canonical ordering: subject_id < object_id alphabetically
object_id              TEXT  NOT NULL
subject_tier           TEXT  NOT NULL           -- per-endpoint tier preserved
object_tier            TEXT  NOT NULL
rank                   TEXT  NOT NULL           -- "preferred" / "normal" / "deprecated"
confidence             REAL  NOT NULL           -- in [0, 1]
references             JSON  NOT NULL           -- citing both side's source rows / posts
qualifiers             JSON
t_valid_from           DATETIME NOT NULL
t_valid_to             DATETIME
t_ingest_from          DATETIME NOT NULL
t_ingest_to            DATETIME
status                 TEXT                     -- "active" / "superseded" / "hitl_pending" / "hitl_committed"
```

Storage convention: single edge (canonical-ordered by node-id) with auto-mirrored read semantics. Querying either endpoint returns the edge.

## New audit_log `kind` values

- `connector_connect` — connection attempt + result
- `connector_discover` — schema discovery + duration + table count
- `connector_map_suggest` — `MappingSuggester` run + confidence distribution
- `connector_map_commit` — user-finalized mapping
- `connector_pull` — delta or full-resync pull
- `connector_crosslink` — `SAME_AS` edge candidate proposed / auto-linked / HITL-queued
- `connector_disconnect` — soft-delete (retain) or hard-delete (close `t_ingest_to`)
- `connector_tier_upgrade_attempt` — every L1 attempt, accepted or rejected
- `multiple_l1_claims` — two L1 sources in conflict on same `(subject, predicate, t_valid_year)`

## Pydantic models (FastAPI surface, also Zod-generated for V1.5b)

```
SourceManifest:
    source_id: str
    engine: Literal['postgres','mysql','sqlite','neo4j','local_file']
    display_name: str
    config: SourceConfig  # discriminated union per engine
    tier: SourceTier
    credential_ref: str | None
    notes: str | None

SchemaSnapshot:
    source_id: str
    discovered_at: datetime
    tables: list[TableSpec]  # for SQL engines
    labels: list[LabelSpec]  # for Neo4j
    rel_types: list[RelTypeSpec]  # for Neo4j

TableSpec:
    name: str
    column_specs: list[ColumnSpec]
    primary_key: list[str] | None
    foreign_keys: list[ForeignKeySpec]
    row_count_estimate: int | None
    sample_rows: list[dict]  # default N=100

MappingProposal:
    source_id: str
    per_table: list[TableMappingProposal]
    overall_confidence: float

TableMappingProposal:
    table_or_label: str
    mapping_type: Literal['node','edge','skip']
    target_type: str | None
    target_properties: dict[str, str]  # column_name -> property_name
    edge_endpoints: tuple[str, str] | None
    confidence: float
    reasoning_chain: list[str]
    routing: Literal['auto','hitl','reject']

ConnectorReceipt:
    source_id: str
    status: Literal['connected','already_connected']
    discovered_table_count: int | None  # populated if engine supports lazy discovery

PullReceipt:
    pull_id: str
    source_id: str
    mode: Literal['delta','full_resync']
    rows_pulled: int
    nodes_written: int
    edges_written: int
    crosslinks_proposed: int
    crosslinks_auto_linked: int
    crosslinks_hitl: int
    audit_log_ref: str
```

## Property conventions (carried from V1)

- `source_tier`, `rank`, `references`, `qualifiers`, bitemporal 4-tuple — required on every materialized node + edge.
- L1 immutability invariant (FR-4.3) holds: an L1 connector's nodes cannot be UPDATEd; new claims are added as new edges with their own bitemporal range.
- A node materialized by a V1.5a connector that matches an existing canonical entity via `CrossGraphLinker` does NOT replace the existing node; both nodes exist with a `SAME_AS` edge.

## Storage estimates (single-user V1.5)

- Typical Postgres connector (10K-row schools table + 100K-row metrics table): ~20 MB of new graph storage, ~5 MB of SQLite metadata (data_sources + mapping_decisions + pulls + state).
- Embedding cache for `MappingSuggester` (BGE-small, 384-dim, content-hash keyed): ~1 KB / column-sample × N columns. ~10 MB for a 200-table DB.
- Feedback log (per ADR-018): retained forever; ~1.5 KB / decision.
