"""Cross-parser edge derivation.

After Phase 1 parsers emit Nodes (and intra-file structural edges), Phase 2 derives cross-file
edges by joining nodes via their properties. Each rule is a pure function that takes a
`NodeIndex` and yields `Edge` objects; no filesystem or graph-store side effects.

See `tools/graphrag/schema.md` for the full edge taxonomy. Deferred to V1.x (require cross-file
import resolution that's hard to do reliably from AST alone): `FUNCTION_CALLS_FUNCTION`,
`TEST_COVERS_FUNCTION`, `FEATURE_IMPLEMENTED_BY`.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

from tools.graphrag.types import Edge, EdgeType, Node, NodeType


@dataclass(frozen=False)
class NodeIndex:
    """Lookup tables built once and shared across all edge-derivation rules."""

    by_id: dict[str, Node] = field(default_factory=dict)
    by_type: dict[NodeType, list[Node]] = field(default_factory=lambda: defaultdict(list))

    # Type-specific lookups
    features_by_slug: dict[str, Node] = field(default_factory=dict)
    requirements_by_feature: dict[str, dict[str, Node]] = field(
        default_factory=lambda: defaultdict(dict)
    )
    acs_by_feature: dict[str, dict[str, Node]] = field(
        default_factory=lambda: defaultdict(dict)
    )
    docpages_by_path: dict[str, Node] = field(default_factory=dict)
    docsections_by_id: dict[str, Node] = field(default_factory=dict)
    code_files_by_path: dict[str, Node] = field(default_factory=dict)
    functions_by_qname: dict[str, Node] = field(default_factory=dict)
    classes_by_qname: dict[str, Node] = field(default_factory=dict)
    testcases_by_qname: dict[str, Node] = field(default_factory=dict)
    adrs_by_id: dict[str, Node] = field(default_factory=dict)

    @classmethod
    def build(cls, nodes: Iterable[Node]) -> NodeIndex:
        idx = cls()
        for node in nodes:
            idx.by_id[node.id] = node
            idx.by_type[node.node_type].append(node)
            handler = _INDEX_HANDLERS.get(node.node_type)
            if handler is not None:
                handler(idx, node)
        return idx


def _index_feature(idx: NodeIndex, node: Node) -> None:
    slug = node.properties.get("slug")
    if isinstance(slug, str):
        idx.features_by_slug[slug] = node


def _index_requirement(idx: NodeIndex, node: Node) -> None:
    slug = node.properties.get("feature_slug")
    req_id = node.properties.get("req_id")
    if isinstance(slug, str) and isinstance(req_id, str):
        idx.requirements_by_feature[slug][req_id] = node


def _index_ac(idx: NodeIndex, node: Node) -> None:
    slug = node.properties.get("feature_slug")
    ac_id = node.properties.get("ac_id")
    if isinstance(slug, str) and isinstance(ac_id, str):
        idx.acs_by_feature[slug][ac_id] = node


def _index_docpage(idx: NodeIndex, node: Node) -> None:
    if node.source_path:
        idx.docpages_by_path[node.source_path] = node


def _index_docsection(idx: NodeIndex, node: Node) -> None:
    idx.docsections_by_id[node.id] = node


def _index_codefile(idx: NodeIndex, node: Node) -> None:
    if node.source_path:
        idx.code_files_by_path[node.source_path] = node


def _index_function(idx: NodeIndex, node: Node) -> None:
    qname = node.properties.get("qualified_name")
    if isinstance(qname, str):
        idx.functions_by_qname[qname] = node


def _index_class(idx: NodeIndex, node: Node) -> None:
    qname = node.properties.get("qualified_name")
    if isinstance(qname, str):
        idx.classes_by_qname[qname] = node


def _index_testcase(idx: NodeIndex, node: Node) -> None:
    qname = node.properties.get("qualified_name")
    if isinstance(qname, str):
        idx.testcases_by_qname[qname] = node


def _index_adr(idx: NodeIndex, node: Node) -> None:
    adr_id = node.properties.get("adr_id")
    if isinstance(adr_id, str):
        idx.adrs_by_id[adr_id] = node


_INDEX_HANDLERS: dict[NodeType, Callable[[NodeIndex, Node], None]] = {
    NodeType.FEATURE: _index_feature,
    NodeType.REQUIREMENT: _index_requirement,
    NodeType.ACCEPTANCE_CRITERION: _index_ac,
    NodeType.DOC_PAGE: _index_docpage,
    NodeType.DOC_SECTION: _index_docsection,
    NodeType.CODE_FILE: _index_codefile,
    NodeType.FUNCTION: _index_function,
    NodeType.CLASS: _index_class,
    NodeType.TEST_CASE: _index_testcase,
    NodeType.ADR: _index_adr,
}


def _edge_id(edge_type: EdgeType, from_id: str, to_id: str) -> str:
    return f"edge:{edge_type.value}:{from_id}->{to_id}"


def derive_feature_has_requirement(idx: NodeIndex) -> Iterable[Edge]:
    for slug, reqs in idx.requirements_by_feature.items():
        feature = idx.features_by_slug.get(slug)
        if feature is None:
            continue
        for req in reqs.values():
            yield Edge(
                id=_edge_id(EdgeType.FEATURE_HAS_REQUIREMENT, feature.id, req.id),
                edge_type=EdgeType.FEATURE_HAS_REQUIREMENT,
                from_node_id=feature.id,
                to_node_id=req.id,
            )


def derive_requirement_has_acceptance_criterion(idx: NodeIndex) -> Iterable[Edge]:
    for slug, acs in idx.acs_by_feature.items():
        reqs_for_slug = idx.requirements_by_feature.get(slug, {})
        for ac in acs.values():
            linked = ac.properties.get("linked_requirement_ids", [])
            if not isinstance(linked, list):
                continue
            for req_id in linked:
                if not isinstance(req_id, str):
                    continue
                req = reqs_for_slug.get(req_id)
                if req is None:
                    continue
                yield Edge(
                    id=_edge_id(EdgeType.REQUIREMENT_HAS_ACCEPTANCE_CRITERION, req.id, ac.id),
                    edge_type=EdgeType.REQUIREMENT_HAS_ACCEPTANCE_CRITERION,
                    from_node_id=req.id,
                    to_node_id=ac.id,
                )


def derive_feature_documented_by(idx: NodeIndex) -> Iterable[Edge]:
    for slug, feature in idx.features_by_slug.items():
        prefix = f"docs/05-features/{slug}/"
        for path, page in idx.docpages_by_path.items():
            if path.startswith(prefix):
                yield Edge(
                    id=_edge_id(EdgeType.FEATURE_DOCUMENTED_BY, feature.id, page.id),
                    edge_type=EdgeType.FEATURE_DOCUMENTED_BY,
                    from_node_id=feature.id,
                    to_node_id=page.id,
                )


def derive_test_covers_requirement(idx: NodeIndex) -> Iterable[Edge]:
    # Build a flat lookup: req_id -> [Requirement nodes]. Different slices may reuse the same
    # FR-N.M id; we link to all matches.
    flat: dict[str, list[Node]] = defaultdict(list)
    for slug_reqs in idx.requirements_by_feature.values():
        for req_id, req in slug_reqs.items():
            flat[req_id].append(req)

    for case in idx.by_type.get(NodeType.TEST_CASE, []):
        linked = case.properties.get("linked_req_ids", [])
        if not isinstance(linked, list):
            continue
        for req_id in linked:
            if not isinstance(req_id, str):
                continue
            for req in flat.get(req_id, []):
                yield Edge(
                    id=_edge_id(EdgeType.TEST_COVERS_REQUIREMENT, case.id, req.id),
                    edge_type=EdgeType.TEST_COVERS_REQUIREMENT,
                    from_node_id=case.id,
                    to_node_id=req.id,
                )


def derive_test_covers_acceptance_criterion(idx: NodeIndex) -> Iterable[Edge]:
    flat: dict[str, list[Node]] = defaultdict(list)
    for slug_acs in idx.acs_by_feature.values():
        for ac_id, ac in slug_acs.items():
            flat[ac_id].append(ac)

    for case in idx.by_type.get(NodeType.TEST_CASE, []):
        linked = case.properties.get("linked_ac_ids", [])
        if not isinstance(linked, list):
            continue
        for ac_id in linked:
            if not isinstance(ac_id, str):
                continue
            for ac in flat.get(ac_id, []):
                yield Edge(
                    id=_edge_id(EdgeType.TEST_COVERS_ACCEPTANCE_CRITERION, case.id, ac.id),
                    edge_type=EdgeType.TEST_COVERS_ACCEPTANCE_CRITERION,
                    from_node_id=case.id,
                    to_node_id=ac.id,
                )


_BACKTICK_TOKEN_RE = re.compile(r"`([^`\n]+?)`")


def derive_doc_section_references_code(idx: NodeIndex) -> Iterable[Edge]:
    """Scan DocSection text for backtick-wrapped paths or qualified names matching known code nodes."""

    yielded: set[tuple[str, str]] = set()
    for section in idx.docsections_by_id.values():
        text = section.properties.get("text", "")
        if not isinstance(text, str):
            continue
        for match in _BACKTICK_TOKEN_RE.finditer(text):
            token = match.group(1).strip()
            target = _resolve_code_token(idx, token)
            if target is None:
                continue
            key = (section.id, target.id)
            if key in yielded:
                continue
            yielded.add(key)
            yield Edge(
                id=_edge_id(EdgeType.DOC_SECTION_REFERENCES_CODE, section.id, target.id),
                edge_type=EdgeType.DOC_SECTION_REFERENCES_CODE,
                from_node_id=section.id,
                to_node_id=target.id,
            )


def _resolve_code_token(idx: NodeIndex, token: str) -> Node | None:
    """Look up a backtick-wrapped token against code-file paths, function qnames, and class qnames."""

    cleaned = token.split("(", 1)[0].strip()
    if not cleaned:
        return None
    if cleaned in idx.code_files_by_path:
        return idx.code_files_by_path[cleaned]
    if cleaned in idx.functions_by_qname:
        return idx.functions_by_qname[cleaned]
    if cleaned in idx.classes_by_qname:
        return idx.classes_by_qname[cleaned]
    return None


def derive_adr_decides(idx: NodeIndex) -> Iterable[Edge]:
    for adr in idx.by_type.get(NodeType.ADR, []):
        modules = adr.properties.get("affects_modules", [])
        if not isinstance(modules, list):
            continue
        for path in modules:
            if not isinstance(path, str):
                continue
            target = idx.code_files_by_path.get(path)
            if target is None:
                continue
            yield Edge(
                id=_edge_id(EdgeType.ADR_DECIDES, adr.id, target.id),
                edge_type=EdgeType.ADR_DECIDES,
                from_node_id=adr.id,
                to_node_id=target.id,
            )


def derive_known_issue_affects(idx: NodeIndex) -> Iterable[Edge]:
    """V1: link KnownIssue → Feature via `feature_slug`. Symbol-level scanning is V1.x."""

    for ki in idx.by_type.get(NodeType.KNOWN_ISSUE, []):
        slug = ki.properties.get("feature_slug")
        if not isinstance(slug, str):
            continue
        feature = idx.features_by_slug.get(slug)
        if feature is None:
            continue
        yield Edge(
            id=_edge_id(EdgeType.KNOWN_ISSUE_AFFECTS, ki.id, feature.id),
            edge_type=EdgeType.KNOWN_ISSUE_AFFECTS,
            from_node_id=ki.id,
            to_node_id=feature.id,
        )


DERIVERS = (
    derive_feature_has_requirement,
    derive_requirement_has_acceptance_criterion,
    derive_feature_documented_by,
    derive_test_covers_requirement,
    derive_test_covers_acceptance_criterion,
    derive_doc_section_references_code,
    derive_adr_decides,
    derive_known_issue_affects,
)


def derive_all_edges(nodes: Iterable[Node]) -> list[Edge]:
    """Run every derivation rule against a freshly-built `NodeIndex`. Deterministic order."""

    idx = NodeIndex.build(nodes)
    edges: list[Edge] = []
    for fn in DERIVERS:
        edges.extend(fn(idx))
    return edges
