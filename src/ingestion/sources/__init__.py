"""V1.5a `DataSource` Protocol + engine implementations.

The `DataSource` Protocol generalizes V1's `SourceAdapter` by wrapping it with
connection lifecycle, schema discovery, user-driven projection, tier
declaration, and re-pull cadence. V1's file-based adapters become a
`LocalFileDataSource`; V1.5a adds Postgres / MySQL / SQLite / Neo4j engines.

See `docs/05-features/02-slice-v1.5a-db-connector/data.md` for the schema and
`api.md` for the surface contract.
"""

from src.ingestion.sources.base import (
    CanonicalRecord,
    ColumnSpec,
    CursorState,
    DataSource,
    DataSourceLifecycleState,
    ForeignKeySpec,
    LabelSpec,
    LocalFileConfig,
    MySQLConfig,
    Neo4jConfig,
    PostgresConfig,
    RelTypeSpec,
    SchemaSnapshot,
    SourceConfig,
    SourceManifest,
    SQLiteConfig,
    TableSpec,
)
from src.ingestion.sources.local_file import LocalFileDataSource
from src.ingestion.sources.mysql import MySQLDataSource
from src.ingestion.sources.neo4j import Neo4jDataSource
from src.ingestion.sources.postgres import PostgresDataSource
from src.ingestion.sources.registry import DataSourceRegistry
from src.ingestion.sources.sqlite import SQLiteDataSource

__all__ = [
    "CanonicalRecord",
    "ColumnSpec",
    "CursorState",
    "DataSource",
    "DataSourceLifecycleState",
    "DataSourceRegistry",
    "ForeignKeySpec",
    "LabelSpec",
    "LocalFileConfig",
    "LocalFileDataSource",
    "MySQLConfig",
    "MySQLDataSource",
    "Neo4jConfig",
    "Neo4jDataSource",
    "PostgresConfig",
    "PostgresDataSource",
    "RelTypeSpec",
    "SQLiteConfig",
    "SQLiteDataSource",
    "SchemaSnapshot",
    "SourceConfig",
    "SourceManifest",
    "TableSpec",
]
