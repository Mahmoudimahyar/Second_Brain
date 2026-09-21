"""Tests for `tools/graphrag/parsers/python_code.py`."""

from __future__ import annotations

from pathlib import Path

import pytest

from tools.graphrag.parsers import python_code
from tools.graphrag.parsers.base import accepts_path
from tools.graphrag.types import EdgeType, NodeType

pytestmark = pytest.mark.unit


class _StubParser:
    ACCEPTS = python_code.ACCEPTS

    def parse(self, file_path, repo_root):  # pragma: no cover
        return None


def test_accepts_src_and_tools() -> None:
    p = _StubParser()
    assert accepts_path(p, "src/gateway/api.py")
    assert accepts_path(p, "tools/graphrag/parsers/markdown.py")


def test_rejects_tests_dir() -> None:
    p = _StubParser()
    assert not accepts_path(p, "tests/graphrag/test_markdown_parser.py")


def _write_py(tmp_repo: Path, repo_relative: str, body: str) -> Path:
    path = tmp_repo / repo_relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def test_emits_codefile_node(tmp_repo: Path) -> None:
    path = _write_py(tmp_repo, "src/x.py", "def foo() -> int:\n    return 1\n")
    result = python_code.parse(path, tmp_repo)

    codefiles = [n for n in result.nodes if n.node_type == NodeType.CODE_FILE]
    assert len(codefiles) == 1
    cf = codefiles[0]
    assert cf.properties["language"] == "python"
    assert cf.properties["function_count"] == 1
    assert cf.properties["class_count"] == 0


def test_extracts_top_level_functions(tmp_repo: Path) -> None:
    path = _write_py(
        tmp_repo,
        "src/x.py",
        'def public_fn(a: int, b: str = "x") -> bool:\n'
        '    """Public function."""\n'
        "    return True\n\n"
        "def _private_fn() -> None:\n"
        "    pass\n",
    )
    result = python_code.parse(path, tmp_repo)

    fns = [n for n in result.nodes if n.node_type == NodeType.FUNCTION]
    names = sorted(n.properties["qualified_name"] for n in fns)
    assert names == ["src.x._private_fn", "src.x.public_fn"]
    pub = next(n for n in fns if n.properties["name"] == "public_fn")
    assert pub.properties["is_public"] is True
    assert pub.properties["docstring"] == "Public function."
    assert "a: int" in pub.properties["signature"]
    priv = next(n for n in fns if n.properties["name"] == "_private_fn")
    assert priv.properties["is_public"] is False


def test_extracts_classes_and_methods(tmp_repo: Path) -> None:
    body = (
        "class Foo:\n"
        '    """Foo class."""\n'
        "    def method_a(self) -> int:\n"
        "        return 1\n\n"
        "    def _method_b(self) -> None:\n"
        "        pass\n"
    )
    path = _write_py(tmp_repo, "src/x.py", body)
    result = python_code.parse(path, tmp_repo)

    classes = [n for n in result.nodes if n.node_type == NodeType.CLASS]
    assert len(classes) == 1
    cls = classes[0]
    assert cls.properties["name"] == "Foo"
    assert cls.properties["docstring"] == "Foo class."
    assert cls.properties["method_names"] == ["method_a", "_method_b"]

    methods = [
        n
        for n in result.nodes
        if n.node_type == NodeType.FUNCTION and n.properties.get("parent_class") == "src.x.Foo"
    ]
    assert sorted(m.properties["name"] for m in methods) == ["_method_b", "method_a"]


def test_emits_intra_file_edges(tmp_repo: Path) -> None:
    body = (
        "def top() -> None:\n    pass\n\n"
        "class C:\n    def m(self) -> None:\n        pass\n"
    )
    path = _write_py(tmp_repo, "src/x.py", body)
    result = python_code.parse(path, tmp_repo)

    file_has_fn = [e for e in result.edges if e.edge_type == EdgeType.FILE_HAS_FUNCTION]
    file_has_class = [e for e in result.edges if e.edge_type == EdgeType.FILE_HAS_CLASS]
    class_has_method = [e for e in result.edges if e.edge_type == EdgeType.CLASS_HAS_METHOD]
    assert len(file_has_fn) == 1
    assert len(file_has_class) == 1
    assert len(class_has_method) == 1


def test_async_function_detected(tmp_repo: Path) -> None:
    path = _write_py(tmp_repo, "src/x.py", "async def go() -> None:\n    pass\n")
    result = python_code.parse(path, tmp_repo)
    fn = next(n for n in result.nodes if n.node_type == NodeType.FUNCTION)
    assert fn.properties["is_async"] is True


def test_syntax_error_returns_warning_no_nodes(tmp_repo: Path) -> None:
    path = _write_py(tmp_repo, "src/broken.py", "def bad(:\n    pass\n")
    result = python_code.parse(path, tmp_repo)
    assert result.nodes == []
    assert any("syntax error" in w for w in result.warnings)


def test_nested_functions_not_emitted(tmp_repo: Path) -> None:
    body = (
        "def outer() -> None:\n"
        "    def inner() -> None:\n"
        "        pass\n"
        "    inner()\n"
    )
    path = _write_py(tmp_repo, "src/x.py", body)
    result = python_code.parse(path, tmp_repo)
    fns = [n for n in result.nodes if n.node_type == NodeType.FUNCTION]
    assert [n.properties["name"] for n in fns] == ["outer"]


def test_body_hash_changes_on_body_edit(tmp_repo: Path) -> None:
    p1 = _write_py(tmp_repo, "src/v1.py", "def foo() -> int:\n    return 1\n")
    p2 = _write_py(tmp_repo, "src/v2.py", "def foo() -> int:\n    return 2\n")
    a = next(n for n in python_code.parse(p1, tmp_repo).nodes if n.node_type == NodeType.FUNCTION)
    b = next(n for n in python_code.parse(p2, tmp_repo).nodes if n.node_type == NodeType.FUNCTION)
    assert a.properties["body_hash"] != b.properties["body_hash"]


def test_idempotent(tmp_repo: Path) -> None:
    path = _write_py(tmp_repo, "src/x.py", "def foo() -> None:\n    pass\n")
    a = python_code.parse(path, tmp_repo)
    b = python_code.parse(path, tmp_repo)
    assert [n.id for n in a.nodes] == [n.id for n in b.nodes]
    assert [e.id for e in a.edges] == [e.id for e in b.edges]
