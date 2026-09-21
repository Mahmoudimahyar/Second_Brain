"""Tests for `tools/graphrag/parsers/test_file.py`."""

from __future__ import annotations

from pathlib import Path

import pytest

from tools.graphrag.parsers import test_file
from tools.graphrag.parsers.base import accepts_path
from tools.graphrag.types import EdgeType, NodeType

pytestmark = pytest.mark.unit


class _StubParser:
    ACCEPTS = test_file.ACCEPTS

    def parse(self, file_path, repo_root):  # pragma: no cover
        return None


def test_accepts_tests_dir() -> None:
    p = _StubParser()
    assert accepts_path(p, "tests/graphrag/test_markdown_parser.py")
    assert accepts_path(p, "tests/extraction/test_cascade.py")


def test_rejects_src_dir() -> None:
    p = _StubParser()
    assert not accepts_path(p, "src/gateway/api.py")


def _write_test(tmp_repo: Path, repo_relative: str, body: str) -> Path:
    path = tmp_repo / repo_relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def test_emits_testfile_node(tmp_repo: Path) -> None:
    body = (
        "import pytest\n\n"
        "def test_x() -> None:\n"
        "    assert True\n"
    )
    path = _write_test(tmp_repo, "tests/test_x.py", body)
    result = test_file.parse(path, tmp_repo)

    tfs = [n for n in result.nodes if n.node_type == NodeType.TEST_FILE]
    assert len(tfs) == 1
    assert tfs[0].properties["test_case_count"] == 1


def test_extracts_test_cases_only(tmp_repo: Path) -> None:
    body = (
        "def helper() -> int:\n"
        "    return 1\n\n"
        "def test_a() -> None:\n"
        "    assert True\n\n"
        "def test_b() -> None:\n"
        "    assert True\n"
    )
    path = _write_test(tmp_repo, "tests/test_x.py", body)
    result = test_file.parse(path, tmp_repo)

    cases = [n for n in result.nodes if n.node_type == NodeType.TEST_CASE]
    names = sorted(n.properties["name"] for n in cases)
    assert names == ["test_a", "test_b"]


def test_extracts_module_pytestmark(tmp_repo: Path) -> None:
    body = (
        "import pytest\n\n"
        "pytestmark = pytest.mark.unit\n\n"
        "def test_x() -> None:\n"
        "    assert True\n"
    )
    path = _write_test(tmp_repo, "tests/test_x.py", body)
    result = test_file.parse(path, tmp_repo)

    case = next(n for n in result.nodes if n.node_type == NodeType.TEST_CASE)
    assert "unit" in case.properties["markers"]


def test_extracts_function_marker(tmp_repo: Path) -> None:
    body = (
        "import pytest\n\n"
        "@pytest.mark.integration\n"
        "def test_x() -> None:\n"
        "    assert True\n"
    )
    path = _write_test(tmp_repo, "tests/test_x.py", body)
    result = test_file.parse(path, tmp_repo)

    case = next(n for n in result.nodes if n.node_type == NodeType.TEST_CASE)
    assert "integration" in case.properties["markers"]


def test_module_pytestmark_list(tmp_repo: Path) -> None:
    body = (
        "import pytest\n\n"
        "pytestmark = [pytest.mark.unit, pytest.mark.smoke]\n\n"
        "def test_x() -> None:\n"
        "    assert True\n"
    )
    path = _write_test(tmp_repo, "tests/test_x.py", body)
    result = test_file.parse(path, tmp_repo)

    case = next(n for n in result.nodes if n.node_type == NodeType.TEST_CASE)
    assert "unit" in case.properties["markers"]
    assert "smoke" in case.properties["markers"]


def test_extracts_req_and_ac_refs_from_docstring(tmp_repo: Path) -> None:
    body = (
        "def test_x() -> None:\n"
        '    """Verifies AC-3 + FR-2.3 + NFR-1."""\n'
        "    assert True\n"
    )
    path = _write_test(tmp_repo, "tests/test_x.py", body)
    result = test_file.parse(path, tmp_repo)

    case = next(n for n in result.nodes if n.node_type == NodeType.TEST_CASE)
    assert "FR-2.3" in case.properties["linked_req_ids"]
    assert "NFR-1" in case.properties["linked_req_ids"]
    assert "AC-3" in case.properties["linked_ac_ids"]


def test_extracts_refs_from_body(tmp_repo: Path) -> None:
    body = (
        "def test_x() -> None:\n"
        "    # AC-5 + FR-1.1\n"
        "    assert True\n"
    )
    path = _write_test(tmp_repo, "tests/test_x.py", body)
    result = test_file.parse(path, tmp_repo)

    case = next(n for n in result.nodes if n.node_type == NodeType.TEST_CASE)
    assert "FR-1.1" in case.properties["linked_req_ids"]
    assert "AC-5" in case.properties["linked_ac_ids"]


def test_emits_test_file_has_case_edges(tmp_repo: Path) -> None:
    body = "def test_a() -> None:\n    assert True\n\ndef test_b() -> None:\n    assert True\n"
    path = _write_test(tmp_repo, "tests/test_x.py", body)
    result = test_file.parse(path, tmp_repo)

    edges = [e for e in result.edges if e.edge_type == EdgeType.TEST_FILE_HAS_CASE]
    assert len(edges) == 2


def test_syntax_error_returns_warning_no_nodes(tmp_repo: Path) -> None:
    path = _write_test(tmp_repo, "tests/test_bad.py", "def test_bad(:\n    pass\n")
    result = test_file.parse(path, tmp_repo)
    assert result.nodes == []
    assert any("syntax error" in w for w in result.warnings)


def test_idempotent(tmp_repo: Path) -> None:
    path = _write_test(tmp_repo, "tests/test_x.py", "def test_x() -> None:\n    assert True\n")
    a = test_file.parse(path, tmp_repo)
    b = test_file.parse(path, tmp_repo)
    assert [n.id for n in a.nodes] == [n.id for n in b.nodes]
