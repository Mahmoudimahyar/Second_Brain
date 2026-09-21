"""ADR-025 GraphRAG-engine bake-off — custom Kùzu store vs Neo4j on real data.

  ./.venv/Scripts/python.exe -m tools.graph_engine_bakeoff.run \
      [--data-dir .agent/dj_l1c] [--neo4j bolt://localhost:7687] [--iters 60]

Loads the real residency graph (Programs/Institutions/Specialties + OFFERED_BY /
IN_SPECIALTY edges) from the existing Kùzu store into Neo4j **idiomatically**
(native node labels + rel types + an id index — Neo4j's best foot forward), then
times five matched queries (point lookup, 1-hop, 2-hop, aggregation, 3-hop) on
both engines and reports p50 / p95 latency. Both engines speak Cypher.

This compares the **store layer** (the only apples-to-apples comparison). LightRAG
and Graphiti are LLM-driven graph *construction* frameworks, not drop-in stores —
their fit is assessed qualitatively in `probe_frameworks()`.
"""

from __future__ import annotations

import argparse
import statistics
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from neo4j import GraphDatabase

from src.graph.kuzu_client import KuzuGraphClient

TOP_INSTITUTION = "institution:nyu_langone_dental_medicine"
SPECIALTY = "specialty:orthodontics"

# (name, kuzu_cypher, neo4j_cypher, params)
QUERIES: tuple[tuple[str, str, str, dict[str, Any]], ...] = (
    ("Q1 point-lookup",
     "MATCH (n:Node {id:$id}) RETURN n.id, n.label",
     "MATCH (n:Entity {id:$id}) RETURN n.id, labels(n)",
     {"id": TOP_INSTITUTION}),
    ("Q2 1-hop programs@inst",
     "MATCH (p:Node)-[e:Edge]->(i:Node {id:$id}) WHERE e.label='OFFERED_BY' RETURN p.id",
     "MATCH (p:Program)-[:OFFERED_BY]->(i:Institution {id:$id}) RETURN p.id",
     {"id": TOP_INSTITUTION}),
    ("Q3 2-hop inst@specialty",
     "MATCH (i:Node)<-[e1:Edge]-(p:Node)-[e2:Edge]->(s:Node {id:$sid}) "
     "WHERE e1.label='OFFERED_BY' AND e2.label='IN_SPECIALTY' RETURN DISTINCT i.id",
     "MATCH (i:Institution)<-[:OFFERED_BY]-(:Program)-[:IN_SPECIALTY]->"
     "(s:Specialty {id:$sid}) RETURN DISTINCT i.id",
     {"sid": SPECIALTY}),
    ("Q4 agg programs/specialty",
     "MATCH (p:Node)-[e:Edge]->(s:Node) WHERE e.label='IN_SPECIALTY' "
     "RETURN s.id, count(p) AS c ORDER BY c DESC",
     "MATCH (:Program)-[:IN_SPECIALTY]->(s:Specialty) "
     "RETURN s.id, count(*) AS c ORDER BY c DESC",
     {}),
    ("Q5 3-hop sibling-specialty",
     "MATCH (s0:Node {id:$sid})<-[e1:Edge]-(p1:Node)-[e2:Edge]->(i:Node)"
     "<-[e3:Edge]-(p2:Node)-[e4:Edge]->(s2:Node) "
     "WHERE e1.label='IN_SPECIALTY' AND e2.label='OFFERED_BY' "
     "AND e3.label='OFFERED_BY' AND e4.label='IN_SPECIALTY' RETURN DISTINCT s2.id",
     "MATCH (s0:Specialty {id:$sid})<-[:IN_SPECIALTY]-(:Program)-[:OFFERED_BY]->"
     "(:Institution)<-[:OFFERED_BY]-(:Program)-[:IN_SPECIALTY]->(s2:Specialty) "
     "RETURN DISTINCT s2.id",
     {"sid": SPECIALTY}),
)


@dataclass
class Bench:
    name: str
    p50_ms: float
    p95_ms: float
    rows: int


def _read_kuzu(client: KuzuGraphClient) -> tuple[list[Any], list[tuple[str, str, str]]]:
    nodes = client.all_nodes()
    res = client._conn.execute(
        "MATCH (a:Node)-[e:Edge]->(b:Node) RETURN a.id, b.id, e.label",
    )
    edges: list[tuple[str, str, str]] = []
    while res.has_next():
        a, b, label = res.get_next()
        edges.append((str(a), str(b), str(label)))
    return nodes, edges


def _load_neo4j(driver: Any, nodes: list[Any], edges: list[tuple[str, str, str]]) -> None:
    with driver.session() as s:
        s.run("MATCH (n) DETACH DELETE n")
        s.run("CREATE INDEX entity_id IF NOT EXISTS FOR (n:Entity) ON (n.id)")
        by_label: dict[str, list[dict[str, str]]] = {}
        for n in nodes:
            by_label.setdefault(n.label, []).append(
                {"id": n.id, "name": str(n.properties.get("canonical_name", ""))},
            )
        for label, rows in by_label.items():
            s.run(
                f"UNWIND $rows AS r CREATE (n:Entity:{label} "
                "{id: r.id, name: r.name})",
                rows=rows,
            )
        by_rel: dict[str, list[dict[str, str]]] = {}
        for a, b, label in edges:
            by_rel.setdefault(label, []).append({"a": a, "b": b})
        for rel, rows in by_rel.items():
            s.run(
                f"UNWIND $rows AS r MATCH (a:Entity {{id:r.a}}), (b:Entity {{id:r.b}}) "
                f"CREATE (a)-[:{rel}]->(b)",
                rows=rows,
            )


def _bench_kuzu(client: KuzuGraphClient, cypher: str, params: dict[str, Any],
                iters: int) -> Bench:
    rows = 0
    lat: list[float] = []
    for _ in range(iters):
        t0 = time.perf_counter()
        res = client._conn.execute(cypher, parameters=params)
        n = 0
        while res.has_next():
            res.get_next()
            n += 1
        lat.append((time.perf_counter() - t0) * 1000)
        rows = n
    return Bench("", _pct(lat, 50), _pct(lat, 95), rows)


def _bench_neo4j(driver: Any, cypher: str, params: dict[str, Any], iters: int) -> Bench:
    rows = 0
    lat: list[float] = []
    with driver.session() as s:
        for _ in range(iters):
            t0 = time.perf_counter()
            rows = len(list(s.run(cypher, **params)))
            lat.append((time.perf_counter() - t0) * 1000)
    return Bench("", _pct(lat, 50), _pct(lat, 95), rows)


def _pct(xs: list[float], p: int) -> float:
    if not xs:
        return 0.0
    return statistics.quantiles(xs, n=100)[p - 1] if len(xs) > 1 else xs[0]


def probe_frameworks() -> list[str]:
    notes: list[str] = []
    for mod, desc in (
        ("graphiti_core", "Graphiti: temporal KG, LLM entity-extraction over Neo4j"),
        ("lightrag", "LightRAG: dual-level graph+vector RAG, LLM graph construction"),
    ):
        try:
            __import__(mod)
            notes.append(f"  [installed] {desc}")
        except Exception as ex:  # spike: report and continue
            notes.append(f"  [missing]   {mod}: {type(ex).__name__}")
    return notes


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default=".agent/dj_l1c")
    ap.add_argument("--neo4j", default="bolt://localhost:7687")
    ap.add_argument("--user", default="neo4j")
    ap.add_argument("--password", default="secbrainspike123")
    ap.add_argument("--iters", type=int, default=60)
    args = ap.parse_args()

    client = KuzuGraphClient(db_path=Path(args.data_dir) / "graph" / "kuzu.db")
    nodes, edges = _read_kuzu(client)
    print(f"loaded from Kùzu: {len(nodes)} nodes, {len(edges)} edges")

    driver = GraphDatabase.driver(args.neo4j, auth=(args.user, args.password))
    t0 = time.perf_counter()
    _load_neo4j(driver, nodes, edges)
    print(f"loaded into Neo4j in {time.perf_counter() - t0:.1f}s\n")

    print(f"  {'query':28} {'Kùzu p50':>9} {'p95':>7} | {'Neo4j p50':>9} {'p95':>7}  rows")
    for name, kcy, ncy, params in QUERIES:
        # warm-up
        _bench_kuzu(client, kcy, params, 3)
        _bench_neo4j(driver, ncy, params, 3)
        k = _bench_kuzu(client, kcy, params, args.iters)
        n = _bench_neo4j(driver, ncy, params, args.iters)
        print(f"  {name:28} {k.p50_ms:8.2f}m {k.p95_ms:6.2f}m | "
              f"{n.p50_ms:8.2f}m {n.p95_ms:6.2f}m  {k.rows}/{n.rows}")

    print("\nframework fit (ADR-025 candidates):")
    for line in probe_frameworks():
        print(line)
    client.close()
    driver.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
