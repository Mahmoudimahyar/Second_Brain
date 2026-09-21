"""V1 product engine CLI.

Single entry point: `python -m src.cli <command>`. Wraps the public APIs from
`src.ingestion`, `src.extraction`, `src.retrieval`, `src.hitl`, `src.observability`.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from src.conflict import Claim, ConflictResolver
from src.conflict.factory import build_three_vendor_judge, build_web_verifier
from src.conflict.l1_claims import build_adea_metric_claims, build_db_fact_claims
from src.conflict.pass4_resolution import (
    build_joint_resolver_if_enabled,
    resolve_pass4_conflicts,
)
from src.embeddings import HashEmbeddingService
from src.embeddings.api import EmbeddingService
from src.embeddings.bge_embedder import BGEEmbeddingService
from src.embeddings.qwen_embedder import QwenEmbeddingService
from src.er.canonical_index import CanonicalIndex
from src.er.llm_matcher import GatewayLLMMatcher
from src.extraction.cache import ExtractionCache
from src.extraction.pass1_mention_extractor import Pass1MentionExtractor
from src.extraction.pass1_structural import Pass1StructuralBuilder
from src.extraction.pass2_labels import Pass2LabelsBuilder
from src.extraction.pass3_clustering import Pass3ClusterRunner
from src.extraction.pass4_sweep import Pass4Input, run_pass4_sweep, summarize
from src.gateway import default_gateway
from src.graph.kuzu_client import KuzuGraphClient
from src.hitl import Decision, HITLQueue
from src.ingestion import DumpManifest, IngestionService
from src.ingestion.adapters.l1_db import build_l1_from_dump, extract_from_dump
from src.ingestion.adapters.l1_excel import L1ExcelAdapter, L1IngestResult
from src.ingestion.adapters.l1_pdf import L1PDFAdapter
from src.ingestion.adapters.l1_residency import (
    build_residency_from_dump,
    extract_residency_from_dump,
)
from src.ingestion.adapters.l2_html import L2HtmlAdapter
from src.ingestion.adapters.l5_reddit import (
    DEFAULT_ADMISSIONS_KEYWORDS,
    L5RedditAdapter,
    L5RedditResult,
)
from src.ingestion.adapters.l5_sdn import L5SDNAdapter
from src.ingestion.l5_batch_ingest import (
    BatchProgress,
    L5BatchJob,
    pending_posts,
    reconcile_checkpoint_to_graph,
    run_l5_batches,
)
from src.ingestion.l5_checkpoint import L5IngestCheckpoint
from src.observability import AuditLog
from src.retrieval import RetrievalService
from src.retrieval.index import HybridIndex
from src.shared.env_loader import load_dotenv
from src.shared.timestamps import utc_now

app = typer.Typer(
    name="secbrain",
    help="Trust-tier-aware knowledge-graph engine: ingest sources, extract, resolve "
    "conflicts, and query with citations.",
    no_args_is_help=True,
    add_completion=False,
)
ingest_app = typer.Typer(
    help="Ingest a source dump. The adapter you pick declares its trust tier "
    "(L1 authoritative ... L5 community).",
)
app.add_typer(ingest_app, name="ingest")
hitl_app = typer.Typer(
    help="Human-in-the-loop review queue: alias matches, conflicts, schema proposals.",
)
app.add_typer(hitl_app, name="hitl")
crawl_app = typer.Typer(
    help="Website-crawl scheduler: register official domains, run crawls. "
    "NOTE: `run`/`tick` open the Kùzu graph exclusively — stop the web "
    "server first (or use the UI's Run-now, which shares its handle).",
)
app.add_typer(crawl_app, name="crawl")

console = Console()


def _force_utf8_streams() -> None:
    """Help text and tables contain characters ("→", "ù") that a cp1252 console or a pipe
    cannot encode; without this, `--help` dies with a UnicodeEncodeError on Windows."""

    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")


def cli() -> None:
    """Console-script entry point (`secbrain`)."""

    _force_utf8_streams()
    app()


@app.callback()
def main(
    ctx: typer.Context,
    data_dir: Annotated[Path, typer.Option(
        envvar="SECBRAIN_DATA_DIR", help="Directory for SQLite + Kùzu + dumps.",
    )] = Path("data"),
    env_file: Annotated[Path, typer.Option(help="Path to .env (auto-loaded).")]
        = Path(".env"),
) -> None:
    """Top-level options stored on the context for sub-commands."""

    load_dotenv(env_file)
    ctx.ensure_object(dict)
    ctx.obj["data_dir"] = Path(data_dir)
    ctx.obj["sqlite_path"] = Path(data_dir) / "sqlite" / "store.db"
    ctx.obj["graph_path"] = Path(data_dir) / "graph" / "kuzu.db"
    ctx.obj["dumps_root"] = Path(data_dir) / "dumps"


def _build_embedder(name: str, device: str = "cpu") -> EmbeddingService:
    """`hash` (fast, no model) | `bge` (BGE-small, low-VRAM fallback) | `qwen`
    (Qwen3-Embedding-0.6B — ADR-022 primary blocker, best recall, heavier)."""
    if name == "qwen":
        return QwenEmbeddingService(device=device)
    if name == "bge":
        return BGEEmbeddingService(device=device)
    return HashEmbeddingService()


@ingest_app.command("l1-adea")
def ingest_l1_adea(
    ctx: typer.Context,
    paths: list[Path],
    source_name: Annotated[str, typer.Option(help="Logical name for the dump (overrides --report).")]
        = "",
    report: Annotated[int, typer.Option(help="ADEA report number: 1 (SDE1 Programs/Enrollment), 2 (SDE2 Tuition/Admission/Attrition), 3 (SDE3 Finances). Sets default source_name = 'ADEA_Report_N'.")]
        = 2,
) -> None:
    """Ingest one or more ADEA SDE Excel files into L1 ground truth.

    Supports SDE1 (`--report 1`, school column = "United States, CODA-accredited
    Dental Schools") and SDE2 (`--report 2`, the default). SDE3 per-school
    sheets work where they follow the same shape; aggregate-by-year sheets
    are skipped (no school column → adapter returns empty for that sheet).

    Examples:
      python -m src.cli ingest l1-adea --report 2 "External Data/.../SDE2_2024-25.xlsx"
      python -m src.cli ingest l1-adea --report 1 "External Data/.../SDE1_2023-24.xlsx"
    """

    if not source_name:
        source_name = f"ADEA_Report_{report}"
    data = ctx.obj
    ingest = IngestionService(
        dumps_root=data["dumps_root"], sqlite_path=data["sqlite_path"],
    )
    adapter = L1ExcelAdapter(sqlite_path=data["sqlite_path"])
    audit = AuditLog(sqlite_path=data["sqlite_path"])
    graph = KuzuGraphClient(db_path=data["graph_path"])
    builder = Pass1StructuralBuilder()

    now = utc_now()
    total_schools = 0
    total_metrics = 0
    total_aliases = 0
    for path in paths:
        if not path.is_file():
            console.print(f"[red]skip:[/] {path} (not a file)")
            continue
        manifest = DumpManifest(
            source_name=source_name,
            source_tier="L1",
            rank_default="preferred",
            license="ADEA proprietary; internal V1 use only",
            t_valid_range=(datetime(2020, 1, 1, tzinfo=now.tzinfo),
                           datetime(2030, 12, 31, tzinfo=now.tzinfo)),
            provenance={"file_name": path.name},
        )
        receipt = ingest.register_dump("L1", manifest, [path])
        audit.log_ingestion(
            dump_id=receipt.dump_id, source_tier="L1",
            source_name=source_name, file_count=1,
            duplicate_of=receipt.duplicate_of,
        )
        result = adapter.parse(path)
        adapter.persist(result, source_dump_id=receipt.dump_id)
        structural = builder.assemble_l1(
            result, source_dump_id=receipt.dump_id, ingest_time=now,
        )
        graph.upsert_nodes(structural.nodes)
        # COPY (vs OOM-prone upsert_edges) is strict on dangling FROM/TO PKs — the
        # adapter emits alias-node edges whose nodes live in sqlite, not the graph,
        # which upsert_edges silently skipped. Filter to real graph endpoints first.
        _valid = {n.id for n in structural.nodes}
        _r = graph._conn.execute("MATCH (n:Node) RETURN n.id")
        while _r.has_next():
            _valid.add(str(_r.get_next()[0]))
        graph.copy_edges([e for e in structural.edges
                          if e.from_id in _valid and e.to_id in _valid])
        total_schools += len(result.schools)
        total_metrics += len(result.metrics)
        total_aliases += len(result.aliases)
        console.print(
            f"[green]ok[/] {path.name}: cycle={result.cycle_year} "
            f"schools={len(result.schools)} metrics={len(result.metrics)} "
            f"dup={receipt.duplicate_of is not None}",
        )

    console.print(
        f"\n[bold]Done.[/] schools={total_schools} metrics={total_metrics} "
        f"aliases={total_aliases}",
    )
    graph.close()


@ingest_app.command("l1-db")
def ingest_l1_db(
    ctx: typer.Context,
    dump: Annotated[Path, typer.Argument(help="PostgreSQL custom-format dump.")],
    sql_file: Annotated[Path | None, typer.Option(
        help="Pre-extracted pg_restore --data-only SQL (skips pg_restore).")] = None,
    pg_restore_bin: Annotated[str | None, typer.Option(
        "--pg-restore", help="Path to pg_restore (else PATH + Program Files).")] = None,
) -> None:
    """Ingest the L1 canonical school universe from a PostgreSQL dump of the reference DB.

    78 dental schools + 322 aliases become the L1 **canonical backbone** (for forum
    mention extraction) + rich immutable `School` nodes carrying the gold facts.
    """

    data = ctx.obj
    if sql_file is not None:
        sql_text = sql_file.read_text(encoding="utf-8", errors="replace")
    else:
        console.print(f"[bold]Extracting backbone tables from[/] {dump.name} via pg_restore…")
        sql_text = extract_from_dump(dump, pg_restore_bin=pg_restore_bin)

    source_dump_id = f"db:{dump.name}"
    result = build_l1_from_dump(sql_text, source_dump_id=source_dump_id)
    if not result.schools:
        console.print("[red]no schools parsed[/] — check the dump/SQL input.")
        raise typer.Exit(code=1)

    adapter = L1ExcelAdapter(sqlite_path=data["sqlite_path"])
    adapter.persist(
        L1IngestResult(cycle_year="2026", schools=result.schools, metrics=[],
                       aliases=result.aliases),
        source_dump_id=source_dump_id,
    )
    graph = KuzuGraphClient(db_path=data["graph_path"])
    graph.upsert_nodes(result.nodes)
    idx = CanonicalIndex(sqlite_path=data["sqlite_path"])
    console.print(
        f"[green]ok[/] L1 DB ingest: schools={len(result.schools)} "
        f"School nodes={len(result.nodes)} aliases(raw)={len(result.aliases)} "
        f"canonical aliases indexed={idx.alias_count()} "
        f"canonical schools={idx.canonical_count()}",
    )
    graph.close()


@ingest_app.command("l1-residency")
def ingest_l1_residency(
    ctx: typer.Context,
    dump: Annotated[Path, typer.Argument(help="PostgreSQL custom-format dump.")],
    sql_file: Annotated[Path | None, typer.Option(
        help="Pre-extracted pg_restore --data-only SQL (skips pg_restore).")] = None,
    pg_restore_bin: Annotated[str | None, typer.Option(
        "--pg-restore", help="Path to pg_restore (else PATH + Program Files).")] = None,
) -> None:
    """Ingest the L1 canonical program universe from a PostgreSQL dump of the reference DB.

    Specialty (31) + Institution (~298) + Program (~817) L1 nodes with OFFERED_BY /
    IN_SPECIALTY edges; specialty + institution names/aliases (OMFS, Perio, Endo …)
    extend the canonical ER backbone alongside the dental schools.
    """

    data = ctx.obj
    if sql_file is not None:
        sql_text = sql_file.read_text(encoding="utf-8", errors="replace")
    else:
        console.print(f"[bold]Extracting programs_* tables from[/] {dump.name} via pg_restore…")
        sql_text = extract_residency_from_dump(dump, pg_restore_bin=pg_restore_bin)

    source_dump_id = f"db:{dump.name}"
    result = build_residency_from_dump(sql_text, source_dump_id=source_dump_id)
    if not result.programs:
        console.print("[red]no residency programs parsed[/] — check the dump/SQL input.")
        raise typer.Exit(code=1)

    adapter = L1ExcelAdapter(sqlite_path=data["sqlite_path"])
    adapter.persist(
        L1IngestResult(cycle_year="2026", schools=result.canonical_registry, metrics=[],
                       aliases=result.aliases),
        source_dump_id=source_dump_id,
    )
    graph = KuzuGraphClient(db_path=data["graph_path"])
    graph.upsert_nodes(result.nodes)
    graph.upsert_edges(result.edges)
    idx = CanonicalIndex(sqlite_path=data["sqlite_path"])
    console.print(
        f"[green]ok[/] L1 residency ingest: specialties={len(result.specialties)} "
        f"institutions={len(result.institutions)} programs={len(result.programs)} "
        f"edges={len(result.edges)} aliases(raw)={len(result.aliases)} "
        f"canonical entities={idx.canonical_count()} aliases indexed={idx.alias_count()}",
    )
    graph.close()


@ingest_app.command("l1-claims")
def ingest_l1_claims(ctx: typer.Context) -> None:
    """Materialize L1 gold facts as immutable L1 `Claim` nodes (ADR-026 anchor).

    Reads the `School`/`Program` L1 nodes (DB facts: board pass rate, positions,
    stipend …) + the ADEA `l1_school_year_metric` rows (resident/non-resident
    tuition) and emits one L1 `Claim` per (entity, predicate) so the conflict
    resolver can adjudicate them against organic L5 forum claims.
    """

    data = ctx.obj
    source_dump_id = "l1:gold"
    graph = KuzuGraphClient(db_path=data["graph_path"])
    db_claims = build_db_fact_claims(graph, source_dump_id=source_dump_id)
    adea_claims = build_adea_metric_claims(
        data["sqlite_path"], source_dump_id=source_dump_id,
    )
    graph.upsert_nodes(db_claims)
    graph.upsert_nodes(adea_claims)
    console.print(
        f"[green]ok[/] L1 fact claims: db_facts={len(db_claims)} "
        f"adea_tuition={len(adea_claims)} total={len(db_claims) + len(adea_claims)}",
    )
    graph.close()


@ingest_app.command("l5-reddit")
def ingest_l5_reddit(
    ctx: typer.Context,
    posts: Annotated[Path, typer.Argument(help="Posts JSONL.")],
    comments: Annotated[Path | None, typer.Argument(help="Comments JSONL.")] = None,
    pass2_labels: Annotated[bool, typer.Option(help="Run Pass 2 flair → Topic.")] = True,
    max_posts: Annotated[int | None, typer.Option(help="Sample cap (V1 smoke).")] = None,
    extract_mentions: Annotated[bool, typer.Option(help="Run Pass 1 MENTIONS_SCHOOL extraction.")] = True,
    llm_matcher: Annotated[bool, typer.Option(help="ADR-022: escalate borderline mentions to a gateway LLM matcher.")] = False,
    topic_filter: Annotated[str, typer.Option(help="Keep posts matching: 'admissions' (KI-006 default) | 'none' | comma-list.")]
        = "none",
) -> None:
    """Ingest a Reddit subreddit dump (posts + optional comments)."""

    data = ctx.obj
    ingest = IngestionService(
        dumps_root=data["dumps_root"], sqlite_path=data["sqlite_path"],
    )
    audit = AuditLog(sqlite_path=data["sqlite_path"])
    graph = KuzuGraphClient(db_path=data["graph_path"])

    now = utc_now()
    payload = [posts] + ([comments] if comments is not None else [])
    manifest = DumpManifest(
        source_name=f"reddit_{posts.stem}",
        source_tier="L5", rank_default="normal",
        license="Reddit ToS / Pushshift",
        t_valid_range=(datetime(2007, 1, 1, tzinfo=now.tzinfo),
                       datetime(2030, 12, 31, tzinfo=now.tzinfo)),
        provenance={"posts_file": posts.name,
                    "comments_file": comments.name if comments else None},
    )
    receipt = ingest.register_dump("L5", manifest, payload)
    audit.log_ingestion(
        dump_id=receipt.dump_id, source_tier="L5",
        source_name=manifest.source_name, file_count=len(payload),
    )

    kw_filter: list[str] | None
    if topic_filter == "admissions":
        kw_filter = list(DEFAULT_ADMISSIONS_KEYWORDS)
    elif topic_filter == "none":
        kw_filter = None
    else:
        kw_filter = [k.strip() for k in topic_filter.split(",") if k.strip()]
    result = L5RedditAdapter().parse(posts, comments, keyword_filter=kw_filter)
    if max_posts is not None and max_posts < len(result.posts):
        # Subset for smoke: keep most-recent N posts + comments tied to them.
        keep = sorted(result.posts, key=lambda p: p.created_utc, reverse=True)[:max_posts]
        keep_ids = {p.post_id for p in keep}
        kept_comments = [c for c in result.comments if c.post_id in keep_ids]
        kept_user_ids = {p.author_user_id for p in keep if p.author_user_id} | {
            c.author_user_id for c in kept_comments if c.author_user_id
        }
        kept_users = [u for u in result.users if u.user_id in kept_user_ids]
        result = L5RedditResult(
            subreddit=result.subreddit, posts=keep,
            comments=kept_comments, users=kept_users,
        )

    extractor = None
    if extract_mentions:
        idx = CanonicalIndex(sqlite_path=data["sqlite_path"])
        if idx.alias_count() > 0:
            matcher = GatewayLLMMatcher(default_gateway()) if llm_matcher else None
            extractor = Pass1MentionExtractor(idx, llm_matcher=matcher)
    structural = Pass1StructuralBuilder().assemble_reddit(
        result, ingest_time=now, mention_extractor=extractor,
    )
    graph.upsert_nodes(structural.nodes)
    graph.upsert_edges(structural.edges)
    console.print(
        f"[green]ok[/] reddit r/{result.subreddit}: posts={len(result.posts)} "
        f"comments={len(result.comments)} users={len(result.users)} "
        f"nodes={len(structural.nodes)} edges={len(structural.edges)}",
    )

    if pass2_labels:
        labels = Pass2LabelsBuilder().build_reddit(result, ingest_time=now)
        graph.upsert_nodes(labels.nodes)
        graph.upsert_edges(labels.edges)
        console.print(
            f"[green]ok[/] pass2: topics={len(labels.nodes)} "
            f"references_topic_edges={len(labels.edges)}",
        )

    graph.close()


@ingest_app.command("l5-reddit-batched")
def ingest_l5_reddit_batched(
    ctx: typer.Context,
    posts: Annotated[Path, typer.Argument(help="Posts JSONL.")],
    comments: Annotated[Path | None, typer.Argument(help="Comments JSONL.")] = None,
    batch_size: Annotated[int, typer.Option(help="Posts per checkpointed batch.")] = 2000,
    rest_seconds: Annotated[float, typer.Option(help="Idle pause between batches to throttle sustained load (Kernel-Power 41 mitigation).")] = 0.0,
    disk_flush: Annotated[bool, typer.Option(help="Force OS cache → disk after each batch (power-cut durability).")] = True,
    pass2_labels: Annotated[bool, typer.Option(help="Run Pass 2 flair → Topic.")] = True,
    extract_mentions: Annotated[bool, typer.Option(help="Run Pass 1 MENTIONS_SCHOOL extraction.")] = True,
    llm_matcher: Annotated[bool, typer.Option(help="ADR-022: escalate borderline mentions to a gateway LLM matcher.")] = False,
    topic_filter: Annotated[str, typer.Option(help="'admissions' | 'none' | comma-list.")] = "none",
    restart: Annotated[bool, typer.Option(help="Clear the checkpoint and re-ingest from scratch.")] = False,
    max_posts_per_run: Annotated[int | None, typer.Option(
        help="Process at most N still-pending posts this invocation, then exit "
             "CLEANLY (a clean exit flushes Kùzu durably). A wrapper loop re-runs "
             "for the next chunk — bounds peak memory so an OOM-kill can't discard "
             "buffered graph writes.")] = None,
) -> None:
    """Crash-resilient r/<subreddit> ingest (Q-028): process posts in checkpointed
    batches so a host crash resumes from the last committed batch. Re-run the same
    command to resume; graph writes are idempotent (Kùzu MERGE)."""

    data = ctx.obj
    ingest = IngestionService(dumps_root=data["dumps_root"], sqlite_path=data["sqlite_path"])
    audit = AuditLog(sqlite_path=data["sqlite_path"])
    graph = KuzuGraphClient(db_path=data["graph_path"])
    now = utc_now()

    payload = [posts] + ([comments] if comments is not None else [])
    manifest = DumpManifest(
        source_name=f"reddit_{posts.stem}", source_tier="L5", rank_default="normal",
        license="Reddit ToS / Pushshift",
        t_valid_range=(datetime(2007, 1, 1, tzinfo=now.tzinfo),
                       datetime(2030, 12, 31, tzinfo=now.tzinfo)),
        provenance={"posts_file": posts.name,
                    "comments_file": comments.name if comments else None},
    )
    receipt = ingest.register_dump("L5", manifest, payload)
    audit.log_ingestion(dump_id=receipt.dump_id, source_tier="L5",
                        source_name=manifest.source_name, file_count=len(payload))

    if topic_filter == "admissions":
        kw_filter: list[str] | None = list(DEFAULT_ADMISSIONS_KEYWORDS)
    elif topic_filter == "none":
        kw_filter = None
    else:
        kw_filter = [k.strip() for k in topic_filter.split(",") if k.strip()]

    console.print("[bold]parsing dump…[/] (re-parsed each resume; the durable bit is the checkpoint)")
    result = L5RedditAdapter().parse(posts, comments, keyword_filter=kw_filter)

    ckpt = L5IngestCheckpoint(data["sqlite_path"], source_key=manifest.source_name)
    if restart:
        ckpt.clear()

    extractor = None
    if extract_mentions:
        idx = CanonicalIndex(sqlite_path=data["sqlite_path"])
        if idx.alias_count() > 0:
            matcher = GatewayLLMMatcher(default_gateway()) if llm_matcher else None
            extractor = Pass1MentionExtractor(idx, llm_matcher=matcher)

    flush_drive = None
    if disk_flush:
        flush_drive = (Path(data["graph_path"]).resolve().drive or "C:").rstrip(":")
    job = L5BatchJob(
        graph=graph, checkpoint=ckpt, result=result, extractor=extractor,
        ingest_time=now, batch_size=batch_size, pass2_labels=pass2_labels,
        rest_seconds=rest_seconds, flush_drive=flush_drive,
        edge_stage_path=str(Path(data["graph_path"]).parent / "_edges_stage.csv"),
    )
    # Self-heal any checkpoint drift from a prior crash (lost Kùzu writes): the
    # graph is the source of truth, so re-ingest posts the checkpoint claims but
    # the graph lacks.
    reclaimed = reconcile_checkpoint_to_graph(job)
    if reclaimed:
        console.print(
            f"[yellow]reconciled[/] {reclaimed} posts were checkpointed but lost "
            "from the graph in a crash — re-ingesting them",
        )
    pending = pending_posts(job)
    if max_posts_per_run is not None and max_posts_per_run > 0:
        pending = pending[:max_posts_per_run]  # bound this run; wrapper loop does the rest
    console.print(
        f"r/{result.subreddit}: posts total={len(result.posts)} done={ckpt.count()} "
        f"pending={len(pending)} (batch_size={batch_size})",
    )

    def _progress(p: BatchProgress) -> None:
        console.print(
            f"[green]batch {p.index}/{p.total}[/] posts={p.posts} comments={p.comments} "
            f"| run nodes={p.run_nodes} edges={p.run_edges} | total done={p.total_done}",
        )

    run_nodes, run_edges = run_l5_batches(job, pending, on_batch=_progress)
    console.print(
        f"[bold green]DONE[/] r/{result.subreddit}: {ckpt.count()} posts ingested "
        f"(this run: {run_nodes} nodes / {run_edges} edges)",
    )
    graph.close()


@ingest_app.command("l2-html")
def ingest_l2_html(
    ctx: typer.Context,
    paths: list[Path],
    source_name: Annotated[str, typer.Option(help="Logical L2 source name (e.g., 'ADEA Blog').")]
        = "L2 source",
) -> None:
    """Ingest one or more HTML files as L2 unstructured-truth documents.

    Per Phase 2 + ADR-005 trust ladder. Each HTML file → one `L2Document`
    node + a `PROVENANCE` edge linking back to the dump.

    Example:
      secbrain ingest l2-html "External Data/L2 Demo/*.html" --source-name "ADEA Blog"
    """

    data = ctx.obj
    ingest = IngestionService(
        dumps_root=data["dumps_root"], sqlite_path=data["sqlite_path"],
    )
    audit = AuditLog(sqlite_path=data["sqlite_path"])
    graph = KuzuGraphClient(db_path=data["graph_path"])
    builder = Pass1StructuralBuilder()

    real_paths = [p for p in paths if p.is_file()]
    if not real_paths:
        console.print(f"[red]no HTML files found at:[/] {paths}")
        graph.close()
        return

    now = utc_now()
    manifest = DumpManifest(
        source_name=source_name,
        source_tier="L2", rank_default="preferred",
        license="L2 official source — internal V1 use only",
        t_valid_range=(datetime(2000, 1, 1, tzinfo=now.tzinfo),
                       datetime(2030, 12, 31, tzinfo=now.tzinfo)),
        provenance={"file_count": len(real_paths)},
    )
    receipt = ingest.register_dump("L2", manifest, real_paths)
    audit.log_ingestion(
        dump_id=receipt.dump_id, source_tier="L2",
        source_name=source_name, file_count=len(real_paths),
        duplicate_of=receipt.duplicate_of,
    )

    result = L2HtmlAdapter().parse(real_paths, source_name=source_name)
    structural = builder.assemble_l2(
        result, source_dump_id=receipt.dump_id, ingest_time=now,
    )
    graph.upsert_nodes(structural.nodes)
    graph.upsert_edges(structural.edges)
    console.print(
        f"[green]ok[/] l2: source={source_name!r} documents={len(result.documents)} "
        f"nodes={len(structural.nodes)} edges={len(structural.edges)} "
        f"dup={receipt.duplicate_of is not None}",
    )
    graph.close()


@ingest_app.command("l1-pdf")
def ingest_l1_pdf(
    ctx: typer.Context,
    paths: list[Path],
    source_name: Annotated[str, typer.Option(help="Logical L1 PDF source name (e.g. 'ADEA_Report_4').")]
        = "ADEA_Report_4",
) -> None:
    """Ingest one or more ADEA SDE4 (Curriculum) PDF files as L1Document nodes.

    SDE4 is narrative survey data; each page becomes one L1Document node tagged
    source_tier=L1. Per-school + per-curriculum-topic structured extraction is V2
    (GAP-045 cont'd). Searchable via the hybrid retrieval index.

    Example:
      secbrain ingest l1-pdf "External Data/.../SDE4_2023-24.pdf"
    """

    data = ctx.obj
    ingest = IngestionService(
        dumps_root=data["dumps_root"], sqlite_path=data["sqlite_path"],
    )
    audit = AuditLog(sqlite_path=data["sqlite_path"])
    graph = KuzuGraphClient(db_path=data["graph_path"])
    builder = Pass1StructuralBuilder()

    real_paths = [p for p in paths if p.is_file()]
    if not real_paths:
        console.print(f"[red]no PDFs found:[/] {paths}")
        graph.close()
        return

    now = utc_now()
    total_pages = 0
    for path in real_paths:
        manifest = DumpManifest(
            source_name=source_name,
            source_tier="L1", rank_default="preferred",
            license="ADEA proprietary; internal V1 use only",
            t_valid_range=(datetime(2010, 1, 1, tzinfo=now.tzinfo),
                           datetime(2030, 12, 31, tzinfo=now.tzinfo)),
            provenance={"file_name": path.name},
        )
        receipt = ingest.register_dump("L1", manifest, [path])
        audit.log_ingestion(
            dump_id=receipt.dump_id, source_tier="L1",
            source_name=source_name, file_count=1,
            duplicate_of=receipt.duplicate_of,
        )
        result = L1PDFAdapter().parse(path, source_name=source_name)
        structural = builder.assemble_l1_pdf(
            result, source_dump_id=receipt.dump_id, ingest_time=now,
        )
        graph.upsert_nodes(structural.nodes)
        graph.upsert_edges(structural.edges)
        total_pages += len(result.pages)
        console.print(
            f"[green]ok[/] {path.name}: cycle={result.cycle_year} "
            f"pages={len(result.pages)} dup={receipt.duplicate_of is not None}",
        )

    console.print(f"\n[bold]Done.[/] pages={total_pages}")
    graph.close()


@ingest_app.command("l5-sdn")
def ingest_l5_sdn(
    ctx: typer.Context,
    metadata: Annotated[Path, typer.Argument(help="sdn_thread_metadata.jsonl")],
    posts_dir: Annotated[Path, typer.Argument(help="Dir containing thread_<id>_posts.jsonl")],
    category: Annotated[str, typer.Option(help="Category filter (set to ALL to disable).")]
        = "Pre-Dental",
    max_threads: Annotated[int | None, typer.Option(help="V1 sample cap.")] = 1000,
) -> None:
    """Ingest the SDN forum (Pre-Dental subset by default)."""

    data = ctx.obj
    ingest = IngestionService(
        dumps_root=data["dumps_root"], sqlite_path=data["sqlite_path"],
    )
    audit = AuditLog(sqlite_path=data["sqlite_path"])
    graph = KuzuGraphClient(db_path=data["graph_path"])

    now = utc_now()
    manifest = DumpManifest(
        source_name=f"sdn_{category.lower().replace(' ', '_')}",
        source_tier="L5", rank_default="normal",
        license="SDN ToS",
        t_valid_range=(datetime(2003, 1, 1, tzinfo=now.tzinfo),
                       datetime(2030, 12, 31, tzinfo=now.tzinfo)),
        provenance={"metadata_file": metadata.name, "posts_dir": str(posts_dir)},
    )
    receipt = ingest.register_dump("L5", manifest, [metadata])
    audit.log_ingestion(
        dump_id=receipt.dump_id, source_tier="L5",
        source_name=manifest.source_name, file_count=1,
    )

    cat = None if category.upper() == "ALL" else category
    result = L5SDNAdapter().parse(
        metadata, posts_dir, category=cat, max_threads=max_threads,
    )
    idx = CanonicalIndex(sqlite_path=data["sqlite_path"])
    extractor = Pass1MentionExtractor(idx) if idx.alias_count() > 0 else None
    structural = Pass1StructuralBuilder().assemble_sdn(
        result, ingest_time=now, mention_extractor=extractor,
    )
    graph.upsert_nodes(structural.nodes)
    _valid = {n.id for n in structural.nodes}
    _r = graph._conn.execute("MATCH (n:Node) RETURN n.id")
    while _r.has_next():
        _valid.add(str(_r.get_next()[0]))
    graph.copy_edges([e for e in structural.edges
                      if e.from_id in _valid and e.to_id in _valid])
    if structural.hitl_items:
        hitl_queue = HITLQueue(sqlite_path=data["sqlite_path"])
        for item in structural.hitl_items:
            hitl_queue.enqueue(
                item_type=item.item_type, payload=item.payload,
            )
    console.print(
        f"[green]ok[/] sdn: threads={len(result.threads)} posts={len(result.posts)} "
        f"users={len(result.users)} nodes={len(structural.nodes)} "
        f"edges={len(structural.edges)} hitl={len(structural.hitl_items)}",
    )
    graph.close()


@app.command()
def cluster(
    ctx: typer.Context,
    sample: Annotated[int, typer.Option(help="Number of Posts to cluster.")] = 100,
    n_clusters: Annotated[int, typer.Option(help="Target cluster count (ignored for HDBSCAN).")] = 8,
    min_cluster_size: Annotated[int, typer.Option()] = 2,
    source: Annotated[str, typer.Option(help="reddit / sdn / all")] = "reddit",
    embedder: Annotated[str, typer.Option(help="hash | bge | qwen (Qwen3, ADR-022 primary)")] = "bge",
    device: Annotated[str, typer.Option(help="cpu | cuda | auto (honors CUDA_VISIBLE_DEVICES)")] = "cpu",
    method: Annotated[str, typer.Option(help="kmeans | hdbscan (V1.x density-based)")] = "kmeans",
    write_back: Annotated[bool, typer.Option()] = True,
) -> None:
    """Pass 3 semantic clustering: BGE-small embeddings + KMeans + per-cluster Gemini summary."""

    data = ctx.obj
    graph = KuzuGraphClient(db_path=data["graph_path"])
    gw = default_gateway()

    emb_svc: EmbeddingService = _build_embedder(embedder, device)

    inputs = _read_post_inputs(graph, source=source, limit=sample)
    if not inputs:
        console.print(f"[yellow]No posts found (source={source}).[/]")
        graph.close()
        return

    posts: list[tuple[str, str]] = [
        (p.post_id, p.text) for p in inputs if p.text.strip()
    ]
    console.print(
        f"[bold]Pass 3 cluster sweep:[/] posts={len(posts)} embedder={embedder} "
        f"n_clusters={n_clusters}",
    )

    runner = Pass3ClusterRunner(
        embedder=emb_svc, gateway=gw,
        n_clusters=n_clusters, min_cluster_size=min_cluster_size,
        method=method,
    )
    out = runner.run(posts, ingest_time=utc_now())

    if write_back and out.nodes:
        graph.upsert_nodes(out.nodes)
        graph.copy_edges(out.edges)   # COPY path (see extract / KuzuGraphClient.copy_edges)

    table = Table(title="Pass 3 clusters")
    table.add_column("cluster_id")
    table.add_column("label")
    table.add_column("members", justify="right")
    for c in out.clusters:
        table.add_row(c.cluster_id[:24], c.label[:40], str(c.member_count))
    console.print(table)
    console.print(
        f"[bold]Total:[/] {len(out.clusters)} clusters · "
        f"{len(out.nodes)} cluster nodes · {len(out.edges)} edges · "
        f"cost ${out.cost_usd:.4f}",
    )
    graph.close()


@app.command()
def extract(  # noqa: PLR0915 — CLI handler accumulates option-handling branches
    ctx: typer.Context,
    task: Annotated[str, typer.Option(help="Pass 4 task: sentiment / interview_q / conflict_candidate / all.")]
        = "sentiment",
    sample: Annotated[int, typer.Option(help="Number of Posts to process.")] = 10,
    source: Annotated[str, typer.Option(help="Filter posts by source: reddit / sdn / all.")] = "reddit",
    write_back: Annotated[bool, typer.Option(help="Write resulting Claim/SentimentAnnotation/InterviewQuestion nodes back to graph.")] = True,
    measure_cascade: Annotated[bool, typer.Option(help="Run sweep twice (cold then warm) and report cache-hit rate (NFR-3).")] = False,
) -> None:
    """Run Pass 4 LLM extraction on a sample of Posts already in the graph.

    Uses `default_gateway()` per ADR-011 routing. Per-task cost printed at end.
    """

    data = ctx.obj
    graph = KuzuGraphClient(db_path=data["graph_path"])
    cache = ExtractionCache(sqlite_path=data["sqlite_path"])
    audit = AuditLog(sqlite_path=data["sqlite_path"])
    gw = default_gateway()

    tasks_arg: tuple[str, ...]
    if task == "all":
        tasks_arg = ("sentiment", "interview_q", "conflict_candidate")
    elif task in ("sentiment", "interview_q", "conflict_candidate"):
        tasks_arg = (task,)
    else:
        console.print(f"[red]unknown task:[/] {task}")
        raise typer.Exit(code=2)

    inputs = _read_post_inputs(graph, source=source, limit=sample)
    if not inputs:
        console.print(
            f"[yellow]No Posts found in graph (source={source}). "
            f"Run `ingest l5-reddit ...` first.[/]",
        )
        graph.close()
        return

    console.print(
        f"[bold]Pass 4 sweep:[/] tasks={tasks_arg} posts={len(inputs)} "
        f"source={source}",
    )
    results = list(run_pass4_sweep(
        inputs, tasks=tasks_arg,  # type: ignore[arg-type]
        gateway=gw, cache=cache, audit=audit, ingest_time=utc_now(),
    ))
    s = summarize(results)

    if write_back:
        all_nodes = [n for r in results for n in r.nodes]
        all_edges = [e for r in results for e in r.edges]
        if all_nodes:
            graph.upsert_nodes(all_nodes)
        if all_edges:
            # COPY path, not incremental upsert_edges: the latter OOMs the Kùzu
            # buffer pool appending edges onto the 1.46M-edge graph (see
            # KuzuGraphClient.copy_edges). Endpoint nodes were just upserted above.
            graph.copy_edges(all_edges)
        console.print(
            f"[green]wrote[/] nodes={len(all_nodes)} edges={len(all_edges)} "
            "to graph.",
        )

    table = Table(title="Pass 4 sweep results")
    table.add_column("metric")
    table.add_column("value", justify="right")
    table.add_row("total inputs", str(s.total_inputs))
    table.add_row("filtered out", str(s.filtered_out))
    table.add_row("processed", str(s.processed))
    table.add_row("cache hits", str(s.cache_hits))
    table.add_row("sentiment annotations", str(s.sentiment_count))
    table.add_row("interview questions", str(s.interview_q_count))
    table.add_row("conflict candidates", str(s.conflict_candidate_count))
    table.add_row("total cost USD", f"${s.total_cost_usd:.4f}")
    console.print(table)

    if measure_cascade and s.processed > 0:
        # Re-run the same sample; all cache hits this time → cost should be 0.
        warm_results = list(run_pass4_sweep(
            inputs, tasks=tasks_arg,  # type: ignore[arg-type]
            gateway=gw, cache=cache, audit=audit, ingest_time=utc_now(),
        ))
        warm = summarize(warm_results)
        cold_hit_rate = (
            s.cache_hits / s.processed if s.processed else 0.0
        )
        warm_hit_rate = (
            warm.cache_hits / warm.processed if warm.processed else 0.0
        )
        cascade = Table(title="Cost cascade (NFR-3)")
        cascade.add_column("sweep")
        cascade.add_column("cache_hit_rate", justify="right")
        cascade.add_column("cost USD", justify="right")
        cascade.add_row("cold", f"{cold_hit_rate:.0%}", f"${s.total_cost_usd:.4f}")
        cascade.add_row("warm", f"{warm_hit_rate:.0%}", f"${warm.total_cost_usd:.4f}")
        console.print(cascade)
        if warm_hit_rate < 0.80:
            console.print(
                f"[yellow]NFR-3 warning:[/] warm cache hit rate "
                f"{warm_hit_rate:.0%} is below the 80% threshold.",
            )
        else:
            console.print(
                f"[green]NFR-3 PASS:[/] warm cache hit rate {warm_hit_rate:.0%} >= 80%.",
            )
    graph.close()


def _read_post_inputs(
    graph: KuzuGraphClient, *, source: str, limit: int,
) -> list[Pass4Input]:
    """Stream up to `limit` Post nodes from the graph for Pass 4 input."""

    conn = graph._conn
    where = ""
    if source == "reddit":
        where = "AND n.id STARTS WITH 'reddit_post:' "
    elif source == "sdn":
        where = "AND n.id STARTS WITH 'sdn_post:' "
    result = conn.execute(
        f"MATCH (n:Node) WHERE n.label = 'Post' {where}"
        "OPTIONAL MATCH (u:Node)-[r:Edge]->(n) WHERE r.label = 'AUTHORED' "
        "RETURN n.id, n.properties_json, u.id LIMIT $cap",
        parameters={"cap": int(limit)},
    )
    scan = result[-1] if isinstance(result, list) else result
    out: list[Pass4Input] = []
    while scan.has_next():
        row = list(scan.get_next())
        post_id = str(row[0])
        try:
            props = json.loads(row[1] or "{}")
        except (json.JSONDecodeError, TypeError):
            props = {}
        if not isinstance(props, dict):
            props = {}
        user_id = row[2] if len(row) > 2 else None
        title = str(props.get("title") or "")
        body = str(props.get("selftext") or props.get("body") or "")
        text = (title + "\n" + body).strip()
        author = str(user_id) if user_id else None
        created_iso = props.get("created_utc")
        try:
            created = (
                datetime.fromisoformat(created_iso)
                if isinstance(created_iso, str) and created_iso else None
            )
        except ValueError:
            created = None
        # Cheap "mentions_entity" heuristic: any uppercase 3+ letter sequence
        # or known school keyword suggests an entity is named.
        mentions_entity = bool(
            text and any(w.isupper() and len(w) >= 3 for w in text.split()),
        )
        out.append(Pass4Input(
            post_id=post_id, text=text, author=author,
            is_reply=False, created_utc=created, mentions_entity=mentions_entity,
        ))
    return out


@app.command()
def query(
    ctx: typer.Context,
    text: str,
    source_tier_min: Annotated[str | None, typer.Option(help="L1..L5 minimum tier.")] = None,
    traversal_depth: Annotated[int, typer.Option()] = 2,
    limit: Annotated[int, typer.Option()] = 20,
    as_of: Annotated[str | None, typer.Option(help="ISO timestamp for bitemporal as_of.")] = None,
    hybrid: Annotated[bool, typer.Option(help="Seed via the BM25+HNSW+RRF HybridIndex (ADR-002).")] = True,
    embedder: Annotated[str, typer.Option(help="hash | bge | qwen — HybridIndex vector side.")] = "hash",
    device: Annotated[str, typer.Option(help="cpu | cuda | auto for the bge embedder.")] = "cpu",
) -> None:
    """`query_graph` against the built graph. Prints a Rich table of results."""

    data = ctx.obj
    graph = KuzuGraphClient(db_path=data["graph_path"])
    canonical = CanonicalIndex(sqlite_path=data["sqlite_path"])
    audit = AuditLog(sqlite_path=data["sqlite_path"])
    hybrid_index: HybridIndex | None = None
    if hybrid:
        emb: EmbeddingService = _build_embedder(embedder, device)
        hybrid_index = HybridIndex(embedder=emb)
        hybrid_index.build(graph.all_nodes())
    svc = RetrievalService(
        graph=graph, canonical_index=canonical, hybrid_index=hybrid_index,
    )

    as_of_dt = datetime.fromisoformat(as_of) if as_of else None
    results = svc.query_graph(
        text,
        source_tier_min=source_tier_min,  # type: ignore[arg-type]
        traversal_depth=traversal_depth,
        limit=limit,
        as_of=as_of_dt,
    )
    audit.log_retrieval(
        query_text=text, result_count=len(results),
        traversal_depth=traversal_depth, time_range=None,
        as_of=as_of, latency_ms=None,
    )

    table = Table(title=f"query: {text!r}  ({len(results)} results)")
    table.add_column("node_id")
    table.add_column("type")
    table.add_column("tier")
    table.add_column("refs")
    for r in results:
        table.add_row(
            r.node_id, r.node_type, r.source_tier,
            ", ".join(r.references[:2]) + ("…" if len(r.references) > 2 else ""),
        )
    console.print(table)
    graph.close()


@app.command()
def ask(
    ctx: typer.Context,
    question: str,
    facts_only: Annotated[bool, typer.Option(
        help="Skip the LLM; print the retrieved facts JSON only.")] = False,
) -> None:
    """NL question -> grounded answer over the KB (consensus + ADEA + sentiment).

    Wraps `src/retrieval/kb_agent.py` (productionized 2026-06-09). Uses the graph
    at `<data_dir>/graph/kuzu.db`; LLM via the gateway's Together gpt-oss-20b
    (degrades to facts-only when no key is present).
    """

    from src.retrieval.kb_agent import KBAgent  # noqa: PLC0415 — heavy load, lazy

    agent = KBAgent(graph_path=ctx.obj["graph_path"])
    try:
        if facts_only:
            console.print_json(json.dumps(agent.retrieve(question), default=str))
            return
        out = agent.answer(question)
        console.print(f"[bold]intent[/bold]: {out['intent']}")
        if out["answer"]:
            console.print(out["answer"])
        else:
            console.print("[yellow]no LLM available — facts only:[/yellow]")
            console.print_json(json.dumps(out["facts"], default=str))
    finally:
        agent.close()


@app.command()
def canonical(
    ctx: typer.Context,
    alias: str,
    entity_type: Annotated[str, typer.Option()] = "School",
) -> None:
    """`get_canonical_entity` per FR-8.2."""

    data = ctx.obj
    graph = KuzuGraphClient(db_path=data["graph_path"])
    index = CanonicalIndex(sqlite_path=data["sqlite_path"])
    svc = RetrievalService(graph=graph, canonical_index=index)
    result = svc.get_canonical_entity(alias, entity_type)  # type: ignore[arg-type]
    if result is None:
        console.print(f"[yellow]No L1 match for[/] {alias!r}")
    else:
        console.print_json(json.dumps({
            "canonical_id": result.canonical_id,
            "canonical_name": result.canonical_name,
            "type": result.type,
            "match_confidence": result.match_confidence,
            "aliases": result.aliases[:5],
        }))
    graph.close()


@app.command()
def stats(ctx: typer.Context) -> None:
    """Print node + edge counts + audit log size."""

    data = ctx.obj
    graph = KuzuGraphClient(db_path=data["graph_path"])
    audit = AuditLog(sqlite_path=data["sqlite_path"])

    counts: dict[str, int] = {}
    for label in (
        "School", "Metric", "CycleYear", "Subreddit", "User", "Post",
        "Comment", "Topic", "SDNThread", "SDNCategory", "L2Document",
        "L1Document",
        "SentimentAnnotation", "InterviewQuestion", "Claim", "Cluster",
    ):
        c = graph.node_count(label=label)
        if c:
            counts[label] = c

    table = Table(title="Graph nodes")
    table.add_column("label")
    table.add_column("count", justify="right")
    for label, c in counts.items():
        table.add_row(label, str(c))
    console.print(table)
    console.print(f"[bold]Total nodes:[/] {graph.node_count()}")
    console.print(f"[bold]Total edges:[/] {graph.edge_count()}")
    console.print(f"[bold]Audit log rows:[/] {audit.count()}")
    graph.close()


@hitl_app.command("list")
def hitl_list(
    ctx: typer.Context,
    status: Annotated[str, typer.Option(help="Filter: pending | claimed | committed | escalated.")] = "",
    limit: Annotated[int, typer.Option()] = 50,
) -> None:
    from src.hitl.queue import ItemStatus  # noqa: PLC0415 — used only by this CLI cmd
    queue = HITLQueue(sqlite_path=ctx.obj["sqlite_path"])
    status_enum: ItemStatus | None = None
    if status:
        try:
            status_enum = ItemStatus(status)
        except ValueError as e:
            console.print(f"[red]invalid --status:[/] {e}")
            raise typer.Exit(code=2) from e
    items = queue.list_items(status=status_enum, limit=limit)
    title = f"HITL queue ({len(items)} most-recent"
    title += f", status={status})" if status else ")"
    table = Table(title=title)
    table.add_column("item_id")
    table.add_column("type")
    table.add_column("status")
    table.add_column("reviewer")
    for it in items:
        table.add_row(
            it.item_id, it.item_type, it.status.value,
            it.claimed_by or "-",
        )
    console.print(table)


@hitl_app.command("show")
def hitl_show(ctx: typer.Context, item_id: str) -> None:
    """Print full HITL item state — payload + decision if committed."""

    queue = HITLQueue(sqlite_path=ctx.obj["sqlite_path"])
    item = queue.get(item_id)
    if item is None:
        console.print(f"[red]No such item:[/] {item_id}")
        raise typer.Exit(code=1)
    console.print_json(json.dumps({
        "item_id": item.item_id,
        "item_type": item.item_type,
        "status": item.status.value,
        "claimed_by": item.claimed_by,
        "claimed_at": item.claimed_at.isoformat() if item.claimed_at else None,
        "committed_at": item.committed_at.isoformat() if item.committed_at else None,
        "payload": item.payload,
        "decision": (
            {"verdict": item.decision.verdict, "notes": item.decision.notes,
             "extra": item.decision.extra}
            if item.decision else None
        ),
    }))


@hitl_app.command("escalate")
def hitl_escalate(
    ctx: typer.Context,
    item_id: str,
    notes: Annotated[str, typer.Option(help="Reason for escalation.")] = "",
    verdict: Annotated[str, typer.Option(help="Verdict tag; defaults to 'escalate'.")] = "escalate",
) -> None:
    """Mark a HITL item escalated. Sugar for `commit --escalate`."""

    queue = HITLQueue(sqlite_path=ctx.obj["sqlite_path"])
    audit = AuditLog(sqlite_path=ctx.obj["sqlite_path"])
    after = queue.commit(item_id, Decision(verdict=verdict, notes=notes), escalate=True)
    if after is None:
        console.print(f"[red]No such item:[/] {item_id}")
        raise typer.Exit(code=1)
    audit.log_hitl(
        reviewer=after.claimed_by or "?", decision=verdict,
        item_id=item_id, item_type=after.item_type, notes=notes,
    )
    console.print(f"[yellow]escalated[/] {item_id} (notes={notes!r})")


@hitl_app.command("commit-from")
def hitl_commit_from(ctx: typer.Context, json_path: Path) -> None:
    """Read a `pull`-written JSON, finalize the decision via `commit`.

    Workflow: `pull` writes a JSON with `decision: {verdict: '', notes: ''}`;
    reviewer fills it in; this command reads it back.
    """

    if not json_path.is_file():
        console.print(f"[red]Not a file:[/] {json_path}")
        raise typer.Exit(code=2)
    blob = json.loads(json_path.read_text(encoding="utf-8"))
    item_id = str(blob.get("item_id") or "")
    decision_obj = blob.get("decision") or {}
    verdict = str(decision_obj.get("verdict") or "")
    notes = str(decision_obj.get("notes") or "")
    if not item_id or not verdict:
        console.print("[red]commit-from requires item_id + decision.verdict in the JSON[/]")
        raise typer.Exit(code=2)
    queue = HITLQueue(sqlite_path=ctx.obj["sqlite_path"])
    audit = AuditLog(sqlite_path=ctx.obj["sqlite_path"])
    escalate = verdict.lower() == "escalate"
    after = queue.commit(item_id, Decision(verdict=verdict, notes=notes), escalate=escalate)
    if after is None:
        console.print(f"[red]No such item:[/] {item_id}")
        raise typer.Exit(code=1)
    audit.log_hitl(
        reviewer=after.claimed_by or "?", decision=verdict,
        item_id=item_id, item_type=after.item_type, notes=notes,
    )
    console.print(f"[green]committed[/] {item_id}: {after.status.value} ({verdict})")


@hitl_app.command("pull")
def hitl_pull(
    ctx: typer.Context,
    reviewer: Annotated[str, typer.Option(
        envvar="SECBRAIN_REVIEWER", help="Who is claiming the item (recorded in the audit log).",
    )] = "reviewer",
) -> None:
    queue = HITLQueue(sqlite_path=ctx.obj["sqlite_path"])
    item = queue.pull(reviewer=reviewer)
    if item is None:
        console.print("[yellow]No pending items[/]")
        return
    out = ctx.obj["data_dir"] / "hitl" / f"{item.item_id}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "item_id": item.item_id, "item_type": item.item_type,
        "payload": item.payload,
        "decision": {"verdict": "", "notes": ""},
    }, indent=2), encoding="utf-8")
    console.print(f"[green]pulled[/] {item.item_id} → {out}")


@hitl_app.command("commit")
def hitl_commit(
    ctx: typer.Context,
    item_id: str,
    verdict: Annotated[str, typer.Option()] = "accept",
    notes: Annotated[str, typer.Option()] = "",
    escalate: Annotated[bool, typer.Option()] = False,
) -> None:
    queue = HITLQueue(sqlite_path=ctx.obj["sqlite_path"])
    audit = AuditLog(sqlite_path=ctx.obj["sqlite_path"])
    decision = Decision(verdict=verdict, notes=notes)
    after = queue.commit(item_id, decision, escalate=escalate)
    if after is None:
        console.print(f"[red]No such item:[/] {item_id}")
        return
    audit.log_hitl(
        reviewer=after.claimed_by or "?", decision=verdict,
        item_id=item_id, item_type=after.item_type, notes=notes,
    )
    console.print(f"[green]committed[/] {item_id}: {after.status.value} ({verdict})")


@app.command()
def resolve(ctx: typer.Context) -> None:
    """Reconcile Pass-4 `Claim` conflicts on the real graph (GAP-052).

    Builds the resolver WITH the 3-vendor judge + web-verifier (best-effort on
    env keys), groups Claim nodes by (subject, predicate), and reconciles each
    multi-claim group — same-tier same-year ties go to the panel, not HITL.
    """

    data = ctx.obj
    graph = KuzuGraphClient(db_path=data["graph_path"])
    resolver = ConflictResolver(
        judge=build_three_vendor_judge(),
        web_verifier=build_web_verifier(),
    )
    report = resolve_pass4_conflicts(
        graph, resolver, ingest_time=utc_now(),
        joint_resolver=build_joint_resolver_if_enabled(),  # ADR-026, flag-gated
        canonical_index=CanonicalIndex(sqlite_path=data["sqlite_path"]),  # subject align
    )
    table = Table(title="Conflict resolution (Pass-4 claims)")
    table.add_column("metric")
    table.add_column("value", justify="right")
    table.add_row("conflict groups", str(report.conflict_groups))
    table.add_row("judge-resolved", str(report.judge_resolved))
    table.add_row("trust-weighted", str(report.trust_weighted))
    table.add_row("L1-clash invalidated", str(report.l1_clash))
    table.add_row("HITL pending", str(report.hitl_pending))
    table.add_row("other", str(report.other))
    console.print(table)
    graph.close()


@app.command()
def reconcile_demo(ctx: typer.Context) -> None:
    """Quick demo of the conflict resolver against a synthetic L1 vs L5 case."""

    # GAP-052 / ADR-024: construct the resolver WITH the 3-vendor judge +
    # web-verifier (best-effort on env keys; falls back to HITL if absent).
    resolver = ConflictResolver(
        judge=build_three_vendor_judge(),
        web_verifier=build_web_verifier(),
    )
    l1 = Claim(
        claim_id="l1:nyu:tuition:2024",
        subject_id="school:nyu", predicate="tuition_resident",
        object_value=94108.0, source_tier="L1", rank="preferred",
        references=["dump:adea24"], credibility=1.0,
    )
    forum = Claim(
        claim_id="forum:nyu:tuition:2024",
        subject_id="school:nyu", predicate="tuition_resident",
        object_value=42000.0, source_tier="L5", rank="normal",
        references=["reddit_post:abc"], credibility=0.3,
    )
    outcome = resolver.reconcile(forum, [l1])
    console.print_json(json.dumps({
        "status": outcome.status.value,
        "winning_claim": outcome.winning_claim.claim_id if outcome.winning_claim else None,
        "losing_claims": [c.claim_id for c in outcome.losing_claims],
        "reason": outcome.reason,
    }))
    _ = ctx  # context unused in this demo path


def _drop_unused() -> None:  # pragma: no cover
    """Keep imports referenced even when typer's signature introspection inlines them."""

    _ = (DumpManifest, IngestionService, Iterable)


# ---------------------------------------------------------------------------
# Website crawl — V1.7 wiring (flows/website_crawl_worker.py)
# ---------------------------------------------------------------------------


def _crawl_resolve_domain_id(sqlite_path: Path, domain_or_id: str) -> str:
    """Accept either a `web:<hash>` domain_id or a bare domain name."""

    from src.ingestion.sources.website_crawl import WebsiteCrawlRegistry

    if domain_or_id.startswith("web:"):
        return domain_or_id
    registry = WebsiteCrawlRegistry(sqlite_path=sqlite_path)
    needle = domain_or_id.strip().lower()
    for row in registry.list_all():
        if row.domain == needle:
            return row.domain_id
    raise typer.BadParameter(
        f"domain '{domain_or_id}' is not registered (use `secbrain crawl register`)",
    )


@crawl_app.command("register")
def crawl_register(
    ctx: typer.Context,
    domain: Annotated[str, typer.Argument(help="e.g. natmatch.com")],
    tier: Annotated[str, typer.Option(help="L1 (official ground truth) or L2")] = "L1",
    stage: Annotated[str, typer.Option(help="L0 | L1 | L2 processing depth")] = "L1",
    cadence: Annotated[str, typer.Option(help="cron, e.g. '0 6 1 * *'")] = "0 6 1 * *",
    max_pages_per_run: Annotated[int, typer.Option()] = 500,
    max_pages_per_month: Annotated[int, typer.Option()] = 5000,
    max_usd_per_month: Annotated[float, typer.Option()] = 5.0,
    confirm_l1: Annotated[bool, typer.Option(
        "--confirm-l1", help="Required for tier=L1: confirms immutable ground-truth handling.",
    )] = False,
    notes: Annotated[str, typer.Option()] = "",
) -> None:
    """Register a crawl domain (idempotent re-register returns the row)."""

    from src.ingestion.sources.website_crawl import WebsiteCrawlRegistry

    registry = WebsiteCrawlRegistry(sqlite_path=ctx.obj["sqlite_path"])
    row = registry.register(
        domain=domain, tier=tier, stage=stage, cadence_cron=cadence,  # type: ignore[arg-type]
        actor="cli", max_pages_per_run=max_pages_per_run,
        max_pages_per_month=max_pages_per_month,
        max_usd_per_month=max_usd_per_month,
        confirm_l1_immutable=confirm_l1, notes=notes or None,
    )
    console.print_json(json.dumps({
        "domain_id": row.domain_id, "domain": row.domain, "tier": row.tier,
        "stage": row.stage, "status": row.status,
        "max_pages_per_run": row.max_pages_per_run,
    }))


@crawl_app.command("run")
def crawl_run(
    ctx: typer.Context,
    domain: Annotated[str, typer.Argument(help="Registered domain name or web:<id>")],
    pages: Annotated[int, typer.Option(help="Override max pages this run (0 = registry cap)")] = 0,
) -> None:
    """Crawl ONE domain end-to-end now (discover -> fetch -> L0 -> L1).

    Opens the graph exclusively — stop the web server first.
    """

    from flows.website_crawl_dispatcher import enqueue_job
    from flows.website_crawl_worker import crawl_domain_once

    data = ctx.obj
    domain_id = _crawl_resolve_domain_id(data["sqlite_path"], domain)
    job_id = enqueue_job(
        sqlite_path=data["sqlite_path"], domain_id=domain_id,
        scheduled_at=utc_now(), trigger="manual",
    )
    graph = KuzuGraphClient(db_path=data["graph_path"])
    try:
        report = crawl_domain_once(
            domain_id, job_id,
            sqlite_path=data["sqlite_path"], graph=graph,
            cache_dir=data["data_dir"] / "crawl_cache",
            max_pages_override=pages or None,
            progress=lambda m: console.print(m),
        )
    finally:
        graph.close()
    # Mark the job row finished (direct run bypasses the dispatcher).
    import sqlite3 as _sqlite3
    with _sqlite3.connect(data["sqlite_path"]) as conn:
        conn.execute(
            "UPDATE crawl_jobs SET status = ?, started_at = COALESCE(started_at, ?), "
            "finished_at = ?, pages_fetched = ?, cost_usd = ? WHERE job_id = ?",
            (
                report.get("status", "succeeded"), utc_now().isoformat(),
                utc_now().isoformat(), int(report.get("pages_fetched") or 0),
                float(report.get("cost_usd") or 0.0), job_id,
            ),
        )
        conn.commit()
    console.print_json(json.dumps(report))


@crawl_app.command("tick")
def crawl_tick(ctx: typer.Context) -> None:
    """Run one dispatcher tick: consume ALL due queued jobs with the real worker.

    Opens the graph exclusively — stop the web server first.
    """

    from flows.website_crawl_dispatcher import WebsiteCrawlDispatcher
    from flows.website_crawl_worker import make_worker

    data = ctx.obj
    graph = KuzuGraphClient(db_path=data["graph_path"])
    try:
        worker = make_worker(
            sqlite_path=data["sqlite_path"], graph=graph,
            cache_dir=data["data_dir"] / "crawl_cache",
            progress=lambda m: console.print(m),
        )
        result = WebsiteCrawlDispatcher(
            sqlite_path=data["sqlite_path"], worker=worker,
        ).tick()
    finally:
        graph.close()
    console.print_json(json.dumps({
        "dispatched": result.jobs_dispatched,
        "succeeded": result.jobs_succeeded,
        "failed": result.jobs_failed,
        "skipped_paused": result.jobs_skipped_paused,
        "skipped_budget": result.jobs_skipped_budget,
    }))


@app.command("ui")
def ui_command(
    ctx: typer.Context,
    api_port: Annotated[int, typer.Option(help="FastAPI port")] = 8000,
    ui_port: Annotated[int, typer.Option(help="Next.js dev port")] = 3000,
    no_browser: Annotated[bool, typer.Option(help="Skip browser auto-open")] = False,
) -> None:
    """V1.5b: boot FastAPI + Next.js dev servers (FR-1.5b-1.3)."""

    from src.web.dev_orchestrator import run  # noqa: PLC0415
    _ = ctx  # ctx unused
    run(api_port=api_port, ui_port=ui_port, open_browser=not no_browser)


if __name__ == "__main__":
    cli()
