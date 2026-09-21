"""Pass 2 — promote Reddit flair + SDN category → Topic nodes. $0, fast.

Runs after Pass 1 in the daily cadence; small and idempotent.
"""

from __future__ import annotations

from pathlib import Path

from prefect import flow, task

from src.extraction.pass2_labels import Pass2LabelsBuilder
from src.graph.kuzu_client import KuzuGraphClient
from src.ingestion.adapters.l5_reddit import L5RedditAdapter
from src.shared.timestamps import utc_now


@task(retries=1)
def label_reddit_topics(
    posts: Path, comments: Path | None, *, graph_path: Path,
) -> dict[str, int]:
    """Reddit flair → `Topic` nodes + `REFERENCES_TOPIC` edges."""

    result = L5RedditAdapter().parse(posts, comments)
    graph = KuzuGraphClient(db_path=graph_path)
    labels = Pass2LabelsBuilder().build_reddit(result, ingest_time=utc_now())
    graph.upsert_nodes(labels.nodes)
    graph.upsert_edges(labels.edges)
    graph.close()
    return {"topic_nodes": len(labels.nodes), "edges": len(labels.edges)}


@flow(name="pass2-labels-incremental")
def pass2_labels_incremental(
    *, reddit_posts: Path, reddit_comments: Path | None, data_dir: Path,
) -> dict[str, int]:
    return label_reddit_topics(
        reddit_posts, reddit_comments,
        graph_path=data_dir / "graph" / "kuzu.db",
    )
