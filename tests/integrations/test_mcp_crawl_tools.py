"""V1.6a Phase 10 — MCP outbound tool tests.

Per V1.6a plan.md Phase 10. Failing-first: register_crawl_domain via
MCP dispatch -> audit_log row written.
"""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

import pytest


def test_register_crawl_domain_via_mcp(tmp_path: Path) -> None:
    """Failing-first per V1.6a plan.md Phase 10."""
    os.environ["CRAWL4AI_USER_AGENT"] = "SecBrain/1.6 (+test@example.invalid)"
    from src.integrations.mcp_crawl_tools import dispatch_crawl_tool

    result = dispatch_crawl_tool(
        "register_crawl_domain",
        {"domain": "adea.org", "tier": "L2", "stage": "L1"},
        sqlite_path=tmp_path / "engine.db",
        actor="test",
    )
    assert result["domain"] == "adea.org"
    assert result["tier"] == "L2"
    assert result["stage"] == "L1"

    # Verify audit row was written.
    with sqlite3.connect(tmp_path / "engine.db") as conn:
        rows = conn.execute(
            "SELECT kind, fields_json FROM audit_log WHERE kind = ?",
            ("mcp_crawl_tool",),
        ).fetchall()
    assert len(rows) >= 1
    fields = json.loads(rows[0][1])
    assert fields["tool"] == "register_crawl_domain"
    assert fields["actor"] == "test"


def test_register_blocked_via_mcp_returns_structured_error(tmp_path: Path) -> None:
    os.environ["CRAWL4AI_USER_AGENT"] = "SecBrain/1.6 (+test@example.invalid)"
    from src.integrations.mcp_crawl_tools import dispatch_crawl_tool
    from src.shared.errors import ErrorCode, StructuredError

    with pytest.raises(StructuredError) as exc:
        dispatch_crawl_tool(
            "register_crawl_domain",
            {"domain": "reddit.com", "tier": "L2", "stage": "L0"},
            sqlite_path=tmp_path / "engine.db",
        )
    assert exc.value.error_code == ErrorCode.DOMAIN_BLOCKED


def test_list_crawl_domains_via_mcp(tmp_path: Path) -> None:
    os.environ["CRAWL4AI_USER_AGENT"] = "SecBrain/1.6 (+test@example.invalid)"
    from src.integrations.mcp_crawl_tools import dispatch_crawl_tool

    dispatch_crawl_tool(
        "register_crawl_domain",
        {"domain": "adea.org", "tier": "L2", "stage": "L0"},
        sqlite_path=tmp_path / "engine.db",
    )
    dispatch_crawl_tool(
        "register_crawl_domain",
        {"domain": "ada.org", "tier": "L2", "stage": "L0"},
        sqlite_path=tmp_path / "engine.db",
    )
    result = dispatch_crawl_tool(
        "list_crawl_domains",
        {"status": "active"},
        sqlite_path=tmp_path / "engine.db",
    )
    domains = {d["domain"] for d in result["domains"]}
    assert {"adea.org", "ada.org"}.issubset(domains)


def test_get_crawl_status_via_mcp_resolves_by_fqdn(tmp_path: Path) -> None:
    os.environ["CRAWL4AI_USER_AGENT"] = "SecBrain/1.6 (+test@example.invalid)"
    from src.integrations.mcp_crawl_tools import dispatch_crawl_tool

    dispatch_crawl_tool(
        "register_crawl_domain",
        {"domain": "adea.org", "tier": "L2", "stage": "L0"},
        sqlite_path=tmp_path / "engine.db",
    )
    result = dispatch_crawl_tool(
        "get_crawl_status",
        {"domain": "adea.org"},  # FQDN, not domain_id
        sqlite_path=tmp_path / "engine.db",
    )
    assert result["domain"]["domain"] == "adea.org"


def test_trigger_crawl_now_via_mcp_enqueues_job(tmp_path: Path) -> None:
    os.environ["CRAWL4AI_USER_AGENT"] = "SecBrain/1.6 (+test@example.invalid)"
    from src.integrations.mcp_crawl_tools import dispatch_crawl_tool

    dispatch_crawl_tool(
        "register_crawl_domain",
        {"domain": "adea.org", "tier": "L2", "stage": "L0"},
        sqlite_path=tmp_path / "engine.db",
    )
    result = dispatch_crawl_tool(
        "trigger_crawl_now",
        {"domain": "adea.org", "force_full_refresh": False},
        sqlite_path=tmp_path / "engine.db",
    )
    assert result["status"] == "queued"
    assert result["job_id"].startswith("job:")


def test_pause_crawl_domain_via_mcp(tmp_path: Path) -> None:
    os.environ["CRAWL4AI_USER_AGENT"] = "SecBrain/1.6 (+test@example.invalid)"
    from src.integrations.mcp_crawl_tools import dispatch_crawl_tool

    dispatch_crawl_tool(
        "register_crawl_domain",
        {"domain": "adea.org", "tier": "L2", "stage": "L0"},
        sqlite_path=tmp_path / "engine.db",
    )
    result = dispatch_crawl_tool(
        "pause_crawl_domain",
        {"domain": "adea.org"},
        sqlite_path=tmp_path / "engine.db",
    )
    assert result["status"] == "paused"


def test_update_crawl_cadence_via_mcp(tmp_path: Path) -> None:
    os.environ["CRAWL4AI_USER_AGENT"] = "SecBrain/1.6 (+test@example.invalid)"
    from src.integrations.mcp_crawl_tools import dispatch_crawl_tool

    dispatch_crawl_tool(
        "register_crawl_domain",
        {"domain": "adea.org", "tier": "L2", "stage": "L0"},
        sqlite_path=tmp_path / "engine.db",
    )
    result = dispatch_crawl_tool(
        "update_crawl_cadence",
        {"domain": "adea.org", "cadence_cron": "*/15 * * * *"},
        sqlite_path=tmp_path / "engine.db",
    )
    assert result["cadence_cron"] == "*/15 * * * *"


def test_update_crawl_cadence_invalid_raises(tmp_path: Path) -> None:
    os.environ["CRAWL4AI_USER_AGENT"] = "SecBrain/1.6 (+test@example.invalid)"
    from src.integrations.mcp_crawl_tools import dispatch_crawl_tool
    from src.shared.errors import ErrorCode, StructuredError

    dispatch_crawl_tool(
        "register_crawl_domain",
        {"domain": "adea.org", "tier": "L2", "stage": "L0"},
        sqlite_path=tmp_path / "engine.db",
    )
    with pytest.raises(StructuredError) as exc:
        dispatch_crawl_tool(
            "update_crawl_cadence",
            {"domain": "adea.org", "cadence_cron": "not-a-cron"},
            sqlite_path=tmp_path / "engine.db",
        )
    assert exc.value.error_code == ErrorCode.INVALID_CRON


def test_unknown_tool_raises(tmp_path: Path) -> None:
    os.environ["CRAWL4AI_USER_AGENT"] = "SecBrain/1.6 (+test@example.invalid)"
    from src.integrations.mcp_crawl_tools import dispatch_crawl_tool

    with pytest.raises(ValueError, match="unknown"):
        dispatch_crawl_tool("nonexistent", {}, sqlite_path=tmp_path / "engine.db")


def test_tool_definitions_match_names_list() -> None:
    from src.integrations.mcp_crawl_tools import (
        CRAWL_TOOL_NAMES,
        crawl_tool_definitions,
    )

    names_from_defs = [d["name"] for d in crawl_tool_definitions()]
    assert names_from_defs == CRAWL_TOOL_NAMES
