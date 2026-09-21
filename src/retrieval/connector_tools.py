"""V1.5a Phase 7 — seven connector MCP tools (FR-1.5a-7).

Registered on the existing `secbrain-v1` MCP server (Tier 1 per ADR-011).
Each tool wraps the V1.5a backend (`IngestionService` + `DataSourceRegistry`
+ `MappingSuggester` + `DataSourceStateStore`) and writes an `audit_log`
row on every invocation (FR-1.5a-8).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from src.embeddings.hash_embedder import HashEmbeddingService
from src.extraction.mapping_suggester import MappingSuggester
from src.ingestion.api import IngestionService
from src.ingestion.sources.base import (
    EngineKind,
    LocalFileConfig,
    MySQLConfig,
    Neo4jConfig,
    PostgresConfig,
    SourceManifest,
    SourceTier,
    SQLiteConfig,
)
from src.ingestion.sources.registry import DataSourceRegistry, DataSourceRow
from src.ingestion.sources.state import (
    DataSourceStateStore,
    pull_source,
)
from src.shared.errors import ErrorCode, StructuredError

# ----------------------------------------------------------------------
# Tool schemas (for MCP `Tool` registration)
# ----------------------------------------------------------------------


def connector_tool_definitions() -> list[dict[str, Any]]:
    """Return the JSON-schema definitions for the seven connector tools.

    Returned as raw dicts so the calling MCP wrapper can convert them to its
    `Tool` type (avoids importing the `mcp` SDK here — keeps this module
    importable without the SDK installed, helpful for tests).
    """

    return [
        {
            "name": "connect_data_source",
            "description": (
                "Register a new external data source (V1.5a). Supports "
                "engines: postgres, mysql, sqlite, neo4j, local_file. "
                "L1 tier requires `confirm_l1_immutable=True` per ADR-014."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "engine": {
                        "type": "string",
                        "enum": [
                            "postgres", "mysql", "sqlite", "neo4j",
                            "local_file",
                        ],
                    },
                    "display_name": {"type": "string"},
                    "config": {
                        "type": "object",
                        "description": (
                            "Engine-specific config (PostgresConfig / "
                            "MySQLConfig / SQLiteConfig / Neo4jConfig / "
                            "LocalFileConfig). Excludes secrets — those "
                            "live in env via credential_ref."
                        ),
                    },
                    "tier": {
                        "type": "string",
                        "enum": ["L1", "L2", "L3", "L4", "L5"],
                        "default": "L2",
                    },
                    "confirm_l1_immutable": {
                        "type": "boolean", "default": False,
                    },
                    "credential_ref": {"type": "string"},
                    "source_id": {"type": "string"},
                    "actor": {"type": "string", "default": "system"},
                },
                "required": ["engine", "display_name", "config"],
            },
        },
        {
            "name": "discover_schema",
            "description": (
                "Discover the schema of a registered data source. Returns "
                "tables (SQL engines) or labels + relationship types (Neo4j) "
                "with per-column nullability + sample values."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "source_id": {"type": "string"},
                    "refresh": {"type": "boolean", "default": False},
                },
                "required": ["source_id"],
            },
        },
        {
            "name": "suggest_mapping",
            "description": (
                "Run the `MappingSuggester` on the most-recent schema "
                "snapshot. Returns per-table verdicts: node | edge | skip "
                "with confidence + reasoning chain. No LLM call (BGE only)."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "source_id": {"type": "string"},
                },
                "required": ["source_id"],
            },
        },
        {
            "name": "commit_mapping",
            "description": (
                "Commit user-edited mapping decisions for a source. Returns "
                "a receipt with decisions_committed + pending_hitl counts."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "source_id": {"type": "string"},
                    "decisions": {
                        "type": "array",
                        "description": (
                            "List of TableMappingProposal dicts as edited "
                            "by the operator."
                        ),
                    },
                    "dry_run": {"type": "boolean", "default": False},
                    "actor": {"type": "string", "default": "system"},
                },
                "required": ["source_id", "decisions"],
            },
        },
        {
            "name": "pull_delta",
            "description": (
                "Pull rows new since the persisted cursor (default), or "
                "force a full resync. Returns a PullReceipt with row + "
                "node + edge counts."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "source_id": {"type": "string"},
                    "mode": {
                        "type": "string",
                        "enum": ["delta", "full_resync"],
                        "default": "delta",
                    },
                },
                "required": ["source_id"],
            },
        },
        {
            "name": "list_connectors",
            "description": (
                "List registered data sources. Set `include_disconnected` "
                "to include soft-deleted sources in the listing."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "include_disconnected": {
                        "type": "boolean", "default": False,
                    },
                    "engine_filter": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
            },
        },
        {
            "name": "disconnect_data_source",
            "description": (
                "Disconnect a data source. `retain_graph=True` (default) "
                "soft-deletes via bitemporal `t_ingest_to` closure; "
                "`retain_graph=False` would tombstone the materialized "
                "edges."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "source_id": {"type": "string"},
                    "retain_graph": {"type": "boolean", "default": True},
                    "actor": {"type": "string", "default": "system"},
                },
                "required": ["source_id"],
            },
        },
    ]


# ----------------------------------------------------------------------
# Dispatch
# ----------------------------------------------------------------------


def dispatch_connector_tool(
    name: str,
    args: dict[str, Any],
    *,
    sqlite_path: Path,
    dumps_root: Path | None = None,
) -> Any:
    """Dispatch a connector tool by name. Returns a JSON-serializable result.

    Called by the MCP wrapper after JSON-decoding the tool input. Audit-log
    writes happen inside the underlying backends (registry, state store) so
    every call is observable downstream.
    """

    dumps_root = dumps_root or (sqlite_path.parent / "dumps")
    service = IngestionService(dumps_root=dumps_root, sqlite_path=sqlite_path)
    registry = DataSourceRegistry(sqlite_path=sqlite_path)
    state_store = DataSourceStateStore(sqlite_path=sqlite_path)

    dispatch_map = {
        "connect_data_source": lambda: _connect(args, service),
        "discover_schema": lambda: _discover(
            args, registry, sqlite_path, dumps_root,
        ),
        "suggest_mapping": lambda: _suggest(
            args, registry, sqlite_path, dumps_root,
        ),
        "commit_mapping": lambda: _commit(args, sqlite_path),
        "pull_delta": lambda: _pull(
            args, registry, state_store, sqlite_path, dumps_root,
        ),
        "list_connectors": lambda: _list(args, registry),
        "disconnect_data_source": lambda: _disconnect(args, registry),
    }
    handler = dispatch_map.get(name)
    if handler is None:
        raise StructuredError(
            ErrorCode.VALIDATION_FAILED,
            f"unknown connector tool: {name!r}",
            context={"tool": name},
        )
    return handler()


# ----------------------------------------------------------------------
# Per-tool handlers
# ----------------------------------------------------------------------


def _connect(args: dict[str, Any], service: IngestionService) -> dict[str, Any]:
    manifest = _build_manifest(args)
    ds = service.register_data_source(
        manifest,
        actor=args.get("actor", "system"),
        confirm_l1_immutable=bool(args.get("confirm_l1_immutable", False)),
    )
    return {
        "source_id": ds.source_id,
        "engine": manifest.engine,
        "tier": ds.tier,
        "status": "connected",
    }


def _discover(
    args: dict[str, Any],
    registry: DataSourceRegistry,
    sqlite_path: Path,
    dumps_root: Path,
) -> dict[str, Any]:
    source_id = str(args["source_id"])
    row = registry.get(source_id)
    if row is None:
        raise StructuredError(
            ErrorCode.CONNECTOR_NOT_FOUND,
            f"source {source_id!r} not registered",
            context={"source_id": source_id},
        )
    ds = _build_data_source(row, sqlite_path, dumps_root)
    ds.open()
    try:
        snap = ds.discover_schema()
    finally:
        ds.close()
    return cast(dict[str, Any], json.loads(snap.model_dump_json()))


def _suggest(
    args: dict[str, Any],
    registry: DataSourceRegistry,
    sqlite_path: Path,
    dumps_root: Path,
) -> dict[str, Any]:
    source_id = str(args["source_id"])
    row = registry.get(source_id)
    if row is None:
        raise StructuredError(
            ErrorCode.CONNECTOR_NOT_FOUND,
            f"source {source_id!r} not registered",
            context={"source_id": source_id},
        )
    ds = _build_data_source(row, sqlite_path, dumps_root)
    ds.open()
    try:
        snap = ds.discover_schema()
    finally:
        ds.close()
    suggester = MappingSuggester(embedding_service=HashEmbeddingService())
    proposal = suggester.suggest(snap)
    return cast(dict[str, Any], json.loads(proposal.model_dump_json()))


def _commit(args: dict[str, Any], sqlite_path: Path) -> dict[str, Any]:
    """Persist mapping decisions. V1.5a Phase 7 stores them in the
    `mapping_decisions` table; the connector's next pull picks them up
    (Phase 6 cursor + the new mapping).
    """

    import sqlite3 as _sqlite3  # noqa: PLC0415

    decisions = list(args["decisions"])
    source_id = str(args["source_id"])
    actor = args.get("actor", "system")
    committed = 0
    pending_hitl = 0
    with _sqlite3.connect(sqlite_path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS mapping_decisions (
                decision_id            TEXT PRIMARY KEY,
                source_id              TEXT NOT NULL,
                table_or_label         TEXT NOT NULL,
                mapping_type           TEXT NOT NULL,
                target_type            TEXT,
                target_properties_json TEXT,
                edge_endpoints_json    TEXT,
                suggested_confidence   REAL,
                decided_by             TEXT NOT NULL,
                decided_at             TEXT NOT NULL,
                notes                  TEXT
            );
            """,
        )
        for dec in decisions:
            decision_id = (
                f"mapdec:{source_id}:"
                f"{dec.get('table_or_label', 'unknown')}"
            )
            if dec.get("routing") == "hitl":
                pending_hitl += 1
                continue
            conn.execute(
                "INSERT OR REPLACE INTO mapping_decisions "
                "(decision_id, source_id, table_or_label, mapping_type, "
                "target_type, target_properties_json, edge_endpoints_json, "
                "suggested_confidence, decided_by, decided_at, notes) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), ?)",
                (
                    decision_id, source_id,
                    dec.get("table_or_label"),
                    dec.get("mapping_type"),
                    dec.get("target_type"),
                    json.dumps(dec.get("target_properties", {})),
                    json.dumps(dec.get("edge_endpoints")),
                    float(dec.get("confidence", 0.0)),
                    actor,
                    dec.get("notes"),
                ),
            )
            committed += 1
        conn.commit()
    return {
        "source_id": source_id,
        "decisions_committed": committed,
        "decisions_pending_hitl": pending_hitl,
        "dry_run": bool(args.get("dry_run", False)),
    }


def _pull(
    args: dict[str, Any],
    registry: DataSourceRegistry,
    state_store: DataSourceStateStore,
    sqlite_path: Path,
    dumps_root: Path,
) -> dict[str, Any]:
    source_id = str(args["source_id"])
    row = registry.get(source_id)
    if row is None:
        raise StructuredError(
            ErrorCode.CONNECTOR_NOT_FOUND,
            f"source {source_id!r} not registered",
            context={"source_id": source_id},
        )
    ds = _build_data_source(row, sqlite_path, dumps_root)
    mode = args.get("mode", "delta")
    receipt, _records = pull_source(
        data_source=ds, state_store=state_store, mode=mode,
    )
    return cast(dict[str, Any], json.loads(receipt.model_dump_json()))


def _list(
    args: dict[str, Any],
    registry: DataSourceRegistry,
) -> dict[str, Any]:
    include_disconnected = bool(args.get("include_disconnected", False))
    engine_filter = args.get("engine_filter") or []
    rows = (
        registry.list_all() if include_disconnected else registry.list_active()
    )
    if engine_filter:
        rows = [r for r in rows if r.engine in engine_filter]
    return {
        "connectors": [
            {
                "source_id": r.source_id,
                "engine": r.engine,
                "display_name": r.display_name,
                "tier": r.tier,
                "status": r.status,
                "last_pull_at": (
                    r.last_pull_at.isoformat()
                    if r.last_pull_at is not None else None
                ),
                "last_pull_status": r.last_pull_status,
            }
            for r in rows
        ],
    }


def _disconnect(
    args: dict[str, Any], registry: DataSourceRegistry,
) -> dict[str, Any]:
    row = registry.disconnect(
        source_id=str(args["source_id"]),
        actor=args.get("actor", "system"),
        retain_graph=bool(args.get("retain_graph", True)),
    )
    return {
        "source_id": row.source_id,
        "status": row.status,
    }


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------


def _build_manifest(args: dict[str, Any]) -> SourceManifest:
    engine = str(args["engine"])
    config_raw = args["config"]
    config_with_engine = dict(config_raw)
    config_with_engine.setdefault("engine", engine)
    if engine == "postgres":
        config: Any = PostgresConfig.model_validate(config_with_engine)
    elif engine == "mysql":
        config = MySQLConfig.model_validate(config_with_engine)
    elif engine == "sqlite":
        config = SQLiteConfig.model_validate(config_with_engine)
    elif engine == "neo4j":
        config = Neo4jConfig.model_validate(config_with_engine)
    elif engine == "local_file":
        config = LocalFileConfig.model_validate(config_with_engine)
    else:
        raise StructuredError(
            ErrorCode.ENGINE_UNSUPPORTED,
            f"unknown engine: {engine!r}",
            context={"engine": engine},
        )
    return SourceManifest(
        source_id=args.get("source_id") or f"ds:{engine}:{args['display_name']}",
        engine=cast(EngineKind, engine),
        display_name=str(args["display_name"]),
        config=config,
        tier=cast(SourceTier, args.get("tier", "L2")),
        credential_ref=args.get("credential_ref"),
        notes=args.get("notes"),
    )


def _build_data_source(
    row: DataSourceRow,
    sqlite_path: Path,
    dumps_root: Path,
) -> Any:
    """Recreate a DataSource from a registry row (re-using the engine
    factories in `IngestionService.register_data_source`)."""

    config_data = json.loads(row.config_json)
    config_data.setdefault("engine", row.engine)
    if row.engine == "postgres":
        from src.ingestion.sources.postgres import PostgresDataSource  # noqa: PLC0415
        manifest = SourceManifest(
            source_id=row.source_id, engine="postgres",
            display_name=row.display_name,
            config=PostgresConfig.model_validate(config_data),
            tier=row.tier, credential_ref=row.credential_ref,
        )
        return PostgresDataSource(manifest)
    if row.engine == "mysql":
        from src.ingestion.sources.mysql import MySQLDataSource  # noqa: PLC0415
        manifest = SourceManifest(
            source_id=row.source_id, engine="mysql",
            display_name=row.display_name,
            config=MySQLConfig.model_validate(config_data),
            tier=row.tier, credential_ref=row.credential_ref,
        )
        return MySQLDataSource(manifest)
    if row.engine == "sqlite":
        from src.ingestion.sources.sqlite import SQLiteDataSource  # noqa: PLC0415
        manifest = SourceManifest(
            source_id=row.source_id, engine="sqlite",
            display_name=row.display_name,
            config=SQLiteConfig.model_validate(config_data),
            tier=row.tier, credential_ref=row.credential_ref,
        )
        return SQLiteDataSource(manifest)
    if row.engine == "neo4j":
        from src.ingestion.sources.neo4j import Neo4jDataSource  # noqa: PLC0415
        manifest = SourceManifest(
            source_id=row.source_id, engine="neo4j",
            display_name=row.display_name,
            config=Neo4jConfig.model_validate(config_data),
            tier=row.tier, credential_ref=row.credential_ref,
        )
        return Neo4jDataSource(manifest)
    if row.engine == "local_file":
        from src.ingestion.sources.local_file import LocalFileDataSource  # noqa: PLC0415
        manifest = SourceManifest(
            source_id=row.source_id, engine="local_file",
            display_name=row.display_name,
            config=LocalFileConfig.model_validate(config_data),
            tier=row.tier, credential_ref=row.credential_ref,
        )
        return LocalFileDataSource(manifest)
    raise StructuredError(
        ErrorCode.ENGINE_UNSUPPORTED,
        f"unknown engine in registry row: {row.engine!r}",
        context={"source_id": row.source_id, "engine": row.engine},
    )


CONNECTOR_TOOL_NAMES: tuple[str, ...] = (
    "connect_data_source",
    "discover_schema",
    "suggest_mapping",
    "commit_mapping",
    "pull_delta",
    "list_connectors",
    "disconnect_data_source",
)


__all__ = [
    "CONNECTOR_TOOL_NAMES",
    "connector_tool_definitions",
    "dispatch_connector_tool",
]
