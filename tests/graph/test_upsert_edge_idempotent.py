"""WP2.2 — `upsert_edge` is idempotent (MERGE, not CREATE).

round1-failure.md noted `upsert_edge` was a plain CREATE, so a re-run after a
crash duplicated every edge instead of healing. It now MERGEs on `edge_id`, so
re-ingesting the same edge updates in place.
"""

from __future__ import annotations

import string
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from src.graph.client import Edge, Node
from src.graph.kuzu_client import KuzuGraphClient


def _client_with_ab(tmp_path: Path) -> KuzuGraphClient:
    g = KuzuGraphClient(db_path=tmp_path / "kuzu.db")
    g.upsert_node(Node(id="a", label="Post", source_tier="L5"))
    g.upsert_node(Node(id="b", label="Post", source_tier="L5"))
    return g


def test_upsert_edge_idempotent_deterministic(tmp_path: Path) -> None:
    g = _client_with_ab(tmp_path)
    e = Edge(id="e1", label="AUTHORED", from_id="a", to_id="b",
             source_tier="L5", rank="normal")
    g.upsert_edge(e)
    g.upsert_edge(e)
    g.upsert_edge(e)
    assert g.edge_count() == 1
    g.close()


def test_upsert_edge_updates_properties_on_repeat(tmp_path: Path) -> None:
    g = _client_with_ab(tmp_path)
    g.upsert_edge(Edge(id="e1", label="AUTHORED", from_id="a", to_id="b",
                       source_tier="L5", rank="normal", confidence=0.5))
    g.upsert_edge(Edge(id="e1", label="AUTHORED", from_id="a", to_id="b",
                       source_tier="L5", rank="normal", confidence=0.9))
    assert g.edge_count() == 1
    (stored,) = g.edges_of_type("AUTHORED")
    assert abs(stored.confidence - 0.9) < 1e-6
    g.close()


@pytest.fixture
def graph_ab(tmp_path: Path) -> KuzuGraphClient:
    g = _client_with_ab(tmp_path)
    yield g
    g.close()


@settings(
    max_examples=30,
    deadline=None,
    # Intentional: the db fixture is shared across examples; each example uses a
    # unique `label` (and thus edge_id), so examples don't interfere.
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    label=st.text(alphabet=string.ascii_uppercase, min_size=4, max_size=10),
    tier=st.sampled_from(["L1", "L2", "L5"]),
    conf=st.floats(min_value=0.0, max_value=1.0),
    times=st.integers(min_value=1, max_value=4),
)
def test_upsert_edge_idempotent_property(
    graph_ab: KuzuGraphClient, label: str, tier: str, conf: float, times: int
) -> None:
    # `label` is the unique discriminator for this example (edge_id derives from
    # it); counting by label isolates the example even though the fixture db is
    # shared across Hypothesis examples.
    edge = Edge(id=f"e:{label}", label=label, from_id="a", to_id="b",
                source_tier=tier, rank="normal", confidence=conf)  # type: ignore[arg-type]
    for _ in range(times):
        graph_ab.upsert_edge(edge)
    assert graph_ab.edge_count(label=label) == 1
    (stored,) = graph_ab.edges_of_type(label)
    assert stored.id == f"e:{label}"
    assert stored.source_tier == tier
    assert abs(stored.confidence - conf) < 1e-6
