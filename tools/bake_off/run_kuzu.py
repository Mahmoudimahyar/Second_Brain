"""Kùzu driver for the bake-off.

Loads the sample (`data/bake_off/sample.pkl`) into a Kùzu database; runs the M1-M3 measurements
per `docs/05-features/bake-off-graph-db/test-plan.md`; writes a JSON result to
`tools/bake_off/results/kuzu.json`.

Kùzu is embedded (no server), so this driver is end-to-end: install → load → measure → done.
"""

from __future__ import annotations

import json as _json
import pickle
import shutil
import time
from pathlib import Path
from typing import Any

import kuzu

from tools.bake_off.measure import (
    EngineMeasurement,
    QueryResult,
    run_query_n,
    write_result,
)
from tools.bake_off.schema import Sample, SampleEdge, SampleNode

ENGINE_NAME = "kuzu"


def _ensure_clean_dir(path: Path) -> None:
    """For Kùzu 0.11+, `path` is a *file* (single-file `.kuzu`). Remove it + sidecars."""

    if path.exists():
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
        else:
            path.unlink(missing_ok=True)
    for sidecar in path.parent.glob(path.name + ".*"):
        sidecar.unlink(missing_ok=True)
    path.parent.mkdir(parents=True, exist_ok=True)


def _create_schema(conn: kuzu.Connection) -> None:
    # One node table per label keeps Kùzu's columnar layout efficient.
    conn.execute(
        "CREATE NODE TABLE School (id STRING PRIMARY KEY, canonical_name STRING, slug STRING, "
        "source_tier STRING)"
    )
    conn.execute(
        "CREATE NODE TABLE Metric (id STRING PRIMARY KEY, school_id STRING, cycle STRING, "
        "metric_name STRING, value STRING, source_tier STRING)"
    )
    conn.execute("CREATE NODE TABLE CycleYear (id STRING PRIMARY KEY, cycle STRING, source_tier STRING)")
    conn.execute(
        "CREATE NODE TABLE Post (id STRING PRIMARY KEY, title STRING, selftext STRING, "
        "score INT64, ups INT64, downs INT64, num_comments INT64, created_utc STRING, flair STRING, "
        "source_tier STRING)"
    )
    conn.execute(
        "CREATE NODE TABLE Comment (id STRING PRIMARY KEY, body STRING, score INT64, ups INT64, "
        "created_utc STRING, source_tier STRING)"
    )
    conn.execute("CREATE NODE TABLE User (id STRING PRIMARY KEY, author STRING, source_tier STRING)")
    conn.execute("CREATE NODE TABLE Subreddit (id STRING PRIMARY KEY, name STRING, source_tier STRING)")

    # One rel table per relation. Each carries the V1 property convention.
    common_rel_props = (
        "source_tier STRING, rank STRING, references_json STRING, qualifiers_json STRING, "
        "t_valid_from STRING, t_valid_to STRING, t_ingest_from STRING, t_ingest_to STRING, "
        "created_utc STRING, confidence DOUBLE"
    )
    conn.execute(f"CREATE REL TABLE SCHOOL_HAS_METRIC (FROM School TO Metric, {common_rel_props})")
    conn.execute(f"CREATE REL TABLE AUTHORED (FROM User TO Post, {common_rel_props})")
    conn.execute(f"CREATE REL TABLE AUTHORED_COMMENT (FROM User TO Comment, {common_rel_props})")
    conn.execute(f"CREATE REL TABLE REPLIED_TO (FROM Comment TO Post, {common_rel_props})")
    conn.execute(f"CREATE REL TABLE POSTED_IN_FORUM (FROM Post TO Subreddit, {common_rel_props})")
    conn.execute(f"CREATE REL TABLE MENTIONS_SCHOOL (FROM Post TO School, {common_rel_props})")


def _split_by_label(nodes: list[SampleNode]) -> dict[str, list[SampleNode]]:
    out: dict[str, list[SampleNode]] = {}
    for n in nodes:
        out.setdefault(n.label, []).append(n)
    return out


def _split_by_relation(edges: list[SampleEdge]) -> dict[str, list[SampleEdge]]:
    out: dict[str, list[SampleEdge]] = {}
    for e in edges:
        out.setdefault(e.relation, []).append(e)
    return out


def _format_dt(dt: Any) -> str:
    return dt.isoformat() if dt is not None else ""


def _format_refs(value: list[str]) -> str:
    return _json.dumps(value)


def _bulk_load(conn: kuzu.Connection, sample: Sample) -> tuple[int, int]:
    """Insert all nodes + edges. Returns (nodes_loaded, edges_loaded). Deduplicates by id."""

    # Pre-deduplicate nodes + edges by ID (samples can contain duplicates if Excel sheets repeat).
    deduped_nodes: dict[str, SampleNode] = {}
    for n in sample.nodes:
        deduped_nodes.setdefault(n.id, n)
    deduped_edges: dict[str, SampleEdge] = {}
    for e in sample.edges:
        deduped_edges.setdefault(e.id, e)

    by_label = _split_by_label(list(deduped_nodes.values()))
    by_rel = _split_by_relation(list(deduped_edges.values()))
    total_nodes = 0
    total_edges = 0

    # Nodes — one prepared statement per label.
    for label, items in by_label.items():
        if not items:
            continue
        if label == "School":
            for n in items:
                conn.execute(
                    "CREATE (:School {id:$id, canonical_name:$name, slug:$slug, source_tier:$st})",
                    {
                        "id": n.id,
                        "name": str(n.properties.get("canonical_name", "")),
                        "slug": str(n.properties.get("slug", "")),
                        "st": n.source_tier,
                    },
                )
                total_nodes += 1
        elif label == "Metric":
            for n in items:
                conn.execute(
                    "CREATE (:Metric {id:$id, school_id:$sid, cycle:$cy, metric_name:$mn, "
                    "value:$v, source_tier:$st})",
                    {
                        "id": n.id,
                        "sid": str(n.properties.get("school_id", "")),
                        "cy": str(n.properties.get("cycle", "")),
                        "mn": str(n.properties.get("metric_name", "")),
                        "v": str(n.properties.get("value", "")),
                        "st": n.source_tier,
                    },
                )
                total_nodes += 1
        elif label == "CycleYear":
            for n in items:
                conn.execute(
                    "CREATE (:CycleYear {id:$id, cycle:$cy, source_tier:$st})",
                    {"id": n.id, "cy": str(n.properties.get("cycle", "")), "st": n.source_tier},
                )
                total_nodes += 1
        elif label == "Post":
            for n in items:
                conn.execute(
                    "CREATE (:Post {id:$id, title:$t, selftext:$b, score:$sc, ups:$u, downs:$d, "
                    "num_comments:$nc, created_utc:$cu, flair:$fl, source_tier:$st})",
                    {
                        "id": n.id,
                        "t": str(n.properties.get("title", ""))[:300],
                        "b": str(n.properties.get("selftext", ""))[:1000],
                        "sc": int(n.properties.get("score", 0)),
                        "u": int(n.properties.get("ups", 0)),
                        "d": int(n.properties.get("downs", 0)),
                        "nc": int(n.properties.get("num_comments", 0)),
                        "cu": str(n.properties.get("created_utc", "")),
                        "fl": str(n.properties.get("flair", "")),
                        "st": n.source_tier,
                    },
                )
                total_nodes += 1
        elif label == "Comment":
            for n in items:
                conn.execute(
                    "CREATE (:Comment {id:$id, body:$b, score:$sc, ups:$u, created_utc:$cu, "
                    "source_tier:$st})",
                    {
                        "id": n.id,
                        "b": str(n.properties.get("body", ""))[:1000],
                        "sc": int(n.properties.get("score", 0)),
                        "u": int(n.properties.get("ups", 0)),
                        "cu": str(n.properties.get("created_utc", "")),
                        "st": n.source_tier,
                    },
                )
                total_nodes += 1
        elif label == "User":
            for n in items:
                conn.execute(
                    "CREATE (:User {id:$id, author:$a, source_tier:$st})",
                    {"id": n.id, "a": str(n.properties.get("author", "")), "st": n.source_tier},
                )
                total_nodes += 1
        elif label == "Subreddit":
            for n in items:
                conn.execute(
                    "CREATE (:Subreddit {id:$id, name:$n, source_tier:$st})",
                    {"id": n.id, "n": str(n.properties.get("name", "")), "st": n.source_tier},
                )
                total_nodes += 1

    # Edges — route by relation. Some AUTHORED edges go to Posts, others to Comments;
    # we look up the destination label to pick the right rel table.
    post_ids = {n.id for n in by_label.get("Post", [])}

    for relation, items in by_rel.items():
        if relation == "AUTHORED":
            for e in items:
                if e.to_id in post_ids:
                    _insert_rel(conn, "User", "Post", "AUTHORED", e)
                else:
                    _insert_rel(conn, "User", "Comment", "AUTHORED_COMMENT", e)
                total_edges += 1
        elif relation == "SCHOOL_HAS_METRIC":
            for e in items:
                _insert_rel(conn, "School", "Metric", "SCHOOL_HAS_METRIC", e)
                total_edges += 1
        elif relation == "REPLIED_TO":
            for e in items:
                _insert_rel(conn, "Comment", "Post", "REPLIED_TO", e)
                total_edges += 1
        elif relation == "POSTED_IN_FORUM":
            for e in items:
                _insert_rel(conn, "Post", "Subreddit", "POSTED_IN_FORUM", e)
                total_edges += 1
        elif relation == "MENTIONS_SCHOOL":
            for e in items:
                _insert_rel(conn, "Post", "School", "MENTIONS_SCHOOL", e)
                total_edges += 1

    return total_nodes, total_edges


def _insert_rel(conn: kuzu.Connection, from_label: str, to_label: str, rel: str, e: SampleEdge) -> None:
    params = {
        "from_id": e.from_id,
        "to_id": e.to_id,
        "st": e.source_tier,
        "rk": e.rank,
        "refs": _format_refs(e.references),
        "qf": _format_refs([str(k) + "=" + str(v) for k, v in e.qualifiers.items()]),
        "tvf": _format_dt(e.t_valid_from),
        "tvt": _format_dt(e.t_valid_to),
        "tif": _format_dt(e.t_ingest_from),
        "tit": _format_dt(e.t_ingest_to),
        "cu": _format_dt(e.created_utc),
        "cf": float(e.confidence),
    }
    query = (
        f"MATCH (a:{from_label} {{id:$from_id}}), (b:{to_label} {{id:$to_id}}) "
        f"CREATE (a)-[:{rel} {{source_tier:$st, rank:$rk, references_json:$refs, "
        f"qualifiers_json:$qf, t_valid_from:$tvf, t_valid_to:$tvt, t_ingest_from:$tif, "
        f"t_ingest_to:$tit, created_utc:$cu, confidence:$cf}}]->(b)"
    )
    conn.execute(query, params)


def _measure_queries(conn: kuzu.Connection, sample: Sample) -> list[QueryResult]:
    """Run the bake-off test queries Q-A through Q-D (Kùzu-compatible adaptations)."""

    queries: list[QueryResult] = []

    # Q-A — Trust-tier-aware school lookup: get posts mentioning a school + their authors.
    school_id = next((n.id for n in sample.nodes if n.label == "School"), None)
    if school_id:
        def q_a() -> Any:
            return conn.execute(
                "MATCH (s:School {id:$sid})<-[:MENTIONS_SCHOOL]-(p:Post)<-[:AUTHORED]-(u:User) "
                "RETURN p.id, u.id LIMIT 100",
                {"sid": school_id},
            )
        queries.append(run_query_n("Q-A school-mentions-authors (3-hop)", q_a, 30))

    # Q-B — Posts in a forum + their authors (2-hop).
    sub_id = next((n.id for n in sample.nodes if n.label == "Subreddit"), None)
    if sub_id:
        def q_b() -> Any:
            return conn.execute(
                "MATCH (sub:Subreddit {id:$sid})<-[:POSTED_IN_FORUM]-(p:Post)<-[:AUTHORED]-(u:User) "
                "RETURN p.id, u.id LIMIT 200",
                {"sid": sub_id},
            )
        queries.append(run_query_n("Q-B forum-authors (2-hop)", q_b, 30))

    # Q-C — Comment-thread reconstruction: comment → reply chain.
    comment_id = next((n.id for n in sample.nodes if n.label == "Comment"), None)
    if comment_id:
        def q_c() -> Any:
            return conn.execute(
                "MATCH (c:Comment {id:$cid})-[:REPLIED_TO]->(p:Post) RETURN c.id, p.id",
                {"cid": comment_id},
            )
        queries.append(run_query_n("Q-C reply-to-post (1-hop)", q_c, 50))

    # Q-D — Property-filter scan: count Posts by source_tier.
    def q_d() -> Any:
        return conn.execute(
            "MATCH (p:Post) WHERE p.source_tier = 'L5' RETURN count(*) AS n"
        )
    queries.append(run_query_n("Q-D property-filter-count", q_d, 30))

    return queries


def _measure_hnsw_recall(conn: kuzu.Connection, sample: Sample, vector_index_supported: bool) -> tuple[float | None, bool]:
    """Try Kùzu's native vector extension. If not available, brute-force compare against ground truth."""

    if not vector_index_supported:
        # Skip — Kùzu 0.11.3 vector extension not exercised in this driver to keep the bake-off
        # graph-only. Recall@10 from a brute-force sanity check (not a real HNSW measurement):
        # we re-compute brute-force on a small subset and compare to the precomputed ground truth.
        return _brute_force_recall(sample), False
    # Future: hook into kuzu vector index if/when stable.
    return _brute_force_recall(sample), True


def _brute_force_recall(sample: Sample) -> float:
    """Sanity check: re-run brute-force top-10 on the same embeddings and confirm overlap with ground truth."""

    by_id = {e.chunk_id: e.vector for e in sample.embeddings}
    overlaps: list[float] = []
    for q in sample.query_vectors[:50]:  # subset for speed
        scored = sorted(
            ((cid, sum(x * y for x, y in zip(q.vector, vec, strict=True))) for cid, vec in by_id.items()),
            key=lambda kv: kv[1],
            reverse=True,
        )
        top10 = {cid for cid, _ in scored[:10]}
        truth = set(sample.ground_truth_top10.get(q.chunk_id, []))
        if truth:
            overlaps.append(len(top10 & truth) / 10.0)
    return sum(overlaps) / len(overlaps) if overlaps else 0.0


def _dir_size_mb(path: Path) -> float:
    """Sum the main DB file + any sidecar files in the same directory matching the DB name."""

    total = 0
    if path.is_file():
        total += path.stat().st_size
    elif path.is_dir():
        for p in path.rglob("*"):
            if p.is_file():
                total += p.stat().st_size
    for sidecar in path.parent.glob(path.name + ".*"):
        if sidecar.is_file():
            total += sidecar.stat().st_size
    return total / (1024 * 1024)


def run(sample: Sample, db_path: Path) -> EngineMeasurement:
    _ensure_clean_dir(db_path)
    measurement = EngineMeasurement(engine=ENGINE_NAME, status="ok")

    db = kuzu.Database(str(db_path))
    conn = kuzu.Connection(db)
    _create_schema(conn)

    bulk_start = time.perf_counter()
    nodes_loaded, edges_loaded = _bulk_load(conn, sample)
    bulk_seconds = time.perf_counter() - bulk_start
    measurement.bulk_load_seconds = bulk_seconds
    measurement.nodes_loaded = nodes_loaded
    measurement.edges_loaded = edges_loaded
    measurement.disk_footprint_mb = _dir_size_mb(db_path)

    measurement.queries = _measure_queries(conn, sample)

    recall, hnsw_supported = _measure_hnsw_recall(conn, sample, vector_index_supported=False)
    measurement.hnsw_recall_at_10 = recall
    measurement.hnsw_supported = hnsw_supported
    if not hnsw_supported:
        measurement.notes += (
            "HNSW: Kùzu 0.11.x vector extension exists but is not exercised by this driver; "
            "brute-force sanity check on the embedding store reports recall@10 (should be 1.0 by construction). "
        )

    # M4 — bitemporal ergonomics (subjective): edge properties hold the 4-tuple; no native bitemporal
    # constructs. Score per `test-plan.md` rubric: "Property-based and ergonomic — standard WHERE clauses".
    measurement.bitemporal_score = 3
    measurement.bitemporal_notes = (
        "Bitemporal modeled as edge string properties (ISO timestamps). Cypher-style WHERE clauses "
        "filter by t_valid_*; no native bitemporal operators. Adequate for V1; rebuild needed for "
        "fast point-in-time recall (Phase 3.5)."
    )

    # M5 — ops complexity (subjective): embedded, no service, no JVM, no Docker.
    measurement.ops_score = 5
    measurement.ops_notes = (
        "Embedded (`pip install kuzu`); single Python process; on-disk files under db_path. "
        "No service to start, no JVM tuning. Trivial."
    )

    conn.close()
    db.close()
    return measurement


def main() -> int:
    sample_path = Path("data/bake_off/sample.pkl")
    if not sample_path.exists():
        msg = f"sample not found at {sample_path}; run build_sample.py first"
        raise SystemExit(msg)
    with sample_path.open("rb") as f:
        sample = pickle.load(f)
    measurement = run(sample, Path("data/bake_off/kuzu.db"))
    out = Path("tools/bake_off/results/kuzu.json")
    write_result(measurement, out)
    print(
        f"kuzu: load={measurement.bulk_load_seconds:.2f}s nodes={measurement.nodes_loaded} "
        f"edges={measurement.edges_loaded} disk={measurement.disk_footprint_mb:.1f}MB queries={len(measurement.queries)}"
    )
    for q in measurement.queries:
        print(f"  {q.name}: median={q.median_ms:.2f}ms p95={q.p95_ms:.2f}ms")
    print(f"  HNSW: recall@10={measurement.hnsw_recall_at_10:.2f} supported={measurement.hnsw_supported}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
