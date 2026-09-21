"""Postgres + Apache AGE driver for the bake-off.

Connects to a Postgres instance with the AGE extension installed. Uses Cypher-via-AGE for
graph queries; same query shapes as the Kùzu / Neo4j drivers.

Defaults to `localhost:5434` / `postgres/bakeoffpass` / db `bakeoff` (matches the Docker container
started in this session via `apache/age:latest`).
"""

from __future__ import annotations

import json
import os
import pickle
import time
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import psycopg

from tools.bake_off.measure import (
    EngineMeasurement,
    QueryResult,
    run_query_n,
    write_result,
)
from tools.bake_off.schema import Sample, SampleEdge, SampleNode

ENGINE_NAME = "postgres-age"

_DSN = os.environ.get(
    "BAKEOFF_AGE_DSN",
    "postgres://postgres:bakeoffpass@127.0.0.1:5436/bakeoff",
)
_GRAPH_NAME = "secbrain_bakeoff"


def _connect() -> psycopg.Connection:
    return psycopg.connect(_DSN, autocommit=False)


def _setup_extension(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        cur.execute("CREATE EXTENSION IF NOT EXISTS age")
    conn.commit()


def _session_setup(cur: psycopg.Cursor) -> None:
    """Per-session: load AGE + put ag_catalog on search_path."""

    cur.execute("LOAD 'age'")
    cur.execute('SET search_path = ag_catalog, "$user", public')


def _reset_graph(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        _session_setup(cur)
        cur.execute(
            "SELECT 1 FROM ag_catalog.ag_graph WHERE name = %s", (_GRAPH_NAME,)
        )
        if cur.fetchone():
            cur.execute("SELECT drop_graph(%s, true)", (_GRAPH_NAME,))
        cur.execute("SELECT create_graph(%s)", (_GRAPH_NAME,))
    conn.commit()


def _format_dt(dt: Any) -> str:
    return dt.isoformat() if dt is not None else ""


def _escape_cypher_string(value: Any) -> str:
    """Convert a Python value to its Cypher literal representation."""

    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    s = str(value).replace("\\", "\\\\").replace("'", "\\'").replace("\n", " ")
    return f"'{s}'"


def _cypher_map(props: dict[str, Any]) -> str:
    """Render a Python dict as a Cypher map literal."""

    parts = [f"{k}: {_escape_cypher_string(v)}" for k, v in props.items()]
    return "{" + ", ".join(parts) + "}"


def _node_props(n: SampleNode) -> dict[str, Any]:
    payload: dict[str, Any] = {"id": n.id, "source_tier": n.source_tier}
    for k, v in n.properties.items():
        if isinstance(v, (str, int, float, bool)) or v is None:
            payload[k] = v
        else:
            payload[k] = str(v)
    return payload


def _edge_props(e: SampleEdge) -> dict[str, Any]:
    # AGE rejects array values inside Cypher literals; serialize lists as JSON strings.
    return {
        "id": e.id,
        "source_tier": e.source_tier,
        "rank": e.rank,
        "references_json": json.dumps(list(e.references)),
        "qualifiers_json": json.dumps({k: str(v) for k, v in e.qualifiers.items()}),
        "t_valid_from": _format_dt(e.t_valid_from),
        "t_valid_to": _format_dt(e.t_valid_to),
        "t_ingest_from": _format_dt(e.t_ingest_from),
        "t_ingest_to": _format_dt(e.t_ingest_to),
        "created_utc": _format_dt(e.created_utc),
        "confidence": float(e.confidence),
    }


def _batch(iterable: Iterable[Any], size: int) -> Iterable[list[Any]]:
    batch: list[Any] = []
    for item in iterable:
        batch.append(item)
        if len(batch) >= size:
            yield batch
            batch = []
    if batch:
        yield batch


def _bulk_load(conn: psycopg.Connection, sample: Sample) -> tuple[int, int]:
    """AGE Cypher is per-statement; we drive it via executemany on prepared `cypher(...)` calls."""

    deduped_nodes: dict[str, SampleNode] = {}
    for n in sample.nodes:
        deduped_nodes.setdefault(n.id, n)
    deduped_edges: dict[str, SampleEdge] = {}
    for e in sample.edges:
        deduped_edges.setdefault(e.id, e)

    by_label: dict[str, list[SampleNode]] = {}
    for n in deduped_nodes.values():
        by_label.setdefault(n.label, []).append(n)

    total_nodes = 0
    with conn.cursor() as cur:
        _session_setup(cur)
        for label, items in by_label.items():
            for n in items:
                map_literal = _cypher_map(_node_props(n))
                cur.execute(
                    f"SELECT * FROM cypher('{_GRAPH_NAME}', "
                    f"$bake$ CREATE (n:`{label}` {map_literal}) RETURN 1 $bake$) AS (v agtype)"
                )
            total_nodes += len(items)

    conn.commit()

    label_of: dict[str, str] = {n.id: n.label for n in deduped_nodes.values()}
    post_ids = {n.id for n in by_label.get("Post", [])}

    grouped: dict[tuple[str, str, str], list[SampleEdge]] = {}
    for e in deduped_edges.values():
        from_label = label_of.get(e.from_id)
        to_label = label_of.get(e.to_id)
        if from_label is None or to_label is None:
            continue
        rel = e.relation
        if rel == "AUTHORED" and e.to_id not in post_ids:
            rel = "AUTHORED_COMMENT"
        grouped.setdefault((rel, from_label, to_label), []).append(e)

    total_edges = 0
    with conn.cursor() as cur:
        _session_setup(cur)
        for (rel, from_label, to_label), items in grouped.items():
            for e in items:
                map_literal = _cypher_map(_edge_props(e))
                from_id_safe = e.from_id.replace("'", "\\'")
                to_id_safe = e.to_id.replace("'", "\\'")
                cur.execute(
                    f"SELECT * FROM cypher('{_GRAPH_NAME}', "
                    f"$bake$ MATCH (a:`{from_label}` {{id: '{from_id_safe}'}}), "
                    f"(b:`{to_label}` {{id: '{to_id_safe}'}}) "
                    f"CREATE (a)-[r:`{rel}` {map_literal}]->(b) RETURN 1 $bake$ ) AS (v agtype)"
                )
                total_edges += 1
    conn.commit()
    return total_nodes, total_edges


def _measure_queries(conn: psycopg.Connection, sample: Sample) -> list[QueryResult]:
    queries: list[QueryResult] = []
    school_id = next((n.id for n in sample.nodes if n.label == "School"), None)
    sub_id = next((n.id for n in sample.nodes if n.label == "Subreddit"), None)
    comment_id = next((n.id for n in sample.nodes if n.label == "Comment"), None)

    def _run(cypher: str, columns: int = 1) -> Any:
        col_list = ", ".join(f"c{i} agtype" for i in range(columns))
        with conn.cursor() as cur:
            _session_setup(cur)
            cur.execute(
                f"SELECT * FROM cypher('{_GRAPH_NAME}', $bake$ " + cypher + f" $bake$ ) AS ({col_list})"
            )
            return cur.fetchall()

    if school_id:
        def q_a() -> Any:
            return _run(
                f"MATCH (s:School {{id: '{school_id}'}})<-[:MENTIONS_SCHOOL]-(p:Post)<-[:AUTHORED]-(u:User) "
                "RETURN p.id, u.id LIMIT 100",
                columns=2,
            )
        queries.append(run_query_n("Q-A school-mentions-authors (3-hop)", q_a, 30))

    if sub_id:
        def q_b() -> Any:
            return _run(
                f"MATCH (sub:Subreddit {{id: '{sub_id}'}})<-[:POSTED_IN_FORUM]-(p:Post)<-[:AUTHORED]-(u:User) "
                "RETURN p.id, u.id LIMIT 200",
                columns=2,
            )
        queries.append(run_query_n("Q-B forum-authors (2-hop)", q_b, 30))

    if comment_id:
        def q_c() -> Any:
            return _run(
                f"MATCH (c:Comment {{id: '{comment_id}'}})-[:REPLIED_TO]->(p:Post) RETURN c.id, p.id",
                columns=2,
            )
        queries.append(run_query_n("Q-C reply-to-post (1-hop)", q_c, 50))

    def q_d() -> Any:
        return _run(
            "MATCH (p:Post) WHERE p.source_tier = 'L5' RETURN count(*) AS n",
            columns=1,
        )
    queries.append(run_query_n("Q-D property-filter-count", q_d, 30))

    return queries


def run(sample: Sample) -> EngineMeasurement:
    measurement = EngineMeasurement(engine=ENGINE_NAME, status="ok")
    conn = _connect()
    try:
        _setup_extension(conn)
        _reset_graph(conn)
        bulk_start = time.perf_counter()
        nodes_loaded, edges_loaded = _bulk_load(conn, sample)
        bulk_seconds = time.perf_counter() - bulk_start
        measurement.bulk_load_seconds = bulk_seconds
        measurement.nodes_loaded = nodes_loaded
        measurement.edges_loaded = edges_loaded
        measurement.queries = _measure_queries(conn, sample)
        measurement.hnsw_supported = None  # pgvector available as extension; not exercised here
        measurement.notes = (
            "AGE 1.5.x on Postgres. Property-filter Cypher executed via agtype. "
            "pgvector extension available for HNSW (Phase 3.5)."
        )
        measurement.bitemporal_score = 3
        measurement.bitemporal_notes = (
            "Bitemporal via SQL columns / agtype properties; no native bitemporal operators. "
            "Standard WHERE clauses filter t_valid_*."
        )
        measurement.ops_score = 3
        measurement.ops_notes = (
            "Postgres server + AGE extension via Docker. Postgres operationally familiar; "
            "AGE extension version compat with Postgres major versions has historically been thorny."
        )
    finally:
        conn.close()
    return measurement


def main() -> int:
    sample_path = Path("data/bake_off/sample.pkl")
    if not sample_path.exists():
        raise SystemExit(f"sample not found at {sample_path}; run build_sample.py first")
    with sample_path.open("rb") as f:
        sample = pickle.load(f)
    measurement = run(sample)
    write_result(measurement, Path("tools/bake_off/results/postgres-age.json"))
    print(
        f"postgres-age: load={measurement.bulk_load_seconds:.2f}s nodes={measurement.nodes_loaded} "
        f"edges={measurement.edges_loaded}"
    )
    for q in measurement.queries:
        print(f"  {q.name}: median={q.median_ms:.2f}ms p95={q.p95_ms:.2f}ms")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
