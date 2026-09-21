"""Tests for `tools/graphrag/store/sqlite_client.py`."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from tools.graphrag.store.client import EdgeQuery, NodeQuery, Snapshot
from tools.graphrag.store.sqlite_client import SQLiteGraphClient
from tools.graphrag.types import Edge, EdgeType, Node, NodeType

pytestmark = pytest.mark.integration


@pytest.fixture
def store(tmp_path: Path) -> SQLiteGraphClient:
    db = tmp_path / "graph.db"
    client = SQLiteGraphClient(db)
    yield client
    client.close()


def _docpage(path: str) -> Node:
    return Node(
        id=f"doc:{path.replace('/', ':')}",
        node_type=NodeType.DOC_PAGE,
        source_path=path,
        content_hash="hash_" + path,
        properties={"title": "T", "section_count": 1},
    )


def _edge(eid: str, etype: EdgeType, from_id: str, to_id: str) -> Edge:
    return Edge(id=eid, edge_type=etype, from_node_id=from_id, to_node_id=to_id, properties={})


def test_upsert_and_get_node(store: SQLiteGraphClient) -> None:
    node = _docpage("docs/x.md")
    store.upsert_node(node, "snap-1")
    store._conn.commit()
    fetched = store.get_node(node.id)
    assert fetched is not None
    assert fetched.id == node.id
    assert fetched.node_type == NodeType.DOC_PAGE
    assert fetched.source_path == "docs/x.md"
    assert fetched.snapshot_id == "snap-1"
    assert fetched.properties == {"title": "T", "section_count": 1}


def test_upsert_node_idempotent(store: SQLiteGraphClient) -> None:
    node = _docpage("docs/x.md")
    store.upsert_node(node, "snap-1")
    first = store.get_node(node.id)
    store.upsert_node(node, "snap-1")
    second = store.get_node(node.id)
    assert first is not None and second is not None
    assert first.created_at == second.created_at
    assert first.last_modified_at == second.last_modified_at


def test_upsert_node_updates_on_content_change(store: SQLiteGraphClient) -> None:
    node = _docpage("docs/x.md")
    store.upsert_node(node, "snap-1")
    first = store.get_node(node.id)
    node_v2 = Node(
        id=node.id,
        node_type=node.node_type,
        source_path=node.source_path,
        content_hash="different",
        properties={"title": "T2", "section_count": 2},
    )
    store.upsert_node(node_v2, "snap-2")
    second = store.get_node(node.id)
    assert first is not None and second is not None
    assert second.content_hash == "different"
    assert second.properties["title"] == "T2"
    assert second.snapshot_id == "snap-2"
    # created_at preserved across the update
    assert first.created_at == second.created_at


def test_upsert_edge_and_get(store: SQLiteGraphClient) -> None:
    a = _docpage("docs/a.md")
    b = _docpage("docs/b.md")
    store.upsert_node(a, "snap-1")
    store.upsert_node(b, "snap-1")
    edge = _edge("e1", EdgeType.DOC_PAGE_HAS_SECTION, a.id, b.id)
    store.upsert_edge(edge, "snap-1")
    store._conn.commit()
    fetched = store.get_edge(edge.id)
    assert fetched is not None
    assert fetched.from_node_id == a.id
    assert fetched.to_node_id == b.id


def test_query_nodes_by_type(store: SQLiteGraphClient) -> None:
    store.upsert_nodes(
        [
            _docpage("docs/a.md"),
            _docpage("docs/b.md"),
            Node(
                id="cls:x.Y",
                node_type=NodeType.CLASS,
                source_path="src/x.py",
                content_hash="h",
                properties={"qualified_name": "x.Y", "name": "Y"},
            ),
        ],
        "snap-1",
    )
    pages = store.query_nodes(NodeQuery(node_type=NodeType.DOC_PAGE))
    assert len(pages) == 2
    classes = store.query_nodes(NodeQuery(node_type=NodeType.CLASS))
    assert len(classes) == 1


def test_query_nodes_by_source_path_prefix(store: SQLiteGraphClient) -> None:
    store.upsert_nodes(
        [
            _docpage("docs/05-features/s1/README.md"),
            _docpage("docs/05-features/s1/plan.md"),
            _docpage("docs/01-core/x.md"),
        ],
        "snap-1",
    )
    s1 = store.query_nodes(NodeQuery(source_path_prefix="docs/05-features/s1/"))
    assert {n.source_path for n in s1} == {
        "docs/05-features/s1/README.md",
        "docs/05-features/s1/plan.md",
    }


def test_query_edges_by_from(store: SQLiteGraphClient) -> None:
    a = _docpage("docs/a.md")
    b = _docpage("docs/b.md")
    c = _docpage("docs/c.md")
    store.upsert_nodes([a, b, c], "snap-1")
    store.upsert_edges(
        [
            _edge("e1", EdgeType.DOC_PAGE_HAS_SECTION, a.id, b.id),
            _edge("e2", EdgeType.DOC_PAGE_HAS_SECTION, a.id, c.id),
            _edge("e3", EdgeType.DOC_PAGE_HAS_SECTION, b.id, c.id),
        ],
        "snap-1",
    )
    from_a = store.query_edges(EdgeQuery(from_node_id=a.id))
    assert len(from_a) == 2


def test_snapshot_lifecycle(store: SQLiteGraphClient) -> None:
    snap = Snapshot(
        snapshot_id="snap-1",
        commit_sha="abc",
        files_indexed=10,
        nodes_total=20,
        edges_total=30,
        created_at=datetime.now(UTC),
        notes="test",
    )
    store.record_snapshot(snap)
    snaps = store.list_snapshots()
    assert len(snaps) == 1
    assert snaps[0].snapshot_id == "snap-1"
    assert snaps[0].nodes_total == 20

    latest = store.latest_snapshot()
    assert latest is not None and latest.snapshot_id == "snap-1"


def test_delete_snapshot_cascades(store: SQLiteGraphClient) -> None:
    snap = Snapshot(
        snapshot_id="snap-1",
        commit_sha="abc",
        files_indexed=1,
        nodes_total=1,
        edges_total=0,
        created_at=datetime.now(UTC),
    )
    store.record_snapshot(snap)
    store.upsert_node(_docpage("docs/x.md"), "snap-1")
    assert store.get_node("doc:docs:x.md") is not None

    store.delete_snapshot("snap-1")
    assert store.get_node("doc:docs:x.md") is None
    assert store.latest_snapshot() is None
