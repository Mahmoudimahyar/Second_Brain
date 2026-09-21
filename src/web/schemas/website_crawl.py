"""V1.6a — Pydantic request + response models for /api/v1/ingest/web/*.

Per api.md §"Pydantic schemas". Each schema mirrors the data.md table
shape; Zod codegen runs at `make generate-types` time and writes to
`web/src/lib/api/generated/`.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class RegisterDomainRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    domain: str = Field(..., min_length=3, max_length=253)
    tier: Literal["L1", "L2"] = "L2"
    stage: Literal["L0", "L1", "L2"] = "L1"
    cadence_cron: str = Field("0 6 * * *")
    max_pages_per_run: int = Field(500, ge=1, le=10_000)
    max_pages_per_month: int = Field(5_000, ge=1, le=1_000_000)
    max_usd_per_month: float = Field(5.0, ge=0, le=10_000)
    concurrency: int = Field(4, ge=1, le=16)
    enable_ocr: bool = False
    enable_scrapingbee: bool = False
    confirm_l1_immutable: bool = False
    notes: str | None = None


class UpdateDomainRequest(BaseModel):
    """All fields optional — PATCH semantics. tier change requires confirm_l1_immutable."""

    model_config = ConfigDict(extra="forbid")

    tier: Literal["L1", "L2"] | None = None
    stage: Literal["L0", "L1", "L2"] | None = None
    cadence_cron: str | None = None
    max_pages_per_run: int | None = Field(None, ge=1, le=10_000)
    max_pages_per_month: int | None = Field(None, ge=1, le=1_000_000)
    max_usd_per_month: float | None = Field(None, ge=0, le=10_000)
    concurrency: int | None = Field(None, ge=1, le=16)
    enable_ocr: bool | None = None
    enable_scrapingbee: bool | None = None
    confirm_l1_immutable: bool = False
    notes: str | None = None


class CrawlDomain(BaseModel):
    model_config = ConfigDict(extra="forbid")

    domain_id: str
    domain: str
    tier: Literal["L1", "L2"]
    stage: Literal["L0", "L1", "L2"]
    cadence_cron: str
    status: Literal["active", "paused", "deleted", "auto_paused"]
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


class CrawlJob(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str
    domain_id: str
    scheduled_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    status: Literal[
        "queued", "running", "succeeded", "failed", "cancelled", "capped",
    ]
    trigger: Literal["cron", "manual", "force_full_refresh"]
    pages_discovered: int | None = None
    pages_fetched: int | None = None
    pages_unchanged: int | None = None
    pages_skipped_robots: int | None = None
    pages_skipped_size: int | None = None
    pages_blocked: int | None = None
    cost_usd: float | None = None
    prefect_run_id: str | None = None
    error_excerpt: str | None = None


class CrawlDomainList(BaseModel):
    model_config = ConfigDict(extra="forbid")

    domains: list[CrawlDomain]
    total: int


class CrawlJobList(BaseModel):
    model_config = ConfigDict(extra="forbid")

    jobs: list[CrawlJob]
    total: int


class TriggerRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    force_full_refresh: bool = False


class BlocklistResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    forum_domains: list[str]
    social_domains: list[str]


class BudgetSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    domain_id: str
    spent_month_usd: float
    cap_usd: float
    projected_next_run_usd: float | None = None


__all__ = [
    "BlocklistResponse",
    "BudgetSnapshot",
    "CrawlDomain",
    "CrawlDomainList",
    "CrawlJob",
    "CrawlJobList",
    "RegisterDomainRequest",
    "TriggerRunRequest",
    "UpdateDomainRequest",
]
