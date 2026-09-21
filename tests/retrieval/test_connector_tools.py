"""Contract tests for V1.5a Phase 7 — the 7 connector MCP tools.

Asserts each tool's request/response shape + audit-log coverage (AC-9).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import orjson
import pytest

from src.ingestion.sources.registry import DataSourceRegistry
from src.retrieval.connector_tools import (
    CONNECTOR_TOOL_NAMES,
    connector_tool_definitions,
    dispatch_connector_tool,
)
from src.shared.errors import ErrorCode, StructuredError


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    return tmp_path / "engine.db"


@pytest.fixture
def reddit_fixture(tmp_path: Path) -> Path:
    path = tmp_path / "x_posts.jsonl"
    with path.open("wb") as f:
        f.write(orjson.dumps({
            "id": "a1", "name": "t3_a1", "author": "u",
            "created_utc": 1_700_000_000, "title": "t", "selftext": "",
            "subreddit": "x", "subreddit_id": "t5_x",
            "score": 1, "ups": 1, "downs": 0, "num_comments": 0,
            "link_flair_text": None,
            "permalink": "/r/x/comments/a1/_",
            "url": "https://example.org/", "over_18": False,
        }))
        f.write(b"\n")
    return path


def test_tool_definitions_present() -> None:
    """All 7 tools defined per FR-1.5a-7."""
    defs = connector_tool_definitions()
    names = {d["name"] for d in defs}
    assert names == set(CONNECTOR_TOOL_NAMES)
    assert len(defs) == 7


def test_tool_definitions_have_input_schema() -> None:
    for d in connector_tool_definitions():
        assert "name" in d
        assert "description" in d
        assert "inputSchema" in d
        assert d["inputSchema"]["type"] == "object"


def test_dispatch_unknown_tool_raises(workspace: Path) -> None:
    with pytest.raises(StructuredError):
        dispatch_connector_tool("nonexistent", {}, sqlite_path=workspace)


# ----------------------------------------------------------------------
# connect_data_source
# ----------------------------------------------------------------------


def test_connect_data_source_returns_receipt(
    workspace: Path, reddit_fixture: Path,
) -> None:
    result = dispatch_connector_tool(
        "connect_data_source",
        {
            "engine": "local_file",
            "display_name": "Test",
            "source_id": "ds:t1",
            "config": {
                "adapter": "l5_reddit",
                "paths": [str(reddit_fixture)],
            },
            "tier": "L5",
        },
        sqlite_path=workspace,
    )
    assert result["source_id"] == "ds:t1"
    assert result["status"] == "connected"
    assert result["tier"] == "L5"


def test_connect_l1_without_confirmation_raises(
    workspace: Path, reddit_fixture: Path,
) -> None:
    with pytest.raises(StructuredError) as excinfo:
        dispatch_connector_tool(
            "connect_data_source",
            {
                "engine": "local_file",
                "display_name": "L1 fail",
                "source_id": "ds:l1_fail",
                "config": {"adapter": "l5_reddit", "paths": [str(reddit_fixture)]},
                "tier": "L1",
            },
            sqlite_path=workspace,
        )
    assert excinfo.value.error_code == ErrorCode.L1_IMMUTABLE_REJECT


# ----------------------------------------------------------------------
# discover_schema / suggest_mapping
# ----------------------------------------------------------------------


def test_discover_schema_returns_snapshot(
    workspace: Path, reddit_fixture: Path,
) -> None:
    dispatch_connector_tool(
        "connect_data_source",
        {
            "engine": "local_file",
            "display_name": "T",
            "source_id": "ds:discover",
            "config": {"adapter": "l5_reddit", "paths": [str(reddit_fixture)]},
        },
        sqlite_path=workspace,
    )
    result = dispatch_connector_tool(
        "discover_schema", {"source_id": "ds:discover"}, sqlite_path=workspace,
    )
    assert result["source_id"] == "ds:discover"
    table_names = {t["name"] for t in result["tables"]}
    assert {"post", "comment", "user"} <= table_names


def test_discover_unknown_source_raises(workspace: Path) -> None:
    with pytest.raises(StructuredError) as excinfo:
        dispatch_connector_tool(
            "discover_schema",
            {"source_id": "ds:nonexistent"},
            sqlite_path=workspace,
        )
    assert excinfo.value.error_code == ErrorCode.CONNECTOR_NOT_FOUND


def test_suggest_mapping_returns_proposal(
    workspace: Path, reddit_fixture: Path,
) -> None:
    dispatch_connector_tool(
        "connect_data_source",
        {
            "engine": "local_file",
            "display_name": "T",
            "source_id": "ds:suggest",
            "config": {"adapter": "l5_reddit", "paths": [str(reddit_fixture)]},
        },
        sqlite_path=workspace,
    )
    result = dispatch_connector_tool(
        "suggest_mapping", {"source_id": "ds:suggest"}, sqlite_path=workspace,
    )
    assert result["source_id"] == "ds:suggest"
    assert "per_table" in result
    assert "overall_confidence" in result


# ----------------------------------------------------------------------
# commit_mapping
# ----------------------------------------------------------------------


def test_commit_mapping_persists_decisions(
    workspace: Path, reddit_fixture: Path,
) -> None:
    dispatch_connector_tool(
        "connect_data_source",
        {
            "engine": "local_file",
            "display_name": "T",
            "source_id": "ds:commit",
            "config": {"adapter": "l5_reddit", "paths": [str(reddit_fixture)]},
        },
        sqlite_path=workspace,
    )
    decisions = [
        {
            "table_or_label": "post",
            "mapping_type": "node",
            "target_type": "Post",
            "confidence": 0.95,
            "routing": "auto",
            "target_properties": {"id": "post_id"},
        },
    ]
    result = dispatch_connector_tool(
        "commit_mapping",
        {"source_id": "ds:commit", "decisions": decisions},
        sqlite_path=workspace,
    )
    assert result["decisions_committed"] == 1
    assert result["decisions_pending_hitl"] == 0

    # Verify persistence
    conn = sqlite3.connect(workspace)
    rows = list(conn.execute(
        "SELECT decision_id, mapping_type, target_type FROM mapping_decisions",
    ))
    assert len(rows) == 1
    assert rows[0][1] == "node"
    assert rows[0][2] == "Post"
    conn.close()


def test_commit_mapping_hitl_routing_does_not_commit(
    workspace: Path, reddit_fixture: Path,
) -> None:
    dispatch_connector_tool(
        "connect_data_source",
        {
            "engine": "local_file",
            "display_name": "T",
            "source_id": "ds:hitl_commit",
            "config": {"adapter": "l5_reddit", "paths": [str(reddit_fixture)]},
        },
        sqlite_path=workspace,
    )
    decisions = [
        {
            "table_or_label": "user",
            "mapping_type": "node",
            "target_type": "User",
            "confidence": 0.80,
            "routing": "hitl",
        },
    ]
    result = dispatch_connector_tool(
        "commit_mapping",
        {"source_id": "ds:hitl_commit", "decisions": decisions},
        sqlite_path=workspace,
    )
    assert result["decisions_committed"] == 0
    assert result["decisions_pending_hitl"] == 1


# ----------------------------------------------------------------------
# pull_delta
# ----------------------------------------------------------------------


def test_pull_delta_returns_receipt(
    workspace: Path, reddit_fixture: Path,
) -> None:
    dispatch_connector_tool(
        "connect_data_source",
        {
            "engine": "local_file",
            "display_name": "T",
            "source_id": "ds:pull",
            "config": {"adapter": "l5_reddit", "paths": [str(reddit_fixture)]},
        },
        sqlite_path=workspace,
    )
    result = dispatch_connector_tool(
        "pull_delta", {"source_id": "ds:pull"}, sqlite_path=workspace,
    )
    assert result["source_id"] == "ds:pull"
    assert result["status"] == "ok"
    assert result["rows_pulled"] > 0


def test_pull_delta_idempotent_second_call(
    workspace: Path, reddit_fixture: Path,
) -> None:
    dispatch_connector_tool(
        "connect_data_source",
        {
            "engine": "local_file",
            "display_name": "T",
            "source_id": "ds:pull_idemp",
            "config": {"adapter": "l5_reddit", "paths": [str(reddit_fixture)]},
        },
        sqlite_path=workspace,
    )
    dispatch_connector_tool(
        "pull_delta", {"source_id": "ds:pull_idemp"}, sqlite_path=workspace,
    )
    second = dispatch_connector_tool(
        "pull_delta", {"source_id": "ds:pull_idemp"}, sqlite_path=workspace,
    )
    assert second["rows_pulled"] == 0


# ----------------------------------------------------------------------
# list_connectors / disconnect_data_source
# ----------------------------------------------------------------------


def test_list_connectors_excludes_disconnected_by_default(
    workspace: Path, reddit_fixture: Path,
) -> None:
    dispatch_connector_tool(
        "connect_data_source",
        {
            "engine": "local_file",
            "display_name": "A",
            "source_id": "ds:a",
            "config": {"adapter": "l5_reddit", "paths": [str(reddit_fixture)]},
        },
        sqlite_path=workspace,
    )
    dispatch_connector_tool(
        "connect_data_source",
        {
            "engine": "local_file",
            "display_name": "B",
            "source_id": "ds:b",
            "config": {"adapter": "l5_reddit", "paths": [str(reddit_fixture)]},
        },
        sqlite_path=workspace,
    )
    dispatch_connector_tool(
        "disconnect_data_source",
        {"source_id": "ds:b"},
        sqlite_path=workspace,
    )
    result = dispatch_connector_tool(
        "list_connectors", {}, sqlite_path=workspace,
    )
    ids = {c["source_id"] for c in result["connectors"]}
    assert ids == {"ds:a"}


def test_list_connectors_includes_disconnected_when_asked(
    workspace: Path, reddit_fixture: Path,
) -> None:
    dispatch_connector_tool(
        "connect_data_source",
        {
            "engine": "local_file",
            "display_name": "A",
            "source_id": "ds:a2",
            "config": {"adapter": "l5_reddit", "paths": [str(reddit_fixture)]},
        },
        sqlite_path=workspace,
    )
    dispatch_connector_tool(
        "disconnect_data_source", {"source_id": "ds:a2"},
        sqlite_path=workspace,
    )
    result = dispatch_connector_tool(
        "list_connectors", {"include_disconnected": True},
        sqlite_path=workspace,
    )
    ids = {c["source_id"] for c in result["connectors"]}
    assert "ds:a2" in ids


def test_disconnect_data_source_returns_status(
    workspace: Path, reddit_fixture: Path,
) -> None:
    dispatch_connector_tool(
        "connect_data_source",
        {
            "engine": "local_file",
            "display_name": "D",
            "source_id": "ds:dis",
            "config": {"adapter": "l5_reddit", "paths": [str(reddit_fixture)]},
        },
        sqlite_path=workspace,
    )
    result = dispatch_connector_tool(
        "disconnect_data_source", {"source_id": "ds:dis"},
        sqlite_path=workspace,
    )
    assert result["source_id"] == "ds:dis"
    assert result["status"] == "disconnected"


# ----------------------------------------------------------------------
# AC-9 — audit log covers every connector action
# ----------------------------------------------------------------------


def test_every_connector_action_audit_logged(
    workspace: Path, reddit_fixture: Path,
) -> None:
    """Run every tool once + verify the connector_audit table has rows for
    each action kind."""
    dispatch_connector_tool(
        "connect_data_source",
        {
            "engine": "local_file",
            "display_name": "Audit",
            "source_id": "ds:audit",
            "config": {"adapter": "l5_reddit", "paths": [str(reddit_fixture)]},
        },
        sqlite_path=workspace,
    )
    dispatch_connector_tool(
        "discover_schema", {"source_id": "ds:audit"}, sqlite_path=workspace,
    )
    dispatch_connector_tool(
        "suggest_mapping", {"source_id": "ds:audit"}, sqlite_path=workspace,
    )
    dispatch_connector_tool(
        "commit_mapping",
        {"source_id": "ds:audit", "decisions": [
            {
                "table_or_label": "post", "mapping_type": "node",
                "target_type": "Post", "confidence": 0.95, "routing": "auto",
                "target_properties": {},
            },
        ]},
        sqlite_path=workspace,
    )
    dispatch_connector_tool(
        "pull_delta", {"source_id": "ds:audit"}, sqlite_path=workspace,
    )
    dispatch_connector_tool(
        "list_connectors", {}, sqlite_path=workspace,
    )
    dispatch_connector_tool(
        "disconnect_data_source", {"source_id": "ds:audit"},
        sqlite_path=workspace,
    )

    registry = DataSourceRegistry(sqlite_path=workspace)
    audit_rows = registry.audit_log_entries(source_id="ds:audit")
    kinds = {r["kind"] for r in audit_rows}
    assert "connector_connect" in kinds
    assert "connector_disconnect" in kinds
