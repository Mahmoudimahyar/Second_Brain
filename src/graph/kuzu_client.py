from __future__ import annotations

import csv
import json
import os
from collections.abc import Iterable
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Any, Literal, cast

import kuzu

from src.graph.client import Edge, Node
from src.shared.timestamps import from_iso, to_iso


def _loads_or(raw: Any, fallback: str) -> Any:
    """Parse a JSON column value, tolerating a NULL / empty / corrupt string
    (e.g. a node partially written before an unclean process kill) by returning
    the parsed fallback — so one bad row can't crash a whole-graph scan."""
    if not raw:
        return json.loads(fallback)
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError, ValueError):
        return json.loads(fallback)


class KuzuGraphClient:
    """V1 graph-store implementation on Kùzu (ADR-001).

    Schema:
      Node(id STRING PK, label STRING, source_tier STRING, properties_json STRING)
      Edge(FROM Node TO Node, label STRING, source_tier STRING, rank STRING,
           references_json STRING, qualifiers_json STRING,
           t_valid_from STRING, t_valid_to STRING,
           t_ingest_from STRING, t_ingest_to STRING,
           confidence DOUBLE)

    The single-node-table design keeps the schema flat — node `label` is a
    property, not a table name. Trade-off: Kùzu's columnar storage is less
    efficient per-label than per-label tables (we measured ~2.5ms 3-hop p95
    on 28K nodes in the bake-off; single-table will be slower but well
    within the < 250ms V1 threshold per NFR-1).

    Property conventions on every node + edge per `data.md`. Bitemporal
    4-tuple stored as ISO strings on edges.
    """

    def __init__(self, db_path: Path, *, database: Any | None = None) -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        # Kùzu takes an exclusive file lock per Database handle, so two handles
        # on one file in one process fail ("Could not set lock"). `database`
        # lets co-resident consumers (e.g. the web app's ask agent + graph
        # routes) share ONE handle while each client keeps its own Connection
        # (Connections are per-thread-safe; the Database is shareable).
        self._owns_db = database is None
        if database is not None:
            self._db = database
        else:
            # Kùzu defaults its buffer pool to ~80% of system RAM; on a
            # small-RAM host (e.g. a 16 GB cloud VM) that, plus the in-memory
            # dump load, OOM-kills the process. SECBRAIN_KUZU_BUFFER_POOL_BYTES
            # caps it (unset/0 = Kùzu's default, unchanged on big-RAM hosts).
            _bp = int(os.environ.get("SECBRAIN_KUZU_BUFFER_POOL_BYTES", "0") or "0")
            self._db = (
                kuzu.Database(str(self._db_path), buffer_pool_size=_bp)
                if _bp > 0
                else kuzu.Database(str(self._db_path))
            )
        self._conn = kuzu.Connection(self._db)
        self.init_schema()

    def init_schema(self) -> None:
        self._conn.execute(
            "CREATE NODE TABLE IF NOT EXISTS Node ("
            "id STRING, label STRING, source_tier STRING, "
            "properties_json STRING, PRIMARY KEY(id))"
        )
        self._conn.execute(
            "CREATE REL TABLE IF NOT EXISTS Edge ("
            "FROM Node TO Node, "
            "edge_id STRING, label STRING, source_tier STRING, "
            "rank STRING, references_json STRING, qualifiers_json STRING, "
            "t_valid_from STRING, t_valid_to STRING, "
            "t_ingest_from STRING, t_ingest_to STRING, "
            "confidence DOUBLE)"
        )

    def upsert_node(self, node: Node) -> None:
        self._conn.execute(
            "MERGE (n:Node {id: $id}) "
            "SET n.label = $label, n.source_tier = $source_tier, "
            "n.properties_json = $properties_json",
            parameters={
                "id": node.id,
                "label": node.label,
                "source_tier": node.source_tier,
                "properties_json": json.dumps(_jsonable(node.properties)),
            },
        )

    def upsert_nodes(self, nodes: Iterable[Node]) -> int:
        # Batch into ONE UNWIND statement, not one auto-commit transaction per
        # node. Per-row writes made Kùzu accumulate ~95 MB / 1000 nodes of
        # transaction overhead that CHECKPOINT never freed -> OOM on large ingests.
        rows = [
            {
                "id": n.id,
                "label": n.label,
                "source_tier": n.source_tier,
                "properties_json": json.dumps(_jsonable(n.properties)),
            }
            for n in nodes
        ]
        if not rows:
            return 0
        self._conn.execute(
            "UNWIND $rows AS r "
            "MERGE (n:Node {id: r.id}) "
            "SET n.label = r.label, n.source_tier = r.source_tier, "
            "n.properties_json = r.properties_json",
            parameters={"rows": rows},
        )
        return len(rows)

    def upsert_edge(self, edge: Edge) -> None:
        params: dict[str, Any] = {
            "from_id": edge.from_id,
            "to_id": edge.to_id,
            "edge_id": edge.id,
            "label": edge.label,
            "source_tier": edge.source_tier,
            "rank": edge.rank,
            "references_json": json.dumps(list(edge.references)),
            "qualifiers_json": json.dumps(_jsonable(edge.qualifiers)),
            "t_valid_from": _iso_or_empty(edge.t_valid_from),
            "t_valid_to": _iso_or_empty(edge.t_valid_to),
            "t_ingest_from": _iso_or_empty(edge.t_ingest_from),
            "t_ingest_to": _iso_or_empty(edge.t_ingest_to),
            "confidence": float(edge.confidence),
        }
        # Idempotent by edge_id (GAP-053 / round1-failure): MERGE so a re-run
        # after a crash heals rather than duplicating. MERGE matches an existing
        # Edge with this edge_id between (a, b) or creates one; SET then writes
        # the current property values. (Bitemporal *supersede* — opening a new
        # version while closing the prior t_ingest_to — is a separate operation,
        # WP3.1.)
        self._conn.execute(
            "MATCH (a:Node {id: $from_id}), (b:Node {id: $to_id}) "
            "MERGE (a)-[r:Edge {edge_id: $edge_id}]->(b) "
            "SET r.label = $label, r.source_tier = $source_tier, r.rank = $rank, "
            "r.references_json = $references_json, "
            "r.qualifiers_json = $qualifiers_json, "
            "r.t_valid_from = $t_valid_from, r.t_valid_to = $t_valid_to, "
            "r.t_ingest_from = $t_ingest_from, r.t_ingest_to = $t_ingest_to, "
            "r.confidence = $confidence",
            parameters=params,
        )

    def upsert_edges(self, edges: Iterable[Edge]) -> int:
        # Batch into ONE UNWIND statement (see upsert_nodes — avoids the
        # per-transaction memory growth that OOM'd large ingests).
        rows = [
            {
                "from_id": e.from_id,
                "to_id": e.to_id,
                "edge_id": e.id,
                "label": e.label,
                "source_tier": e.source_tier,
                "rank": e.rank,
                "references_json": json.dumps(list(e.references)),
                "qualifiers_json": json.dumps(_jsonable(e.qualifiers)),
                "t_valid_from": _iso_or_empty(e.t_valid_from),
                "t_valid_to": _iso_or_empty(e.t_valid_to),
                "t_ingest_from": _iso_or_empty(e.t_ingest_from),
                "t_ingest_to": _iso_or_empty(e.t_ingest_to),
                "confidence": float(e.confidence),
            }
            for e in edges
        ]
        if not rows:
            return 0
        # CREATE, not MERGE: MERGE on an edge checks existence by SCANNING (Kùzu
        # can't index a rel property like edge_id), which is O(graph) per edge ->
        # O(n^2) over the ingest (edge upsert hit 64 s/batch at 75k nodes, vs
        # 1.6 s early). Idempotency is instead provided at the POST level by the
        # L5 checkpoint (already-ingested posts are skipped), so a fresh ingest
        # writes each edge exactly once. (Relaxes the per-edge MERGE of GAP-053;
        # a mid-batch-crash resume could duplicate edges — acceptable given the
        # checkpoint, and far better than an ingest that can't finish.)
        self._conn.execute(
            "UNWIND $rows AS r "
            "MATCH (a:Node {id: r.from_id}), (b:Node {id: r.to_id}) "
            "CREATE (a)-[:Edge {edge_id: r.edge_id, label: r.label, "
            "source_tier: r.source_tier, rank: r.rank, "
            "references_json: r.references_json, qualifiers_json: r.qualifiers_json, "
            "t_valid_from: r.t_valid_from, t_valid_to: r.t_valid_to, "
            "t_ingest_from: r.t_ingest_from, t_ingest_to: r.t_ingest_to, "
            "confidence: r.confidence}]->(b)",
            parameters={"rows": rows},
        )
        return len(rows)

    def copy_edges_from_csv(self, csv_path: str) -> None:
        """Bulk-load edges from a headerless CSV whose columns are, in order:
        from_id, to_id, edge_id, label, source_tier, rank, references_json,
        qualifiers_json, t_valid_from, t_valid_to, t_ingest_from, t_ingest_to,
        confidence (see module-level `edge_csv_row`). Kùzu builds the CSR in ONE
        pass — linear (~400k edges/s), vs the O(n^2) of incremental edge inserts.
        Appends to the Edge table, so it composes with prior (e.g. L1) writes."""
        # Kùzu's COPY parser treats backslashes as escapes; use forward slashes so
        # a Windows path (C:\...) doesn't break the statement (no-op on POSIX).
        safe = str(csv_path).replace("\\", "/")
        self._conn.execute(f"COPY Edge FROM '{safe}' (HEADER=false)")

    def copy_edges(self, edges: Iterable[Edge]) -> int:
        """Bulk-write `edges` via a staged CSV → COPY — the scalable write-back
        path, vs incremental `upsert_edges`.

        Incremental edge CREATE on a large graph is not just O(n^2) in Kùzu's CSR
        storage; it pulls the existing endpoint node-groups' CSR regions into the
        buffer pool to append, so it OOMs ("buffer pool is full") writing even a
        few hundred edges onto the 1.46M-edge V1 graph. COPY builds the CSR in one
        linear pass and sidesteps both. Returns the number of edges written.

        Stages to a temp CSV beside the db (Kùzu infers the format from the .csv
        extension). The caller MUST have already upserted the edges' endpoint
        nodes — COPY aborts on a dangling FROM/TO primary key; this checkpoints
        first so freshly-upserted endpoints are visible to that PK lookup."""
        rows = [edge_csv_row(e) for e in edges]
        if not rows:
            return 0
        self.checkpoint()   # flush pending endpoint-node writes for COPY's PK lookup
        stage = str(self._db_path) + ".edgecopy.csv"
        with open(stage, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerows(rows)
        self.copy_edges_from_csv(stage)
        self.checkpoint()
        return len(rows)

    def supersede_edge(
        self,
        new_edge: Edge,
        *,
        at: datetime,
        prior_edge_id: str | None = None,
    ) -> None:
        """Atomically close the prior edge version and open `new_edge` (GAP-053,
        ADR-005, non-negotiable #3).

        Sets the prior edge's ``t_ingest_to = at`` and writes ``new_edge`` with
        ``t_ingest_from = at`` — both at the **same instant** ``at``, in one
        transaction. A bitemporal ``query_graph(..., as_of=t)`` then returns the
        prior value for ``t < at`` and the new value for ``t >= at``.

        The prior edge is the one with ``prior_edge_id`` when given; otherwise
        every currently-open edge (``t_ingest_to`` empty) sharing
        ``new_edge``'s (from_id, to_id, label) is closed. ``new_edge`` MUST carry
        a fresh ``id`` distinct from the prior version (each version is its own
        edge row).
        """

        at_iso = to_iso(at)
        self._conn.execute("BEGIN TRANSACTION")
        try:
            if prior_edge_id is not None:
                self._conn.execute(
                    "MATCH (a:Node {id: $from_id})-[r:Edge {edge_id: $prior}]->"
                    "(b:Node {id: $to_id}) SET r.t_ingest_to = $at",
                    parameters={
                        "from_id": new_edge.from_id, "to_id": new_edge.to_id,
                        "prior": prior_edge_id, "at": at_iso,
                    },
                )
            else:
                self._conn.execute(
                    "MATCH (a:Node {id: $from_id})-[r:Edge {label: $label}]->"
                    "(b:Node {id: $to_id}) "
                    "WHERE r.t_ingest_to = '' AND r.edge_id <> $new_id "
                    "SET r.t_ingest_to = $at",
                    parameters={
                        "from_id": new_edge.from_id, "to_id": new_edge.to_id,
                        "label": new_edge.label, "new_id": new_edge.id, "at": at_iso,
                    },
                )
            self.upsert_edge(replace(new_edge, t_ingest_from=at))
            self._conn.execute("COMMIT")
        except Exception:
            self._conn.execute("ROLLBACK")
            raise

    def get_node(self, node_id: str) -> Node | None:
        result = self._conn.execute(
            "MATCH (n:Node {id: $id}) "
            "RETURN n.id, n.label, n.source_tier, n.properties_json",
            parameters={"id": node_id},
        )
        result = _expect_one_result(result)
        if not result.has_next():
            return None
        row = result.get_next()
        properties_raw = row[3] or "{}"
        return Node(
            id=str(row[0]),
            label=str(row[1]),
            source_tier=cast(Any, row[2]),
            properties=json.loads(properties_raw),
        )

    def neighbors(
        self,
        node_id: str,
        *,
        relation: str | None = None,
        direction: Literal["out", "in", "both"] = "out",
    ) -> list[tuple[Edge, Node]]:
        if direction == "out":
            pattern = "(a:Node {id: $id})-[r:Edge]->(b:Node)"
        elif direction == "in":
            pattern = "(b:Node)-[r:Edge]->(a:Node {id: $id})"
        else:
            pattern = "(a:Node {id: $id})-[r:Edge]-(b:Node)"
        params: dict[str, Any] = {"id": node_id}
        clause = ""
        if relation is not None:
            clause = "WHERE r.label = $relation "
            params["relation"] = relation
        result = self._conn.execute(
            f"MATCH {pattern} {clause}"
            "RETURN b.id, b.label, b.source_tier, b.properties_json, "
            "r.edge_id, r.label, r.source_tier, r.rank, "
            "r.references_json, r.qualifiers_json, "
            "r.t_valid_from, r.t_valid_to, r.t_ingest_from, r.t_ingest_to, "
            "r.confidence, a.id",
            parameters=params,
        )
        result = _expect_one_result(result)
        out: list[tuple[Edge, Node]] = []
        while result.has_next():
            row = result.get_next()
            other = Node(
                id=str(row[0]),
                label=str(row[1]),
                source_tier=cast(Any, row[2]),
                properties=_loads_or(row[3], "{}"),
            )
            from_id = node_id if direction != "in" else str(row[15])
            to_id = str(row[0]) if direction != "in" else node_id
            edge = Edge(
                id=str(row[4]),
                label=str(row[5]),
                from_id=from_id,
                to_id=to_id,
                source_tier=cast(Any, row[6]),
                rank=cast(Any, row[7]),
                references=_loads_or(row[8], "[]"),
                qualifiers=_loads_or(row[9], "{}"),
                t_valid_from=_iso_or_none(row[10]),
                t_valid_to=_iso_or_none(row[11]),
                t_ingest_from=_iso_or_none(row[12]),
                t_ingest_to=_iso_or_none(row[13]),
                confidence=float(row[14]) if row[14] is not None else 1.0,
            )
            out.append((edge, other))
        return out

    def nodes_of_label(self, label: str, *, limit: int = 10_000) -> list[Node]:
        """V1.5c W1-3 — return every node with `n.label = ?`.

        Used by per-team data loaders to read Pass-4 outputs
        (``SentimentAnnotation``, ``InterviewQuestion``, ``Claim``) out
        of the graph. Bounded by ``limit`` to keep memory predictable on
        large corpora; raise the cap when V1.6 indexing lands.
        """

        result = self._conn.execute(
            "MATCH (n:Node) WHERE n.label = $label "
            "RETURN n.id, n.label, n.source_tier, n.properties_json LIMIT $cap",
            parameters={"label": label, "cap": int(limit)},
        )
        result = _expect_one_result(result)
        out: list[Node] = []
        while result.has_next():
            row = result.get_next()
            out.append(Node(
                id=str(row[0]),
                label=str(row[1]),
                source_tier=cast(Any, row[2]),
                properties=_loads_or(row[3], "{}"),
            ))
        return out

    def node_ids_of_label(self, label: str) -> set[str]:
        """Every node id with ``n.label = label`` — UNCAPPED. Returns ids only
        (not full Node objects), so it stays memory-light on large corpora. The
        L5 reconcile uses this: it must see ALL Posts, or a LIMIT would make it
        treat real, persisted posts as 'phantom' and wrongly drop them."""
        result = self._conn.execute(
            "MATCH (n:Node {label: $label}) RETURN n.id",
            parameters={"label": label},
        )
        result = _expect_one_result(result)
        out: set[str] = set()
        while result.has_next():
            out.add(str(result.get_next()[0]))
        return out

    def all_nodes(self, *, limit: int = 100_000) -> list[Node]:
        """Return every node (bounded by `limit`). Used to (re)build the
        retrieval `HybridIndex` (ADR-002 / GAP-051). Raise the cap when V1.6
        per-shard indexing lands.
        """

        result = self._conn.execute(
            "MATCH (n:Node) "
            "RETURN n.id, n.label, n.source_tier, n.properties_json LIMIT $cap",
            parameters={"cap": int(limit)},
        )
        result = _expect_one_result(result)
        out: list[Node] = []
        while result.has_next():
            row = result.get_next()
            out.append(Node(
                id=str(row[0]), label=str(row[1]),
                source_tier=cast(Any, row[2]),
                properties=_loads_or(row[3], "{}"),
            ))
        return out

    def edges_of_type(self, label: str) -> list[Edge]:
        """V1.5b — return every edge with `r.label = ?`. Used by Level C
        cross-link retrieval (`query_graph_crosslinks` for SAME_AS scan).
        Small graphs only; V1.6 may add an index.
        """

        result = self._conn.execute(
            "MATCH (a:Node)-[r:Edge {label: $label}]->(b:Node) "
            "RETURN r.edge_id, r.label, a.id, b.id, "
            "r.source_tier, r.rank, "
            "r.references_json, r.qualifiers_json, "
            "r.t_valid_from, r.t_valid_to, r.t_ingest_from, r.t_ingest_to, "
            "r.confidence",
            parameters={"label": label},
        )
        result = _expect_one_result(result)
        out: list[Edge] = []
        while result.has_next():
            row = result.get_next()
            out.append(Edge(
                id=str(row[0]),
                label=str(row[1]),
                from_id=str(row[2]),
                to_id=str(row[3]),
                source_tier=cast(Any, row[4]),
                rank=cast(Any, row[5]),
                references=_loads_or(row[6], "[]"),
                qualifiers=_loads_or(row[7], "{}"),
                t_valid_from=_iso_or_none(row[8]),
                t_valid_to=_iso_or_none(row[9]),
                t_ingest_from=_iso_or_none(row[10]),
                t_ingest_to=_iso_or_none(row[11]),
                confidence=float(row[12]) if row[12] is not None else 1.0,
            ))
        return out

    def node_count(self, *, label: str | None = None) -> int:
        if label is None:
            result = self._conn.execute("MATCH (n:Node) RETURN count(*)")
        else:
            result = self._conn.execute(
                "MATCH (n:Node) WHERE n.label = $label RETURN count(*)",
                parameters={"label": label},
            )
        result = _expect_one_result(result)
        if not result.has_next():
            return 0
        return int(result.get_next()[0])

    def edge_count(self, *, label: str | None = None) -> int:
        if label is None:
            result = self._conn.execute("MATCH ()-[r:Edge]->() RETURN count(*)")
        else:
            result = self._conn.execute(
                "MATCH ()-[r:Edge]->() WHERE r.label = $label RETURN count(*)",
                parameters={"label": label},
            )
        result = _expect_one_result(result)
        if not result.has_next():
            return 0
        return int(result.get_next()[0])

    def checkpoint(self) -> None:
        """Flush the WAL into the main DB file so committed writes survive a hard
        power-cut. Kùzu buffers writes in the WAL and only persists them on a
        checkpoint; without this a crash loses every write since the last
        (auto-)checkpoint — observed as the graph lagging the ingest checkpoint
        by thousands of posts after a Kernel-Power crash."""
        self._conn.execute("CHECKPOINT")

    def close(self) -> None:
        # kuzu Connection + Database release on GC; explicit close not exposed
        # uniformly across versions. We null the refs so callers can re-open.
        self._conn = None  # type: ignore[assignment]
        self._db = None  # type: ignore[assignment]


def _jsonable(value: Any) -> Any:
    """Coerce dicts/lists/scalars into JSON-serializable shapes."""

    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, list | tuple | set):
        return [_jsonable(v) for v in value]
    return str(value)


def _iso_or_empty(dt: Any) -> str:
    if dt is None:
        return ""
    return to_iso(dt)


def _iso_or_none(text: Any) -> Any:
    if text is None or text == "":
        return None
    try:
        return from_iso(str(text))
    except (ValueError, TypeError):
        return None


def _expect_one_result(result: Any) -> Any:
    """Some Kùzu versions return a list[QueryResult] for multi-statement queries."""

    if isinstance(result, list):
        return result[-1]
    return result


def edge_csv_row(edge: Edge) -> list[Any]:
    """Serialize an Edge to a row for `KuzuGraphClient.copy_edges_from_csv`. Column
    order matches the Edge REL TABLE (FROM/TO ids first, then properties in
    definition order), using the SAME JSON/ISO serialization as `upsert_edge` so
    bulk-COPY'd edges read back identically to incrementally-inserted ones."""
    return [
        edge.from_id, edge.to_id, edge.id, edge.label, edge.source_tier, edge.rank,
        json.dumps(list(edge.references)), json.dumps(_jsonable(edge.qualifiers)),
        _iso_or_empty(edge.t_valid_from), _iso_or_empty(edge.t_valid_to),
        _iso_or_empty(edge.t_ingest_from), _iso_or_empty(edge.t_ingest_to),
        float(edge.confidence),
    ]
