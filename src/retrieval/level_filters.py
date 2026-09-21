"""V1.5b Phase 3 — level-specific subgraph filters (ADR-012).

Three retrieval contracts on top of the V1 graph store:

- **Level A — structural**: User / Post / Comment / Thread / Subreddit nodes
  + Pass-1 edges (AUTHORED / REPLIED_TO / BELONGS_TO_THREAD / POSTED_IN_FORUM
  / UPVOTED). Deterministic Pass-1 output. NO Pass-2/3/4 derived data.
- **Level B — clusters**: Topic + Cluster nodes + IN_CLUSTER /
  REFERENCES_TOPIC edges. Aggregation layer with sample post counts.
- **Level C — analyzed**: full V1 graph including Pass-4 extractions +
  conflict-resolved claims + V1.5a cross-graph SAME_AS edges.

The level segmentation is implemented as named subgraph selectors rather
than separate stores — same Kùzu graph, different filter functions.
"""

from __future__ import annotations

from typing import Literal

GraphLevel = Literal["A", "B", "C"]


# ----------------------------------------------------------------------
# Node-type sets per level
# ----------------------------------------------------------------------


LEVEL_A_NODE_TYPES: frozenset[str] = frozenset({
    "User", "Post", "Comment", "Thread", "Subreddit", "SDNCategory",
})

LEVEL_B_NODE_TYPES: frozenset[str] = frozenset({
    "Topic", "Cluster",
})

# Level C is open — every node type. Listed explicitly for clarity.
LEVEL_C_NODE_TYPES: frozenset[str] = frozenset({
    "User", "Post", "Comment", "Thread", "Subreddit", "SDNCategory",
    "School", "Program", "Metric", "CycleYear", "SchoolAttribute",
    "Topic", "Cluster", "Claim", "InterviewQuestion", "Conflict",
    "ResearchNeed", "L1Document", "L2Document", "Alias",
    "UnresolvedEntity", "HITLItem", "Dump",
})


# ----------------------------------------------------------------------
# Edge-type sets per level
# ----------------------------------------------------------------------


LEVEL_A_EDGE_TYPES: frozenset[str] = frozenset({
    "AUTHORED", "COMMENTED", "REPLIED_TO",
    "BELONGS_TO_THREAD", "POSTED_IN_FORUM", "UPVOTED",
    "MENTIONS_SCHOOL",     # Pass-1 deterministic; kept for cross-reference
    "MENTIONS_PROGRAM",    # same
})

LEVEL_B_EDGE_TYPES: frozenset[str] = frozenset({
    "IN_CLUSTER", "REFERENCES_TOPIC",
})

# Level C includes everything.
LEVEL_C_EDGE_TYPES: frozenset[str] = (
    LEVEL_A_EDGE_TYPES | LEVEL_B_EDGE_TYPES | frozenset({
        "MENTIONS_METRIC", "STATES_VALUE", "SUPPORTS", "CONTRADICTS",
        "HAS_ALIAS", "INVALIDATED_BY", "SCHOOL_HAS_METRIC",
        "SCHOOL_OFFERS_PROGRAM", "EMITS_RESEARCH_NEED", "PROVENANCE",
        "HITL_TARGET", "SAME_AS",
    })
)


# ----------------------------------------------------------------------
# Selectors
# ----------------------------------------------------------------------


def node_types_for(level: GraphLevel) -> frozenset[str]:
    if level == "A":
        return LEVEL_A_NODE_TYPES
    if level == "B":
        return LEVEL_B_NODE_TYPES
    return LEVEL_C_NODE_TYPES


def edge_types_for(level: GraphLevel) -> frozenset[str]:
    if level == "A":
        return LEVEL_A_EDGE_TYPES
    if level == "B":
        return LEVEL_B_EDGE_TYPES
    return LEVEL_C_EDGE_TYPES


def is_node_visible_at_level(node_type: str, level: GraphLevel) -> bool:
    return node_type in node_types_for(level)


def is_edge_visible_at_level(edge_label: str, level: GraphLevel) -> bool:
    return edge_label in edge_types_for(level)


__all__ = [
    "LEVEL_A_EDGE_TYPES",
    "LEVEL_A_NODE_TYPES",
    "LEVEL_B_EDGE_TYPES",
    "LEVEL_B_NODE_TYPES",
    "LEVEL_C_EDGE_TYPES",
    "LEVEL_C_NODE_TYPES",
    "GraphLevel",
    "edge_types_for",
    "is_edge_visible_at_level",
    "is_node_visible_at_level",
    "node_types_for",
]
