"""V1.5a `DataSource` Protocol + supporting Pydantic models.

Per `docs/05-features/02-slice-v1.5a-db-connector/data.md` + `api.md`.
Pydantic models here are the single source of truth — V1.5b derives Zod
schemas from these via `make generate-types`.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

SourceTier = Literal["L1", "L2", "L3", "L4", "L5"]
EngineKind = Literal["postgres", "mysql", "sqlite", "neo4j", "local_file"]
LocalAdapterKind = Literal[
    "l1_excel", "l1_pdf", "l2_html", "l5_reddit", "l5_sdn",
]


# ---------------------------------------------------------------------------
# Lifecycle states (per state-machine.md §1)
# ---------------------------------------------------------------------------


class DataSourceLifecycleState(StrEnum):
    UNREGISTERED = "unregistered"
    REGISTERED = "registered"
    DISCOVERED = "discovered"
    SUGGESTED = "suggested"
    MAPPED = "mapped"
    PULLING = "pulling"
    ACTIVE = "active"
    PAUSED = "paused"
    ERRORED = "errored"
    DISCONNECTED = "disconnected"


# ---------------------------------------------------------------------------
# Engine-specific config (discriminated union; per api.md §SourceConfig)
# ---------------------------------------------------------------------------


class PostgresConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    engine: Literal["postgres"] = "postgres"
    host: str
    port: int = 5432
    database: str
    user: str
    ssl_mode: Literal[
        "disable", "allow", "prefer", "require", "verify-ca", "verify-full",
    ] = "prefer"
    search_path: str | None = None
    schema_filter: list[str] | None = None


class MySQLConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    engine: Literal["mysql"] = "mysql"
    host: str
    port: int = 3306
    database: str
    user: str
    ssl_disabled: bool = False


class SQLiteConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    engine: Literal["sqlite"] = "sqlite"
    file_path: str


class Neo4jConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    engine: Literal["neo4j"] = "neo4j"
    uri: str
    user: str
    database: str = "neo4j"


class LocalFileConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    engine: Literal["local_file"] = "local_file"
    adapter: LocalAdapterKind
    paths: list[str]


SourceConfig = (
    PostgresConfig | MySQLConfig | SQLiteConfig | Neo4jConfig | LocalFileConfig
)


# ---------------------------------------------------------------------------
# Schema descriptors (per data.md §Pydantic models)
# ---------------------------------------------------------------------------


class ColumnSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    type: str                       # engine-native type string
    nullable: bool = True
    sample_values: list[Any] = Field(default_factory=list)


class ForeignKeySpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    columns: list[str]
    references_table: str
    references_columns: list[str]


class TableSpec(BaseModel):
    """SQL table (or wrapped V1 adapter's canonical-record-type)."""

    model_config = ConfigDict(extra="forbid")

    name: str
    column_specs: list[ColumnSpec]
    primary_key: list[str] | None = None
    foreign_keys: list[ForeignKeySpec] = Field(default_factory=list)
    row_count_estimate: int | None = None
    sample_rows: list[dict[str, Any]] = Field(default_factory=list)


class LabelSpec(BaseModel):
    """Neo4j node label."""

    model_config = ConfigDict(extra="forbid")

    name: str
    property_specs: list[ColumnSpec] = Field(default_factory=list)
    sample_nodes: list[dict[str, Any]] = Field(default_factory=list)
    node_count_estimate: int | None = None


class RelTypeSpec(BaseModel):
    """Neo4j relationship type."""

    model_config = ConfigDict(extra="forbid")

    name: str
    start_labels: list[str] = Field(default_factory=list)
    end_labels: list[str] = Field(default_factory=list)
    property_specs: list[ColumnSpec] = Field(default_factory=list)
    edge_count_estimate: int | None = None


class SchemaSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: str
    discovered_at: datetime
    tables: list[TableSpec] = Field(default_factory=list)
    labels: list[LabelSpec] = Field(default_factory=list)
    rel_types: list[RelTypeSpec] = Field(default_factory=list)
    snapshot_hash: str | None = None


# ---------------------------------------------------------------------------
# Cursor + canonical record envelope
# ---------------------------------------------------------------------------


class CursorState(BaseModel):
    """Per-source-table cursor for delta pulls (FR-1.5a-6).

    For SQL: typically `cursor_column='updated_at'`, value = ISO timestamp.
    For local files: `cursor_column='content_hash'`, value = sha256 of file
    set (or concatenation).
    """

    model_config = ConfigDict(extra="forbid")

    cursor_table: str | None = None
    cursor_column: str
    cursor_value: str
    last_full_resync_at: datetime | None = None


@dataclass(frozen=True)
class CanonicalRecord:
    """An envelope around a single canonical record emitted by a DataSource.

    `table_or_label` is the conceptual bucket the record belongs to (e.g.,
    `"post"`, `"comment"`, `"user"` for Reddit; `"School"`, `"Metric"` for
    ADEA). `payload` is the engine-specific canonical dataclass (immutable).
    `primary_key` is a stable identifier for citation traceability.
    `content_hash` is the per-record hash used for idempotency (FR-1.5a-6.2).
    """

    table_or_label: str
    payload: object
    primary_key: str
    content_hash: str


# ---------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------


class SourceManifest(BaseModel):
    """User-facing source descriptor (per data.md §SourceManifest)."""

    model_config = ConfigDict(extra="forbid")

    source_id: str
    engine: EngineKind
    display_name: str
    config: SourceConfig = Field(discriminator="engine")
    tier: SourceTier = "L2"
    credential_ref: str | None = None
    notes: str | None = None


# ---------------------------------------------------------------------------
# The Protocol itself
# ---------------------------------------------------------------------------


@runtime_checkable
class DataSource(Protocol):
    """V1.5a connector contract (FR-1.5a-1.1).

    Lifecycle: `open()` is called once before any other method; `close()`
    releases resources. Implementations are context-manager safe (use
    `with ds:` to ensure deterministic cleanup).

    `discover_schema()` returns a snapshot of the source's structural shape.
    For SQL engines this enumerates tables + columns + FKs. For Neo4j this
    enumerates labels + relationship types. For wrapped V1 adapters this
    describes the canonical record types the adapter emits.

    `sample_rows(table_or_label, n)` returns N sample rows (as dicts) from
    the named bucket. Used by the UI + `MappingSuggester` for embedding-based
    hints (V1.5a Phase 3).

    `pull_delta(cursor)` yields `CanonicalRecord` envelopes for every record
    newer than `cursor`. Idempotent: re-running with the same cursor against
    an unchanged source yields nothing. `cursor=None` means "pull everything".

    `manifest()` returns the original `SourceManifest` (read-only).
    """

    @property
    def source_id(self) -> str: ...

    @property
    def tier(self) -> SourceTier: ...

    def manifest(self) -> SourceManifest: ...

    def open(self) -> None: ...

    def close(self) -> None: ...

    def is_open(self) -> bool: ...

    def discover_schema(self) -> SchemaSnapshot: ...

    def sample_rows(
        self, table_or_label: str, n: int = 100,
    ) -> list[dict[str, Any]]: ...

    def pull_delta(
        self, cursor: CursorState | None,
    ) -> Iterator[CanonicalRecord]: ...

    def advance_cursor(self) -> CursorState | None:
        """Return a fresh cursor pointing at the current source state.

        Called after a successful pull. The returned cursor is what the
        caller passes back on the next `pull_delta(cursor)` to get only
        deltas since this point.
        """
        ...


# ---------------------------------------------------------------------------
# Helpers used by every concrete DataSource
# ---------------------------------------------------------------------------


def iter_records(
    records: Iterable[CanonicalRecord],
) -> Iterator[CanonicalRecord]:
    """Identity passthrough — explicit to keep imports easy in callers."""

    yield from records
