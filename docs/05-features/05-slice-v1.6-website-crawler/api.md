# API — V1.6a Website-Crawl Ingestion

> Extends V1.5b/c. New routes under `/api/v1/ingest/web/*` + MCP outbound surface.

## FastAPI routes

### Domains

```
GET    /api/v1/ingest/web/domains
       ?status={active|paused|deleted|auto_paused|all}
       &q={domain-substring}
       &page={int}&page_size={int<=100}

POST   /api/v1/ingest/web/domains
       body = RegisterDomainRequest
       422 DOMAIN_BLOCKED | UNREACHABLE_DOMAIN | INVALID_CRON | L1_NOT_CONFIRMED

GET    /api/v1/ingest/web/domains/{domain_id}

PATCH  /api/v1/ingest/web/domains/{domain_id}
       body = UpdateDomainRequest
       (cadence, stage, max_pages_per_run, max_pages_per_month, max_usd_per_month,
        concurrency, enable_ocr, enable_scrapingbee, tier (with confirm_l1))

POST   /api/v1/ingest/web/domains/{domain_id}/pause
POST   /api/v1/ingest/web/domains/{domain_id}/resume
DELETE /api/v1/ingest/web/domains/{domain_id}             # soft delete

POST   /api/v1/ingest/web/domains/{domain_id}/purge-stage
       body = {level: "L1"|"L2"}
       Deletes downstream nodes/edges for the given stage; keeps L0.
```

### Crawl jobs

```
GET    /api/v1/ingest/web/domains/{domain_id}/jobs
       ?status={...}&page=...&page_size=...

GET    /api/v1/ingest/web/jobs/{job_id}

POST   /api/v1/ingest/web/domains/{domain_id}/run-now
       body = {force_full_refresh: bool = false}
       Enqueues a row; dispatcher picks up within 5 min.

POST   /api/v1/ingest/web/jobs/{job_id}/cancel       # cancels a queued or running job
```

### Pages

```
GET    /api/v1/ingest/web/domains/{domain_id}/pages
       ?mime={text/html|application/pdf|...}
       &q={url-substring}
       &page=...&page_size=...

GET    /api/v1/ingest/web/pages/{page_index_id}

GET    /api/v1/ingest/web/pages/{page_index_id}/history
       Returns bitemporal version list.

GET    /api/v1/ingest/web/pages/{page_index_id}/links
       Returns LINKS_TO targets (in-domain + ExternalRef).

GET    /api/v1/ingest/web/pages/{page_index_id}/entities
       L1 stage; returns MENTIONS edges + linked entities.

GET    /api/v1/ingest/web/pages/{page_index_id}/raw
       Returns the cached raw bytes (HTML / PDF / etc.).
```

### Cost / budget

```
GET    /api/v1/ingest/web/domains/{domain_id}/cost?days={n}
       Returns daily cost series for the last n days (default 30).

GET    /api/v1/ingest/web/domains/{domain_id}/budget
       Returns current spend + cap + projected_cost_next_run.

POST   /api/v1/ingest/web/domains/{domain_id}/budget/reset
       Manual unfreeze after `crawl_cap_hit`.
```

### Settings

```
GET    /api/v1/ingest/web/settings                       # globals (UA, contact email, cache dir, defaults)
PATCH  /api/v1/ingest/web/settings                       # admin-only knobs

GET    /api/v1/ingest/web/settings/scrapingbee
PATCH  /api/v1/ingest/web/settings/scrapingbee           # API key (plaintext .env per V1.5)
POST   /api/v1/ingest/web/settings/scrapingbee/health    # ping
```

### Blocklist

```
GET    /api/v1/ingest/web/blocklist
       Returns FORUM_DOMAINS + SOCIAL_DOMAINS + last_audit_at.
```

### HITL extensions (item types added by V1.6a)

V1.6a uses the existing HITL queue (`POST /api/v1/hitl/items/{id}/commit`) but introduces five new item types:

| Item type | Body schema | Resolution UI |
|---|---|---|
| `crawl_cap_hit` | `{domain_id, cap_usd, spent_usd, queued_pages}` | "Buy more budget" / "Skip rest of month" |
| `crawl_chronic_failure` | `{domain_id, failure_log[]}` | "Resume" / "Pause permanently" / "Delete" |
| `crawl_blocked` | `{domain_id, url, last_status, suggested_fix}` | "Retry once" / "Add to ScrapingBee fallback" / "Skip URL" |
| `entity_link_ambiguous` | `{page_id, mention, candidates[]}` | "Pick canonical" / "Mark new entity" / "Skip" |
| `budget_capped` | `{domain_id, projected_cost, remaining_budget}` | "Raise cap" / "Run only L0+L1" / "Skip run" |

## Pydantic schemas

```python
# src/web/schemas/website_crawl.py

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
    confirm_l1_immutable: bool = False   # required if tier = "L1"
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
    created_at: datetime
    updated_at: datetime
    created_by: str
    notes: str | None = None

class CrawlJob(BaseModel):
    model_config = ConfigDict(extra="forbid")
    job_id: str
    domain_id: str
    scheduled_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    status: Literal["queued", "running", "succeeded", "failed", "cancelled", "capped"]
    trigger: Literal["cron", "manual", "force_full_refresh"]
    pages_discovered: int | None
    pages_fetched: int | None
    pages_unchanged: int | None
    pages_skipped_robots: int | None
    pages_skipped_size: int | None
    pages_blocked: int | None
    cost_usd: float | None
    prefect_run_id: str | None
    error_excerpt: str | None
```

All Pydantic schemas have Zod counterparts generated via `make generate-types`.

## Error envelopes (V1.6a-specific)

| Code | HTTP | Meaning |
|---|---|---|
| `DOMAIN_BLOCKED` | 422 | Domain is on FORUM_DOMAINS or SOCIAL_DOMAINS list |
| `UNREACHABLE_DOMAIN` | 422 | Health-check failed at registration |
| `INVALID_CRON` | 422 | `cadence_cron` not parseable by `croniter` |
| `L1_NOT_CONFIRMED` | 422 | tier=L1 without confirm_l1_immutable=true |
| `BUDGET_EXCEEDED` | 429 | Per-domain monthly cap hit |
| `CRAWL_RUNNING` | 409 | Cannot mutate domain settings while a crawl is running |
| `SCRAPINGBEE_UNAVAILABLE` | 503 | ScrapingBee key invalid or quota exhausted |
| `OVERSIZED_PAGE` | 200 + warning | Page > 50 MB, skipped (informational) |

## Authentication

V1.6 stays single-user localhost (per V2 multi-tenant deferral). No auth required for these routes.

## Versioning

Routes mounted under `/api/v1/ingest/web/*`. V2 may introduce `/api/v2/*` with auth scoping; V1.6a stays in v1.

## MCP outbound surface

Tools exposed via `src/integrations/mcp_crawl_tools.py`:

```python
@mcp_tool
def register_crawl_domain(
    domain: str,
    tier: Literal["L1", "L2"] = "L2",
    stage: Literal["L0", "L1", "L2"] = "L1",
    cadence_cron: str = "0 6 * * *",
    max_pages_per_run: int = 500,
    max_pages_per_month: int = 5000,
    max_usd_per_month: float = 5.0,
    concurrency: int = 4,
    enable_ocr: bool = False,
    enable_scrapingbee: bool = False,
    confirm_l1_immutable: bool = False,
    notes: str | None = None,
) -> CrawlDomain: ...

@mcp_tool
def list_crawl_domains(
    status: str | None = None,
    q: str | None = None,
) -> list[CrawlDomain]: ...

@mcp_tool
def get_crawl_status(domain: str) -> dict: ...
# Returns {'domain': CrawlDomain, 'last_job': CrawlJob | None, 'next_run_at': datetime | None,
#          'pages_count': int, 'month_cost_usd': float, 'month_cap_usd': float}

@mcp_tool
def trigger_crawl_now(domain: str, force_full_refresh: bool = False) -> CrawlJob: ...

@mcp_tool
def pause_crawl_domain(domain: str) -> CrawlDomain: ...

@mcp_tool
def update_crawl_cadence(domain: str, cadence_cron: str) -> CrawlDomain: ...
```

Every MCP tool writes an `audit_log` row with the calling actor; failures return structured errors mirroring the FastAPI ones above.
