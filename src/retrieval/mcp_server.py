"""V1 product-engine MCP stdio server — surfaces `query_graph` + `get_canonical_entity`.

Per FR-8 / `api.md` "MCP — Inbound (V1 internal callers consume these)". This is
the **product engine** MCP, distinct from `tools/graphrag/mcp_server.py` (the
repo MCP context server). Two deployments per `docs/04-architecture/system-overview.md`.

Run: `python -m src.retrieval.mcp_server` (consumed by Claude Code via `.mcp.json`).
"""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from src.er.canonical_index import CanonicalIndex
from src.graph.kuzu_client import KuzuGraphClient
from src.observability import AuditLog
from src.retrieval import RetrievalService
from src.retrieval.connector_tools import (
    CONNECTOR_TOOL_NAMES,
    connector_tool_definitions,
    dispatch_connector_tool,
)

log = structlog.get_logger(__name__)
_SERVER_NAME = "secbrain-v1"


def _data_dir() -> Path:
    return Path(os.environ.get("SECBRAIN_DATA_DIR", "data"))


def _services() -> tuple[RetrievalService, KuzuGraphClient, AuditLog]:
    data = _data_dir()
    sqlite_path = data / "sqlite" / "store.db"
    graph_path = data / "graph" / "kuzu.db"
    if not graph_path.exists():
        raise FileNotFoundError(
            f"V1 graph DB not found at {graph_path}. "
            "Run `python -m src.cli ingest l1-adea ...` first.",
        )
    graph = KuzuGraphClient(db_path=graph_path)
    index = CanonicalIndex(sqlite_path=sqlite_path)
    audit = AuditLog(sqlite_path=sqlite_path)
    return RetrievalService(graph=graph, canonical_index=index), graph, audit


def _tools() -> list[Tool]:
    return [
        Tool(
            name="query_graph",
            description=(
                "Trust-tier-aware graph query. Returns node records with citation "
                "references (NFR-4 ≥99%), bitemporal `as_of` support, and per-tier "
                "filtering. Use for any 'what does the knowledge engine know about X' "
                "question."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "source_tier_min": {
                        "type": "string",
                        "enum": ["L1", "L2", "L3", "L4", "L5"],
                        "description": "Minimum trust tier (L1 strictest).",
                    },
                    "traversal_depth": {"type": "integer", "default": 2},
                    "limit": {"type": "integer", "default": 20},
                    "as_of": {
                        "type": "string",
                        "description": "ISO-8601 datetime for bitemporal as-of reconstruction.",
                    },
                    "include_anomalies": {"type": "boolean", "default": False},
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="get_canonical_entity",
            description=(
                "Snap a free-text alias to its L1 canonical entity (school / "
                "program / specialty). Returns canonical_id + canonical_name + "
                "match_confidence."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "alias": {"type": "string"},
                    "entity_type": {
                        "type": "string",
                        "enum": ["School", "Program", "Specialty"],
                        "default": "School",
                    },
                },
                "required": ["alias"],
            },
        ),
        Tool(
            name="stats",
            description="Graph + audit-log size snapshot. Useful for sanity checks.",
            inputSchema={"type": "object", "properties": {}},
        ),
        *[
            Tool(
                name=defn["name"],
                description=defn["description"],
                inputSchema=defn["inputSchema"],
            )
            for defn in connector_tool_definitions()
        ],
    ]


async def _dispatch(name: str, args: dict[str, Any]) -> list[TextContent]:
    svc, graph, audit = _services()
    try:
        payload: Any
        if name == "query_graph":
            as_of = (
                datetime.fromisoformat(args["as_of"]) if args.get("as_of") else None
            )
            results = svc.query_graph(
                query=str(args["query"]),
                source_tier_min=args.get("source_tier_min"),
                traversal_depth=int(args.get("traversal_depth", 2)),
                limit=int(args.get("limit", 20)),
                include_anomalies=bool(args.get("include_anomalies", False)),
                as_of=as_of,
            )
            audit.log_retrieval(
                query_text=args["query"], result_count=len(results),
                traversal_depth=args.get("traversal_depth", 2),
                time_range=None, as_of=args.get("as_of"),
            )
            payload = [_serialize(r) for r in results]
        elif name == "get_canonical_entity":
            canonical = svc.get_canonical_entity(
                alias=str(args["alias"]),
                entity_type=args.get("entity_type", "School"),
            )
            payload = _serialize(canonical) if canonical is not None else None
        elif name == "stats":
            payload = {
                "total_nodes": graph.node_count(),
                "total_edges": graph.edge_count(),
                "audit_rows": audit.count(),
            }
        elif name in CONNECTOR_TOOL_NAMES:
            sqlite_path = _data_dir() / "sqlite" / "store.db"
            dumps_root = _data_dir() / "dumps"
            payload = dispatch_connector_tool(
                name, args, sqlite_path=sqlite_path, dumps_root=dumps_root,
            )
        else:
            raise ValueError(f"Unknown tool: {name}")
        return [TextContent(type="text", text=json.dumps(payload, default=_json_safe))]
    finally:
        graph.close()


def _serialize(value: Any) -> Any:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, "__dataclass_fields__"):
        return {k: _serialize(v) for k, v in asdict(value).items()}
    if isinstance(value, dict):
        return {str(k): _serialize(v) for k, v in value.items()}
    if isinstance(value, list | tuple | set):
        return [_serialize(v) for v in value]
    return str(value)


def _json_safe(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


async def _serve() -> None:
    server: Server[Any] = Server(_SERVER_NAME)

    @server.list_tools()  # type: ignore[no-untyped-call,untyped-decorator]
    async def _list_tools_decorator() -> list[Tool]:
        return _tools()

    @server.call_tool()  # type: ignore[untyped-decorator]
    async def _call_tool_decorator(
        name: str, arguments: dict[str, Any],
    ) -> list[TextContent]:
        log.info("mcp.call", tool=name, args=arguments)
        try:
            return await _dispatch(name, arguments)
        except Exception as e:
            log.error("mcp.error", tool=name, error=str(e))
            return [TextContent(type="text", text=json.dumps({
                "error": str(e),
                "ts": datetime.now(UTC).isoformat(),
            }))]

    async with stdio_server() as (reader, writer):
        await server.run(reader, writer, server.create_initialization_options())


def main() -> None:
    asyncio.run(_serve())


if __name__ == "__main__":
    main()
