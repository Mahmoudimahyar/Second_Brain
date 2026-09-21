"""V1.6a — MCP outbound tool surface for the website-crawl scheduler.

Per ADR-019 + V1.6a plan.md Phase 10 + FR-1.6a-7. Six tools the LLM
agent calls (via stdio MCP) + the FastAPI routes (Phase 8) wrap the
same machinery. Every dispatch writes an `audit_log` row.

The tool surface mirrors api.md:
- register_crawl_domain
- list_crawl_domains
- get_crawl_status
- trigger_crawl_now
- pause_crawl_domain
- update_crawl_cadence

This module exposes:
- `CRAWL_TOOL_NAMES` — registered tool names (for the MCP server's
  tool-listing surface)
- `crawl_tool_definitions()` — Tool descriptors (name + schema)
- `dispatch_crawl_tool(name, args, sqlite_path)` — JSON-serializable
  result; raises StructuredError on validation/business failures
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from croniter import croniter

from flows.website_crawl_dispatcher import enqueue_job
from src.ingestion.sources import blocked_domains
from src.ingestion.sources.website_crawl import (
    CrawlDomainRow,
    WebsiteCrawlRegistry,
)
from src.shared.errors import ErrorCode, StructuredError

CRAWL_TOOL_NAMES: list[str] = [
    "register_crawl_domain",
    "list_crawl_domains",
    "get_crawl_status",
    "trigger_crawl_now",
    "pause_crawl_domain",
    "update_crawl_cadence",
]


# ---------------------------------------------------------------------------
# Tool definitions (MCP-compatible JSON schemas)
# ---------------------------------------------------------------------------


def crawl_tool_definitions() -> list[dict[str, Any]]:
    """Return MCP `Tool`-compatible dicts. The MCP server constructs
    proper `mcp.types.Tool` objects from these."""

    return [
        {
            "name": "register_crawl_domain",
            "description": (
                "Register a new website-crawl domain. Forums + social "
                "media are hard-blocked at this call. L1 tier requires "
                "confirm_l1_immutable=True."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "domain": {"type": "string"},
                    "tier": {"type": "string", "enum": ["L1", "L2"], "default": "L2"},
                    "stage": {"type": "string", "enum": ["L0", "L1", "L2"], "default": "L1"},
                    "cadence_cron": {"type": "string", "default": "0 6 * * *"},
                    "max_pages_per_run": {"type": "integer", "default": 500},
                    "max_pages_per_month": {"type": "integer", "default": 5000},
                    "max_usd_per_month": {"type": "number", "default": 5.0},
                    "concurrency": {"type": "integer", "default": 4},
                    "enable_ocr": {"type": "boolean", "default": False},
                    "enable_scrapingbee": {"type": "boolean", "default": False},
                    "confirm_l1_immutable": {"type": "boolean", "default": False},
                    "notes": {"type": "string"},
                },
                "required": ["domain"],
            },
        },
        {
            "name": "list_crawl_domains",
            "description": "List registered crawl domains (active + paused + auto_paused).",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "status": {"type": "string", "default": "active"},
                    "q": {"type": "string"},
                },
            },
        },
        {
            "name": "get_crawl_status",
            "description": "Return one domain's details + last job + budget snapshot.",
            "inputSchema": {
                "type": "object",
                "properties": {"domain": {"type": "string"}},
                "required": ["domain"],
            },
        },
        {
            "name": "trigger_crawl_now",
            "description": "Enqueue a crawl_jobs row for the dispatcher to pick up.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "domain": {"type": "string"},
                    "force_full_refresh": {"type": "boolean", "default": False},
                },
                "required": ["domain"],
            },
        },
        {
            "name": "pause_crawl_domain",
            "description": "Pause future scheduled crawls for a domain.",
            "inputSchema": {
                "type": "object",
                "properties": {"domain": {"type": "string"}},
                "required": ["domain"],
            },
        },
        {
            "name": "update_crawl_cadence",
            "description": "Change a domain's cron cadence.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "domain": {"type": "string"},
                    "cadence_cron": {"type": "string"},
                },
                "required": ["domain", "cadence_cron"],
            },
        },
    ]


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------


def dispatch_crawl_tool(
    name: str,
    args: dict[str, Any],
    *,
    sqlite_path: Path,
    actor: str = "mcp",
) -> dict[str, Any]:
    """Dispatch one MCP tool call. Returns JSON-serializable result.

    Raises:
        StructuredError: validation / business-logic failure.
        ValueError: unknown tool name.
    """

    if name not in CRAWL_TOOL_NAMES:
        raise ValueError(f"unknown crawl tool: {name!r}")

    registry = WebsiteCrawlRegistry(sqlite_path=sqlite_path)
    result: dict[str, Any]

    if name == "register_crawl_domain":
        row = registry.register(
            domain=str(args["domain"]),
            tier=args.get("tier", "L2"),
            stage=args.get("stage", "L1"),
            cadence_cron=args.get("cadence_cron", "0 6 * * *"),
            actor=actor,
            max_pages_per_run=args.get("max_pages_per_run"),
            max_pages_per_month=args.get("max_pages_per_month"),
            max_usd_per_month=args.get("max_usd_per_month"),
            concurrency=args.get("concurrency"),
            enable_ocr=args.get("enable_ocr"),
            enable_scrapingbee=args.get("enable_scrapingbee"),
            confirm_l1_immutable=bool(args.get("confirm_l1_immutable", False)),
            notes=args.get("notes"),
        )
        result = _row_to_json(row)

    elif name == "list_crawl_domains":
        status = args.get("status", "active")
        rows = registry.list_all() if status == "all" else registry.list_active()
        q = args.get("q")
        if q:
            rows = [r for r in rows if q.lower() in r.domain.lower()]
        result = {"domains": [_row_to_json(r) for r in rows]}

    elif name == "get_crawl_status":
        row = _resolve_by_domain(registry, args["domain"])
        result = {"domain": _row_to_json(row)}

    elif name == "trigger_crawl_now":
        row = _resolve_by_domain(registry, args["domain"])
        job_id = enqueue_job(
            sqlite_path=sqlite_path,
            domain_id=row.domain_id,
            scheduled_at=datetime.now(UTC),
            trigger="force_full_refresh" if args.get("force_full_refresh") else "manual",
        )
        result = {"job_id": job_id, "status": "queued"}

    elif name == "pause_crawl_domain":
        row = _resolve_by_domain(registry, args["domain"])
        registry.pause(row.domain_id, actor=actor)
        refreshed = registry.get(row.domain_id)
        assert refreshed is not None
        result = _row_to_json(refreshed)

    elif name == "update_crawl_cadence":
        row = _resolve_by_domain(registry, args["domain"])
        cron = str(args["cadence_cron"])
        if not croniter.is_valid(cron):
            raise StructuredError(
                ErrorCode.INVALID_CRON,
                f"cadence_cron '{cron}' is not a valid cron expression.",
                context={"cadence_cron": cron},
            )
        with sqlite3.connect(sqlite_path) as conn:
            conn.execute(
                "UPDATE crawl_domains SET cadence_cron = ?, updated_at = ? "
                "WHERE domain_id = ?",
                (cron, datetime.now(UTC).isoformat(), row.domain_id),
            )
            conn.commit()
        refreshed = registry.get(row.domain_id)
        assert refreshed is not None
        result = _row_to_json(refreshed)

    else:  # pragma: no cover
        raise ValueError(f"unhandled tool: {name}")

    _write_mcp_audit(
        sqlite_path=sqlite_path, actor=actor, tool=name, args=args, result=result,
    )
    return result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_by_domain(
    registry: WebsiteCrawlRegistry, domain_or_id: str,
) -> CrawlDomainRow:
    """Accept either a domain_id ('web:...') or a bare FQDN."""

    # Try domain_id first.
    row = registry.get(domain_or_id)
    if row is not None:
        return row
    # Fall back to FQDN scan.
    for r in registry.list_all():
        if r.domain == domain_or_id.lower():
            return r
    raise StructuredError(
        ErrorCode.CONNECTOR_NOT_FOUND,
        f"crawl domain '{domain_or_id}' not found",
        context={"domain": domain_or_id},
    )


def _row_to_json(row: CrawlDomainRow) -> dict[str, Any]:
    return {
        "domain_id": row.domain_id,
        "domain": row.domain,
        "tier": row.tier,
        "stage": row.stage,
        "cadence_cron": row.cadence_cron,
        "status": row.status,
        "max_pages_per_run": row.max_pages_per_run,
        "max_pages_per_month": row.max_pages_per_month,
        "max_usd_per_month": row.max_usd_per_month,
        "concurrency": row.concurrency,
        "enable_ocr": row.enable_ocr,
        "enable_scrapingbee": row.enable_scrapingbee,
        "confirm_l1": row.confirm_l1,
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
        "created_by": row.created_by,
        "notes": row.notes,
    }


def _write_mcp_audit(
    *,
    sqlite_path: Path,
    actor: str,
    tool: str,
    args: dict[str, Any],
    result: dict[str, Any],
) -> None:
    """Write `kind='mcp_crawl_tool'` row to audit_log matching V1 shape."""

    with sqlite3.connect(sqlite_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS audit_log (
                audit_id     TEXT PRIMARY KEY,
                kind         TEXT NOT NULL,
                ts           TEXT NOT NULL,
                fields_json  TEXT NOT NULL,
                ttl_pinned   INTEGER
            )
            """,
        )
        conn.execute(
            "INSERT INTO audit_log (audit_id, kind, ts, fields_json, ttl_pinned) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                f"audit:{uuid.uuid4().hex[:16]}",
                "mcp_crawl_tool",
                datetime.now(UTC).isoformat(),
                json.dumps({
                    "actor": actor, "tool": tool,
                    "args": args, "result_keys": list(result.keys()),
                }),
                None,
            ),
        )
        conn.commit()


# Exempt unused import warnings — we reference blocked_domains for the
# tool surface's hidden constraint (the registry enforces, but importing
# here documents the dep).
_ = blocked_domains


__all__ = [
    "CRAWL_TOOL_NAMES",
    "crawl_tool_definitions",
    "dispatch_crawl_tool",
]
