"""Test-file parser: emits `TestFile` + `TestCase` nodes for `tests/**/*.py`.

Extracts:
  - `TestFile`: one per `tests/**/*.py`.
  - `TestCase`: one per top-level function named `test_*` (per pytest convention).
  - `markers`: from `@pytest.mark.<name>` decorators + module-level `pytestmark`.
  - `linked_req_ids` / `linked_ac_ids`: from docstring tags (e.g., `# AC-3` or `# FR-2.3`) and from
    references in the test function name or docstring.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from tools.graphrag.parsers._util import hash_text
from tools.graphrag.types import Edge, EdgeType, Node, NodeType, ParseResult

ACCEPTS: tuple[str, ...] = ("tests/**/*.py",)

_REQ_REF_RE = re.compile(r"\b(?P<id>(?:N?FR)-\d+(?:\.\d+)?)\b")
_AC_REF_RE = re.compile(r"\bAC-\d+\b")


def _module_name_from_path(repo_relative: str) -> str:
    return repo_relative.removesuffix(".py").replace("/", ".").replace("\\", ".")


def _module_pytestmarks(tree: ast.Module) -> list[str]:
    """Extract `pytestmark = pytest.mark.<name>` (or list-of) from module body."""

    result: list[str] = []
    for stmt in tree.body:
        if not isinstance(stmt, ast.Assign):
            continue
        for target in stmt.targets:
            if isinstance(target, ast.Name) and target.id == "pytestmark":
                result.extend(_extract_marker_names(stmt.value))
    return result


def _extract_marker_names(expr: ast.expr) -> list[str]:
    """Pull marker names from `pytest.mark.X`, `pytest.mark.X(...)`, or a list of them."""

    if isinstance(expr, ast.List):
        names: list[str] = []
        for elt in expr.elts:
            names.extend(_extract_marker_names(elt))
        return names

    target = expr.func if isinstance(expr, ast.Call) else expr
    parts: list[str] = []
    current = target
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if isinstance(current, ast.Name):
        parts.append(current.id)
    parts.reverse()
    # Accept patterns like ["pytest", "mark", "<name>"] or ["mark", "<name>"]
    for i in range(len(parts) - 1):
        if parts[i] == "mark":
            return [parts[i + 1]]
    return []


def _function_markers(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
    markers: list[str] = []
    for deco in node.decorator_list:
        markers.extend(_extract_marker_names(deco))
    return markers


def _extract_refs_from_text(text: str | None) -> tuple[list[str], list[str]]:
    if not text:
        return ([], [])
    reqs = sorted({m.group("id") for m in _REQ_REF_RE.finditer(text)})
    acs = sorted({m.group(0) for m in _AC_REF_RE.finditer(text)})
    return (reqs, acs)


def parse(file_path: Path, repo_root: Path) -> ParseResult:
    text = file_path.read_text(encoding="utf-8")
    repo_relative = file_path.relative_to(repo_root).as_posix()
    module_name = _module_name_from_path(repo_relative)

    try:
        tree = ast.parse(text, filename=repo_relative)
    except SyntaxError as exc:
        return ParseResult(warnings=[f"syntax error in {repo_relative}: {exc.msg} at line {exc.lineno}"])

    module_markers = _module_pytestmarks(tree)
    file_id = f"testfile:{repo_relative}"
    test_cases: list[Node] = []
    edges: list[Edge] = []

    for child in tree.body:
        if not isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not child.name.startswith("test_"):
            continue

        qualified = f"{module_name}.{child.name}"
        case_id = f"test:{qualified}"
        docstring = ast.get_docstring(child)
        body_lines = "\n".join(text.splitlines()[child.lineno - 1 : child.end_lineno])
        marker_names = sorted(set(module_markers) | set(_function_markers(child)))
        reqs_from_doc, acs_from_doc = _extract_refs_from_text(docstring)
        reqs_from_body, acs_from_body = _extract_refs_from_text(body_lines)
        linked_req_ids = sorted(set(reqs_from_doc) | set(reqs_from_body))
        linked_ac_ids = sorted(set(acs_from_doc) | set(acs_from_body))

        test_cases.append(
            Node(
                id=case_id,
                node_type=NodeType.TEST_CASE,
                source_path=repo_relative,
                content_hash=hash_text(body_lines),
                properties={
                    "qualified_name": qualified,
                    "name": child.name,
                    "parent_file": repo_relative,
                    "markers": marker_names,
                    "linked_req_ids": linked_req_ids,
                    "linked_ac_ids": linked_ac_ids,
                    "docstring": docstring,
                    "start_line": child.lineno,
                    "end_line": child.end_lineno,
                    "is_async": isinstance(child, ast.AsyncFunctionDef),
                },
            )
        )
        edges.append(
            Edge(
                id=f"edge:{file_id}-case-{case_id}",
                edge_type=EdgeType.TEST_FILE_HAS_CASE,
                from_node_id=file_id,
                to_node_id=case_id,
            )
        )

    file_node = Node(
        id=file_id,
        node_type=NodeType.TEST_FILE,
        source_path=repo_relative,
        content_hash=hash_text(text),
        properties={
            "source_path": repo_relative,
            "test_case_count": len(test_cases),
            "module_pytestmarks": module_markers,
        },
    )
    return ParseResult(nodes=[file_node, *test_cases], edges=edges)
