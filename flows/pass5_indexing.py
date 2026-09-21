"""Pass 5 — refresh retrieval indexes. Cheap; runs after each Pass 1-4 cycle.

V1 retrieval is substring + outbound traversal (see `src.retrieval.api`); no
heavy indexes to rebuild. This flow exists as a placeholder for V1.x when
BM25 + HNSW indexes land per ADR-002.
"""

from __future__ import annotations

from pathlib import Path

from prefect import flow, task

from src.graph.kuzu_client import KuzuGraphClient


@task
def snapshot_retrieval_stats(*, data_dir: Path) -> dict[str, int]:
    graph = KuzuGraphClient(db_path=data_dir / "graph" / "kuzu.db")
    stats = {
        "nodes": graph.node_count(),
        "edges": graph.edge_count(),
    }
    graph.close()
    return stats


@flow(name="pass5-indexing-refresh")
def pass5_indexing_refresh(*, data_dir: Path) -> dict[str, int]:
    return snapshot_retrieval_stats(data_dir=data_dir)
