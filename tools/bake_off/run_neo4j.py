"""Neo4j driver for the bake-off (Graphiti+Neo4j candidate).

We use raw Cypher via the `neo4j` Python driver. The bake-off compares engines, not libraries;
Graphiti's value-add is the bitemporal edge schema (M4), which is captured qualitatively below.

Assumes Neo4j 5.x is running locally; defaults to `bolt://localhost:7688` with `neo4j/bakeoffpass`
(matches the Docker container started in this session).
"""

from __future__ import annotations

import json
import os
import pickle
import time
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from neo4j import Driver, GraphDatabase, Session

from tools.bake_off.measure import (
    EngineMeasurement,
    QueryResult,
    run_query_n,
    write_result,
)
from tools.bake_off.schema import Sample, SampleEdge, SampleNode

ENGINE_NAME = "neo4j"

_DEFAULT_URI = os.environ.get("BAKEOFF_NEO4J_URI", "bolt://localhost:7688")
_DEFAULT_USER = os.environ.get("BAKEOFF_NEO4J_USER", "neo4j")
_DEFAULT_PASSWORD = os.environ.get("BAKEOFF_NEO4J_PASSWORD", "bakeoffpass")


def _connect() -> Driver:
    return GraphDatabase.driver(_DEFAULT_URI, auth=(_DEFAULT_USER, _DEFAULT_PASSWORD))


def _reset(session: Session) -> None:
    session.run("MATCH (n) DETACH DELETE n").consume()
    # Drop indexes from previous runs (best-effort).
    for label in (
        "School", "Metric", "CycleYear", "Post", "Comment", "User", "Subreddit",
    ):
        try:
            session.run(f"DROP INDEX `{label.lower()}_id` IF EXISTS").consume()
        except Exception:
            pass


def _create_indexes(session: Session) -> None:
    for label in ("School", "Metric", "CycleYear", "Post", "Comment", "User", "Subreddit"):
        session.run(
            f"CREATE INDEX `{label.lower()}_id` IF NOT EXISTS FOR (n:`{label}`) ON (n.id)"
        ).consume()


def _format_dt(dt: Any) -> str:
    return dt.isoformat() if dt is not None else ""


def _node_to_props(n: SampleNode) -> dict[str, Any]:
    out: dict[str, Any] = {"id": n.id, "source_tier": n.source_tier}
    for k, v in n.properties.items():
        if isinstance(v, (str, int, float, bool)) or v is None:
            out[k] = v
        else:
            out[k] = str(v)
    return out


def _edge_props(e: SampleEdge) -> dict[str, Any]:
    # Neo4j edge properties must be primitives or arrays-of-primitives. Dicts → JSON.
    return {
        "from_id": e.from_id,
        "to_id": e.to_id,
        "source_tier": e.source_tier,
        "rank": e.rank,
        "references": list(e.references),
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


def _bulk_load(session: Session, sample: Sample) -> tuple[int, int]:
    # Dedupe by id
    deduped_nodes: dict[str, SampleNode] = {}
    for n in sample.nodes:
        deduped_nodes.setdefault(n.id, n)
    deduped_edges: dict[str, SampleEdge] = {}
    for e in sample.edges:
        deduped_edges.setdefault(e.id, e)

    # Nodes by label.
    by_label: dict[str, list[SampleNode]] = {}
    for n in deduped_nodes.values():
        by_label.setdefault(n.label, []).append(n)

    total_nodes = 0
    for label, items in by_label.items():
        for chunk in _batch(items, 1000):
            session.run(
                f"UNWIND $rows AS row CREATE (n:`{label}`) SET n = row",
                rows=[_node_to_props(n) for n in chunk],
            ).consume()
            total_nodes += len(chunk)

    # For Neo4j, infer from→to labels via lookups. Easier to use APOC-style MERGE by id.
    # Group edges by (relation, from_label, to_label).
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
    for (rel, from_label, to_label), items in grouped.items():
        for chunk in _batch(items, 1000):
            session.run(
                f"UNWIND $rows AS row "
                f"MATCH (a:`{from_label}` {{id: row.from_id}}), (b:`{to_label}` {{id: row.to_id}}) "
                f"CREATE (a)-[r:`{rel}`]->(b) "
                f"SET r = row",
                rows=[_edge_props(e) for e in chunk],
            ).consume()
            total_edges += len(chunk)
    return total_nodes, total_edges


def _measure_queries(session: Session, sample: Sample) -> list[QueryResult]:
    queries: list[QueryResult] = []
    school_id = next((n.id for n in sample.nodes if n.label == "School"), None)
    sub_id = next((n.id for n in sample.nodes if n.label == "Subreddit"), None)
    comment_id = next((n.id for n in sample.nodes if n.label == "Comment"), None)

    if school_id:
        def q_a() -> Any:
            return session.run(
                "MATCH (s:School {id:$sid})<-[:MENTIONS_SCHOOL]-(p:Post)<-[:AUTHORED]-(u:User) "
                "RETURN p.id AS pid, u.id AS uid LIMIT 100",
                sid=school_id,
            ).data()
        queries.append(run_query_n("Q-A school-mentions-authors (3-hop)", q_a, 30))

    if sub_id:
        def q_b() -> Any:
            return session.run(
                "MATCH (sub:Subreddit {id:$sid})<-[:POSTED_IN_FORUM]-(p:Post)<-[:AUTHORED]-(u:User) "
                "RETURN p.id AS pid, u.id AS uid LIMIT 200",
                sid=sub_id,
            ).data()
        queries.append(run_query_n("Q-B forum-authors (2-hop)", q_b, 30))

    if comment_id:
        def q_c() -> Any:
            return session.run(
                "MATCH (c:Comment {id:$cid})-[:REPLIED_TO]->(p:Post) RETURN c.id, p.id",
                cid=comment_id,
            ).data()
        queries.append(run_query_n("Q-C reply-to-post (1-hop)", q_c, 50))

    def q_d() -> Any:
        return session.run(
            "MATCH (p:Post) WHERE p.source_tier = 'L5' RETURN count(*) AS n"
        ).data()
    queries.append(run_query_n("Q-D property-filter-count", q_d, 30))

    return queries


def _store_size_mb(session: Session) -> float:
    """Best-effort: read Neo4j's store info via a CALL. Fallback to 0 if not available."""

    try:
        rows = session.run("CALL dbms.queryJmx('org.neo4j:instance=kernel#0,name=Store sizes')").data()
        if rows:
            attributes = rows[0].get("attributes", {})
            total = attributes.get("TotalStoreSize", {}).get("value", 0)
            return total / (1024 * 1024)
    except Exception:
        return 0.0
    return 0.0


def run(sample: Sample) -> EngineMeasurement:
    measurement = EngineMeasurement(engine=ENGINE_NAME, status="ok")
    driver = _connect()
    try:
        with driver.session() as session:
            _reset(session)
            _create_indexes(session)
            bulk_start = time.perf_counter()
            nodes_loaded, edges_loaded = _bulk_load(session, sample)
            bulk_seconds = time.perf_counter() - bulk_start
            measurement.bulk_load_seconds = bulk_seconds
            measurement.nodes_loaded = nodes_loaded
            measurement.edges_loaded = edges_loaded
            measurement.disk_footprint_mb = _store_size_mb(session)
            measurement.queries = _measure_queries(session, sample)

        # HNSW: Neo4j 5 has a native vector index (since 5.11). We can create one and test it
        # for completeness. Skipping for the bake-off since the comparison is structural.
        measurement.hnsw_recall_at_10 = None
        measurement.hnsw_supported = True
        measurement.notes = "Neo4j 5 native HNSW vector index available; not exercised here."

        # M4 — bitemporal: Graphiti library models this natively. Score: 4 (library-supported).
        measurement.bitemporal_score = 4
        measurement.bitemporal_notes = (
            "Native t_valid_*/t_ingest_* exposure via Graphiti (when used). Raw Neo4j supports "
            "property-based filtering with WHERE clauses; Graphiti adds first-class operators."
        )

        # M5 — ops: Docker container; JVM heap config; separate process.
        measurement.ops_score = 2
        measurement.ops_notes = (
            "Docker compose for Neo4j Community; JVM heap tuning required; separate process to manage. "
            "GPLv3 license + single-DB limit on Community edition."
        )
    finally:
        driver.close()
    return measurement


def main() -> int:
    sample_path = Path("data/bake_off/sample.pkl")
    if not sample_path.exists():
        raise SystemExit(f"sample not found at {sample_path}; run build_sample.py first")
    with sample_path.open("rb") as f:
        sample = pickle.load(f)
    measurement = run(sample)
    write_result(measurement, Path("tools/bake_off/results/neo4j.json"))
    print(
        f"neo4j: load={measurement.bulk_load_seconds:.2f}s nodes={measurement.nodes_loaded} "
        f"edges={measurement.edges_loaded}"
    )
    for q in measurement.queries:
        print(f"  {q.name}: median={q.median_ms:.2f}ms p95={q.p95_ms:.2f}ms")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
