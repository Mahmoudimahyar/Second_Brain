"""Tests for V1.5b Phase 3 — level-filter selectors (ADR-012)."""

from __future__ import annotations

from src.retrieval.level_filters import (
    LEVEL_A_EDGE_TYPES,
    LEVEL_A_NODE_TYPES,
    LEVEL_B_EDGE_TYPES,
    LEVEL_B_NODE_TYPES,
    LEVEL_C_EDGE_TYPES,
    LEVEL_C_NODE_TYPES,
    edge_types_for,
    is_edge_visible_at_level,
    is_node_visible_at_level,
    node_types_for,
)


def test_level_a_includes_structural_node_types() -> None:
    expected = {"User", "Post", "Comment", "Thread", "Subreddit"}
    assert expected <= LEVEL_A_NODE_TYPES


def test_level_a_excludes_pass4_derived() -> None:
    """Level A is pure Pass-1 — no Claim / Cluster / Conflict."""
    forbidden = {"Claim", "Cluster", "Conflict", "Topic"}
    assert not (forbidden & LEVEL_A_NODE_TYPES)


def test_level_b_focuses_on_clusters_only() -> None:
    assert {"Topic", "Cluster"} == LEVEL_B_NODE_TYPES


def test_level_b_edges_are_cluster_edges() -> None:
    assert {"IN_CLUSTER", "REFERENCES_TOPIC"} == LEVEL_B_EDGE_TYPES


def test_level_c_is_superset() -> None:
    """Level C is the full graph — A ⊆ C and B ⊆ C."""
    assert LEVEL_A_NODE_TYPES <= LEVEL_C_NODE_TYPES
    assert LEVEL_B_NODE_TYPES <= LEVEL_C_NODE_TYPES
    assert LEVEL_A_EDGE_TYPES <= LEVEL_C_EDGE_TYPES
    assert LEVEL_B_EDGE_TYPES <= LEVEL_C_EDGE_TYPES


def test_level_c_includes_same_as_edge() -> None:
    """V1.5a cross-graph edges live at Level C."""
    assert "SAME_AS" in LEVEL_C_EDGE_TYPES


def test_node_visibility_predicates() -> None:
    assert is_node_visible_at_level("User", "A")
    assert not is_node_visible_at_level("Claim", "A")
    assert is_node_visible_at_level("Cluster", "B")
    assert not is_node_visible_at_level("User", "B")
    assert is_node_visible_at_level("Claim", "C")


def test_edge_visibility_predicates() -> None:
    assert is_edge_visible_at_level("AUTHORED", "A")
    assert not is_edge_visible_at_level("SUPPORTS", "A")
    assert is_edge_visible_at_level("IN_CLUSTER", "B")
    assert is_edge_visible_at_level("SAME_AS", "C")


def test_selectors_return_frozenset() -> None:
    assert isinstance(node_types_for("A"), frozenset)
    assert isinstance(edge_types_for("C"), frozenset)


def test_no_pass4_edges_at_level_a() -> None:
    """SUPPORTS / CONTRADICTS / MENTIONS_METRIC are Pass-4 derivations."""
    forbidden = {"SUPPORTS", "CONTRADICTS", "MENTIONS_METRIC"}
    assert not (forbidden & LEVEL_A_EDGE_TYPES)
