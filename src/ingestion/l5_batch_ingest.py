"""Checkpointed, crash-resilient batch ingest of an L5 Reddit dump.

Processes posts in fixed-size batches; after each batch's graph writes land it
records the batch in the durable `L5IngestCheckpoint`. A host crash (Q-028) thus
costs at most one batch, and re-running resumes from the last committed batch
(graph writes are idempotent Kùzu MERGEs). Pure orchestration over the existing
Pass-1 structural builder + Pass-2 labels; progress is reported via a callback so
this module stays UI-free.
"""

from __future__ import annotations

import csv
import subprocess
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any

from src.extraction.pass1_structural import Pass1StructuralBuilder
from src.extraction.pass2_labels import Pass2LabelsBuilder
from src.ingestion.adapters.l5_reddit import L5RedditResult

if TYPE_CHECKING:
    from collections.abc import Callable

    from src.extraction.pass1_mention_extractor import Pass1MentionExtractor
    from src.graph.kuzu_client import KuzuGraphClient
    from src.ingestion.l5_checkpoint import L5IngestCheckpoint


def flush_volume_to_disk(drive_letter: str) -> bool:
    """Force the OS file-cache for a volume to physical disk (Windows
    Write-VolumeCache, no admin needed). Kùzu's CHECKPOINT only flushes to the OS
    cache; without this a power-cut loses it. Best-effort: returns False on any
    failure (the graph↔checkpoint reconcile is the correctness backstop)."""
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command",
             f"Write-VolumeCache -DriveLetter {drive_letter}"],
            capture_output=True, timeout=60, check=False,
        )
        return r.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


@dataclass(frozen=True)
class L5BatchJob:
    graph: KuzuGraphClient
    checkpoint: L5IngestCheckpoint
    result: L5RedditResult
    extractor: Pass1MentionExtractor | None
    ingest_time: datetime
    batch_size: int
    pass2_labels: bool
    rest_seconds: float = 0.0   # idle pause between batches (throttle sustained load)
    flush_drive: str | None = None   # volume letter to force-flush to disk per batch
    edge_stage_path: str | None = None   # if set, stage edges to this CSV + bulk COPY at end


@dataclass(frozen=True)
class BatchProgress:
    index: int
    total: int
    posts: int
    comments: int
    run_nodes: int
    run_edges: int
    total_done: int


def reconcile_checkpoint_to_graph(job: L5BatchJob) -> int:
    """The graph is the source of truth: drop checkpoint entries for posts not
    actually present in the graph. A hard power-cut can lose Kùzu writes still
    buffered in the WAL while the per-commit-fsync'd SQLite checkpoint survives,
    leaving the checkpoint *ahead* of the durable graph — without this, those
    posts would be silently skipped on resume and never ingested. Returns the
    number of phantom (lost-write) entries removed.
    """
    # MUST be uncapped: a LIMITed read would treat real posts beyond the cap as
    # phantom and drop them, causing the checkpoint to oscillate forever.
    in_graph = job.graph.node_ids_of_label("Post")
    phantom = job.checkpoint.done_post_ids() - in_graph
    if phantom:
        job.checkpoint.remove(phantom)
    return len(phantom)


def pending_posts(job: L5BatchJob) -> list[Any]:
    """Posts not yet checkpointed, in a stable (post_id) order for resumability."""
    done = job.checkpoint.done_post_ids()
    ordered = sorted(job.result.posts, key=lambda p: p.post_id)
    return [p for p in ordered if p.post_id not in done]


def run_l5_batches(
    job: L5BatchJob,
    pending: list[Any],
    *,
    on_batch: Callable[[BatchProgress], None] | None = None,
) -> tuple[int, int]:
    """Ingest `pending` posts in checkpointed batches. Returns (nodes, edges).

    Nodes stream in per batch (idempotent Kùzu UNWIND/MERGE). Edges are STAGED to
    a CSV and bulk-`COPY`-loaded in one linear pass at the end (when
    ``job.edge_stage_path`` is set) — incremental edge insert is O(n^2) in Kùzu's
    CSR storage (~64 s/batch at 75k nodes), whereas COPY is ~400k edges/s. Because
    staged edges land only at the very end, this is a single-pass build: re-run
    from a fresh graph rather than resuming a partially-edged one.
    """
    from src.graph.kuzu_client import edge_csv_row  # noqa: PLC0415 (lazy: avoid import cycle)

    comments_by_post: dict[str, list[Any]] = defaultdict(list)
    for c in job.result.comments:
        comments_by_post[c.post_id].append(c)
    users_by_id = {u.user_id: u for u in job.result.users}

    sbuilder = Pass1StructuralBuilder()
    lbuilder = Pass2LabelsBuilder()
    n_batches = (len(pending) + job.batch_size - 1) // job.batch_size
    run_nodes = run_edges = 0
    node_ids: set[str] = set()   # real node ids, to drop dangling edges before COPY

    stage = (
        open(job.edge_stage_path, "w", newline="", encoding="utf-8")  # noqa: SIM115
        if job.edge_stage_path else None
    )
    writer = csv.writer(stage) if stage is not None else None
    try:
        for bi in range(n_batches):
            batch_posts = pending[bi * job.batch_size:(bi + 1) * job.batch_size]
            batch_comments = [
                c for p in batch_posts for c in comments_by_post.get(p.post_id, [])
            ]
            uids = {p.author_user_id for p in batch_posts if p.author_user_id} | {
                c.author_user_id for c in batch_comments if c.author_user_id
            }
            batch_users = [users_by_id[u] for u in uids if u in users_by_id]
            sub = L5RedditResult(
                subreddit=job.result.subreddit, posts=batch_posts,
                comments=batch_comments, users=batch_users,
            )
            structural = sbuilder.assemble_reddit(
                sub, ingest_time=job.ingest_time, mention_extractor=job.extractor,
            )
            job.graph.upsert_nodes(structural.nodes)
            node_ids.update(n.id for n in structural.nodes)
            run_nodes += len(structural.nodes)
            run_edges += len(structural.edges)
            batch_edges = list(structural.edges)
            if job.pass2_labels:
                labels = lbuilder.build_reddit(sub, ingest_time=job.ingest_time)
                job.graph.upsert_nodes(labels.nodes)
                node_ids.update(n.id for n in labels.nodes)
                batch_edges.extend(labels.edges)
            # Edges: stage for bulk COPY (fast) or upsert incrementally (fallback).
            if writer is not None:
                writer.writerows(edge_csv_row(e) for e in batch_edges)
            else:
                job.graph.upsert_edges(batch_edges)
            # No per-batch CHECKPOINT: each one accumulates Kùzu node-group
            # versions and bloated the .db ~30x (filled the disk at ~90%). Kùzu's
            # auto_checkpoint (WAL threshold) flushes dirty pages to bound buffer-
            # pool pressure; one explicit CHECKPOINT runs after the edge COPY.
            job.checkpoint.mark_done({p.post_id for p in batch_posts}, bi)
            if on_batch is not None:
                on_batch(BatchProgress(
                    index=bi + 1, total=n_batches, posts=len(batch_posts),
                    comments=len(batch_comments), run_nodes=run_nodes,
                    run_edges=run_edges, total_done=job.checkpoint.count(),
                ))
            if job.rest_seconds > 0 and bi + 1 < n_batches:
                time.sleep(job.rest_seconds)
    finally:
        if stage is not None:
            stage.close()

    # Bulk-load staged edges in one linear CSR build (vs O(n^2) incremental).
    # First drop edges with a dangling endpoint (e.g. a deleted parent comment
    # that was never a node): Kùzu COPY aborts on a missing FROM/TO primary key
    # (the old incremental MERGE silently skipped them). The filtered file must
    # end in .csv (Kùzu infers the format from the extension).
    if job.edge_stage_path is not None and run_edges:
        filtered = job.edge_stage_path[:-4] + "_filtered.csv"
        with open(job.edge_stage_path, newline="", encoding="utf-8") as src, \
                open(filtered, "w", newline="", encoding="utf-8") as dst:
            reader = csv.reader(src)
            fwriter = csv.writer(dst)
            for row in reader:
                if len(row) >= 2 and row[0] in node_ids and row[1] in node_ids:
                    fwriter.writerow(row)
        job.graph.copy_edges_from_csv(filtered)
        job.graph.checkpoint()
    return run_nodes, run_edges
