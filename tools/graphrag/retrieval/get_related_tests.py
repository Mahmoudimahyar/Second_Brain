"""`get_related_tests(target, ...)` — traverse `TEST_COVERS_*` edges to find tests."""

from __future__ import annotations

from dataclasses import dataclass

from tools.graphrag.store.client import EdgeQuery
from tools.graphrag.store.sqlite_client import SQLiteGraphClient
from tools.graphrag.types import EdgeType, Node, NodeType


@dataclass(frozen=True)
class RelatedTest:
    test_case_id: str
    qualified_name: str
    source_path: str | None
    markers: list[str]
    linked_req_ids: list[str]
    linked_ac_ids: list[str]


def _string_list_prop(node: Node, key: str) -> list[str]:
    value = node.properties.get(key, [])
    if not isinstance(value, list):
        return []
    return [str(x) for x in value if isinstance(x, str)]


def get_related_tests(
    store: SQLiteGraphClient,
    target: str,
    *,
    limit: int = 30,
) -> list[RelatedTest]:
    """Find TestCases linked to `target` (which may be a Requirement / AC / Feature / Function / CodeFile)."""

    target_node = store.get_node(target)
    if target_node is None:
        return []

    test_case_ids: set[str] = set()

    # Direct TEST_COVERS_* edges into target.
    for et in (
        EdgeType.TEST_COVERS_REQUIREMENT,
        EdgeType.TEST_COVERS_ACCEPTANCE_CRITERION,
        EdgeType.TEST_COVERS_FUNCTION,
        EdgeType.TEST_COVERS_CODE,
    ):
        for edge in store.query_edges(EdgeQuery(edge_type=et, to_node_id=target)):
            test_case_ids.add(edge.from_node_id)

    # Indirect: Feature → Requirement → TEST_COVERS_REQUIREMENT.
    if target_node.node_type == NodeType.FEATURE:
        req_edges = store.query_edges(
            EdgeQuery(edge_type=EdgeType.FEATURE_HAS_REQUIREMENT, from_node_id=target_node.id)
        )
        for req_edge in req_edges:
            for edge in store.query_edges(
                EdgeQuery(edge_type=EdgeType.TEST_COVERS_REQUIREMENT, to_node_id=req_edge.to_node_id)
            ):
                test_case_ids.add(edge.from_node_id)

    out: list[RelatedTest] = []
    for tc_id in test_case_ids:
        node = store.get_node(tc_id)
        if node is None or node.node_type != NodeType.TEST_CASE:
            continue
        out.append(
            RelatedTest(
                test_case_id=node.id,
                qualified_name=str(node.properties.get("qualified_name") or node.id),
                source_path=node.source_path,
                markers=_string_list_prop(node, "markers"),
                linked_req_ids=_string_list_prop(node, "linked_req_ids"),
                linked_ac_ids=_string_list_prop(node, "linked_ac_ids"),
            )
        )
    out.sort(key=lambda t: t.qualified_name)
    return out[:limit]
