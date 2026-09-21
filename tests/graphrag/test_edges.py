"""Tests for `tools/graphrag/edges.py` cross-parser edge derivation."""

from __future__ import annotations

import pytest

from tools.graphrag.edges import (
    NodeIndex,
    derive_adr_decides,
    derive_all_edges,
    derive_doc_section_references_code,
    derive_feature_documented_by,
    derive_feature_has_requirement,
    derive_known_issue_affects,
    derive_requirement_has_acceptance_criterion,
    derive_test_covers_acceptance_criterion,
    derive_test_covers_requirement,
)
from tools.graphrag.types import Edge, EdgeType, Node, NodeType

pytestmark = pytest.mark.unit


# ---------- Builders ----------


def _feature(slug: str, name: str = "F") -> Node:
    return Node(
        id=f"feature:{slug}",
        node_type=NodeType.FEATURE,
        source_path=f"docs/05-features/{slug}/README.md",
        properties={"slug": slug, "name": name, "status": "proposed"},
    )


def _requirement(slug: str, req_id: str, kind: str = "functional") -> Node:
    return Node(
        id=f"req:{slug}:{req_id}",
        node_type=NodeType.REQUIREMENT,
        source_path=f"docs/05-features/{slug}/requirements.md",
        properties={"feature_slug": slug, "req_id": req_id, "kind": kind, "title": req_id, "description": "x"},
    )


def _ac(slug: str, ac_id: str, linked: list[str] | None = None) -> Node:
    return Node(
        id=f"ac:{slug}:{ac_id}",
        node_type=NodeType.ACCEPTANCE_CRITERION,
        source_path=f"docs/05-features/{slug}/test-plan.md",
        properties={
            "feature_slug": slug,
            "ac_id": ac_id,
            "title": ac_id,
            "description": "x",
            "linked_requirement_ids": linked or [],
        },
    )


def _docpage(path: str) -> Node:
    return Node(
        id=f"doc:{path.replace('/', ':')}",
        node_type=NodeType.DOC_PAGE,
        source_path=path,
        properties={"title": "T", "section_count": 0, "frontmatter": {}, "byte_size": 0},
    )


def _docsection(page_id: str, anchor: str, text: str) -> Node:
    return Node(
        id=f"{page_id}#{anchor}",
        node_type=NodeType.DOC_SECTION,
        source_path=f"{page_id}#{anchor}",
        properties={"level": 2, "heading": anchor, "text": text, "anchor": anchor, "page_id": page_id},
    )


def _codefile(path: str) -> Node:
    return Node(
        id=f"code:{path}",
        node_type=NodeType.CODE_FILE,
        source_path=path,
        properties={"language": "python", "loc": 10, "function_count": 1, "class_count": 0, "module_name": path.removesuffix(".py").replace("/", ".")},
    )


def _function(qname: str, parent: str = "src/x.py") -> Node:
    return Node(
        id=f"fn:{qname}",
        node_type=NodeType.FUNCTION,
        source_path=parent,
        properties={"qualified_name": qname, "name": qname.rsplit(".", 1)[-1], "parent_file": parent, "is_public": True, "is_async": False, "start_line": 1, "end_line": 1, "signature": "def x()", "docstring": None, "body_hash": "h"},
    )


def _class_node(qname: str, parent: str = "src/x.py") -> Node:
    return Node(
        id=f"cls:{qname}",
        node_type=NodeType.CLASS,
        source_path=parent,
        properties={"qualified_name": qname, "name": qname.rsplit(".", 1)[-1], "parent_file": parent, "bases": [], "docstring": None, "is_public": True, "start_line": 1, "end_line": 1, "body_hash": "h", "method_names": []},
    )


def _testcase(qname: str, linked_req: list[str] | None = None, linked_ac: list[str] | None = None) -> Node:
    return Node(
        id=f"test:{qname}",
        node_type=NodeType.TEST_CASE,
        source_path="tests/test_x.py",
        properties={
            "qualified_name": qname,
            "name": qname.rsplit(".", 1)[-1],
            "parent_file": "tests/test_x.py",
            "markers": [],
            "linked_req_ids": linked_req or [],
            "linked_ac_ids": linked_ac or [],
            "docstring": None,
            "start_line": 1,
            "end_line": 1,
            "is_async": False,
        },
    )


def _adr(adr_id: str, affects: list[str] | None = None) -> Node:
    return Node(
        id=f"adr:{adr_id}",
        node_type=NodeType.ADR,
        source_path=f"docs/11-decisions/{adr_id}-x.md",
        properties={"adr_id": adr_id, "title": adr_id, "status": "accepted", "date": "2026-05-20", "decision_summary": "x", "affects_modules": affects or []},
    )


def _known_issue(slug: str, ki_id: str) -> Node:
    return Node(
        id=f"ki:{slug}:{ki_id}",
        node_type=NodeType.KNOWN_ISSUE,
        source_path=f"docs/05-features/{slug}/known-issues.md",
        properties={"ki_id": ki_id, "feature_slug": slug, "severity": "med", "category": "x", "description": "x", "workaround": "", "resolution_plan": ""},
    )


def _edges_for(edges: list[Edge], edge_type: EdgeType) -> list[Edge]:
    return [e for e in edges if e.edge_type == edge_type]


# ---------- NodeIndex ----------


def test_node_index_builds_lookups() -> None:
    nodes = [
        _feature("s1"),
        _requirement("s1", "FR-1.1"),
        _ac("s1", "AC-1", linked=["FR-1.1"]),
        _docpage("docs/01-core/x.md"),
        _codefile("src/x.py"),
    ]
    idx = NodeIndex.build(nodes)
    assert idx.features_by_slug["s1"].id == "feature:s1"
    assert idx.requirements_by_feature["s1"]["FR-1.1"].properties["req_id"] == "FR-1.1"
    assert idx.acs_by_feature["s1"]["AC-1"].properties["ac_id"] == "AC-1"
    assert idx.code_files_by_path["src/x.py"].id == "code:src/x.py"


# ---------- FEATURE_HAS_REQUIREMENT ----------


def test_feature_has_requirement() -> None:
    nodes = [_feature("s1"), _requirement("s1", "FR-1.1"), _requirement("s1", "FR-1.2")]
    edges = list(derive_feature_has_requirement(NodeIndex.build(nodes)))
    assert len(edges) == 2
    assert all(e.from_node_id == "feature:s1" for e in edges)


def test_feature_has_requirement_skips_orphan_requirements() -> None:
    nodes = [_requirement("missing-slice", "FR-1")]  # no Feature with this slug
    edges = list(derive_feature_has_requirement(NodeIndex.build(nodes)))
    assert edges == []


# ---------- REQUIREMENT_HAS_ACCEPTANCE_CRITERION ----------


def test_requirement_has_acceptance_criterion() -> None:
    nodes = [
        _requirement("s1", "FR-1.1"),
        _requirement("s1", "FR-2.3"),
        _ac("s1", "AC-1", linked=["FR-1.1"]),
        _ac("s1", "AC-2", linked=["FR-1.1", "FR-2.3"]),
        _ac("s1", "AC-3", linked=[]),
    ]
    edges = list(derive_requirement_has_acceptance_criterion(NodeIndex.build(nodes)))
    # AC-1 -> FR-1.1, AC-2 -> FR-1.1 + FR-2.3 = 3 edges total
    assert len(edges) == 3
    by_from = {e.from_node_id for e in edges}
    assert by_from == {"req:s1:FR-1.1", "req:s1:FR-2.3"}


def test_requirement_has_acceptance_criterion_skips_unknown_fr() -> None:
    nodes = [_requirement("s1", "FR-1"), _ac("s1", "AC-1", linked=["FR-1", "FR-NOPE"])]
    edges = list(derive_requirement_has_acceptance_criterion(NodeIndex.build(nodes)))
    assert len(edges) == 1


# ---------- FEATURE_DOCUMENTED_BY ----------


def test_feature_documented_by() -> None:
    nodes = [
        _feature("s1"),
        _docpage("docs/05-features/s1/README.md"),
        _docpage("docs/05-features/s1/plan.md"),
        _docpage("docs/05-features/s2/README.md"),  # different slice
        _docpage("docs/01-core/product-vision.md"),  # not a slice doc
    ]
    edges = list(derive_feature_documented_by(NodeIndex.build(nodes)))
    assert len(edges) == 2
    assert all(e.from_node_id == "feature:s1" for e in edges)


# ---------- TEST_COVERS_REQUIREMENT ----------


def test_test_covers_requirement() -> None:
    nodes = [
        _requirement("s1", "FR-1.1"),
        _requirement("s1", "FR-2.3"),
        _testcase("tests.test_x.test_a", linked_req=["FR-1.1", "FR-2.3"]),
        _testcase("tests.test_x.test_b", linked_req=["FR-NOPE"]),
    ]
    edges = list(derive_test_covers_requirement(NodeIndex.build(nodes)))
    assert len(edges) == 2  # test_a → 2 reqs; test_b → nothing
    assert all(e.from_node_id == "test:tests.test_x.test_a" for e in edges)


# ---------- TEST_COVERS_ACCEPTANCE_CRITERION ----------


def test_test_covers_acceptance_criterion() -> None:
    nodes = [
        _ac("s1", "AC-1"),
        _ac("s1", "AC-2"),
        _testcase("tests.test_x.test_a", linked_ac=["AC-1", "AC-2", "AC-99"]),
    ]
    edges = list(derive_test_covers_acceptance_criterion(NodeIndex.build(nodes)))
    assert len(edges) == 2


# ---------- DOC_SECTION_REFERENCES_CODE ----------


def test_doc_section_references_code_finds_path_in_backticks() -> None:
    nodes = [
        _codefile("src/gateway/api.py"),
        _docsection("doc:docs:01-core:x.md", "intro", "See `src/gateway/api.py` for details."),
    ]
    edges = list(derive_doc_section_references_code(NodeIndex.build(nodes)))
    assert len(edges) == 1
    assert edges[0].to_node_id == "code:src/gateway/api.py"


def test_doc_section_references_code_finds_qualified_name() -> None:
    nodes = [
        _function("src.gateway.api.LLMClient.complete"),
        _class_node("src.gateway.api.LLMClient"),
        _docsection(
            "doc:docs:04-architecture:tech-stack.md",
            "gateway",
            "The `LLMClient` ABC owns lint enforcement; `src.gateway.api.LLMClient.complete` is the entry point.",
        ),
    ]
    edges = list(derive_doc_section_references_code(NodeIndex.build(nodes)))
    qnames = {e.to_node_id for e in edges}
    assert "fn:src.gateway.api.LLMClient.complete" in qnames
    # Bare `LLMClient` (short name) is NOT matched — only qualified names. The test
    # ensures we don't accidentally over-match.
    assert "cls:src.gateway.api.LLMClient" not in qnames


def test_doc_section_references_code_dedupes_repeated_references() -> None:
    nodes = [
        _codefile("src/x.py"),
        _docsection("doc:p", "s", "See `src/x.py` and also `src/x.py` again."),
    ]
    edges = list(derive_doc_section_references_code(NodeIndex.build(nodes)))
    assert len(edges) == 1


def test_doc_section_references_code_strips_parens() -> None:
    nodes = [
        _function("src.x.foo"),
        _docsection("doc:p", "s", "Call `src.x.foo()` to get started."),
    ]
    edges = list(derive_doc_section_references_code(NodeIndex.build(nodes)))
    assert len(edges) == 1
    assert edges[0].to_node_id == "fn:src.x.foo"


# ---------- ADR_DECIDES ----------


def test_adr_decides() -> None:
    nodes = [
        _codefile("src/gateway/api.py"),
        _codefile("src/conflict/resolver.py"),
        _adr("ADR-011", affects=["src/gateway/api.py", "src/conflict/resolver.py", "src/missing.py"]),
    ]
    edges = list(derive_adr_decides(NodeIndex.build(nodes)))
    assert len(edges) == 2  # missing.py skipped
    targets = {e.to_node_id for e in edges}
    assert targets == {"code:src/gateway/api.py", "code:src/conflict/resolver.py"}


# ---------- KNOWN_ISSUE_AFFECTS ----------


def test_known_issue_affects_links_to_feature() -> None:
    nodes = [
        _feature("s1"),
        _known_issue("s1", "KI-001"),
        _known_issue("s1", "KI-002"),
        _known_issue("s-missing", "KI-003"),  # orphan
    ]
    edges = list(derive_known_issue_affects(NodeIndex.build(nodes)))
    assert len(edges) == 2
    assert all(e.to_node_id == "feature:s1" for e in edges)


# ---------- derive_all_edges ----------


def test_derive_all_edges_composes_rules_deterministically() -> None:
    nodes = [
        _feature("s1"),
        _requirement("s1", "FR-1.1"),
        _ac("s1", "AC-1", linked=["FR-1.1"]),
        _docpage("docs/05-features/s1/README.md"),
        _codefile("src/x.py"),
        _adr("ADR-001", affects=["src/x.py"]),
    ]
    a = derive_all_edges(nodes)
    b = derive_all_edges(nodes)
    assert [(e.id, e.edge_type) for e in a] == [(e.id, e.edge_type) for e in b]
    types = {e.edge_type for e in a}
    assert EdgeType.FEATURE_HAS_REQUIREMENT in types
    assert EdgeType.REQUIREMENT_HAS_ACCEPTANCE_CRITERION in types
    assert EdgeType.FEATURE_DOCUMENTED_BY in types
    assert EdgeType.ADR_DECIDES in types


def test_edge_ids_are_unique() -> None:
    nodes = [
        _feature("s1"),
        _requirement("s1", "FR-1"),
        _requirement("s1", "FR-2"),
    ]
    edges = derive_all_edges(nodes)
    ids = [e.id for e in edges]
    assert len(ids) == len(set(ids))
