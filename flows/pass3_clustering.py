"""Pass 3 — semantic clustering (BGE embeddings + HDBSCAN or KMeans).

Weekly full rebuild + daily incremental are both supported by simply varying
`sample_size`. ADR-010 §Architecture impact.
"""

from __future__ import annotations

from pathlib import Path

from prefect import flow, task
from prefect.tasks import exponential_backoff

from src.embeddings import HashEmbeddingService
from src.embeddings.bge_embedder import BGEEmbeddingService
from src.extraction.pass3_clustering import Pass3ClusterRunner
from src.gateway import default_gateway
from src.graph.kuzu_client import KuzuGraphClient
from src.shared.timestamps import utc_now


def _read_posts(graph: KuzuGraphClient, *, source: str, limit: int) -> list[tuple[str, str]]:
    """Reused from `src.cli._read_post_inputs` — minimal Cypher to keep flow self-contained."""

    where = ""
    if source == "reddit":
        where = "WHERE p.label = 'Post' AND p.id STARTS WITH 'reddit_post:'"
    elif source == "sdn":
        where = "WHERE p.label = 'Post' AND p.id STARTS WITH 'sdn_post:'"
    cyp = (
        f"MATCH (p:Post) {where} "
        f"RETURN p.id, p.properties LIMIT {int(limit)}"
    )
    return graph.query(cyp)  # type: ignore[no-any-return]


@task(retries=2, retry_delay_seconds=exponential_backoff(backoff_factor=30))
def run_pass3_cluster(
    *, data_dir: Path, source: str, sample: int,
    method: str, embedder_name: str,
) -> dict[str, float | int]:
    graph = KuzuGraphClient(db_path=data_dir / "graph" / "kuzu.db")
    posts = _read_posts(graph, source=source, limit=sample)
    if not posts:
        graph.close()
        return {"clusters": 0, "cost_usd": 0.0}

    embedder = (
        BGEEmbeddingService() if embedder_name == "bge" else HashEmbeddingService()
    )
    runner = Pass3ClusterRunner(
        embedder=embedder, gateway=default_gateway(),
        method=method, min_cluster_size=3,
    )
    out = runner.run(
        [(pid, str(props.get("body") or "")) for pid, props in posts],
        ingest_time=utc_now(),
    )
    if out.nodes:
        graph.upsert_nodes(out.nodes)
        graph.upsert_edges(out.edges)
    graph.close()
    return {"clusters": len(out.clusters), "cost_usd": float(out.cost_usd)}


@flow(name="pass3-clustering-weekly")
def pass3_clustering_weekly(
    *, data_dir: Path, source: str = "reddit", sample: int = 5000,
    method: str = "hdbscan", embedder_name: str = "bge",
) -> dict[str, float | int]:
    return run_pass3_cluster(
        data_dir=data_dir, source=source, sample=sample,
        method=method, embedder_name=embedder_name,
    )
