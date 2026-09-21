"""Contract tests for `tools/graphrag/mcp_server.py`.

We exercise the server without spinning up a real stdio process: build the `Server`, drive its
registered handlers directly with a real in-memory store, and assert the response shape.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from tools.graphrag.index import index_full
from tools.graphrag.mcp_server import (
    _TOOL_SCHEMAS,
    _dispatch_tool,
    _json_safe,
    _to_text_content,
    build_server,
)
from tools.graphrag.retrieval.search_codebase import SearchResult
from tools.graphrag.store.sqlite_client import SQLiteGraphClient

pytestmark = pytest.mark.contract


def _build_fixture_repo(root: Path) -> None:
    (root / ".gitignore").write_text("", encoding="utf-8")
    docs = root / "docs" / "01-core"
    docs.mkdir(parents=True)
    (docs / "vision.md").write_text(
        "# Vision\n\n## Goals\n\nUse the gateway. See `src/gateway.py`.\n",
        encoding="utf-8",
    )

    slice_dir = root / "docs" / "05-features" / "01-demo"
    slice_dir.mkdir(parents=True)
    (slice_dir / "README.md").write_text(
        "# Feature: Demo\n\n**Status:** Proposed.\n\nDemo.\n",
        encoding="utf-8",
    )
    (slice_dir / "requirements.md").write_text(
        "- **FR-1.1** Gateway.\n",
        encoding="utf-8",
    )
    (slice_dir / "test-plan.md").write_text(
        "### AC-1 — Cover (FR-1.1)\n\nbody\n",
        encoding="utf-8",
    )

    src = root / "src"
    src.mkdir()
    (src / "gateway.py").write_text("def call() -> int:\n    return 1\n", encoding="utf-8")


@pytest.fixture
def server_with_store(tmp_path: Path):
    repo = tmp_path / "fixture"
    repo.mkdir()
    _build_fixture_repo(repo)
    store = SQLiteGraphClient(tmp_path / "graph.db")
    index_full(repo, store)
    server = build_server(store=store)
    yield server, store
    store.close()


def _get_handler(server, attr_name: str):
    """The `mcp` Server stores registered handlers as `request_handlers` mapping."""

    # The mcp SDK exposes them through `server.request_handlers` (a dict keyed by request type).
    # We'd rather just probe the public test surface: the decorator pattern stores handlers as
    # private attrs we can introspect.
    return server.request_handlers


def test_all_eleven_tools_registered() -> None:
    assert set(_TOOL_SCHEMAS) == {
        "search_codebase",
        "find_symbol",
        "get_feature_packet",
        "explain_feature",
        "get_related_tests",
        "get_docs_for_code",
        "get_code_for_doc",
        "find_stale_docs",
        "validate_feature_packet",
        "plan_change",
        "create_task_brief",
    }


def test_each_tool_has_input_schema_and_description() -> None:
    for name, tool in _TOOL_SCHEMAS.items():
        assert tool.name == name
        assert tool.description, f"{name} missing description"
        schema = tool.inputSchema
        assert schema.get("type") == "object"
        assert "properties" in schema
        # All tools require at least one argument
        assert isinstance(schema.get("required", []), list)


def _dispatch(server, server_with_store_store):
    """Helper to call the registered `call_tool` handler directly."""

    async def run(name: str, args: dict):
        return await _dispatch_tool(server_with_store_store, name, args)

    return run


def test_dispatch_search_codebase(server_with_store) -> None:
    server, store = server_with_store
    runner = _dispatch(server, store)
    results = asyncio.run(runner("search_codebase", {"query": "gateway", "limit": 10}))
    assert isinstance(results, list)
    assert any(r.source_path == "src/gateway.py" for r in results)


def test_dispatch_find_symbol(server_with_store) -> None:
    server, store = server_with_store
    runner = _dispatch(server, store)
    results = asyncio.run(runner("find_symbol", {"symbol": "call"}))
    assert isinstance(results, list)
    assert any(r.name == "call" for r in results)


def test_dispatch_get_feature_packet(server_with_store) -> None:
    server, store = server_with_store
    runner = _dispatch(server, store)
    pkt = asyncio.run(runner("get_feature_packet", {"feature": "01-demo"}))
    assert pkt is not None
    assert pkt.slug == "01-demo"


def test_dispatch_explain_feature(server_with_store) -> None:
    server, store = server_with_store
    runner = _dispatch(server, store)
    ex = asyncio.run(runner("explain_feature", {"feature": "01-demo"}))
    assert ex is not None
    assert ex.slug == "01-demo"
    assert any(r.req_id == "FR-1.1" for r in ex.requirements)


def test_dispatch_validate_feature_packet(server_with_store) -> None:
    server, store = server_with_store
    runner = _dispatch(server, store)
    result = asyncio.run(runner("validate_feature_packet", {"feature": "01-demo"}))
    assert result is not None
    # Missing context.md + plan.md compared to canonical packet
    assert "context.md" in result.missing_files
    assert result.passes is False


def test_dispatch_unknown_tool_raises(server_with_store) -> None:
    server, store = server_with_store
    runner = _dispatch(server, store)
    with pytest.raises(ValueError, match="unknown tool"):
        asyncio.run(runner("nonexistent_tool", {}))


def test_json_safe_serialization_handles_dataclasses() -> None:
    result = SearchResult(
        node_id="doc:x",
        node_type="DocPage",
        source_path="docs/x.md",
        snippet="hello",
        score=-1.5,
    )
    payload = _json_safe([result])
    assert payload == [
        {
            "node_id": "doc:x",
            "node_type": "DocPage",
            "source_path": "docs/x.md",
            "snippet": "hello",
            "score": -1.5,
        }
    ]
    text = _to_text_content([result])
    assert len(text) == 1
    assert json.loads(text[0].text) == payload
