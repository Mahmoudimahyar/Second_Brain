"""V1.6a — `WebsiteCrawlRegistry` per ADR-019.

This module owns the per-domain registry (the `crawl_domains` SQLite
table) + the registration / pause / resume / delete lifecycle. The
heavier `WebsiteCrawlSource` (DataSource Protocol implementation) +
the sitemap-driven `discover` / `pull_delta` pull paths land in Phase 4
when the L0 flow is ready to consume them — keeping Phase 3 focused on
the contract that gates everything downstream (the blocklist + the L1
confirmation + cron validation + audit).
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from croniter import croniter

from src.ingestion.sources import blocked_domains
from src.shared.errors import ErrorCode, StructuredError

CrawlStage = Literal["L0", "L1", "L2"]
CrawlTier = Literal["L1", "L2"]
CrawlStatus = Literal["active", "paused", "deleted", "auto_paused"]


@dataclass(frozen=True)
class CrawlDomainRow:
    """One `crawl_domains` row — what the registry returns."""

    domain_id: str
    domain: str
    tier: CrawlTier
    stage: CrawlStage
    cadence_cron: str
    status: CrawlStatus
    max_pages_per_run: int
    max_pages_per_month: int
    max_usd_per_month: float
    concurrency: int
    enable_ocr: bool
    enable_scrapingbee: bool
    confirm_l1: bool
    created_at: datetime
    updated_at: datetime
    created_by: str
    notes: str | None = None


# ---------------------------------------------------------------------------
# Defaults — wired via the registry constructor for testability
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CrawlDefaults:
    """Per-domain defaults applied at registration time."""

    stage: CrawlStage = "L1"
    max_pages_per_run: int = 500
    max_pages_per_month: int = 5_000
    max_usd_per_month: float = 5.0
    concurrency: int = 4
    enable_ocr: bool = False
    enable_scrapingbee: bool = False


# ---------------------------------------------------------------------------
# Registry — SQLite-backed
# ---------------------------------------------------------------------------


class WebsiteCrawlRegistry:
    """SQLite-backed registry for the V1.6a website-crawl source.

    Tests pass `sqlite_path=tmp_path/...`; production wires the central
    `engine.db`.
    """

    def __init__(
        self,
        *,
        sqlite_path: Path,
        defaults: CrawlDefaults | None = None,
    ) -> None:
        self._sqlite_path = Path(sqlite_path)
        self._sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        self._defaults = defaults or CrawlDefaults()
        self._init_schema()

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._sqlite_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(SCHEMA_SQL)
            conn.commit()

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(
        self,
        *,
        domain: str,
        tier: CrawlTier,
        stage: CrawlStage,
        cadence_cron: str,
        actor: str,
        max_pages_per_run: int | None = None,
        max_pages_per_month: int | None = None,
        max_usd_per_month: float | None = None,
        concurrency: int | None = None,
        enable_ocr: bool | None = None,
        enable_scrapingbee: bool | None = None,
        confirm_l1_immutable: bool = False,
        notes: str | None = None,
    ) -> CrawlDomainRow:
        """Register a new crawl domain.

        Returns the existing row when the domain is already registered
        (idempotent). Raises StructuredError with one of:
        - DOMAIN_BLOCKED (forum/social blocklist match)
        - L1_NOT_CONFIRMED (tier=L1 without confirm_l1_immutable)
        - INVALID_CRON (cadence_cron not parseable by croniter)
        """

        normalized = _normalize_domain(domain)
        if blocked_domains.is_blocked(normalized):
            reason = blocked_domains.block_reason(normalized) or "Blocked"
            raise StructuredError(
                ErrorCode.DOMAIN_BLOCKED,
                reason,
                context={"domain": normalized},
            )
        if tier == "L1" and not confirm_l1_immutable:
            raise StructuredError(
                ErrorCode.L1_NOT_CONFIRMED,
                f"Tier=L1 for '{normalized}' requires confirm_l1_immutable=true. "
                "L1 sources are treated as immutable ground truth; existing L1 "
                "nodes from other sources will not be overwritten and conflicts "
                "escalate to HITL.",
                context={"domain": normalized, "tier": tier},
            )
        if not croniter.is_valid(cadence_cron):
            raise StructuredError(
                ErrorCode.INVALID_CRON,
                f"cadence_cron '{cadence_cron}' is not a valid cron expression.",
                context={"domain": normalized, "cadence_cron": cadence_cron},
            )

        # Idempotent: return existing row if already registered.
        existing = self._find_by_domain(normalized)
        if existing is not None:
            return existing

        defaults = self._defaults
        now = datetime.now(UTC)
        domain_id = _domain_id(normalized)
        row = CrawlDomainRow(
            domain_id=domain_id,
            domain=normalized,
            tier=tier,
            stage=stage,
            cadence_cron=cadence_cron,
            status="active",
            max_pages_per_run=max_pages_per_run or defaults.max_pages_per_run,
            max_pages_per_month=max_pages_per_month or defaults.max_pages_per_month,
            max_usd_per_month=max_usd_per_month or defaults.max_usd_per_month,
            concurrency=concurrency or defaults.concurrency,
            enable_ocr=bool(enable_ocr) if enable_ocr is not None else defaults.enable_ocr,
            enable_scrapingbee=bool(enable_scrapingbee)
            if enable_scrapingbee is not None else defaults.enable_scrapingbee,
            confirm_l1=confirm_l1_immutable,
            created_at=now,
            updated_at=now,
            created_by=actor,
            notes=notes,
        )
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO crawl_domains (
                    domain_id, domain, tier, stage, cadence_cron, status,
                    max_pages_per_run, max_pages_per_month, max_usd_per_month,
                    concurrency, enable_ocr, enable_scrapingbee, confirm_l1,
                    created_at, updated_at, created_by, notes
                ) VALUES (
                    :domain_id, :domain, :tier, :stage, :cadence_cron, :status,
                    :max_pages_per_run, :max_pages_per_month, :max_usd_per_month,
                    :concurrency, :enable_ocr, :enable_scrapingbee, :confirm_l1,
                    :created_at, :updated_at, :created_by, :notes
                )
                """,
                _row_to_params(row),
            )
            _write_audit(
                conn, domain_id=domain_id, actor=actor,
                kind="domain_registered",
                detail=f"tier={tier} stage={stage} cadence={cadence_cron}",
            )
            conn.commit()
        return row

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def pause(self, domain_id: str, *, actor: str) -> None:
        self._set_status(domain_id, "paused", actor=actor, kind="domain_paused")

    def resume(self, domain_id: str, *, actor: str) -> None:
        self._set_status(domain_id, "active", actor=actor, kind="domain_resumed")

    def delete(self, domain_id: str, *, actor: str) -> None:
        self._set_status(domain_id, "deleted", actor=actor, kind="domain_deleted")

    def _set_status(
        self, domain_id: str, status: CrawlStatus, *, actor: str, kind: str,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE crawl_domains SET status = ?, updated_at = ? WHERE domain_id = ?",
                (status, datetime.now(UTC).isoformat(), domain_id),
            )
            _write_audit(conn, domain_id=domain_id, actor=actor, kind=kind, detail=status)
            conn.commit()

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    def get(self, domain_id: str) -> CrawlDomainRow | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM crawl_domains WHERE domain_id = ?", (domain_id,),
            ).fetchone()
        return _row_from_sqlite(row) if row else None

    def list_active(self) -> list[CrawlDomainRow]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM crawl_domains "
                "WHERE status IN ('active', 'paused', 'auto_paused') "
                "ORDER BY created_at DESC",
            ).fetchall()
        return [_row_from_sqlite(r) for r in rows]

    def list_all(self) -> list[CrawlDomainRow]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM crawl_domains ORDER BY created_at DESC",
            ).fetchall()
        return [_row_from_sqlite(r) for r in rows]

    def _find_by_domain(self, domain: str) -> CrawlDomainRow | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM crawl_domains WHERE domain = ?", (domain,),
            ).fetchone()
        return _row_from_sqlite(row) if row else None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _normalize_domain(domain: str) -> str:
    d = (domain or "").strip().lower()
    for prefix in ("https://", "http://"):
        if d.startswith(prefix):
            d = d[len(prefix):]
    for sep in ("/", "?", "#"):
        idx = d.find(sep)
        if idx >= 0:
            d = d[:idx]
    return d


def _domain_id(domain: str) -> str:
    return f"web:{hashlib.sha256(domain.encode('utf-8')).hexdigest()[:16]}"


def _row_to_params(row: CrawlDomainRow) -> dict[str, object]:
    return {
        "domain_id": row.domain_id,
        "domain": row.domain,
        "tier": row.tier,
        "stage": row.stage,
        "cadence_cron": row.cadence_cron,
        "status": row.status,
        "max_pages_per_run": row.max_pages_per_run,
        "max_pages_per_month": row.max_pages_per_month,
        "max_usd_per_month": row.max_usd_per_month,
        "concurrency": row.concurrency,
        "enable_ocr": int(row.enable_ocr),
        "enable_scrapingbee": int(row.enable_scrapingbee),
        "confirm_l1": int(row.confirm_l1),
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
        "created_by": row.created_by,
        "notes": row.notes,
    }


def _row_from_sqlite(row: sqlite3.Row) -> CrawlDomainRow:
    return CrawlDomainRow(
        domain_id=row["domain_id"],
        domain=row["domain"],
        tier=row["tier"],
        stage=row["stage"],
        cadence_cron=row["cadence_cron"],
        status=row["status"],
        max_pages_per_run=int(row["max_pages_per_run"]),
        max_pages_per_month=int(row["max_pages_per_month"]),
        max_usd_per_month=float(row["max_usd_per_month"]),
        concurrency=int(row["concurrency"]),
        enable_ocr=bool(row["enable_ocr"]),
        enable_scrapingbee=bool(row["enable_scrapingbee"]),
        confirm_l1=bool(row["confirm_l1"]),
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
        created_by=row["created_by"],
        notes=row["notes"],
    )


def _write_audit(
    conn: sqlite3.Connection,
    *,
    domain_id: str,
    actor: str,
    kind: str,
    detail: str,
) -> None:
    """Write an audit_log row using V1's shape.

    Per `src.observability.audit.AuditLog._init_schema`: the audit_log
    table is `(audit_id PRIMARY KEY, kind TEXT, ts TEXT, fields_json
    TEXT, ttl_pinned INTEGER)`. Our V1.6a-specific fields (actor,
    entity_kind, entity_id, detail) go into `fields_json`.
    """

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS audit_log (
            audit_id     TEXT PRIMARY KEY,
            kind         TEXT NOT NULL,
            ts           TEXT NOT NULL,
            fields_json  TEXT NOT NULL,
            ttl_pinned   INTEGER
        );
        """,
    )
    fields = {
        "actor": actor,
        "entity_kind": "crawl_domain",
        "entity_id": domain_id,
        "detail": detail,
    }
    conn.execute(
        "INSERT INTO audit_log (audit_id, kind, ts, fields_json, ttl_pinned) "
        "VALUES (?, ?, ?, ?, ?)",
        (
            f"audit:{uuid.uuid4().hex[:16]}",
            kind,
            datetime.now(UTC).isoformat(),
            json.dumps(fields),
            None,
        ),
    )


# ---------------------------------------------------------------------------
# Schema — V1.6a migration 0008_website_crawl
# ---------------------------------------------------------------------------

SCHEMA_SQL: str = """
CREATE TABLE IF NOT EXISTS crawl_domains (
    domain_id            TEXT  PRIMARY KEY,
    domain               TEXT  NOT NULL UNIQUE,
    tier                 TEXT  NOT NULL,
    stage                TEXT  NOT NULL,
    cadence_cron         TEXT  NOT NULL,
    status               TEXT  NOT NULL,
    max_pages_per_run    INTEGER NOT NULL DEFAULT 500,
    max_pages_per_month  INTEGER NOT NULL DEFAULT 5000,
    max_usd_per_month    REAL  NOT NULL DEFAULT 5.00,
    concurrency          INTEGER NOT NULL DEFAULT 4,
    enable_ocr           INTEGER NOT NULL DEFAULT 0,
    enable_scrapingbee   INTEGER NOT NULL DEFAULT 0,
    confirm_l1           INTEGER NOT NULL DEFAULT 0,
    created_at           TEXT NOT NULL,
    updated_at           TEXT NOT NULL,
    created_by           TEXT NOT NULL,
    notes                TEXT
);

CREATE TABLE IF NOT EXISTS crawl_jobs (
    job_id               TEXT  PRIMARY KEY,
    domain_id            TEXT  NOT NULL,
    scheduled_at         TEXT NOT NULL,
    started_at           TEXT,
    finished_at          TEXT,
    status               TEXT  NOT NULL,
    trigger              TEXT  NOT NULL,
    pages_discovered     INTEGER,
    pages_fetched        INTEGER,
    pages_unchanged      INTEGER,
    pages_skipped_robots INTEGER,
    pages_skipped_size   INTEGER,
    pages_blocked        INTEGER,
    cost_usd             REAL,
    prefect_run_id       TEXT,
    error_excerpt        TEXT,
    FOREIGN KEY (domain_id) REFERENCES crawl_domains(domain_id)
);

CREATE TABLE IF NOT EXISTS crawl_fetch_log (
    fetch_id             TEXT  PRIMARY KEY,
    job_id               TEXT  NOT NULL,
    domain_id            TEXT  NOT NULL,
    url                  TEXT  NOT NULL,
    mime                 TEXT,
    status_code          INTEGER,
    etag                 TEXT,
    last_modified        TEXT,
    content_hash         TEXT,
    bytes                INTEGER,
    fetched_at           TEXT NOT NULL,
    via_proxy            INTEGER NOT NULL DEFAULT 0,
    cost_usd             REAL NOT NULL DEFAULT 0,
    latency_ms           INTEGER,
    cache_hit            INTEGER NOT NULL DEFAULT 0,
    error_excerpt        TEXT,
    FOREIGN KEY (job_id) REFERENCES crawl_jobs(job_id),
    FOREIGN KEY (domain_id) REFERENCES crawl_domains(domain_id)
);

CREATE TABLE IF NOT EXISTS crawl_cost (
    cost_id              TEXT  PRIMARY KEY,
    domain_id            TEXT  NOT NULL,
    job_id               TEXT,
    kind                 TEXT  NOT NULL,
    cost_usd             REAL NOT NULL,
    ts                   TEXT NOT NULL,
    notes                TEXT,
    FOREIGN KEY (domain_id) REFERENCES crawl_domains(domain_id),
    FOREIGN KEY (job_id)   REFERENCES crawl_jobs(job_id)
);

CREATE TABLE IF NOT EXISTS robots_cache (
    domain_id            TEXT  PRIMARY KEY,
    robots_txt           TEXT  NOT NULL,
    fetched_at           TEXT NOT NULL,
    expires_at           TEXT NOT NULL,
    allow_paths          TEXT,
    disallow_paths       TEXT,
    crawl_delay_s        REAL,
    sitemaps             TEXT,
    FOREIGN KEY (domain_id) REFERENCES crawl_domains(domain_id)
);

CREATE TABLE IF NOT EXISTS pages_index (
    page_index_id        TEXT  PRIMARY KEY,
    domain_id            TEXT  NOT NULL,
    url                  TEXT  NOT NULL,
    graph_node_id        TEXT  NOT NULL,
    mime                 TEXT,
    first_seen_at        TEXT NOT NULL,
    last_seen_at         TEXT NOT NULL,
    last_content_hash    TEXT,
    last_etag            TEXT,
    last_last_modified   TEXT,
    version_count        INTEGER NOT NULL DEFAULT 1,
    stage_l1_done_at     TEXT,
    stage_l2_done_at     TEXT,
    FOREIGN KEY (domain_id) REFERENCES crawl_domains(domain_id)
);

CREATE TABLE IF NOT EXISTS web_chunks_index (
    chunk_id             TEXT  PRIMARY KEY,
    page_index_id        TEXT  NOT NULL,
    graph_node_id        TEXT  NOT NULL,
    token_start          INTEGER NOT NULL,
    token_end            INTEGER NOT NULL,
    content_hash         TEXT  NOT NULL,
    embedding_dim        INTEGER NOT NULL DEFAULT 384,
    embedding_norm       REAL  NOT NULL,
    created_at           TEXT NOT NULL,
    FOREIGN KEY (page_index_id) REFERENCES pages_index(page_index_id)
);

CREATE INDEX IF NOT EXISTS idx_crawl_jobs_due
    ON crawl_jobs(scheduled_at, status) WHERE status IN ('queued');
CREATE INDEX IF NOT EXISTS idx_crawl_jobs_domain
    ON crawl_jobs(domain_id, finished_at DESC);
CREATE INDEX IF NOT EXISTS idx_crawl_fetch_log_job
    ON crawl_fetch_log(job_id, fetched_at);
CREATE INDEX IF NOT EXISTS idx_crawl_cost_domain_month
    ON crawl_cost(domain_id, ts);
CREATE INDEX IF NOT EXISTS idx_pages_index_domain_url
    ON pages_index(domain_id, url);
CREATE INDEX IF NOT EXISTS idx_web_chunks_page
    ON web_chunks_index(page_index_id);
"""


__all__ = [
    "SCHEMA_SQL",
    "CrawlDefaults",
    "CrawlDomainRow",
    "CrawlStage",
    "CrawlStatus",
    "CrawlTier",
    "WebsiteCrawlRegistry",
]
