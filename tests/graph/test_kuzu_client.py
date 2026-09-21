"""Tests for `src.graph.kuzu_client.KuzuGraphClient` (ADR-001)."""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime
from pathlib import Path

import pytest

from src.graph.client import Edge, Node
from src.graph.kuzu_client import KuzuGraphClient


def _make_client(tmp_path: Path) -> KuzuGraphClient:
    return KuzuGraphClient(db_path=tmp_path / "kuzu.db")


def _utc(year: int, month: int, day: int) -> datetime:
    return datetime(year, month, day, tzinfo=UTC)


def test_init_schema_is_idempotent(tmp_path: Path) -> None:
    c1 = _make_client(tmp_path)
    c1.init_schema()
    c1.init_schema()
    assert c1.node_count() == 0
    c1.close()


def test_upsert_node_then_get(tmp_path: Path) -> None:
    c = _make_client(tmp_path)

    c.upsert_node(Node(
        id="school:nyu_dental",
        label="School",
        source_tier="L1",
        properties={"canonical_name": "NYU College of Dentistry", "state": "NY"},
    ))
    fetched = c.get_node("school:nyu_dental")

    assert fetched is not None
    assert fetched.id == "school:nyu_dental"
    assert fetched.label == "School"
    assert fetched.source_tier == "L1"
    assert fetched.properties["canonical_name"] == "NYU College of Dentistry"
    assert fetched.properties["state"] == "NY"
    c.close()


def test_upsert_node_is_idempotent(tmp_path: Path) -> None:
    c = _make_client(tmp_path)

    node = Node(id="x", label="Post", source_tier="L5", properties={"score": 1})
    c.upsert_node(node)
    c.upsert_node(node)

    assert c.node_count() == 1
    c.close()


def test_get_node_returns_none_for_missing(tmp_path: Path) -> None:
    c = _make_client(tmp_path)
    assert c.get_node("nonexistent") is None
    c.close()


def test_upsert_node_updates_properties_on_repeat(tmp_path: Path) -> None:
    c = _make_client(tmp_path)
    c.upsert_node(Node(id="x", label="Post", source_tier="L5", properties={"v": 1}))
    c.upsert_node(Node(id="x", label="Post", source_tier="L5", properties={"v": 2}))
    fetched = c.get_node("x")
    assert fetched is not None
    assert fetched.properties["v"] == 2
    c.close()


def test_upsert_nodes_batch_returns_count(tmp_path: Path) -> None:
    c = _make_client(tmp_path)
    nodes = [
        Node(id=f"n{i}", label="Post", source_tier="L5", properties={"i": i})
        for i in range(5)
    ]
    count = c.upsert_nodes(nodes)
    assert count == 5
    assert c.node_count() == 5
    c.close()


def test_upsert_edge_then_neighbors(tmp_path: Path) -> None:
    c = _make_client(tmp_path)
    c.upsert_node(Node(
        id="reddit:DentalSchool:alice", label="User", source_tier="L5", properties={},
    ))
    c.upsert_node(Node(
        id="reddit_post:abc", label="Post", source_tier="L5", properties={},
    ))

    c.upsert_edge(Edge(
        id="e1",
        label="AUTHORED",
        from_id="reddit:DentalSchool:alice",
        to_id="reddit_post:abc",
        source_tier="L5",
        rank="normal",
        references=["reddit_post:abc"],
        t_valid_from=_utc(2020, 1, 1),
        t_ingest_from=_utc(2026, 1, 1),
    ))

    neighbors = c.neighbors("reddit:DentalSchool:alice", direction="out")
    assert len(neighbors) == 1
    edge, target = neighbors[0]
    assert edge.label == "AUTHORED"
    assert edge.rank == "normal"
    assert edge.references == ["reddit_post:abc"]
    assert edge.t_valid_from == _utc(2020, 1, 1)
    assert target.id == "reddit_post:abc"
    c.close()


def test_neighbors_filtered_by_relation(tmp_path: Path) -> None:
    c = _make_client(tmp_path)
    c.upsert_node(Node(id="u", label="User", source_tier="L5", properties={}))
    c.upsert_node(Node(id="p", label="Post", source_tier="L5", properties={}))
    c.upsert_node(Node(id="t", label="Topic", source_tier="L5", properties={}))

    c.upsert_edge(Edge(
        id="e1", label="AUTHORED", from_id="u", to_id="p",
        source_tier="L5", rank="normal",
        t_valid_from=_utc(2020, 1, 1), t_ingest_from=_utc(2026, 1, 1),
    ))
    c.upsert_edge(Edge(
        id="e2", label="REFERENCES_TOPIC", from_id="u", to_id="t",
        source_tier="L5", rank="normal",
        t_valid_from=_utc(2020, 1, 1), t_ingest_from=_utc(2026, 1, 1),
    ))

    authored = c.neighbors("u", relation="AUTHORED")
    refs = c.neighbors("u", relation="REFERENCES_TOPIC")
    assert len(authored) == 1
    assert authored[0][1].id == "p"
    assert len(refs) == 1
    assert refs[0][1].id == "t"
    c.close()


def test_neighbors_direction_in(tmp_path: Path) -> None:
    c = _make_client(tmp_path)
    c.upsert_node(Node(id="u", label="User", source_tier="L5", properties={}))
    c.upsert_node(Node(id="p", label="Post", source_tier="L5", properties={}))
    c.upsert_edge(Edge(
        id="e1", label="AUTHORED", from_id="u", to_id="p",
        source_tier="L5", rank="normal",
        t_valid_from=_utc(2020, 1, 1), t_ingest_from=_utc(2026, 1, 1),
    ))

    incoming = c.neighbors("p", direction="in")
    assert len(incoming) == 1
    _, source = incoming[0]
    assert source.id == "u"
    c.close()


def test_edge_count_by_label(tmp_path: Path) -> None:
    c = _make_client(tmp_path)
    c.upsert_node(Node(id="a", label="User", source_tier="L5", properties={}))
    c.upsert_node(Node(id="b", label="Post", source_tier="L5", properties={}))
    c.upsert_node(Node(id="c", label="Topic", source_tier="L5", properties={}))
    c.upsert_edge(Edge(id="e1", label="AUTHORED", from_id="a", to_id="b",
                       source_tier="L5", rank="normal",
                       t_valid_from=_utc(2020,1,1), t_ingest_from=_utc(2026,1,1)))
    c.upsert_edge(Edge(id="e2", label="AUTHORED", from_id="a", to_id="c",
                       source_tier="L5", rank="normal",
                       t_valid_from=_utc(2020,1,1), t_ingest_from=_utc(2026,1,1)))
    c.upsert_edge(Edge(id="e3", label="REFERENCES_TOPIC", from_id="a", to_id="c",
                       source_tier="L5", rank="normal",
                       t_valid_from=_utc(2020,1,1), t_ingest_from=_utc(2026,1,1)))

    assert c.edge_count() == 3
    assert c.edge_count(label="AUTHORED") == 2
    assert c.edge_count(label="REFERENCES_TOPIC") == 1
    c.close()


def test_node_count_by_label(tmp_path: Path) -> None:
    c = _make_client(tmp_path)
    c.upsert_node(Node(id="s1", label="School", source_tier="L1", properties={}))
    c.upsert_node(Node(id="s2", label="School", source_tier="L1", properties={}))
    c.upsert_node(Node(id="p1", label="Post", source_tier="L5", properties={}))
    assert c.node_count(label="School") == 2
    assert c.node_count(label="Post") == 1
    assert c.node_count() == 3
    c.close()


def test_edge_preserves_bitemporal_tuple_and_confidence(tmp_path: Path) -> None:
    c = _make_client(tmp_path)
    c.upsert_node(Node(id="a", label="Post", source_tier="L5", properties={}))
    c.upsert_node(Node(id="b", label="School", source_tier="L1", properties={}))

    c.upsert_edge(Edge(
        id="e1", label="MENTIONS_SCHOOL", from_id="a", to_id="b",
        source_tier="L5", rank="normal",
        references=["post:abc"], qualifiers={"span": [10, 14]},
        t_valid_from=_utc(2020, 6, 15),
        t_valid_to=_utc(2021, 6, 15),
        t_ingest_from=_utc(2026, 5, 21),
        confidence=0.87,
    ))

    out = c.neighbors("a")
    edge, _ = out[0]
    assert edge.t_valid_from == _utc(2020, 6, 15)
    assert edge.t_valid_to == _utc(2021, 6, 15)
    assert edge.t_ingest_from == _utc(2026, 5, 21)
    assert edge.t_ingest_to is None
    assert edge.qualifiers == {"span": [10, 14]}
    assert edge.references == ["post:abc"]
    assert edge.confidence == pytest.approx(0.87)
    c.close()


def test_dataclass_node_edge_are_frozen() -> None:
    n = Node(id="x", label="Post", source_tier="L5", properties={})
    with pytest.raises(dataclasses.FrozenInstanceError):
        n.label = "Other"  # type: ignore[misc]

    e = Edge(
        id="e", label="AUTHORED", from_id="a", to_id="b",
        source_tier="L5", rank="normal",
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        e.confidence = 0.5  # type: ignore[misc]
