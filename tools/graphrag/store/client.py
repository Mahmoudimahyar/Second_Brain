"""`GraphClient` Protocol for the repo MCP context server.

Concrete implementations (SQLite, LadybugDB, Postgres+AGE, Neo4j) all implement the same surface.
V1 ships with `SQLiteGraphClient` since the bake-off (ADR-001) hasn't run yet — once it does,
the chosen V1-product-engine driver can be reused here.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

from tools.graphrag.types import Edge, EdgeType, Node, NodeType


@dataclass(frozen=True)
class Snapshot:
    """Identifies one indexing-run. `snapshot_id` is `sha256(commit_sha + sorted-content-hashes)`."""

    snapshot_id: str
    commit_sha: str | None
    files_indexed: int
    nodes_total: int
    edges_total: int
    created_at: datetime
    notes: str = ""


@dataclass(frozen=False)
class NodeQuery:
    """Filter spec for `GraphClient.query_nodes()`. All filters are AND-combined."""

    node_type: NodeType | None = None
    node_types: tuple[NodeType, ...] = field(default_factory=tuple)
    source_path_prefix: str | None = None
    source_path_exact: str | None = None
    content_hash: str | None = None
    snapshot_id: str | None = None
    limit: int | None = None


@dataclass(frozen=False)
class EdgeQuery:
    """Filter spec for `GraphClient.query_edges()`."""

    edge_type: EdgeType | None = None
    edge_types: tuple[EdgeType, ...] = field(default_factory=tuple)
    from_node_id: str | None = None
    to_node_id: str | None = None
    snapshot_id: str | None = None
    limit: int | None = None


class GraphClient(Protocol):
    """Storage surface. Pure CRUD; no business logic."""

    def upsert_node(self, node: Node, snapshot_id: str) -> None: ...

    def upsert_edge(self, edge: Edge, snapshot_id: str) -> None: ...

    def upsert_nodes(self, nodes: Iterable[Node], snapshot_id: str) -> int: ...

    def upsert_edges(self, edges: Iterable[Edge], snapshot_id: str) -> int: ...

    def get_node(self, node_id: str) -> Node | None: ...

    def get_edge(self, edge_id: str) -> Edge | None: ...

    def query_nodes(self, query: NodeQuery) -> list[Node]: ...

    def query_edges(self, query: EdgeQuery) -> list[Edge]: ...

    def list_snapshots(self) -> list[Snapshot]: ...

    def record_snapshot(self, snapshot: Snapshot) -> None: ...

    def latest_snapshot(self) -> Snapshot | None: ...

    def delete_snapshot(self, snapshot_id: str) -> None: ...

    def close(self) -> None: ...
