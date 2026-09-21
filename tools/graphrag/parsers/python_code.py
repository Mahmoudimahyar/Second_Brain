"""Python code parser: AST-based extraction of `CodeFile` + `Function` + `Class` nodes.

Scope: `src/**/*.py` + `tools/**/*.py` (NOT `tests/**/*.py` — those go to `test_file.py`).

Traverses the AST and walks only top-level definitions (functions + classes); methods of a class
are emitted as `Function` nodes with a `CLASS_HAS_METHOD` edge. Closures + nested functions are
not emitted as separate nodes.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

from tools.graphrag.parsers._util import hash_text
from tools.graphrag.types import Edge, EdgeType, Node, NodeType, ParseResult

ACCEPTS: tuple[str, ...] = (
    "src/**/*.py",
    "tools/**/*.py",
)


def _signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    return f"def {node.name}{ast.unparse(node.args)}"


def _body_text(source: str, node: ast.AST) -> str:
    lineno = getattr(node, "lineno", None)
    end_lineno = getattr(node, "end_lineno", None)
    if lineno is None or end_lineno is None:
        return ""
    lines = source.splitlines()
    return "\n".join(lines[lineno - 1 : end_lineno])


def _is_public(name: str) -> bool:
    return not name.startswith("_")


def _module_name_from_path(repo_relative: str) -> str:
    return repo_relative.removesuffix(".py").replace("/", ".").replace("\\", ".")


def parse(file_path: Path, repo_root: Path) -> ParseResult:
    text = file_path.read_text(encoding="utf-8")
    repo_relative = file_path.relative_to(repo_root).as_posix()
    module_name = _module_name_from_path(repo_relative)

    try:
        tree = ast.parse(text, filename=repo_relative)
    except SyntaxError as exc:
        return ParseResult(warnings=[f"syntax error in {repo_relative}: {exc.msg} at line {exc.lineno}"])

    file_id = f"code:{repo_relative}"
    func_count = 0
    class_count = 0
    nodes: list[Node] = []
    edges: list[Edge] = []

    # Walk top-level only — closures + nested defs are not extracted.
    for child in tree.body:
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
            func_count += 1
            qualified = f"{module_name}.{child.name}"
            fn_id = f"fn:{qualified}"
            body = _body_text(text, child)
            nodes.append(
                Node(
                    id=fn_id,
                    node_type=NodeType.FUNCTION,
                    source_path=repo_relative,
                    content_hash=hash_text(body),
                    properties={
                        "qualified_name": qualified,
                        "name": child.name,
                        "parent_file": repo_relative,
                        "signature": _signature(child),
                        "docstring": ast.get_docstring(child),
                        "is_public": _is_public(child.name),
                        "is_async": isinstance(child, ast.AsyncFunctionDef),
                        "start_line": child.lineno,
                        "end_line": child.end_lineno,
                        "body_hash": hash_text(body),
                    },
                )
            )
            edges.append(
                Edge(
                    id=f"edge:{file_id}-fn-{fn_id}",
                    edge_type=EdgeType.FILE_HAS_FUNCTION,
                    from_node_id=file_id,
                    to_node_id=fn_id,
                )
            )

        elif isinstance(child, ast.ClassDef):
            class_count += 1
            class_qualified = f"{module_name}.{child.name}"
            cls_id = f"cls:{class_qualified}"
            class_body = _body_text(text, child)
            bases = [ast.unparse(base) for base in child.bases]
            method_names: list[str] = []

            nodes.append(
                Node(
                    id=cls_id,
                    node_type=NodeType.CLASS,
                    source_path=repo_relative,
                    content_hash=hash_text(class_body),
                    properties={
                        "qualified_name": class_qualified,
                        "name": child.name,
                        "parent_file": repo_relative,
                        "bases": bases,
                        "docstring": ast.get_docstring(child),
                        "is_public": _is_public(child.name),
                        "start_line": child.lineno,
                        "end_line": child.end_lineno,
                        "body_hash": hash_text(class_body),
                        "method_names": method_names,
                    },
                )
            )
            edges.append(
                Edge(
                    id=f"edge:{file_id}-cls-{cls_id}",
                    edge_type=EdgeType.FILE_HAS_CLASS,
                    from_node_id=file_id,
                    to_node_id=cls_id,
                )
            )

            for class_child in child.body:
                if isinstance(class_child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    method_qualified = f"{class_qualified}.{class_child.name}"
                    method_id = f"fn:{method_qualified}"
                    method_body = _body_text(text, class_child)
                    method_names.append(class_child.name)
                    nodes.append(
                        Node(
                            id=method_id,
                            node_type=NodeType.FUNCTION,
                            source_path=repo_relative,
                            content_hash=hash_text(method_body),
                            properties={
                                "qualified_name": method_qualified,
                                "name": class_child.name,
                                "parent_file": repo_relative,
                                "parent_class": class_qualified,
                                "signature": _signature(class_child),
                                "docstring": ast.get_docstring(class_child),
                                "is_public": _is_public(class_child.name),
                                "is_async": isinstance(class_child, ast.AsyncFunctionDef),
                                "start_line": class_child.lineno,
                                "end_line": class_child.end_lineno,
                                "body_hash": hash_text(method_body),
                            },
                        )
                    )
                    edges.append(
                        Edge(
                            id=f"edge:{cls_id}-method-{method_id}",
                            edge_type=EdgeType.CLASS_HAS_METHOD,
                            from_node_id=cls_id,
                            to_node_id=method_id,
                        )
                    )

    file_props: dict[str, Any] = {
        "language": "python",
        "loc": len(text.splitlines()),
        "function_count": func_count,
        "class_count": class_count,
        "module_name": module_name,
    }
    file_node = Node(
        id=file_id,
        node_type=NodeType.CODE_FILE,
        source_path=repo_relative,
        content_hash=hash_text(text),
        properties=file_props,
    )
    return ParseResult(nodes=[file_node, *nodes], edges=edges)
