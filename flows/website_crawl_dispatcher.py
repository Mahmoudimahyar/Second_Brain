"""V1.6a — Prefect cron dispatcher for the website-crawl scheduler.

Per ADR-010 + FR-1.6a-5. Runs every 5 minutes (deployed as a Prefect
cron flow). For each tick:

1. Read crawl_jobs for due rows (scheduled_at <= now, status='queued').
2. For each due job:
   a. Check the owning domain's status (skip paused / deleted /
      auto_paused).
   b. Check the third budget-enforcement point per ADR-020: if
      spent_month >= max_usd_per_month, auto-pause the domain + skip.
   c. Mark the job 'running' (atomically), invoke the worker, then mark
      'succeeded' or 'failed' based on outcome.
3. Quarantine per-domain failures so they don't block other domains
   (per NFR-1.6a-5 reliability).

The dispatcher is structured as a plain Python class so unit tests
don't need a Prefect runtime. A `@flow`-decorated wrapper in production
calls `WebsiteCrawlDispatcher.tick()` once per cron firing.
"""

from __future__ import annotations

import sqlite3
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

WorkerFn = Callable[[str, str], dict[str, Any]]


# ---------------------------------------------------------------------------
# Dispatcher result
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DispatcherTickResult:
    """What one dispatcher tick produced. Logged + exposed to observability."""

    jobs_dispatched: int
    jobs_succeeded: int
    jobs_failed: int
    jobs_skipped_paused: int
    jobs_skipped_budget: int


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def enqueue_job(
    *,
    sqlite_path: Path,
    domain_id: str,
    scheduled_at: datetime,
    trigger: str,
) -> str:
    """Insert a row into `crawl_jobs` with status='queued'."""

    job_id = f"job:{uuid.uuid4().hex[:16]}"
    with sqlite3.connect(sqlite_path) as conn:
        conn.execute(
            "INSERT INTO crawl_jobs (job_id, domain_id, scheduled_at, status, trigger) "
            "VALUES (?, ?, ?, ?, ?)",
            (job_id, domain_id, scheduled_at.isoformat(), "queued", trigger),
        )
        conn.commit()
    return job_id


def spent_this_month(
    *, sqlite_path: Path, domain_id: str, now: datetime,
) -> float:
    """Sum of `crawl_cost.cost_usd` for the current calendar month."""

    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    with sqlite3.connect(sqlite_path) as conn:
        row = conn.execute(
            "SELECT COALESCE(SUM(cost_usd), 0) FROM crawl_cost "
            "WHERE domain_id = ? AND ts >= ?",
            (domain_id, month_start.isoformat()),
        ).fetchone()
    return float(row[0]) if row else 0.0


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------


class WebsiteCrawlDispatcher:
    """Cron-driven dispatcher for the website-crawl scheduler.

    The `worker` callable runs one crawl. It receives (domain_id,
    job_id) and returns a dict with at least `{"status": str, ...}`.
    Production wires this to a Prefect task that drives the full
    fetch -> L0 -> L1 -> L2 pipeline; unit tests inject a stub.
    """

    def __init__(
        self,
        *,
        sqlite_path: Path,
        worker: WorkerFn,
    ) -> None:
        self._sqlite_path = Path(sqlite_path)
        self._worker = worker

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def tick(self, *, now: datetime | None = None) -> DispatcherTickResult:
        """Run one dispatcher tick. Returns counters per outcome."""

        now = now or datetime.now(UTC)
        due = self._read_due_jobs(now=now)
        dispatched = 0
        succeeded = 0
        failed = 0
        skipped_paused = 0
        skipped_budget = 0

        for job in due:
            domain = self._read_domain(domain_id=job["domain_id"])
            if domain is None:
                continue
            # Skip non-active domains
            if domain["status"] != "active":
                self._mark_status(job["job_id"], "cancelled")
                skipped_paused += 1
                continue
            # 3rd budget-enforcement point: dispatcher-boot refusal
            spent = spent_this_month(
                sqlite_path=self._sqlite_path,
                domain_id=domain["domain_id"], now=now,
            )
            if spent >= float(domain["max_usd_per_month"]):
                # Auto-pause the domain + mark the job 'cancelled'.
                self._auto_pause(domain_id=domain["domain_id"])
                self._mark_status(job["job_id"], "cancelled")
                skipped_budget += 1
                continue
            # Dispatch
            self._mark_running(job["job_id"], now=now)
            dispatched += 1
            try:
                result = self._worker(domain["domain_id"], job["job_id"])
            except Exception as exc:
                self._finalize(
                    job["job_id"],
                    status="failed",
                    finished_at=datetime.now(UTC),
                    error=str(exc)[:512],
                )
                failed += 1
                continue
            self._finalize(
                job["job_id"],
                status=result.get("status", "succeeded"),
                finished_at=datetime.now(UTC),
                pages_fetched=int(result.get("pages_fetched") or 0),
                cost_usd=float(result.get("cost_usd") or 0.0),
            )
            succeeded += 1

        return DispatcherTickResult(
            jobs_dispatched=dispatched,
            jobs_succeeded=succeeded,
            jobs_failed=failed,
            jobs_skipped_paused=skipped_paused,
            jobs_skipped_budget=skipped_budget,
        )

    # ------------------------------------------------------------------
    # SQLite helpers
    # ------------------------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._sqlite_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _read_due_jobs(self, *, now: datetime) -> list[sqlite3.Row]:
        with self._connect() as conn:
            return list(conn.execute(
                "SELECT * FROM crawl_jobs "
                "WHERE status = 'queued' AND scheduled_at <= ? "
                "ORDER BY scheduled_at ASC LIMIT 50",
                (now.isoformat(),),
            ).fetchall())

    def _read_domain(self, *, domain_id: str) -> sqlite3.Row | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM crawl_domains WHERE domain_id = ?", (domain_id,),
            ).fetchone()
        # sqlite3.fetchone() is typed `Any`; narrow explicitly for mypy.
        return row if row is not None else None

    def _mark_running(self, job_id: str, *, now: datetime) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE crawl_jobs SET status = 'running', started_at = ? "
                "WHERE job_id = ?",
                (now.isoformat(), job_id),
            )
            conn.commit()

    def _mark_status(self, job_id: str, status: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE crawl_jobs SET status = ?, finished_at = ? WHERE job_id = ?",
                (status, datetime.now(UTC).isoformat(), job_id),
            )
            conn.commit()

    def _finalize(
        self,
        job_id: str,
        *,
        status: str,
        finished_at: datetime,
        pages_fetched: int = 0,
        cost_usd: float = 0.0,
        error: str | None = None,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE crawl_jobs SET status = ?, finished_at = ?, "
                "pages_fetched = ?, cost_usd = ?, error_excerpt = ? "
                "WHERE job_id = ?",
                (status, finished_at.isoformat(), pages_fetched,
                 cost_usd, error, job_id),
            )
            conn.commit()

    def _auto_pause(self, *, domain_id: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE crawl_domains SET status = 'auto_paused', updated_at = ? "
                "WHERE domain_id = ?",
                (datetime.now(UTC).isoformat(), domain_id),
            )
            conn.commit()


__all__ = [
    "DispatcherTickResult",
    "WebsiteCrawlDispatcher",
    "WorkerFn",
    "enqueue_job",
    "spent_this_month",
]
