from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal, Protocol

SourceTier = Literal["L1", "L2", "L3", "L4", "L5"]
Rank = Literal["preferred", "normal", "deprecated"]


@dataclass(frozen=True)
class Node:
    """V1 graph node. Property conventions per `docs/05-features/01.../data.md`."""

    id: str
    label: str            # node-type label, e.g. "School", "Post", "Comment"
    source_tier: SourceTier
    properties: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Edge:
    """V1 graph edge with full property convention + bitemporal 4-tuple."""

    id: str
    label: str            # relation, e.g. "AUTHORED", "MENTIONS_SCHOOL"
    from_id: str
    to_id: str
    source_tier: SourceTier
    rank: Rank
    references: list[str] = field(default_factory=list)
    qualifiers: dict[str, Any] = field(default_factory=dict)
    t_valid_from: datetime | None = None
    t_valid_to: datetime | None = None
    t_ingest_from: datetime | None = None
    t_ingest_to: datetime | None = None
    confidence: float = 1.0


class GraphClient(Protocol):
    """V1 graph-store Protocol per `docs/04-architecture/module-boundaries.md`.

    The concrete driver picked by ADR-001 (Kùzu) implements this; other modules
    depend only on the Protocol so a future engine swap is contained.
    """

    def init_schema(self) -> None: ...
    def upsert_node(self, node: Node) -> None: ...
    def upsert_edge(self, edge: Edge) -> None: ...
    def upsert_nodes(self, nodes: Iterable[Node]) -> int: ...
    def upsert_edges(self, edges: Iterable[Edge]) -> int: ...
    def supersede_edge(
        self, new_edge: Edge, *, at: datetime, prior_edge_id: str | None = None,
    ) -> None: ...
    def get_node(self, node_id: str) -> Node | None: ...
    def neighbors(
        self, node_id: str, *, relation: str | None = None,
        direction: Literal["out", "in", "both"] = "out",
    ) -> list[tuple[Edge, Node]]: ...
    def node_count(self, *, label: str | None = None) -> int: ...
    def edge_count(self, *, label: str | None = None) -> int: ...
    def close(self) -> None: ...
