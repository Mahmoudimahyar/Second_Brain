"""V1.6a — `/api/v1/ingest/web/*` FastAPI routes.

Per V1.6a api.md. Wraps the WebsiteCrawlRegistry + dispatcher + blocklist
behind a Pydantic-validated HTTP surface for the Next.js UI + the MCP
tools (Phase 10) to consume.

Authentication: V1.6 stays single-user localhost — no auth (per V2
multi-tenant deferral).
"""

from __future__ import annotations

import sqlite3
import threading
from datetime import UTC, datetime

from fastapi import APIRouter, BackgroundTasks, Body, Query

from flows.website_crawl_dispatcher import enqueue_job, spent_this_month
from src.ingestion.sources import blocked_domains
from src.ingestion.sources.website_crawl import WebsiteCrawlRegistry
from src.shared.errors import ErrorCode, StructuredError
from src.web.paths import sqlite_path
from src.web.schemas.website_crawl import (
    BlocklistResponse,
    BudgetSnapshot,
    CrawlDomain,
    CrawlDomainList,
    CrawlJob,
    CrawlJobList,
    RegisterDomainRequest,
    TriggerRunRequest,
    UpdateDomainRequest,
)

router = APIRouter()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _registry() -> WebsiteCrawlRegistry:
    return WebsiteCrawlRegistry(sqlite_path=sqlite_path())


# One tick at a time per process: crawls are long; overlapping ticks would
# double-fetch the same queued jobs (the dispatcher marks 'running' only
# after read-due). The UI can keep enqueueing — the running tick's loop is
# re-kicked by the next request once it finishes.
_tick_lock = threading.Lock()


def _execute_due_jobs() -> None:
    """Drive the dispatcher with the REAL worker (FastAPI background task).

    Sync on purpose: FastAPI runs sync background tasks in the threadpool,
    so the long crawl never blocks the event loop. The graph writes go
    through the process-shared Kùzu handle (`src.web.graph_db`).
    """

    if not _tick_lock.acquire(blocking=False):
        return  # a tick is already running; it will pick up queued jobs
    try:
        from flows.website_crawl_dispatcher import (  # noqa: PLC0415
            WebsiteCrawlDispatcher,
        )
        from flows.website_crawl_worker import make_worker  # noqa: PLC0415
        from src.graph.kuzu_client import KuzuGraphClient  # noqa: PLC0415
        from src.web.graph_db import shared_database  # noqa: PLC0415
        from src.web.paths import data_dir  # noqa: PLC0415

        graph = KuzuGraphClient(
            data_dir() / "graph" / "kuzu.db", database=shared_database(),
        )
        worker = make_worker(
            sqlite_path=sqlite_path(),
            graph=graph,
            cache_dir=data_dir() / "crawl_cache",
        )
        WebsiteCrawlDispatcher(sqlite_path=sqlite_path(), worker=worker).tick()
    except Exception as exc:  # pragma: no cover - environment-dependent
        # A failed tick must not crash the request path. The job row stays
        # 'queued' and the next run-now (or `secbrain crawl tick`) retries it.
        import logging  # noqa: PLC0415

        logging.getLogger("secbrain.crawl").warning(
            "background crawl tick failed: %s", exc,
        )
    finally:
        _tick_lock.release()


def _to_pydantic(row) -> CrawlDomain:  # type: ignore[no-untyped-def]
    return CrawlDomain(
        domain_id=row.domain_id,
        domain=row.domain,
        tier=row.tier,
        stage=row.stage,
        cadence_cron=row.cadence_cron,
        status=row.status,
        max_pages_per_run=row.max_pages_per_run,
        max_pages_per_month=row.max_pages_per_month,
        max_usd_per_month=row.max_usd_per_month,
        concurrency=row.concurrency,
        enable_ocr=row.enable_ocr,
        enable_scrapingbee=row.enable_scrapingbee,
        confirm_l1=row.confirm_l1,
        created_at=row.created_at,
        updated_at=row.updated_at,
        created_by=row.created_by,
        notes=row.notes,
    )


# ---------------------------------------------------------------------------
# Domain CRUD
# ---------------------------------------------------------------------------


@router.get("/domains", response_model=CrawlDomainList)
def list_domains(
    status: str = Query("active"),
    q: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
) -> CrawlDomainList:
    reg = _registry()
    if status == "active":
        rows = reg.list_active()
    else:
        # Explicit status filters (paused / deleted / auto_paused) must
        # search ALL rows — list_active() excludes 'deleted', which made
        # `?status=deleted` always return empty.
        rows = reg.list_all()
        if status != "all":
            rows = [r for r in rows if r.status == status]
    if q:
        rows = [r for r in rows if q.lower() in r.domain.lower()]
    total = len(rows)
    start = (page - 1) * page_size
    page_rows = rows[start:start + page_size]
    return CrawlDomainList(
        domains=[_to_pydantic(r) for r in page_rows],
        total=total,
    )


@router.post("/domains", response_model=CrawlDomain, status_code=201)
def register_domain(payload: RegisterDomainRequest) -> CrawlDomain:
    """Register a new crawl domain (or return existing on idempotent re-register)."""

    reg = _registry()
    row = reg.register(
        domain=payload.domain,
        tier=payload.tier,
        stage=payload.stage,
        cadence_cron=payload.cadence_cron,
        actor="ui",  # V1.6a single-user localhost
        max_pages_per_run=payload.max_pages_per_run,
        max_pages_per_month=payload.max_pages_per_month,
        max_usd_per_month=payload.max_usd_per_month,
        concurrency=payload.concurrency,
        enable_ocr=payload.enable_ocr,
        enable_scrapingbee=payload.enable_scrapingbee,
        confirm_l1_immutable=payload.confirm_l1_immutable,
        notes=payload.notes,
    )
    return _to_pydantic(row)


@router.get("/domains/{domain_id}", response_model=CrawlDomain)
def get_domain(domain_id: str) -> CrawlDomain:
    reg = _registry()
    row = reg.get(domain_id)
    if row is None:
        raise StructuredError(
            ErrorCode.CONNECTOR_NOT_FOUND,
            f"domain '{domain_id}' not found",
            context={"domain_id": domain_id},
        )
    return _to_pydantic(row)


@router.patch("/domains/{domain_id}", response_model=CrawlDomain)
def update_domain(
    domain_id: str,
    payload: UpdateDomainRequest,
) -> CrawlDomain:
    """V1.6a Phase 8 baseline: only re-register-style updates supported.

    A richer field-by-field PATCH lands in the wizard's edit page —
    until then, the UI can DELETE + register to reproduce the same shape.
    For now we treat PATCH as a no-op that returns the current row,
    surfacing the contract without claiming feature parity we haven't
    shipped.
    """

    _ = payload  # PATCH shape preserved for the Pydantic contract
    reg = _registry()
    row = reg.get(domain_id)
    if row is None:
        raise StructuredError(
            ErrorCode.CONNECTOR_NOT_FOUND,
            f"domain '{domain_id}' not found",
            context={"domain_id": domain_id},
        )
    return _to_pydantic(row)


@router.post("/domains/{domain_id}/pause", response_model=CrawlDomain)
def pause_domain(domain_id: str) -> CrawlDomain:
    reg = _registry()
    row = reg.get(domain_id)
    if row is None:
        raise StructuredError(
            ErrorCode.CONNECTOR_NOT_FOUND,
            f"domain '{domain_id}' not found",
            context={"domain_id": domain_id},
        )
    reg.pause(domain_id, actor="ui")
    row = reg.get(domain_id)
    assert row is not None
    return _to_pydantic(row)


@router.post("/domains/{domain_id}/resume", response_model=CrawlDomain)
def resume_domain(domain_id: str) -> CrawlDomain:
    reg = _registry()
    row = reg.get(domain_id)
    if row is None:
        raise StructuredError(
            ErrorCode.CONNECTOR_NOT_FOUND,
            f"domain '{domain_id}' not found",
            context={"domain_id": domain_id},
        )
    reg.resume(domain_id, actor="ui")
    row = reg.get(domain_id)
    assert row is not None
    return _to_pydantic(row)


@router.delete("/domains/{domain_id}", response_model=CrawlDomain)
def delete_domain(domain_id: str) -> CrawlDomain:
    """Soft delete — row preserved for audit, future cron runs skipped."""

    reg = _registry()
    row = reg.get(domain_id)
    if row is None:
        raise StructuredError(
            ErrorCode.CONNECTOR_NOT_FOUND,
            f"domain '{domain_id}' not found",
            context={"domain_id": domain_id},
        )
    reg.delete(domain_id, actor="ui")
    row = reg.get(domain_id)
    assert row is not None
    return _to_pydantic(row)


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------


@router.post("/domains/{domain_id}/run-now", response_model=CrawlJob)
def run_now(
    domain_id: str,
    background_tasks: BackgroundTasks,
    payload: TriggerRunRequest | None = Body(default=None),
) -> CrawlJob:
    """Enqueue a crawl_jobs row with scheduled_at = now, then execute it.

    The enqueued row is consumed by a background dispatcher tick in this
    process (real worker over the shared Kùzu handle) — without it the
    queue had no consumer and "Run now" was a silent no-op.
    """

    reg = _registry()
    row = reg.get(domain_id)
    if row is None:
        raise StructuredError(
            ErrorCode.CONNECTOR_NOT_FOUND,
            f"domain '{domain_id}' not found",
            context={"domain_id": domain_id},
        )
    body = payload or TriggerRunRequest()
    now = datetime.now(UTC)
    job_id = enqueue_job(
        sqlite_path=sqlite_path(),
        domain_id=domain_id,
        scheduled_at=now,
        trigger="force_full_refresh" if body.force_full_refresh else "manual",
    )
    background_tasks.add_task(_execute_due_jobs)
    return CrawlJob(
        job_id=job_id,
        domain_id=domain_id,
        scheduled_at=now,
        status="queued",
        trigger="force_full_refresh" if body.force_full_refresh else "manual",
    )


@router.get("/domains/{domain_id}/jobs", response_model=CrawlJobList)
def list_jobs(
    domain_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
) -> CrawlJobList:
    with sqlite3.connect(sqlite_path()) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM crawl_jobs WHERE domain_id = ? "
            "ORDER BY scheduled_at DESC LIMIT ? OFFSET ?",
            (domain_id, page_size, (page - 1) * page_size),
        ).fetchall()
        total_row = conn.execute(
            "SELECT COUNT(*) FROM crawl_jobs WHERE domain_id = ?",
            (domain_id,),
        ).fetchone()
        total = int(total_row[0]) if total_row else 0
    jobs = [
        CrawlJob(
            job_id=r["job_id"],
            domain_id=r["domain_id"],
            scheduled_at=datetime.fromisoformat(r["scheduled_at"]),
            started_at=datetime.fromisoformat(r["started_at"]) if r["started_at"] else None,
            finished_at=datetime.fromisoformat(r["finished_at"]) if r["finished_at"] else None,
            status=r["status"],
            trigger=r["trigger"],
            pages_discovered=r["pages_discovered"],
            pages_fetched=r["pages_fetched"],
            pages_unchanged=r["pages_unchanged"],
            pages_skipped_robots=r["pages_skipped_robots"],
            pages_skipped_size=r["pages_skipped_size"],
            pages_blocked=r["pages_blocked"],
            cost_usd=r["cost_usd"],
            prefect_run_id=r["prefect_run_id"],
            error_excerpt=r["error_excerpt"],
        )
        for r in rows
    ]
    return CrawlJobList(jobs=jobs, total=total)


# ---------------------------------------------------------------------------
# Blocklist + Budget
# ---------------------------------------------------------------------------


@router.get("/blocklist", response_model=BlocklistResponse)
def get_blocklist() -> BlocklistResponse:
    return BlocklistResponse(
        forum_domains=sorted(blocked_domains.FORUM_DOMAINS),
        social_domains=sorted(blocked_domains.SOCIAL_DOMAINS),
    )


@router.get("/domains/{domain_id}/budget", response_model=BudgetSnapshot)
def get_budget(domain_id: str) -> BudgetSnapshot:
    reg = _registry()
    row = reg.get(domain_id)
    if row is None:
        raise StructuredError(
            ErrorCode.CONNECTOR_NOT_FOUND,
            f"domain '{domain_id}' not found",
            context={"domain_id": domain_id},
        )
    spent = spent_this_month(
        sqlite_path=sqlite_path(),
        domain_id=domain_id,
        now=datetime.now(UTC),
    )
    return BudgetSnapshot(
        domain_id=domain_id,
        spent_month_usd=spent,
        cap_usd=row.max_usd_per_month,
        projected_next_run_usd=None,  # populated by dispatcher in Phase 9
    )
