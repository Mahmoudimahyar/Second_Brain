"""WP3.1 / GAP-053 — bitemporal `supersede_edge` (ADR-005, non-negotiable #3).

A supersede atomically closes the prior edge version (`t_ingest_to = at`) and
opens the new one (`t_ingest_from = at`) at the same instant, so a bitemporal
`as_of` query replays the value the graph believed at any past time.
"""

from __future__ import annotations

import string
from datetime import UTC, datetime
from pathlib import Path

import pytest
from freezegun import freeze_time
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from src.graph.client import Edge, Node
from src.graph.kuzu_client import KuzuGraphClient
from src.retrieval.api import _edge_passes_filters


def _utc(y: int, m: int, d: int) -> datetime:
    return datetime(y, m, d, tzinfo=UTC)


def _client_ab(tmp_path: Path) -> KuzuGraphClient:
    g = KuzuGraphClient(db_path=tmp_path / "kuzu.db")
    g.upsert_node(Node(id="a", label="Post", source_tier="L5"))
    g.upsert_node(Node(id="b", label="School", source_tier="L1"))
    return g


def _visible(edge: Edge, as_of: datetime) -> bool:
    return _edge_passes_filters(
        edge, source_tier_min=None, time_range=None,
        as_of=as_of, include_anomalies=True,
    )


def test_supersede_closes_prior_opens_new(tmp_path: Path) -> None:
    g = _client_ab(tmp_path)
    t0, at = _utc(2024, 1, 1), _utc(2024, 6, 1)
    g.upsert_edge(Edge(id="e_v1", label="TUITION", from_id="a", to_id="b",
                       source_tier="L5", rank="normal", t_ingest_from=t0,
                       references=["src_2023"], confidence=0.5))
    g.supersede_edge(
        Edge(id="e_v2", label="TUITION", from_id="a", to_id="b",
             source_tier="L5", rank="normal", references=["src_2024"], confidence=0.9),
        at=at, prior_edge_id="e_v1",
    )
    by_id = {e.id: e for e in g.edges_of_type("TUITION")}
    assert by_id["e_v1"].t_ingest_to == at      # prior closed at `at`
    assert by_id["e_v2"].t_ingest_from == at    # new opened at `at`
    assert by_id["e_v2"].t_ingest_to is None    # new still open
    g.close()


def test_as_of_replay_invariant(tmp_path: Path) -> None:
    g = _client_ab(tmp_path)
    t0, at = _utc(2024, 1, 1), _utc(2024, 6, 1)
    g.upsert_edge(Edge(id="e_v1", label="TUITION", from_id="a", to_id="b",
                       source_tier="L5", rank="normal", t_ingest_from=t0,
                       references=["src_2023"]))
    g.supersede_edge(
        Edge(id="e_v2", label="TUITION", from_id="a", to_id="b",
             source_tier="L5", rank="normal", references=["src_2024"]),
        at=at, prior_edge_id="e_v1",
    )
    by_id = {e.id: e for e in g.edges_of_type("TUITION")}
    before, after = _utc(2024, 3, 1), _utc(2024, 9, 1)

    # Before the supersede instant: only the prior version is visible.
    assert _visible(by_id["e_v1"], before) is True
    assert _visible(by_id["e_v2"], before) is False
    # At/after: only the new version is visible.
    assert _visible(by_id["e_v1"], after) is False
    assert _visible(by_id["e_v2"], after) is True
    g.close()


def test_supersede_at_frozen_now(tmp_path: Path) -> None:
    g = _client_ab(tmp_path)
    g.upsert_edge(Edge(id="e_v1", label="POLICY", from_id="a", to_id="b",
                       source_tier="L5", rank="normal", t_ingest_from=_utc(2023, 1, 1)))
    with freeze_time("2025-02-02T00:00:00+00:00"):
        now = datetime.now(tz=UTC)
        g.supersede_edge(
            Edge(id="e_v2", label="POLICY", from_id="a", to_id="b",
                 source_tier="L5", rank="normal"),
            at=now, prior_edge_id="e_v1",
        )
    by_id = {e.id: e for e in g.edges_of_type("POLICY")}
    assert by_id["e_v1"].t_ingest_to == datetime(2025, 2, 2, tzinfo=UTC)
    assert by_id["e_v2"].t_ingest_from == datetime(2025, 2, 2, tzinfo=UTC)
    g.close()


@pytest.fixture
def graph_ab(tmp_path: Path) -> KuzuGraphClient:
    g = _client_ab(tmp_path)
    yield g
    g.close()


@settings(
    max_examples=15,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    label=st.text(alphabet=string.ascii_uppercase, min_size=4, max_size=10),
    k=st.integers(min_value=1, max_value=4),
)
def test_supersede_chain_keeps_one_open(
    graph_ab: KuzuGraphClient, label: str, k: int
) -> None:
    graph_ab.upsert_edge(Edge(id=f"{label}:v0", label=label, from_id="a", to_id="b",
                              source_tier="L5", rank="normal", t_ingest_from=_utc(2024, 1, 1)))
    for i in range(1, k + 1):
        graph_ab.supersede_edge(
            Edge(id=f"{label}:v{i}", label=label, from_id="a", to_id="b",
                 source_tier="L5", rank="normal"),
            at=_utc(2024, 1, 1 + i),  # label-based close of the current open version
        )
    assert graph_ab.edge_count(label=label) == k + 1
    open_edges = [e for e in graph_ab.edges_of_type(label) if e.t_ingest_to is None]
    assert len(open_edges) == 1
    assert open_edges[0].id == f"{label}:v{k}"
