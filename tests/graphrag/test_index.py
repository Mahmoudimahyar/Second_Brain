"""Tests for `tools/graphrag/index.py`."""

from __future__ import annotations

from pathlib import Path

import pytest

from tools.graphrag.index import index_full, index_incremental
from tools.graphrag.store.client import EdgeQuery, NodeQuery
from tools.graphrag.store.sqlite_client import SQLiteGraphClient
from tools.graphrag.types import EdgeType, NodeType

pytestmark = pytest.mark.integration


def _build_fixture_repo(root: Path) -> None:
    """Lay down a small repo with one of every parseable file kind."""

    (root / ".gitignore").write_text("__pycache__/\n", encoding="utf-8")

    # Markdown doc
    core = root / "docs" / "01-core"
    core.mkdir(parents=True)
    (core / "product-vision.md").write_text(
        "# Vision\n\n## Goals\n\nDo things with `src/x.py`.\n",
        encoding="utf-8",
    )

    # Feature packet
    slice_dir = root / "docs" / "05-features" / "01-test-slice"
    slice_dir.mkdir(parents=True)
    (slice_dir / "README.md").write_text(
        "# Feature: Test Slice\n\n**Status:** Proposed.\n",
        encoding="utf-8",
    )
    (slice_dir / "requirements.md").write_text(
        "- **FR-1.1** First requirement.\n- **NFR-1 Latency**: < 250ms.\n",
        encoding="utf-8",
    )
    (slice_dir / "test-plan.md").write_text(
        "### AC-1 — Coverage (FR-1.1)\n\n- Unit test.\n",
        encoding="utf-8",
    )
    (slice_dir / "known-issues.md").write_text(
        "| ID | Issue | Category | Severity |\n"
        "|---|---|---|---|\n"
        "| KI-001 | Real issue | Data | Med |\n",
        encoding="utf-8",
    )

    # ADR
    adr_dir = root / "docs" / "11-decisions"
    adr_dir.mkdir(parents=True)
    (adr_dir / "ADR-001-x.md").write_text(
        "# ADR-001: First Decision\n\n"
        "Status: accepted\nDate: 2026-05-20\n\n"
        "## Decision\n\nFirst paragraph.\n\n"
        "## Related code\n\n- `src/x.py`\n",
        encoding="utf-8",
    )

    # Python code
    src = root / "src"
    src.mkdir()
    (src / "x.py").write_text(
        "def foo() -> int:\n    return 1\n\n"
        "class Bar:\n    def method(self) -> None:\n        pass\n",
        encoding="utf-8",
    )

    # Test file
    tests_dir = root / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_x.py").write_text(
        "import pytest\n\n"
        "pytestmark = pytest.mark.unit\n\n"
        "def test_a() -> None:\n"
        '    """Covers FR-1.1 and AC-1."""\n'
        "    assert True\n",
        encoding="utf-8",
    )

    # Config
    (root / ".env.example").write_text(
        "# Test key\nTEST_KEY=\n",
        encoding="utf-8",
    )
    (root / "pyproject.toml").write_text(
        '[project]\nname = "fixture"\nversion = "0.1"\nrequires-python = ">=3.12"\n',
        encoding="utf-8",
    )

    # Context pack
    pack_dir = root / "docs" / "14-context-packs" / "demo"
    pack_dir.mkdir(parents=True)
    (pack_dir / "README.md").write_text(
        "# Demo pack\n\nA test pack.\n",
        encoding="utf-8",
    )


def test_index_full_produces_expected_node_counts(tmp_path: Path) -> None:
    repo = tmp_path / "fixture"
    repo.mkdir()
    _build_fixture_repo(repo)
    store = SQLiteGraphClient(tmp_path / "graph.db")

    snapshot = index_full(repo, store)

    # Snapshot stats
    assert snapshot.files_indexed > 0
    assert snapshot.nodes_total > 0
    assert snapshot.edges_total > 0

    # Spot-check per-type counts
    features = store.query_nodes(NodeQuery(node_type=NodeType.FEATURE))
    assert len(features) == 1
    requirements = store.query_nodes(NodeQuery(node_type=NodeType.REQUIREMENT))
    assert len(requirements) == 2  # FR-1.1 + NFR-1
    acs = store.query_nodes(NodeQuery(node_type=NodeType.ACCEPTANCE_CRITERION))
    assert len(acs) == 1
    adrs = store.query_nodes(NodeQuery(node_type=NodeType.ADR))
    assert len(adrs) == 1
    code_files = store.query_nodes(NodeQuery(node_type=NodeType.CODE_FILE))
    assert len(code_files) == 1
    functions = store.query_nodes(NodeQuery(node_type=NodeType.FUNCTION))
    # foo + Bar.method
    assert len(functions) == 2
    classes = store.query_nodes(NodeQuery(node_type=NodeType.CLASS))
    assert len(classes) == 1
    test_cases = store.query_nodes(NodeQuery(node_type=NodeType.TEST_CASE))
    assert len(test_cases) == 1
    known_issues = store.query_nodes(NodeQuery(node_type=NodeType.KNOWN_ISSUE))
    assert len(known_issues) == 1
    context_packs = store.query_nodes(NodeQuery(node_type=NodeType.CONTEXT_PACK))
    assert len(context_packs) == 1
    config_keys = store.query_nodes(NodeQuery(node_type=NodeType.CONFIG_KEY))
    # 1 env key + 3 pyproject required keys (name, version, requires-python)
    assert len(config_keys) >= 4

    store.close()


def test_index_full_skips_data_and_external_dirs(tmp_path: Path) -> None:
    repo = tmp_path / "fixture"
    repo.mkdir()
    _build_fixture_repo(repo)
    # Add files in skipped dirs
    (repo / "data").mkdir()
    (repo / "data" / "should-skip.md").write_text("# skip me\n", encoding="utf-8")
    (repo / "External Data").mkdir()
    (repo / "External Data" / "ignore.md").write_text("# also skip\n", encoding="utf-8")
    (repo / ".venv").mkdir()
    (repo / ".venv" / "lib.py").write_text("def x() -> int:\n    return 0\n", encoding="utf-8")

    store = SQLiteGraphClient(tmp_path / "graph.db")
    index_full(repo, store)

    docpages = store.query_nodes(NodeQuery(node_type=NodeType.DOC_PAGE))
    paths = {n.source_path for n in docpages}
    assert "data/should-skip.md" not in paths
    assert "External Data/ignore.md" not in paths

    store.close()


def test_full_index_creates_cross_file_edges(tmp_path: Path) -> None:
    repo = tmp_path / "fixture"
    repo.mkdir()
    _build_fixture_repo(repo)
    store = SQLiteGraphClient(tmp_path / "graph.db")

    index_full(repo, store)

    feature_reqs = store.query_edges(EdgeQuery(edge_type=EdgeType.FEATURE_HAS_REQUIREMENT))
    assert len(feature_reqs) == 2  # FR-1.1 + NFR-1

    # REQUIREMENT_HAS_ACCEPTANCE_CRITERION
    req_ac = store.query_edges(EdgeQuery(edge_type=EdgeType.REQUIREMENT_HAS_ACCEPTANCE_CRITERION))
    assert len(req_ac) == 1  # AC-1 -> FR-1.1

    # TEST_COVERS_*
    test_req = store.query_edges(EdgeQuery(edge_type=EdgeType.TEST_COVERS_REQUIREMENT))
    assert len(test_req) >= 1
    test_ac = store.query_edges(EdgeQuery(edge_type=EdgeType.TEST_COVERS_ACCEPTANCE_CRITERION))
    assert len(test_ac) >= 1

    # ADR_DECIDES
    adr_decides = store.query_edges(EdgeQuery(edge_type=EdgeType.ADR_DECIDES))
    assert len(adr_decides) == 1  # ADR-001 -> src/x.py

    # KNOWN_ISSUE_AFFECTS
    ki_affects = store.query_edges(EdgeQuery(edge_type=EdgeType.KNOWN_ISSUE_AFFECTS))
    assert len(ki_affects) == 1

    # DOC_SECTION_REFERENCES_CODE
    doc_refs = store.query_edges(EdgeQuery(edge_type=EdgeType.DOC_SECTION_REFERENCES_CODE))
    assert any(e.to_node_id == "code:src/x.py" for e in doc_refs)

    store.close()


def test_incremental_falls_back_to_full_when_no_prior_snapshot(tmp_path: Path) -> None:
    repo = tmp_path / "fixture"
    repo.mkdir()
    _build_fixture_repo(repo)
    store = SQLiteGraphClient(tmp_path / "graph.db")

    snap = index_incremental(repo, store)
    assert snap.nodes_total > 0

    store.close()


def test_incremental_produces_new_snapshot_id_when_files_change(tmp_path: Path) -> None:
    repo = tmp_path / "fixture"
    repo.mkdir()
    _build_fixture_repo(repo)
    store = SQLiteGraphClient(tmp_path / "graph.db")

    snap1 = index_full(repo, store)

    # Mutate one file
    (repo / "docs" / "01-core" / "product-vision.md").write_text(
        "# Vision\n\n## Goals\n\nUpdated content.\n",
        encoding="utf-8",
    )
    snap2 = index_incremental(repo, store)
    assert snap1.snapshot_id != snap2.snapshot_id

    store.close()


def test_restrict_globs_limits_indexing(tmp_path: Path) -> None:
    repo = tmp_path / "fixture"
    repo.mkdir()
    _build_fixture_repo(repo)
    store = SQLiteGraphClient(tmp_path / "graph.db")

    index_full(repo, store, restrict_globs=("docs/**/*.md",))

    code_files = store.query_nodes(NodeQuery(node_type=NodeType.CODE_FILE))
    assert code_files == []  # src/x.py not indexed
    docpages = store.query_nodes(NodeQuery(node_type=NodeType.DOC_PAGE))
    assert len(docpages) > 0

    store.close()
