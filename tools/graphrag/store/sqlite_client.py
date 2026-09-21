"""SQLite-backed `GraphClient` — V1 minimum viable store.

Schema lives in `_SCHEMA_SQL`. WAL mode for concurrent reads. Properties stored as JSON.
Snapshots tracked separately so `list_snapshots()` is cheap. FTS5 virtual table indexes node
searchable text for BM25-ranked retrieval (`search_text()`).

HNSW vector index is deferred to Phase 3.5 (separate concern; the V1 product-engine bake-off
decides which engine wins, then we plug HNSW + Tantivy sidecars).
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import orjson

from tools.graphrag.store.client import EdgeQuery, NodeQuery, Snapshot
from tools.graphrag.types import Edge, EdgeType, Node, NodeType

_SCHEMA_SQL = """
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;
PRAGMA synchronous = NORMAL;

CREATE TABLE IF NOT EXISTS node (
    id              TEXT PRIMARY KEY,
    node_type       TEXT NOT NULL,
    source_path     TEXT,
    content_hash    TEXT,
    properties_json TEXT NOT NULL,
    snapshot_id     TEXT NOT NULL,
    created_at      TEXT NOT NULL,
    last_seen_at    TEXT NOT NULL,
    last_modified_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_node_type ON node(node_type);
CREATE INDEX IF NOT EXISTS idx_node_source_path ON node(source_path);
CREATE INDEX IF NOT EXISTS idx_node_snapshot ON node(snapshot_id);

CREATE TABLE IF NOT EXISTS edge (
    id              TEXT PRIMARY KEY,
    edge_type       TEXT NOT NULL,
    from_node_id    TEXT NOT NULL,
    to_node_id      TEXT NOT NULL,
    properties_json TEXT NOT NULL,
    snapshot_id     TEXT NOT NULL,
    created_at      TEXT NOT NULL,
    last_seen_at    TEXT NOT NULL,
    last_modified_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_edge_type ON edge(edge_type);
CREATE INDEX IF NOT EXISTS idx_edge_from ON edge(from_node_id);
CREATE INDEX IF NOT EXISTS idx_edge_to ON edge(to_node_id);
CREATE INDEX IF NOT EXISTS idx_edge_snapshot ON edge(snapshot_id);

CREATE TABLE IF NOT EXISTS snapshot (
    snapshot_id  TEXT PRIMARY KEY,
    commit_sha   TEXT,
    files_indexed INTEGER NOT NULL,
    nodes_total  INTEGER NOT NULL,
    edges_total  INTEGER NOT NULL,
    created_at   TEXT NOT NULL,
    notes        TEXT NOT NULL DEFAULT ''
);

CREATE VIRTUAL TABLE IF NOT EXISTS node_fts USING fts5(
    node_id UNINDEXED,
    node_type UNINDEXED,
    text,
    tokenize = 'porter unicode61'
);
"""


_SEARCHABLE_KEYS: tuple[str, ...] = (
    "name",
    "title",
    "heading",
    "qualified_name",
    "text",
    "description",
    "docstring",
    "signature",
    "decision_summary",
    "purpose",
    "key",
    "module_name",
    "adr_id",
    "req_id",
    "ac_id",
    "ki_id",
    "pack_name",
)


def _utcnow_iso() -> str:
    return datetime.now(UTC).isoformat()


def _from_iso(s: str) -> datetime:
    return datetime.fromisoformat(s)


def _props_to_json(properties: dict[str, object]) -> str:
    return orjson.dumps(properties, default=str).decode("utf-8")


def _json_to_props(s: str) -> dict[str, object]:
    data = orjson.loads(s)
    return dict(data) if isinstance(data, dict) else {}


def extract_searchable_text(node: Node) -> str:
    """Concatenate node properties that are useful for text retrieval."""

    parts: list[str] = [node.id, node.node_type.value]
    if node.source_path:
        parts.append(node.source_path)
    for key in _SEARCHABLE_KEYS:
        value = node.properties.get(key)
        if isinstance(value, str) and value:
            parts.append(value)
        elif isinstance(value, list):
            parts.extend(str(item) for item in value if isinstance(item, (str, int, float)))
    return " ".join(parts)


@dataclass(frozen=True)
class SearchHit:
    """A BM25-ranked search result. `score` is FTS5 bm25 — *lower is better*."""

    node: Node
    score: float
    snippet: str


class SQLiteGraphClient:
    """File-backed `GraphClient` impl. Use `Path(":memory:")` for tests."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self._conn = sqlite3.connect(str(db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA_SQL)
        self._conn.commit()

    # ----- core writes -----

    def upsert_node(self, node: Node, snapshot_id: str) -> None:
        now = _utcnow_iso()
        existing = self._conn.execute(
            "SELECT created_at, content_hash, last_modified_at FROM node WHERE id = ?",
            (node.id,),
        ).fetchone()
        created_at = existing["created_at"] if existing is not None else now
        modified_at = now
        if existing is not None and existing["content_hash"] == node.content_hash:
            modified_at = existing["last_modified_at"]

        self._conn.execute(
            """
            INSERT INTO node(id, node_type, source_path, content_hash, properties_json,
                             snapshot_id, created_at, last_seen_at, last_modified_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                node_type = excluded.node_type,
                source_path = excluded.source_path,
                content_hash = excluded.content_hash,
                properties_json = excluded.properties_json,
                snapshot_id = excluded.snapshot_id,
                last_seen_at = excluded.last_seen_at,
                last_modified_at = excluded.last_modified_at
            """,
            (
                node.id,
                node.node_type.value,
                node.source_path,
                node.content_hash,
                _props_to_json(node.properties),
                snapshot_id,
                created_at,
                now,
                modified_at,
            ),
        )

        # Maintain the FTS index: delete-then-insert keeps it consistent on every upsert.
        self._conn.execute("DELETE FROM node_fts WHERE node_id = ?", (node.id,))
        self._conn.execute(
            "INSERT INTO node_fts(node_id, node_type, text) VALUES (?, ?, ?)",
            (node.id, node.node_type.value, extract_searchable_text(node)),
        )

    def upsert_edge(self, edge: Edge, snapshot_id: str) -> None:
        now = _utcnow_iso()
        existing = self._conn.execute(
            "SELECT created_at FROM edge WHERE id = ?", (edge.id,)
        ).fetchone()
        created_at = existing["created_at"] if existing is not None else now
        self._conn.execute(
            """
            INSERT INTO edge(id, edge_type, from_node_id, to_node_id, properties_json,
                             snapshot_id, created_at, last_seen_at, last_modified_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                edge_type = excluded.edge_type,
                from_node_id = excluded.from_node_id,
                to_node_id = excluded.to_node_id,
                properties_json = excluded.properties_json,
                snapshot_id = excluded.snapshot_id,
                last_seen_at = excluded.last_seen_at
            """,
            (
                edge.id,
                edge.edge_type.value,
                edge.from_node_id,
                edge.to_node_id,
                _props_to_json(edge.properties),
                snapshot_id,
                created_at,
                now,
                now,
            ),
        )

    def upsert_nodes(self, nodes: Iterable[Node], snapshot_id: str) -> int:
        count = 0
        for node in nodes:
            self.upsert_node(node, snapshot_id)
            count += 1
        self._conn.commit()
        return count

    def upsert_edges(self, edges: Iterable[Edge], snapshot_id: str) -> int:
        count = 0
        for edge in edges:
            self.upsert_edge(edge, snapshot_id)
            count += 1
        self._conn.commit()
        return count

    # ----- core reads -----

    def get_node(self, node_id: str) -> Node | None:
        row = self._conn.execute("SELECT * FROM node WHERE id = ?", (node_id,)).fetchone()
        return _row_to_node(row) if row else None

    def get_edge(self, edge_id: str) -> Edge | None:
        row = self._conn.execute("SELECT * FROM edge WHERE id = ?", (edge_id,)).fetchone()
        return _row_to_edge(row) if row else None

    def query_nodes(self, query: NodeQuery) -> list[Node]:
        sql = "SELECT * FROM node WHERE 1=1"
        params: list[object] = []
        if query.node_type is not None:
            sql += " AND node_type = ?"
            params.append(query.node_type.value)
        if query.node_types:
            placeholders = ",".join("?" * len(query.node_types))
            sql += f" AND node_type IN ({placeholders})"
            params.extend(nt.value for nt in query.node_types)
        if query.source_path_prefix is not None:
            sql += " AND source_path LIKE ? || '%'"
            params.append(query.source_path_prefix)
        if query.source_path_exact is not None:
            sql += " AND source_path = ?"
            params.append(query.source_path_exact)
        if query.content_hash is not None:
            sql += " AND content_hash = ?"
            params.append(query.content_hash)
        if query.snapshot_id is not None:
            sql += " AND snapshot_id = ?"
            params.append(query.snapshot_id)
        sql += " ORDER BY id"
        if query.limit is not None:
            sql += " LIMIT ?"
            params.append(query.limit)
        rows = self._conn.execute(sql, params).fetchall()
        return [_row_to_node(r) for r in rows]

    def query_edges(self, query: EdgeQuery) -> list[Edge]:
        sql = "SELECT * FROM edge WHERE 1=1"
        params: list[object] = []
        if query.edge_type is not None:
            sql += " AND edge_type = ?"
            params.append(query.edge_type.value)
        if query.edge_types:
            placeholders = ",".join("?" * len(query.edge_types))
            sql += f" AND edge_type IN ({placeholders})"
            params.extend(et.value for et in query.edge_types)
        if query.from_node_id is not None:
            sql += " AND from_node_id = ?"
            params.append(query.from_node_id)
        if query.to_node_id is not None:
            sql += " AND to_node_id = ?"
            params.append(query.to_node_id)
        if query.snapshot_id is not None:
            sql += " AND snapshot_id = ?"
            params.append(query.snapshot_id)
        sql += " ORDER BY id"
        if query.limit is not None:
            sql += " LIMIT ?"
            params.append(query.limit)
        rows = self._conn.execute(sql, params).fetchall()
        return [_row_to_edge(r) for r in rows]

    # ----- search -----

    def search_text(
        self,
        query: str,
        *,
        node_types: tuple[NodeType, ...] = (),
        limit: int = 20,
    ) -> list[SearchHit]:
        """BM25-ranked text search over the FTS5 index.

        `query` is passed to FTS5 directly; callers should escape special tokens if accepting
        untrusted input. Returns `SearchHit` objects with `node`, `score` (lower = better), and
        a short FTS5 snippet.
        """

        sql_parts = [
            "SELECT n.*, bm25(node_fts) AS rank, "
            "       snippet(node_fts, 2, '<<', '>>', '…', 16) AS snip ",
            "FROM node_fts ",
            "JOIN node n ON n.id = node_fts.node_id ",
            "WHERE node_fts MATCH ? ",
        ]
        params: list[object] = [query]
        if node_types:
            placeholders = ",".join("?" * len(node_types))
            sql_parts.append(f"AND node_fts.node_type IN ({placeholders}) ")
            params.extend(nt.value for nt in node_types)
        sql_parts.append("ORDER BY rank LIMIT ?")
        params.append(limit)
        rows = self._conn.execute("".join(sql_parts), params).fetchall()
        hits: list[SearchHit] = []
        for row in rows:
            node = _row_to_node(row)
            hits.append(SearchHit(node=node, score=float(row["rank"]), snippet=row["snip"]))
        return hits

    # ----- snapshots -----

    def list_snapshots(self) -> list[Snapshot]:
        rows = self._conn.execute(
            "SELECT * FROM snapshot ORDER BY created_at DESC"
        ).fetchall()
        return [_row_to_snapshot(r) for r in rows]

    def record_snapshot(self, snapshot: Snapshot) -> None:
        self._conn.execute(
            """
            INSERT INTO snapshot(snapshot_id, commit_sha, files_indexed,
                                 nodes_total, edges_total, created_at, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(snapshot_id) DO UPDATE SET
                commit_sha = excluded.commit_sha,
                files_indexed = excluded.files_indexed,
                nodes_total = excluded.nodes_total,
                edges_total = excluded.edges_total,
                notes = excluded.notes
            """,
            (
                snapshot.snapshot_id,
                snapshot.commit_sha,
                snapshot.files_indexed,
                snapshot.nodes_total,
                snapshot.edges_total,
                snapshot.created_at.isoformat(),
                snapshot.notes,
            ),
        )
        self._conn.commit()

    def latest_snapshot(self) -> Snapshot | None:
        row = self._conn.execute(
            "SELECT * FROM snapshot ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
        return _row_to_snapshot(row) if row else None

    def delete_snapshot(self, snapshot_id: str) -> None:
        self._conn.execute(
            "DELETE FROM node_fts WHERE node_id IN (SELECT id FROM node WHERE snapshot_id = ?)",
            (snapshot_id,),
        )
        self._conn.execute("DELETE FROM edge WHERE snapshot_id = ?", (snapshot_id,))
        self._conn.execute("DELETE FROM node WHERE snapshot_id = ?", (snapshot_id,))
        self._conn.execute("DELETE FROM snapshot WHERE snapshot_id = ?", (snapshot_id,))
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()


def _row_to_node(row: sqlite3.Row) -> Node:
    return Node(
        id=row["id"],
        node_type=NodeType(row["node_type"]),
        source_path=row["source_path"],
        content_hash=row["content_hash"],
        properties=_json_to_props(row["properties_json"]),
        snapshot_id=row["snapshot_id"],
        created_at=_from_iso(row["created_at"]),
        last_seen_at=_from_iso(row["last_seen_at"]),
        last_modified_at=_from_iso(row["last_modified_at"]),
    )


def _row_to_edge(row: sqlite3.Row) -> Edge:
    return Edge(
        id=row["id"],
        edge_type=EdgeType(row["edge_type"]),
        from_node_id=row["from_node_id"],
        to_node_id=row["to_node_id"],
        properties=_json_to_props(row["properties_json"]),
        snapshot_id=row["snapshot_id"],
        created_at=_from_iso(row["created_at"]),
        last_seen_at=_from_iso(row["last_seen_at"]),
        last_modified_at=_from_iso(row["last_modified_at"]),
    )


def _row_to_snapshot(row: sqlite3.Row) -> Snapshot:
    return Snapshot(
        snapshot_id=row["snapshot_id"],
        commit_sha=row["commit_sha"],
        files_indexed=row["files_indexed"],
        nodes_total=row["nodes_total"],
        edges_total=row["edges_total"],
        created_at=_from_iso(row["created_at"]),
        notes=row["notes"],
    )


_ = Any  # re-exported for the dataclass slot above; keeps mypy quiet on optional Any imports
