"""Pass 4 — selective LLM extraction (sentiment / interview_q / conflict_candidate).

Daily incremental over filter-surviving posts. Heavier retry policy than Pass 1-3
because vendor APIs are the typical failure mode.
"""

from __future__ import annotations

from pathlib import Path

from prefect import flow, task
from prefect.tasks import exponential_backoff

from src.conflict import ConflictResolver
from src.conflict.factory import build_three_vendor_judge, build_web_verifier
from src.conflict.pass4_resolution import (
    build_joint_resolver_if_enabled,
    resolve_pass4_conflicts,
)
from src.extraction.cache import ExtractionCache
from src.extraction.pass4_sweep import Pass4Input, Pass4TaskName, run_pass4_sweep, summarize
from src.gateway import default_gateway
from src.graph.kuzu_client import KuzuGraphClient
from src.observability import AuditLog
from src.shared.timestamps import utc_now


@task(retries=3, retry_delay_seconds=exponential_backoff(backoff_factor=60))
def run_pass4_extraction(
    *, data_dir: Path, sample: int, tasks: tuple[Pass4TaskName, ...],
    source: str,
) -> dict[str, float | int]:
    graph = KuzuGraphClient(db_path=data_dir / "graph" / "kuzu.db")
    audit = AuditLog(sqlite_path=data_dir / "sqlite" / "store.db")
    cache = ExtractionCache(sqlite_path=data_dir / "sqlite" / "store.db")
    gateway = default_gateway()

    where = ""
    if source == "reddit":
        where = "WHERE p.label = 'Post' AND p.id STARTS WITH 'reddit_post:'"
    elif source == "sdn":
        where = "WHERE p.label = 'Post' AND p.id STARTS WITH 'sdn_post:'"
    rows = graph.query(
        f"MATCH (p:Post) {where} RETURN p.id, p.properties LIMIT {int(sample)}",
    )
    inputs = [
        Pass4Input(
            post_id=pid,
            text=str(props.get("body") or ""),
            author=props.get("author_user_id"),
            is_reply=False,
        )
        for pid, props in rows
    ]

    results = list(run_pass4_sweep(
        inputs, tasks=tasks, gateway=gateway, cache=cache, audit=audit,
        ingest_time=utc_now(),
    ))
    nodes = [n for r in results for n in r.nodes]
    edges = [e for r in results for e in r.edges]
    if nodes:
        graph.upsert_nodes(nodes)
    if edges:
        graph.upsert_edges(edges)

    # GAP-052 / ADR-024: reconcile the conflict candidates this sweep produced
    # with the resolver WIRED to the 3-vendor judge + web-verifier (best-effort
    # on env keys). Same-tier same-year ties go to the panel, not straight to HITL.
    resolver = ConflictResolver(
        judge=build_three_vendor_judge(), web_verifier=build_web_verifier(),
    )
    res = resolve_pass4_conflicts(
        graph, resolver, ingest_time=utc_now(),
        joint_resolver=build_joint_resolver_if_enabled(),  # ADR-026, flag-gated
    )
    graph.close()

    s = summarize(results)
    return {
        "processed": s.processed,
        "filtered_out": s.filtered_out,
        "cache_hits": s.cache_hits,
        "cost_usd": s.total_cost_usd,
        "conflict_groups": res.conflict_groups,
        "judge_resolved": res.judge_resolved,
    }


@flow(name="pass4-llm-daily")
def pass4_llm_daily(
    *, data_dir: Path, sample: int = 500,
    tasks: tuple[Pass4TaskName, ...] = ("sentiment", "interview_q"),
    source: str = "reddit",
) -> dict[str, float | int]:
    return run_pass4_extraction(
        data_dir=data_dir, sample=sample, tasks=tasks, source=source,
    )
