"""Pass 1 — structural graph build (deterministic, $0). ADR-010 §Architecture impact.

Wraps `src.cli ingest l1-adea / l2-html / l5-reddit / l5-sdn` as Prefect tasks
so they can be scheduled, retried, and observed in the Prefect UI.

V1 scope: per-source tasks; the flow composes them in serial order to respect
the L1 → L5 reference dependency (canonical aliases must exist before
mention-extraction can route MENTIONS_SCHOOL edges).
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from prefect import flow, task
from prefect.tasks import exponential_backoff

from src.er.canonical_index import CanonicalIndex
from src.extraction.pass1_mention_extractor import Pass1MentionExtractor
from src.extraction.pass1_structural import Pass1StructuralBuilder
from src.graph.kuzu_client import KuzuGraphClient
from src.ingestion import DumpManifest, IngestionService
from src.ingestion.adapters.l1_excel import L1ExcelAdapter
from src.ingestion.adapters.l5_reddit import L5RedditAdapter
from src.observability import AuditLog
from src.shared.timestamps import utc_now


@task(retries=2, retry_delay_seconds=exponential_backoff(backoff_factor=10))
def ingest_l1_excel(
    excel_path: Path, *, sqlite_path: Path, graph_path: Path,
    dumps_root: Path, source_name: str,
) -> dict[str, int]:
    """Single ADEA SDE Excel file → L1 schools + metrics + aliases."""

    ingest = IngestionService(dumps_root=dumps_root, sqlite_path=sqlite_path)
    adapter = L1ExcelAdapter(sqlite_path=sqlite_path)
    audit = AuditLog(sqlite_path=sqlite_path)
    graph = KuzuGraphClient(db_path=graph_path)
    builder = Pass1StructuralBuilder()

    now = utc_now()
    manifest = DumpManifest(
        source_name=source_name,
        source_tier="L1",
        rank_default="preferred",
        license="ADEA proprietary; internal V1 use only",
        t_valid_range=(datetime(2020, 1, 1, tzinfo=now.tzinfo),
                       datetime(2030, 12, 31, tzinfo=now.tzinfo)),
        provenance={"file_name": excel_path.name},
    )
    receipt = ingest.register_dump("L1", manifest, [excel_path])
    audit.log_ingestion(
        dump_id=receipt.dump_id, source_tier="L1",
        source_name=source_name, file_count=1,
        duplicate_of=receipt.duplicate_of,
    )
    result = adapter.parse(excel_path)
    adapter.persist(result, source_dump_id=receipt.dump_id)
    structural = builder.assemble_l1(
        result, source_dump_id=receipt.dump_id, ingest_time=now,
    )
    graph.upsert_nodes(structural.nodes)
    graph.upsert_edges(structural.edges)
    graph.close()
    return {
        "schools": len(result.schools),
        "metrics": len(result.metrics),
        "aliases": len(result.aliases),
    }


@task(retries=2, retry_delay_seconds=exponential_backoff(backoff_factor=10))
def ingest_reddit(
    posts: Path, comments: Path | None, *,
    sqlite_path: Path, graph_path: Path, dumps_root: Path,
    max_posts: int | None = None,
) -> dict[str, int]:
    """Reddit posts + comments → L5 graph + Pass 1 mention extraction."""

    ingest = IngestionService(dumps_root=dumps_root, sqlite_path=sqlite_path)
    audit = AuditLog(sqlite_path=sqlite_path)
    graph = KuzuGraphClient(db_path=graph_path)

    now = utc_now()
    payload = [posts] + ([comments] if comments is not None else [])
    manifest = DumpManifest(
        source_name=f"reddit_{posts.stem}", source_tier="L5",
        rank_default="normal", license="Reddit ToS / Pushshift",
        t_valid_range=(datetime(2007, 1, 1, tzinfo=now.tzinfo),
                       datetime(2030, 12, 31, tzinfo=now.tzinfo)),
        provenance={"posts": posts.name},
    )
    receipt = ingest.register_dump("L5", manifest, payload)
    audit.log_ingestion(
        dump_id=receipt.dump_id, source_tier="L5",
        source_name=manifest.source_name, file_count=len(payload),
    )
    result = L5RedditAdapter().parse(posts, comments)
    if max_posts is not None:
        keep_ids = {p.post_id for p in result.posts[:max_posts]}
        result.posts[:] = result.posts[:max_posts]
        result.comments[:] = [c for c in result.comments if c.post_id in keep_ids]

    idx = CanonicalIndex(sqlite_path=sqlite_path)
    extractor = Pass1MentionExtractor(idx) if idx.alias_count() > 0 else None
    structural = Pass1StructuralBuilder().assemble_reddit(
        result, ingest_time=now, mention_extractor=extractor,
    )
    graph.upsert_nodes(structural.nodes)
    graph.upsert_edges(structural.edges)
    graph.close()
    return {
        "posts": len(result.posts),
        "comments": len(result.comments),
        "users": len(result.users),
    }


@flow(name="pass1-structural-incremental")
def pass1_structural_incremental(
    *,
    l1_excel_paths: list[Path],
    reddit_posts: Path,
    reddit_comments: Path | None,
    data_dir: Path,
) -> dict[str, dict[str, int]]:
    """Daily incremental: refresh L1 + ingest new Reddit dump.

    Order matters: L1 must run first so `Pass1MentionExtractor` sees
    canonical aliases before Reddit mention-extraction runs.
    """

    sqlite_path = data_dir / "sqlite" / "store.db"
    graph_path = data_dir / "graph" / "kuzu.db"
    dumps_root = data_dir / "dumps"

    l1_stats: dict[str, int] = {"schools": 0, "metrics": 0, "aliases": 0}
    for path in l1_excel_paths:
        s = ingest_l1_excel(
            path, sqlite_path=sqlite_path, graph_path=graph_path,
            dumps_root=dumps_root, source_name=f"ADEA_{path.stem}",
        )
        for k, v in s.items():
            l1_stats[k] += v

    reddit_stats = ingest_reddit(
        reddit_posts, reddit_comments, sqlite_path=sqlite_path,
        graph_path=graph_path, dumps_root=dumps_root,
    )

    return {"l1": l1_stats, "reddit": reddit_stats}


if __name__ == "__main__":  # pragma: no cover - operator-invoked
    import os
    data = Path(os.environ.get("SECBRAIN_DATA_DIR", "data"))
    pass1_structural_incremental(
        l1_excel_paths=[],
        reddit_posts=Path("External Data/Forum/Reddit/r_DentalSchool_posts.jsonl"),
        reddit_comments=Path("External Data/Forum/Reddit/r_DentalSchool_comments.jsonl"),
        data_dir=data,
    )
