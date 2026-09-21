"""Stdio MCP server wrapping the 11 retrieval primitives.

Run via `python -m tools.graphrag.mcp_server` (or the `graphrag-mcp` console script). Claude
Code consumes the server via `.mcp.json` at the repo root.

Tool schemas are Pydantic-modeled in `_TOOL_SCHEMAS`; arguments are validated at the boundary
before calls reach the primitive functions. Results are serialized to JSON `TextContent`.

Security (per `tools/mcp/security.md`):
  - Sandbox: repo root only (paths are validated when callers supply them).
  - Read-only: no write tools in V1.
  - Audit log: every tool call → `tools/graphrag/logs/mcp.jsonl`.
  - Never returns `.env` / `*.key` / `*.pem` content.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from dataclasses import asdict, is_dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

import orjson
import structlog
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from tools.graphrag.retrieval import (
    create_task_brief,
    explain_feature,
    find_stale_docs,
    find_symbol,
    get_code_for_doc,
    get_docs_for_code,
    get_feature_packet,
    get_related_tests,
    plan_change,
    search_codebase,
    validate_feature_packet,
)
from tools.graphrag.store.sqlite_client import SQLiteGraphClient
from tools.graphrag.types import NodeType

log = structlog.get_logger(__name__)

_SERVER_NAME = "secbrain-graphrag"
_LOG_PATH = Path("tools/graphrag/logs/mcp.jsonl")


def _open_store() -> SQLiteGraphClient:
    db_path = Path(os.environ.get("GRAPHRAG_DB_PATH", "./data/graph/repo.db"))
    if not db_path.exists():
        raise FileNotFoundError(
            f"GraphRAG index not found at {db_path}. Run `python -m tools.graphrag.index --full` first."
        )
    return SQLiteGraphClient(db_path)


def _audit_log(tool_name: str, args: dict[str, Any], result_count: int, latency_ms: float, error: str | None = None) -> None:
    _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "ts": datetime.utcnow().isoformat() + "Z",
        "tool": tool_name,
        "args_hash": str(abs(hash(json.dumps(args, sort_keys=True, default=str)))),
        "result_count": result_count,
        "latency_ms": latency_ms,
        "error": error,
    }
    with _LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def _json_safe(value: Any) -> Any:  # noqa: PLR0911 - dispatch on type
    """Recursively convert dataclasses, enums, datetimes, and Pydantic models to JSON-safe shapes."""

    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if is_dataclass(value) and not isinstance(value, type):
        return _json_safe(asdict(value))
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, "model_dump"):
        return _json_safe(value.model_dump())
    return value


def _to_text_content(value: Any) -> list[TextContent]:
    payload = orjson.dumps(_json_safe(value), option=orjson.OPT_INDENT_2).decode("utf-8")
    return [TextContent(type="text", text=payload)]


def _node_types_from_strings(raw: list[Any] | None) -> tuple[NodeType, ...]:
    if not raw:
        return ()
    out: list[NodeType] = []
    for value in raw:
        if not isinstance(value, str):
            continue
        try:
            out.append(NodeType(value))
        except ValueError:
            continue
    return tuple(out)


_TOOL_SCHEMAS: dict[str, Tool] = {
    "search_codebase": Tool(
        name="search_codebase",
        description=(
            "Hybrid BM25 + filter search across docs / code / tests / ADRs / known issues. "
            "Use this BEFORE broad Read / Grep / Glob calls."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Free-text query"},
                "kind_filter": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional list of node types (e.g., 'DocSection', 'Function').",
                },
                "limit": {"type": "integer", "default": 20, "minimum": 1, "maximum": 100},
            },
            "required": ["query"],
        },
    ),
    "find_symbol": Tool(
        name="find_symbol",
        description="Exact / prefix / substring lookup on Function, Class, CodeFile, ConfigKey, TestCase names.",
        inputSchema={
            "type": "object",
            "properties": {
                "symbol": {"type": "string"},
                "kind_filter": {"type": "array", "items": {"type": "string"}},
                "limit": {"type": "integer", "default": 10, "minimum": 1, "maximum": 50},
            },
            "required": ["symbol"],
        },
    ),
    "get_feature_packet": Tool(
        name="get_feature_packet",
        description="Return every doc under docs/05-features/<slug>/ in canonical order.",
        inputSchema={
            "type": "object",
            "properties": {"feature": {"type": "string", "description": "Slug or canonical ID."}},
            "required": ["feature"],
        },
    ),
    "explain_feature": Tool(
        name="explain_feature",
        description="Aggregated Feature view: README summary + Reqs + ACs + Code + Tests + ADRs + KnownIssues.",
        inputSchema={
            "type": "object",
            "properties": {
                "feature": {"type": "string"},
                "max_per_section": {"type": "integer", "default": 15, "minimum": 1, "maximum": 50},
            },
            "required": ["feature"],
        },
    ),
    "get_related_tests": Tool(
        name="get_related_tests",
        description="Traverse TEST_COVERS_* edges from a Requirement / AC / Feature / Function / CodeFile.",
        inputSchema={
            "type": "object",
            "properties": {
                "target": {"type": "string", "description": "Canonical ID of the target node."},
                "limit": {"type": "integer", "default": 30, "minimum": 1, "maximum": 200},
            },
            "required": ["target"],
        },
    ),
    "get_docs_for_code": Tool(
        name="get_docs_for_code",
        description="Reverse traversal: DocSections that reference a given code file or symbol.",
        inputSchema={
            "type": "object",
            "properties": {
                "file_or_symbol": {"type": "string"},
                "limit": {"type": "integer", "default": 20, "minimum": 1, "maximum": 100},
            },
            "required": ["file_or_symbol"],
        },
    ),
    "get_code_for_doc": Tool(
        name="get_code_for_doc",
        description="Forward traversal: code targets referenced from a DocPage's sections.",
        inputSchema={
            "type": "object",
            "properties": {
                "doc_path": {"type": "string"},
                "include_subsections": {"type": "boolean", "default": True},
            },
            "required": ["doc_path"],
        },
    ),
    "find_stale_docs": Tool(
        name="find_stale_docs",
        description="Heuristic stale-doc detection: DocSections older than the code they reference.",
        inputSchema={
            "type": "object",
            "properties": {
                "changed_files": {"type": "array", "items": {"type": "string"}},
                "days_threshold": {"type": "integer", "default": 30, "minimum": 0},
            },
            "required": ["changed_files"],
        },
    ),
    "validate_feature_packet": Tool(
        name="validate_feature_packet",
        description="Check that a feature packet has README + requirements + plan + test-plan + context.",
        inputSchema={
            "type": "object",
            "properties": {"feature": {"type": "string"}},
            "required": ["feature"],
        },
    ),
    "plan_change": Tool(
        name="plan_change",
        description="Search + cluster-by-feature: suggest where to start for a goal.",
        inputSchema={
            "type": "object",
            "properties": {
                "request": {"type": "string"},
                "k_features": {"type": "integer", "default": 3, "minimum": 1, "maximum": 10},
            },
            "required": ["request"],
        },
    ),
    "create_task_brief": Tool(
        name="create_task_brief",
        description="Compose a Markdown task brief from `plan_change` output.",
        inputSchema={
            "type": "object",
            "properties": {
                "goal": {"type": "string"},
                "save_path": {"type": "string", "description": "Optional path to save the brief Markdown."},
            },
            "required": ["goal"],
        },
    ),
}


_DISPATCH_TABLE: dict[str, Any] = {
    "search_codebase": lambda store, args: search_codebase(
        store,
        args["query"],
        kind_filter=_node_types_from_strings(args.get("kind_filter")),
        limit=int(args.get("limit", 20)),
    ),
    "find_symbol": lambda store, args: find_symbol(
        store,
        args["symbol"],
        kind_filter=_node_types_from_strings(args.get("kind_filter")),
        limit=int(args.get("limit", 10)),
    ),
    "get_feature_packet": lambda store, args: get_feature_packet(store, args["feature"]),
    "explain_feature": lambda store, args: explain_feature(
        store,
        args["feature"],
        max_per_section=int(args.get("max_per_section", 15)),
    ),
    "get_related_tests": lambda store, args: get_related_tests(
        store, args["target"], limit=int(args.get("limit", 30))
    ),
    "get_docs_for_code": lambda store, args: get_docs_for_code(
        store, args["file_or_symbol"], limit=int(args.get("limit", 20))
    ),
    "get_code_for_doc": lambda store, args: get_code_for_doc(
        store,
        args["doc_path"],
        include_subsections=bool(args.get("include_subsections", True)),
    ),
    "find_stale_docs": lambda store, args: find_stale_docs(
        store,
        list(args["changed_files"]),
        days_threshold=int(args.get("days_threshold", 30)),
    ),
    "validate_feature_packet": lambda store, args: validate_feature_packet(
        store, args["feature"]
    ),
    "plan_change": lambda store, args: plan_change(
        store, args["request"], k_features=int(args.get("k_features", 3))
    ),
    "create_task_brief": lambda store, args: create_task_brief(
        store,
        args["goal"],
        save_path=Path(args["save_path"]) if isinstance(args.get("save_path"), str) else None,
    ),
}


async def _dispatch_tool(
    store: SQLiteGraphClient, name: str, args: dict[str, Any]
) -> Any:
    handler = _DISPATCH_TABLE.get(name)
    if handler is None:
        raise ValueError(f"unknown tool: {name}")
    return handler(store, args)


def build_server(store: SQLiteGraphClient | None = None) -> Server:
    """Build a configured `Server`. `store` may be injected (tests); else opened from env."""

    server: Server = Server(_SERVER_NAME)

    async def list_tools_handler() -> list[Tool]:
        return list(_TOOL_SCHEMAS.values())

    async def call_tool_handler(name: str, arguments: dict[str, Any] | None) -> list[TextContent]:
        args = arguments or {}
        active_store = store if store is not None else _open_store()
        start = datetime.utcnow()
        try:
            result = await _dispatch_tool(active_store, name, args)
            payload = _to_text_content(result)
            count = _result_count(result)
            elapsed = (datetime.utcnow() - start).total_seconds() * 1000
            _audit_log(name, args, count, elapsed)
            return payload
        except Exception as exc:
            elapsed = (datetime.utcnow() - start).total_seconds() * 1000
            _audit_log(name, args, 0, elapsed, error=str(exc))
            log.exception("graphrag.mcp.tool_failed", tool=name)
            return [TextContent(type="text", text=json.dumps({"error_code": "TOOL_FAILED", "message": str(exc)}))]
        finally:
            if store is None:
                active_store.close()

    list_tools_decorator: Any = server.list_tools()  # type: ignore[no-untyped-call]
    call_tool_decorator: Any = server.call_tool()
    list_tools_decorator(list_tools_handler)
    call_tool_decorator(call_tool_handler)
    return server


def _result_count(result: Any) -> int:
    if result is None:
        return 0
    if isinstance(result, list):
        return len(result)
    return 1


async def _async_main() -> None:
    server = build_server()
    options = server.create_initialization_options()
    async with stdio_server() as (read, write):
        await server.run(read, write, options)


def main() -> int:
    asyncio.run(_async_main())
    return 0


if __name__ == "__main__":
    sys.exit(main())
