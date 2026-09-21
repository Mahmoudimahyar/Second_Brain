"""End-to-end tests for the 11 retrieval primitives in `tools/graphrag/retrieval/`.

Builds a small fixture repo, runs the indexer, then exercises each primitive against the
resulting store. This is integration-level by design — each primitive composes parser + edge
+ store, and we want to verify the composition works.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tools.graphrag.index import index_full
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

pytestmark = pytest.mark.integration


def _build_fixture_repo(root: Path) -> None:
    (root / ".gitignore").write_text("", encoding="utf-8")

    core = root / "docs" / "01-core"
    core.mkdir(parents=True)
    (core / "vision.md").write_text(
        "# Vision\n\n## Goals\n\nBuild a thing. See `src/gateway.py` for the gateway.\n",
        encoding="utf-8",
    )

    slice_dir = root / "docs" / "05-features" / "01-demo-slice"
    slice_dir.mkdir(parents=True)
    (slice_dir / "README.md").write_text(
        "# Feature: Demo Slice\n\n**Status:** Proposed.\n\nThe demo slice exercises the gateway.\n",
        encoding="utf-8",
    )
    (slice_dir / "context.md").write_text("# Context\n\nbody\n", encoding="utf-8")
    (slice_dir / "requirements.md").write_text(
        "- **FR-1.1** First requirement uses gateway.\n"
        "- **FR-2.1** Second requirement.\n"
        "- **NFR-1 Latency**: < 250 ms.\n",
        encoding="utf-8",
    )
    (slice_dir / "plan.md").write_text("# Plan\n\nDo it.\n", encoding="utf-8")
    (slice_dir / "test-plan.md").write_text(
        "### AC-1 — Gateway works (FR-1.1)\n\nbody\n\n"
        "### AC-2 — Latency (NFR-1)\n\nbody\n",
        encoding="utf-8",
    )
    (slice_dir / "known-issues.md").write_text(
        "| ID | Issue | Category | Severity |\n"
        "|---|---|---|---|\n"
        "| KI-001 | Cache TTL silently dropped | Cost | High |\n",
        encoding="utf-8",
    )

    src = root / "src"
    src.mkdir()
    (src / "gateway.py").write_text(
        '"""LLM gateway module."""\n\n'
        "def call_anthropic(prompt: str) -> str:\n"
        '    """Call Anthropic via the gateway."""\n'
        "    return prompt\n\n"
        "class LLMClient:\n"
        '    """Vendor-portable ABC."""\n'
        "    def complete(self, prompt: str) -> str:\n"
        '        """Run a completion."""\n'
        "        return prompt\n",
        encoding="utf-8",
    )

    tests_dir = root / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_gateway.py").write_text(
        "import pytest\n\n"
        "pytestmark = pytest.mark.unit\n\n"
        "def test_call_anthropic() -> None:\n"
        '    """Covers FR-1.1 and AC-1."""\n'
        "    assert True\n\n"
        "def test_latency() -> None:\n"
        '    """Covers NFR-1 and AC-2."""\n'
        "    assert True\n",
        encoding="utf-8",
    )

    adr_dir = root / "docs" / "11-decisions"
    adr_dir.mkdir(parents=True)
    (adr_dir / "ADR-001-gateway.md").write_text(
        "# ADR-001: Gateway Choice\n\n"
        "Status: accepted\nDate: 2026-05-21\n\n"
        "## Decision\n\nUse a vendor-portable gateway.\n\n"
        "## Related code\n\n- `src/gateway.py` — gateway impl\n",
        encoding="utf-8",
    )

    (root / ".env.example").write_text(
        "# Anthropic\nANTHROPIC_API_KEY=\n",
        encoding="utf-8",
    )
    (root / "pyproject.toml").write_text(
        '[project]\nname = "fixture"\nversion = "0.1"\nrequires-python = ">=3.12"\n',
        encoding="utf-8",
    )


@pytest.fixture
def indexed_store(tmp_path: Path) -> SQLiteGraphClient:
    repo = tmp_path / "fixture"
    repo.mkdir()
    _build_fixture_repo(repo)
    store = SQLiteGraphClient(tmp_path / "graph.db")
    index_full(repo, store)
    yield store
    store.close()


# ---------- search_codebase ----------


def test_search_codebase_finds_relevant_nodes(indexed_store: SQLiteGraphClient) -> None:
    results = search_codebase(indexed_store, "gateway", limit=15)
    assert len(results) > 0
    # Spot-check: the gateway code file should show up
    paths = {r.source_path for r in results}
    assert "src/gateway.py" in paths


def test_search_codebase_kind_filter(indexed_store: SQLiteGraphClient) -> None:
    code_only = search_codebase(
        indexed_store,
        "gateway",
        kind_filter=(NodeType.CODE_FILE,),
        limit=10,
    )
    assert all(r.node_type == "CodeFile" for r in code_only)


def test_search_codebase_empty_query_safe(indexed_store: SQLiteGraphClient) -> None:
    results = search_codebase(indexed_store, "", limit=5)
    assert results == []


# ---------- find_symbol ----------


def test_find_symbol_exact_function(indexed_store: SQLiteGraphClient) -> None:
    results = find_symbol(indexed_store, "call_anthropic")
    assert results
    assert results[0].match_kind == "exact"
    assert results[0].qualified_name == "src.gateway.call_anthropic"


def test_find_symbol_exact_class(indexed_store: SQLiteGraphClient) -> None:
    results = find_symbol(indexed_store, "LLMClient")
    assert results
    assert results[0].match_kind == "exact"
    assert results[0].name == "LLMClient"


def test_find_symbol_prefix(indexed_store: SQLiteGraphClient) -> None:
    results = find_symbol(indexed_store, "call_an")
    assert any(r.match_kind == "prefix" for r in results)


def test_find_symbol_empty_safe(indexed_store: SQLiteGraphClient) -> None:
    assert find_symbol(indexed_store, "") == []


# ---------- get_feature_packet ----------


def test_get_feature_packet_returns_ordered_documents(indexed_store: SQLiteGraphClient) -> None:
    pkt = get_feature_packet(indexed_store, "01-demo-slice")
    assert pkt is not None
    names = [d.source_path.rsplit("/", 1)[-1] for d in pkt.documents]
    # README first, then context, then requirements, etc.
    assert names[0] == "README.md"
    assert "requirements.md" in names
    assert "test-plan.md" in names


def test_get_feature_packet_unknown_returns_none(indexed_store: SQLiteGraphClient) -> None:
    assert get_feature_packet(indexed_store, "nonexistent") is None


# ---------- explain_feature ----------


def test_explain_feature_aggregates(indexed_store: SQLiteGraphClient) -> None:
    ex = explain_feature(indexed_store, "01-demo-slice")
    assert ex is not None
    assert ex.slug == "01-demo-slice"
    assert ex.status == "proposed"
    req_ids = {r.req_id for r in ex.requirements}
    assert {"FR-1.1", "FR-2.1", "NFR-1"} <= req_ids
    ac_ids = {a.ac_id for a in ex.acceptance_criteria}
    assert "AC-1" in ac_ids
    assert "AC-2" in ac_ids
    # Tests should pick up the docstring-tagged AC-1 / AC-2 references
    assert len(ex.tests) >= 1
    assert len(ex.known_issues) >= 1


def test_explain_feature_unknown(indexed_store: SQLiteGraphClient) -> None:
    assert explain_feature(indexed_store, "nope") is None


# ---------- get_related_tests ----------


def test_get_related_tests_via_requirement(indexed_store: SQLiteGraphClient) -> None:
    tests = get_related_tests(indexed_store, "req:01-demo-slice:FR-1.1")
    assert tests
    assert any("test_call_anthropic" in t.qualified_name for t in tests)


def test_get_related_tests_via_ac(indexed_store: SQLiteGraphClient) -> None:
    tests = get_related_tests(indexed_store, "ac:01-demo-slice:AC-2")
    assert any("test_latency" in t.qualified_name for t in tests)


def test_get_related_tests_via_feature(indexed_store: SQLiteGraphClient) -> None:
    tests = get_related_tests(indexed_store, "feature:01-demo-slice")
    assert len(tests) >= 1


def test_get_related_tests_unknown_target(indexed_store: SQLiteGraphClient) -> None:
    assert get_related_tests(indexed_store, "missing:thing") == []


# ---------- get_docs_for_code ----------


def test_get_docs_for_code_finds_doc_section_referencing_code(indexed_store: SQLiteGraphClient) -> None:
    refs = get_docs_for_code(indexed_store, "src/gateway.py")
    assert any("01-core/vision.md" in r.page_path for r in refs)


def test_get_docs_for_code_unknown_returns_empty(indexed_store: SQLiteGraphClient) -> None:
    assert get_docs_for_code(indexed_store, "src/missing.py") == []


# ---------- get_code_for_doc ----------


def test_get_code_for_doc_returns_referenced_code(indexed_store: SQLiteGraphClient) -> None:
    refs = get_code_for_doc(indexed_store, "docs/01-core/vision.md")
    assert any(r.source_path == "src/gateway.py" for r in refs)


def test_get_code_for_doc_unknown_doc_returns_empty(indexed_store: SQLiteGraphClient) -> None:
    assert get_code_for_doc(indexed_store, "docs/nope.md") == []


# ---------- find_stale_docs ----------


def test_find_stale_docs_returns_empty_for_fresh_repo(indexed_store: SQLiteGraphClient) -> None:
    # No staleness immediately after indexing — code and docs have the same modified_at.
    stale = find_stale_docs(indexed_store, ["src/gateway.py"], days_threshold=1)
    assert stale == []


def test_find_stale_docs_handles_unknown_path(indexed_store: SQLiteGraphClient) -> None:
    assert find_stale_docs(indexed_store, ["src/missing.py"]) == []


# ---------- validate_feature_packet ----------


def test_validate_feature_packet_passes_for_minimal_slice(indexed_store: SQLiteGraphClient) -> None:
    result = validate_feature_packet(indexed_store, "01-demo-slice")
    assert result is not None
    assert result.passes is True
    assert "README.md" in result.present_files


def test_validate_feature_packet_flags_missing_files(tmp_path: Path) -> None:
    # Build a packet missing test-plan.md
    repo = tmp_path / "fixture"
    repo.mkdir()
    slice_dir = repo / "docs" / "05-features" / "02-thin-slice"
    slice_dir.mkdir(parents=True)
    (slice_dir / "README.md").write_text(
        "# Feature: Thin Slice\n\n**Status:** Proposed.\n",
        encoding="utf-8",
    )
    (repo / ".gitignore").write_text("", encoding="utf-8")

    store = SQLiteGraphClient(tmp_path / "graph.db")
    index_full(repo, store)
    result = validate_feature_packet(store, "02-thin-slice")
    assert result is not None
    assert result.passes is False
    assert "test-plan.md" in result.missing_files
    store.close()


def test_validate_feature_packet_unknown(indexed_store: SQLiteGraphClient) -> None:
    assert validate_feature_packet(indexed_store, "nope") is None


# ---------- plan_change ----------


def test_plan_change_selects_relevant_feature(indexed_store: SQLiteGraphClient) -> None:
    plan = plan_change(indexed_store, "improve the gateway", k_features=2)
    assert plan.selected_features
    assert plan.selected_features[0].slug == "01-demo-slice"


# ---------- create_task_brief ----------


def test_create_task_brief_includes_features_and_files(indexed_store: SQLiteGraphClient) -> None:
    brief = create_task_brief(indexed_store, "improve the gateway")
    assert "Demo Slice" in brief.brief_markdown
    assert "01-demo-slice" in brief.selected_features
    assert brief.saved_to is None


def test_create_task_brief_writes_file_when_path_given(indexed_store: SQLiteGraphClient, tmp_path: Path) -> None:
    out = tmp_path / "briefs" / "improve-gateway.md"
    brief = create_task_brief(indexed_store, "improve the gateway", save_path=out)
    assert brief.saved_to == str(out)
    assert out.exists()
    assert "Demo Slice" in out.read_text(encoding="utf-8")
