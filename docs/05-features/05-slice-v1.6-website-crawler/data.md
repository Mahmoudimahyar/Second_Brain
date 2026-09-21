# Data Model — V1.6a Website-Crawl Ingestion

> Extends V1 + V1.5a + V1.5b + V1.5c. New SQLite tables for crawl scheduling + fetch + cost; new graph node + edge types for Pages / Sitemaps / MediaAssets / Tables.

## New SQLite tables

### `crawl_domains`

```
domain_id            TEXT  PRIMARY KEY               -- "web:<sha256-16-of-domain>"
domain               TEXT  NOT NULL UNIQUE           -- e.g. "www.adea.org"
tier                 TEXT  NOT NULL                  -- "L1" / "L2"
stage                TEXT  NOT NULL                  -- "L0" / "L1" / "L2"
cadence_cron         TEXT  NOT NULL                  -- e.g. "0 6 * * *"
status               TEXT  NOT NULL                  -- "active" / "paused" / "deleted" / "auto_paused"
max_pages_per_run    INTEGER NOT NULL DEFAULT 500
max_pages_per_month  INTEGER NOT NULL DEFAULT 5000
max_usd_per_month    REAL  NOT NULL DEFAULT 5.00
concurrency          INTEGER NOT NULL DEFAULT 4
enable_ocr           INTEGER NOT NULL DEFAULT 0
enable_scrapingbee   INTEGER NOT NULL DEFAULT 0
confirm_l1           INTEGER NOT NULL DEFAULT 0      -- required if tier=L1
created_at           DATETIME NOT NULL
updated_at           DATETIME NOT NULL
created_by           TEXT NOT NULL                   -- actor
notes                TEXT
```

### `crawl_jobs`

```
job_id               TEXT  PRIMARY KEY              -- "job:<uuid>"
domain_id            TEXT  NOT NULL REFERENCES crawl_domains(domain_id)
scheduled_at         DATETIME NOT NULL              -- when due
started_at           DATETIME
finished_at          DATETIME
status               TEXT  NOT NULL                 -- "queued" / "running" / "succeeded" / "failed" / "cancelled" / "capped"
trigger              TEXT  NOT NULL                 -- "cron" / "manual" / "force_full_refresh"
pages_discovered     INTEGER
pages_fetched        INTEGER
pages_unchanged      INTEGER
pages_skipped_robots INTEGER
pages_skipped_size   INTEGER
pages_blocked        INTEGER
cost_usd             REAL
prefect_run_id       TEXT
error_excerpt        TEXT
```

### `crawl_fetch_log`

```
fetch_id             TEXT  PRIMARY KEY              -- "fetch:<uuid>"
job_id               TEXT  NOT NULL REFERENCES crawl_jobs(job_id)
domain_id            TEXT  NOT NULL REFERENCES crawl_domains(domain_id)
url                  TEXT  NOT NULL
mime                 TEXT
status_code          INTEGER
etag                 TEXT
last_modified        TEXT
content_hash         TEXT
bytes                INTEGER
fetched_at           DATETIME NOT NULL
via_proxy            INTEGER NOT NULL DEFAULT 0     -- 1 = ScrapingBee
cost_usd             REAL NOT NULL DEFAULT 0
latency_ms           INTEGER
cache_hit            INTEGER NOT NULL DEFAULT 0
error_excerpt        TEXT
```

### `crawl_cost`

```
cost_id              TEXT  PRIMARY KEY              -- "cost:<uuid>"
domain_id            TEXT  NOT NULL REFERENCES crawl_domains(domain_id)
job_id               TEXT  REFERENCES crawl_jobs(job_id)
kind                 TEXT  NOT NULL                 -- "scrapingbee" / "l2_summary" / "l2_extract" / "ocr"
cost_usd             REAL NOT NULL
ts                   DATETIME NOT NULL
notes                TEXT
```

### `robots_cache`

```
domain_id            TEXT  PRIMARY KEY REFERENCES crawl_domains(domain_id)
robots_txt           TEXT  NOT NULL
fetched_at           DATETIME NOT NULL
expires_at           DATETIME NOT NULL              -- min(max-age, 24h)
allow_paths          TEXT                           -- JSON
disallow_paths       TEXT                           -- JSON
crawl_delay_s        REAL
sitemaps             TEXT                           -- JSON list
```

### `pages_index`

> Lightweight side-table for fast "what pages have we seen for this domain" lookups; the canonical record lives in the graph.

```
page_index_id        TEXT  PRIMARY KEY               -- "pageidx:<sha256-16-of-url>"
domain_id            TEXT  NOT NULL REFERENCES crawl_domains(domain_id)
url                  TEXT  NOT NULL
graph_node_id        TEXT  NOT NULL                  -- "page:<sha256-16>"
mime                 TEXT
first_seen_at        DATETIME NOT NULL
last_seen_at         DATETIME NOT NULL
last_content_hash    TEXT
last_etag            TEXT
last_last_modified   TEXT
version_count        INTEGER NOT NULL DEFAULT 1
stage_l1_done_at     DATETIME
stage_l2_done_at     DATETIME
```

### `web_chunks_index`

> Side-table backing L1 chunk-embedding lookups. Mirrors V1's chunk index schema.

```
chunk_id             TEXT  PRIMARY KEY              -- "chunk:<sha256-16-of-content>"
page_index_id        TEXT  NOT NULL REFERENCES pages_index(page_index_id)
graph_node_id        TEXT  NOT NULL                 -- corresponding Chunk node in graph
token_start          INTEGER NOT NULL
token_end            INTEGER NOT NULL
content_hash         TEXT  NOT NULL
embedding_dim        INTEGER NOT NULL DEFAULT 384
embedding_norm       REAL  NOT NULL
created_at           DATETIME NOT NULL
```

## Migrations

All five tables ship as one migration `migrations/0008_website_crawl.sql`. Backward-compatible — existing tables not touched.

## New graph node types

All carry V1's bitemporal stamps (`t_valid_from`, `t_valid_to`, `t_ingest_from`, `t_ingest_to`), `source_tier`, `rank`, `references`, and `qualifiers` per ADR-005.

### `Page`

```
node_id:        "page:<sha256-16-of-url+content_hash>"
url:            string                  -- canonical (HTML <link rel="canonical"> if present, else fetch URL)
domain:         string                  -- FQDN
mime:           string                  -- text/html / application/pdf / ...
title:          string                  -- HTML <title> / PDF metadata title / first heading
body_md:        string                  -- Trafilatura main-content as Markdown (HTML pages only)
content_hash:   string                  -- sha256 of raw bytes
etag:           string | null
last_modified:  string | null
bytes:          integer
crawled_at:     datetime
domain_id:      string                  -- FK to crawl_domains
source_tier:    "L1" | "L2"
rank:           "preferred" | "normal" | "deprecated"
```

### `Sitemap`

```
node_id:        "sitemap:<sha256-16-of-url>"
url:            string                  -- sitemap URL
domain:         string
urlset_count:   integer                 -- number of <url> entries
last_fetched:   datetime
sub_sitemaps:   string[]                -- child sitemap URLs (for sitemap-index)
source_tier:    "L1" | "L2"
```

### `MediaAsset`

```
node_id:        "asset:<sha256-16-of-url>"
url:            string
domain:         string
mime:           string                  -- image/* / video/* / audio/* / etc.
alt:            string | null
bytes:          integer
ocr_text:       string | null           -- populated only when enable_ocr=true
ocr_engine:     string | null           -- e.g. "easyocr-1.7.x"
source_tier:    "L1" | "L2"
```

### `Table`

```
node_id:        "table:<sha256-16-of-url+ordinal>"
parent_page_id: string                  -- FK to Page.node_id
ordinal:        integer                 -- 0-indexed position in page
caption:        string | null
rows:           integer
cols:           integer
cells_json:     string                  -- JSON [[r0c0, r0c1, ...], ...]
source_tier:    "L1" | "L2"
```

### `Entity` (extension of existing V1 Entity nodes)

V1.6a doesn't introduce a new `Entity` type; it reuses V1's existing entity nodes (`Person`, `Organization`, `Place`, `Date`, `Money`, `Program`, `School-or-Institution`, `Procedure`, etc.) and writes `MENTIONS` edges from `Chunk`/`Page` to them.

### `ExternalRef` (lightweight placeholder)

```
node_id:        "extref:<sha256-16-of-url>"
url:            string                  -- out-of-corpus URL
first_seen_at:  datetime
source_tier:    "L2"                    -- always L2 (we haven't verified it)
```

## New graph edge types

All carry V1's bitemporal stamps + `source_tier` + `rank` per ADR-005.

| Edge | From | To | Cardinality | Notes |
|---|---|---|---|---|
| `LINKS_TO` | `Page` | `Page` \| `ExternalRef` | many-to-many | one per `<a href>` in body, deduplicated within a page |
| `BELONGS_TO_SITEMAP` | `Page` | `Sitemap` | many-to-one | URL appeared in sitemap.xml |
| `EMBEDS` | `Page` | `MediaAsset` | many-to-many | `<img>` / `<video>` / `<audio>` |
| `TABLE_OF` | `Page` | `Table` | one-to-many | HTML `<table>` block |
| `HAS_CHUNK` | `Page` | `Chunk` | one-to-many | L1 stage |
| `MENTIONS` | `Chunk` \| `Page` | `Entity` | many-to-many | L1 stage; carries `confidence` float |
| `REFERENCES_TOPIC` | `Chunk` \| `Page` | `Topic` | many-to-many | L1 stage |
| `IN_CLUSTER` | `Chunk` | `Cluster` | many-to-one | L2 stage |
| `SUMMARIZES` | `Summary` | `Cluster` | one-to-one | L2 stage |
| `CLAIMS_FROM` | `Claim` | `Chunk` | one-to-many | L2 stage; ties claim back to text |
| `SUPPORTS` / `CONTRADICTS` | `Claim` | `Claim` \| existing graph claim | many-to-many | L2 stage; per V1 ADR-006 |

## Domain summary view (SQL)

```sql
CREATE VIEW v_domain_summary AS
SELECT
    d.domain_id, d.domain, d.tier, d.stage, d.cadence_cron, d.status,
    COUNT(DISTINCT pi.page_index_id) AS pages_count,
    SUM(CASE WHEN pi.stage_l1_done_at IS NOT NULL THEN 1 ELSE 0 END) AS pages_l1_done,
    SUM(CASE WHEN pi.stage_l2_done_at IS NOT NULL THEN 1 ELSE 0 END) AS pages_l2_done,
    COALESCE(SUM(c.cost_usd), 0)              AS month_cost_usd,
    d.max_usd_per_month                       AS month_cap_usd,
    (
      SELECT MAX(j.finished_at) FROM crawl_jobs j
       WHERE j.domain_id = d.domain_id AND j.status = 'succeeded'
    ) AS last_succeeded_at,
    (
      SELECT MIN(j.scheduled_at) FROM crawl_jobs j
       WHERE j.domain_id = d.domain_id AND j.status IN ('queued','running')
    ) AS next_run_at
FROM crawl_domains d
LEFT JOIN pages_index pi ON pi.domain_id = d.domain_id
LEFT JOIN crawl_cost c   ON c.domain_id = d.domain_id
                        AND c.ts >= date('now','start of month')
GROUP BY d.domain_id;
```

## Bitemporal write semantics

Re-crawl with new `content_hash` for an existing `Page`:

1. `UPDATE page SET t_valid_to = :now, t_ingest_to = :now WHERE node_id = :prior_node_id AND t_valid_to IS NULL`
2. `INSERT new Page node` with `t_valid_from = :now`, `t_ingest_from = :now`, new `content_hash`.
3. Tombstone-then-rewrite for downstream chunks: `Chunk` rows for prior `Page` get `t_valid_to = :now`. New chunks open.
4. Entity `MENTIONS` edges flow follow: any `MENTIONS` edge pointing to a closed chunk is automatically closed by the bitemporal write helper in V1.

Removed URL (in sitemap last run, absent this run):

1. Mark `pages_index.last_seen_at = :now - max_pages_per_run × cadence` (heuristic — only consider removed after one full cadence cycle absent).
2. After two consecutive absences (≥ 2 × cadence apart), close `Page` node with `t_valid_to = :now`.

## Index recommendations

```sql
CREATE INDEX idx_crawl_jobs_due           ON crawl_jobs(scheduled_at, status) WHERE status IN ('queued');
CREATE INDEX idx_crawl_jobs_domain        ON crawl_jobs(domain_id, finished_at DESC);
CREATE INDEX idx_crawl_fetch_log_job      ON crawl_fetch_log(job_id, fetched_at);
CREATE INDEX idx_crawl_cost_domain_month  ON crawl_cost(domain_id, ts);
CREATE INDEX idx_pages_index_domain_url   ON pages_index(domain_id, url);
CREATE INDEX idx_web_chunks_page          ON web_chunks_index(page_index_id);
```

## .env additions

```
# Required when V1.6a is active
CRAWL4AI_USER_AGENT=SecBrain/1.6 (+you@example.com)
CRAWL4AI_CONTACT_EMAIL=you@example.com
CRAWL4AI_MAX_CONCURRENCY=4

# Optional — opt-in proxy fallback
SCRAPINGBEE_API_KEY=

# Budget defaults (used at domain registration time)
WEBSITE_CRAWL_DEFAULT_BUDGET_USD=5.00
WEBSITE_CRAWL_DEFAULT_BUDGET_PAGES=5000

# Local cache (per NFR-1.6a-7)
WEB_CACHE_DIR=data/web_cache
WEB_CACHE_MAX_BYTES=5368709120     # 5 GB
```
