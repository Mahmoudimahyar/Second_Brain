"""V1.6a Phase 7 — Prefect cron dispatcher unit tests.

Per ADR-010 + V1.6a plan.md Phase 7 + FR-1.6a-5. The dispatcher:
1. Runs every 5 min (cron-driven by the Prefect deployment)
2. Queries crawl_jobs for due rows OR generates due rows from
   crawl_domains based on cadence_cron
3. Dispatches one worker per due domain (quarantined failures don't
   block other domains)
4. Honors concurrency caps + per-domain backoff after failures
5. Refuses to dispatch a domain whose spent_month >= max_usd_per_month
   (third budget-enforcement point per ADR-020)
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path


def test_dispatcher_picks_due_jobs_and_dispatches(tmp_path: Path) -> None:
    """Failing-first: 3 due rows -> dispatcher transitions all to 'running'."""
    os.environ["CRAWL4AI_USER_AGENT"] = "SecBrain/1.6 (+test@example.invalid)"
    from flows.website_crawl_dispatcher import (
        WebsiteCrawlDispatcher,
        enqueue_job,
    )
    from src.ingestion.sources.website_crawl import WebsiteCrawlRegistry

    registry = WebsiteCrawlRegistry(sqlite_path=tmp_path / "engine.db")
    domains = [
        registry.register(
            domain=f"d{i}.example.invalid", tier="L2", stage="L0",
            cadence_cron="0 6 * * *", actor="t",
        )
        for i in range(3)
    ]

    now = datetime.now(UTC)
    for d in domains:
        enqueue_job(
            sqlite_path=tmp_path / "engine.db",
            domain_id=d.domain_id,
            scheduled_at=now - timedelta(minutes=1),  # due
            trigger="manual",
        )

    dispatched: list[str] = []

    def _worker(domain_id: str, job_id: str) -> dict:
        dispatched.append(domain_id)
        return {"status": "succeeded", "pages_fetched": 0}

    dispatcher = WebsiteCrawlDispatcher(
        sqlite_path=tmp_path / "engine.db",
        worker=_worker,
    )
    result = dispatcher.tick(now=now)
    assert result.jobs_dispatched == 3
    assert set(dispatched) == {d.domain_id for d in domains}


def test_dispatcher_skips_paused_domains(tmp_path: Path) -> None:
    os.environ["CRAWL4AI_USER_AGENT"] = "SecBrain/1.6 (+test@example.invalid)"
    from flows.website_crawl_dispatcher import (
        WebsiteCrawlDispatcher,
        enqueue_job,
    )
    from src.ingestion.sources.website_crawl import WebsiteCrawlRegistry

    registry = WebsiteCrawlRegistry(sqlite_path=tmp_path / "engine.db")
    d = registry.register(
        domain="paused.example.invalid", tier="L2", stage="L0",
        cadence_cron="0 6 * * *", actor="t",
    )
    registry.pause(d.domain_id, actor="t")

    enqueue_job(
        sqlite_path=tmp_path / "engine.db",
        domain_id=d.domain_id,
        scheduled_at=datetime.now(UTC) - timedelta(minutes=1),
        trigger="manual",
    )

    dispatched: list[str] = []

    def _worker(domain_id: str, job_id: str) -> dict:
        dispatched.append(domain_id)
        return {"status": "succeeded", "pages_fetched": 0}

    dispatcher = WebsiteCrawlDispatcher(
        sqlite_path=tmp_path / "engine.db", worker=_worker,
    )
    result = dispatcher.tick(now=datetime.now(UTC))
    assert result.jobs_dispatched == 0
    assert dispatched == []


def test_dispatcher_quarantines_failed_domain(tmp_path: Path) -> None:
    """A failing worker for domain A must not prevent domain B from dispatching."""
    os.environ["CRAWL4AI_USER_AGENT"] = "SecBrain/1.6 (+test@example.invalid)"
    from flows.website_crawl_dispatcher import (
        WebsiteCrawlDispatcher,
        enqueue_job,
    )
    from src.ingestion.sources.website_crawl import WebsiteCrawlRegistry

    registry = WebsiteCrawlRegistry(sqlite_path=tmp_path / "engine.db")
    bad = registry.register(
        domain="bad.example.invalid", tier="L2", stage="L0",
        cadence_cron="0 6 * * *", actor="t",
    )
    good = registry.register(
        domain="good.example.invalid", tier="L2", stage="L0",
        cadence_cron="0 6 * * *", actor="t",
    )
    now = datetime.now(UTC)
    enqueue_job(
        sqlite_path=tmp_path / "engine.db", domain_id=bad.domain_id,
        scheduled_at=now - timedelta(minutes=1), trigger="manual",
    )
    enqueue_job(
        sqlite_path=tmp_path / "engine.db", domain_id=good.domain_id,
        scheduled_at=now - timedelta(minutes=1), trigger="manual",
    )

    def _worker(domain_id: str, job_id: str) -> dict:
        if domain_id == bad.domain_id:
            raise RuntimeError("boom")
        return {"status": "succeeded", "pages_fetched": 5}

    dispatcher = WebsiteCrawlDispatcher(
        sqlite_path=tmp_path / "engine.db", worker=_worker,
    )
    result = dispatcher.tick(now=now)
    # Both jobs were attempted; one failed but the other succeeded.
    assert result.jobs_dispatched == 2
    assert result.jobs_failed == 1
    assert result.jobs_succeeded == 1


def test_dispatcher_refuses_when_budget_exceeded(tmp_path: Path) -> None:
    """Domain whose spent_month >= max_usd_per_month is auto-paused (3rd budget point)."""
    import sqlite3
    os.environ["CRAWL4AI_USER_AGENT"] = "SecBrain/1.6 (+test@example.invalid)"
    from flows.website_crawl_dispatcher import (
        WebsiteCrawlDispatcher,
        enqueue_job,
    )
    from src.ingestion.sources.website_crawl import WebsiteCrawlRegistry

    db = tmp_path / "engine.db"
    registry = WebsiteCrawlRegistry(sqlite_path=db)
    d = registry.register(
        domain="capped.example.invalid", tier="L2", stage="L2",
        cadence_cron="0 6 * * *", actor="t",
        max_usd_per_month=0.05,
    )
    # Simulate prior spend.
    with sqlite3.connect(db) as conn:
        conn.execute(
            "INSERT INTO crawl_cost (cost_id, domain_id, kind, cost_usd, ts) "
            "VALUES (?, ?, ?, ?, ?)",
            ("c1", d.domain_id, "l2_summary", 0.05,
             datetime.now(UTC).isoformat()),
        )
        conn.commit()

    enqueue_job(
        sqlite_path=db, domain_id=d.domain_id,
        scheduled_at=datetime.now(UTC) - timedelta(minutes=1),
        trigger="manual",
    )

    dispatched: list[str] = []
    def _worker(domain_id: str, job_id: str) -> dict:
        dispatched.append(domain_id)
        return {"status": "succeeded", "pages_fetched": 0}

    dispatcher = WebsiteCrawlDispatcher(sqlite_path=db, worker=_worker)
    result = dispatcher.tick(now=datetime.now(UTC))
    assert result.jobs_dispatched == 0
    assert result.jobs_skipped_budget == 1
    # Domain auto-paused.
    refreshed = registry.get(d.domain_id)
    assert refreshed is not None
    assert refreshed.status == "auto_paused"
