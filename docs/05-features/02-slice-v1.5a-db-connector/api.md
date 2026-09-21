# API — V1.5a

> Seven new MCP tools + a Python API surface. Pydantic models in `data.md` are the single source of truth — Zod schemas are generated from them for V1.5b consumption.

## MCP tools (Tier 1, registered on `secbrain-v1`)

All tools accept structured input, return structured output with `ConnectorReceipt`-style envelopes, and write to `audit_log` on every invocation. Errors return discriminated-union problem objects.

### `connect_data_source`

```
Input:
  engine: Literal['postgres','mysql','sqlite','neo4j','local_file']
  config: SourceConfig                        # engine-specific discriminated union
  tier: SourceTier = 'L2'
  confirm_l1_immutable: bool = False          # required iff tier='L1'
  display_name: str
  credential_ref: str | None                  # env-var name; not the secret

Output: ConnectorReceipt

Errors:
  INVALID_TIER_UPGRADE — tier='L1' without confirm_l1_immutable
  ENGINE_UNSUPPORTED — engine not in V1.5a set
  CONNECTION_FAILED — driver-level error; cause attached
  CRED_NOT_FOUND — credential_ref env var missing
```

### `discover_schema`

```
Input:
  source_id: str
  refresh: bool = False                       # if True, ignore cached snapshot

Output: SchemaSnapshot

Errors:
  SOURCE_NOT_FOUND
  CONNECTION_FAILED
  SCHEMA_TOO_LARGE — > 5000 tables; offer paged discovery
```

### `suggest_mapping`

```
Input:
  source_id: str
  schema_snapshot_hash: str | None            # use a specific snapshot; default = latest

Output: MappingProposal

Errors:
  SOURCE_NOT_FOUND
  SCHEMA_NOT_DISCOVERED — must call discover_schema first
```

### `commit_mapping`

```
Input:
  source_id: str
  decisions: list[TableMappingProposal]       # user-edited list
  dry_run: bool = False

Output:
  MappingCommitReceipt:
    source_id: str
    decisions_committed: int
    decisions_pending_hitl: int
    estimated_pull_rows: int
    dry_run: bool

Errors:
  SOURCE_NOT_FOUND
  INVALID_MAPPING — semantic error in decisions
  L1_CONFLICT — committing this mapping would create a multi-L1 collision
```

### `pull_delta`

```
Input:
  source_id: str
  mode: Literal['delta','full_resync'] = 'delta'
  table_filter: list[str] | None              # restrict pull to subset

Output: PullReceipt

Errors:
  SOURCE_NOT_FOUND
  MAPPING_NOT_COMMITTED — commit_mapping must run first
  PULL_IN_PROGRESS
  COST_CAP_HIT — propagated from web-search subsystem (V1.5c only; null in V1.5a)
```

### `list_connectors`

```
Input:
  include_disconnected: bool = False
  engine_filter: list[str] | None

Output:
  ConnectorList:
    connectors: list[ConnectorSummary]

ConnectorSummary:
  source_id: str
  engine: str
  display_name: str
  tier: SourceTier
  status: str
  last_pull_at: datetime | None
  last_pull_status: str | None
  nodes_total: int
  edges_total: int
  crosslinks_total: int
```

### `disconnect_data_source`

```
Input:
  source_id: str
  retain_graph: bool = True                   # if False, close t_ingest_to on all materialized edges

Output: DisconnectReceipt

Errors:
  SOURCE_NOT_FOUND
  ACTIVE_PULL_RUNNING
```

## Python API (internal — for V1.5b backend + Prefect flows)

```python
from src.ingestion.api import IngestionService
from src.ingestion.sources.base import DataSource

class IngestionService:
    def connect(self, manifest: SourceManifest) -> ConnectorReceipt: ...
    def discover(self, source_id: str, *, refresh: bool = False) -> SchemaSnapshot: ...
    def suggest_mapping(self, source_id: str) -> MappingProposal: ...
    def commit_mapping(self, source_id: str, decisions: list[TableMappingProposal], *, dry_run: bool = False) -> MappingCommitReceipt: ...
    def pull(self, source_id: str, *, mode: Literal['delta','full_resync'] = 'delta', tables: list[str] | None = None) -> PullReceipt: ...
    def list_connectors(self, *, include_disconnected: bool = False) -> list[ConnectorSummary]: ...
    def disconnect(self, source_id: str, *, retain_graph: bool = True) -> DisconnectReceipt: ...
```

## CLI surface (V1.5a ships these for power-users + smoke tests)

```
secbrain connect db --engine postgres --display "Partner DB" --tier L2 --cred-ref PARTNER_DB_PASSWORD
secbrain discover-schema --source-id ds:postgres:partner_db
secbrain suggest-mapping --source-id ds:postgres:partner_db --out mapping.json
secbrain commit-mapping --source-id ds:postgres:partner_db --decisions mapping.json
secbrain pull --source-id ds:postgres:partner_db [--mode delta|full_resync]
secbrain list-connectors
secbrain disconnect --source-id ds:postgres:partner_db [--retain-graph|--purge]
```

## FastAPI routes (V1.5b consumes — defined in V1.5a so the surface is stable)

```
POST   /api/v1/sources                       # connect_data_source
GET    /api/v1/sources                       # list_connectors
GET    /api/v1/sources/{source_id}           # detail
PATCH  /api/v1/sources/{source_id}           # update display_name/tier (re-tier triggers re-pull)
DELETE /api/v1/sources/{source_id}           # disconnect
POST   /api/v1/sources/{source_id}/discover  # discover_schema
GET    /api/v1/sources/{source_id}/schema    # last snapshot
POST   /api/v1/sources/{source_id}/mapping/suggest
POST   /api/v1/sources/{source_id}/mapping/commit
GET    /api/v1/sources/{source_id}/mapping   # current committed mapping
POST   /api/v1/sources/{source_id}/pull      # pull_delta
GET    /api/v1/sources/{source_id}/pulls     # paginated history
```

All routes require nothing more than localhost binding (V1.5 no auth per ADR-013). V2 multi-tenant adds `/t/{tenant}/` prefix.

## Engine-specific `SourceConfig` shapes

```
PostgresConfig:
  host: str
  port: int = 5432
  database: str
  user: str
  ssl_mode: Literal['disable','allow','prefer','require','verify-ca','verify-full'] = 'prefer'
  search_path: str | None
  schema_filter: list[str] | None             # ['public', 'analytics']

MySQLConfig:
  host: str
  port: int = 3306
  database: str
  user: str
  ssl_disabled: bool = False

SQLiteConfig:
  file_path: str                              # absolute path on Mahyar's machine

Neo4jConfig:
  uri: str                                    # bolt://localhost:7687 or neo4j+s://...
  user: str
  database: str = 'neo4j'

LocalFileConfig:
  paths: list[str]
  adapter: Literal['l1_excel','l1_pdf','l2_html','l5_reddit','l5_sdn']  # V1 adapters wrapped
```

Credentials NEVER go in `SourceConfig` — only `credential_ref` (an env-var name). The connector resolves at connect-time and never logs the resolved value.

## Idempotency contract

- `connect_data_source` with identical `(engine, config, display_name)` returns the existing `source_id` with `status='already_connected'`. No state change.
- `commit_mapping` with identical decisions is a no-op; receipt returns `decisions_committed=0`.
- `pull_delta` with no source-side changes writes 0 nodes / 0 edges.
- `disconnect` with `retain_graph=True` is reversible (a future `connect` with same config re-attaches).
- `disconnect` with `retain_graph=False` is bitemporally reversible (re-ingest re-opens `t_ingest_from`).

## Observability

Every MCP/API call emits a structlog JSON event + writes an `audit_log` row + (for LLM-invoking calls only) a Langfuse trace. Mapping-suggestion runs annotate `langfuse_session = source_id` so per-connector LLM cost is attributable.
