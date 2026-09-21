# Data Model

> V1 slice subset of the V1 product engine's full data model. The full schema lives in `docs/07-data/data-dictionary.md` (TBD next batch). This file describes what V1 slice actually populates + queries.

## Two stores

1. **Graph store** (**Kùzu** `0.11.3`, ADR-001 — bake-off complete 2026-05-21; Graphiti+Neo4j is the V2 swap-target) — nodes + edges + HNSW vector index.
2. **SQLite side store** — L1 ground truth (loaded from ADEA Excel) + HITL queue + extraction cache + audit log + lightweight relational lookups.

If the bake-off lands on Postgres+AGE+pgvector, the two stores collapse into one Postgres instance.

## Property conventions (apply to every node + edge in V1)

| Property | Type | Notes |
|---|---|---|
| `source_tier` | enum `L1`/`L2`/`L3`/`L4`/`L5` | A-014. Required on every node + edge. |
| `rank` | enum `preferred`/`normal`/`deprecated` | Wikidata-style. Required on every claim edge. A-028. |
| `references` | list[str] | Citation back-pointers (source `dump_id`, `post_id`, etc.). Required ≥ 1 on every claim edge for FR-8.3. |
| `qualifiers` | dict | Free-form context (e.g., `{"out_of_state": true}` on a tuition claim). |
| `t_valid_from` | datetime | Wall-clock start of validity. Required on every edge. A-027. |
| `t_valid_to` | datetime \| NULL | NULL = open-ended. Required on every edge. |
| `t_ingest_from` | datetime | When the graph first learned this. Required. |
| `t_ingest_to` | datetime \| NULL | NULL = still current. Set when superseded. |
| `created_utc` | datetime | Wall-clock content creation time (e.g., Reddit `created_utc`). |
| `confidence` | float [0,1] | Extraction confidence. Defaults to 1.0 for L1; computed for L5. |
| `status` | enum (see below) | Lifecycle. Default `active`. |

`status` values:
- `active` — current.
- `superseded` — replaced by a newer ingest; preserved for bitemporal "as-of" queries.
- `invalidated_by_official_data` — L1 clash flagged the claim. FR-6.1.
- `anomaly` — outlier preserved per A-032.
- `hitl_pending` — awaiting reviewer.
- `hitl_committed` — reviewer decided.
- `unresolved_entity` — alias snap failed (<0.75 sim).

## SQLite side store schema

### `l1_school` (canonical universe; populated from ADEA Excel)
```
canonical_id        TEXT  PRIMARY KEY    -- e.g., "school:nyu_dental"
canonical_name      TEXT  NOT NULL
city                TEXT
state               TEXT
country             TEXT  DEFAULT 'US'
ada_code            TEXT  -- ADA-issued code if available
website             TEXT
source_dump_id      TEXT  NOT NULL       -- back to ADEA dump
created_utc         DATETIME
```

### `l1_school_year_metric`
```
metric_id            TEXT  PRIMARY KEY
canonical_school_id  TEXT  REFERENCES l1_school(canonical_id)
cycle_year           TEXT  NOT NULL       -- e.g., "2024-25"
metric_name          TEXT  NOT NULL       -- "tuition_resident", "avg_DAT_AA", "avg_GPA_science", ...
metric_value         REAL
unit                 TEXT
source_dump_id       TEXT  NOT NULL
source_row           TEXT                 -- back to specific Excel cell range
t_valid_from         DATETIME NOT NULL
t_valid_to           DATETIME
```

### `l1_program` (residency / advanced programs from CODA SADV)
```
canonical_program_id TEXT  PRIMARY KEY
canonical_school_id  TEXT  REFERENCES l1_school(canonical_id)
specialty            TEXT  NOT NULL       -- "Endodontics", "Periodontics", etc.
duration_months      INT
source_dump_id       TEXT  NOT NULL
```

### `dump`
```
dump_id              TEXT  PRIMARY KEY
source_tier          TEXT  NOT NULL
source_name          TEXT
manifest_json        TEXT  NOT NULL
content_hashes_json  TEXT  NOT NULL       -- list of file content-hashes
t_ingest_from        DATETIME NOT NULL
```

### `alias` (the L1 canonical alias list)
```
alias_id             TEXT  PRIMARY KEY
canonical_id         TEXT  NOT NULL       -- → l1_school or l1_program
alias_text           TEXT  NOT NULL
alias_source         TEXT                 -- "manual", "hitl", "discovered"
confidence           REAL
created_utc          DATETIME
```

### `hitl_queue`
```
item_id              TEXT  PRIMARY KEY
item_type            TEXT  NOT NULL       -- "alias_match", "conflict", "new_type_proposal", "judge_disagreement"
payload_json         TEXT  NOT NULL
status               TEXT  NOT NULL       -- "pending", "claimed", "committed", "escalated"
claimed_by           TEXT
claimed_at           DATETIME
committed_at         DATETIME
decision_json        TEXT
```

### `extraction_cache` (R-008 §1.8, content-addressable)
```
cache_key            TEXT  PRIMARY KEY    -- hash(thread + prompt_id + prompt_version + schema_hash + model_id)
output_json          TEXT  NOT NULL
vendor               TEXT
model                TEXT
model_version        TEXT
input_tokens         INT
output_tokens        INT
cached_input_tokens  INT
cost_usd             REAL
created_utc          DATETIME
```

### `audit_log` (FR-11)
```
audit_id             TEXT  PRIMARY KEY
kind                 TEXT  NOT NULL       -- "extraction" | "retrieval" | "hitl" | "ingestion"
ts                   DATETIME NOT NULL
fields_json          TEXT  NOT NULL       -- per-kind schema (see FR-11)
ttl_pinned           INT                  -- must be 3600 for extraction; lint enforced
```

## Graph node types (V1 slice)

| Label | Tier | Notes |
|---|---|---|
| `School` | L1 | canonical (mirrors `l1_school`). Immutable. |
| `Program` | L1 | canonical (mirrors `l1_program`). Immutable. |
| `CycleYear` | L1 | "2024-25" etc. |
| `Metric` | L1 | named yearly metrics on schools. |
| `Post` | L5 | Reddit posts + SDN threads. Properties: `title`, `body`/`selftext`, `created_utc`, `score`, `ups`, `downs`, `num_comments`. Reddit only on score fields; SDN nulls them. |
| `Comment` | L5 | Reddit comments only (SDN posts collapse comments into post graph). |
| `User` | L5 | Author. ID namespaced: `reddit:<sub>:<author>` or `sdn:<author>`. |
| `Topic` | derived | Emergent from Stage 1 + clustering. Examples: `Topic:DAT_prep`, `Topic:Interview_attire`. |
| `Claim` | L5-derived | Atomic factual / opinion claim extracted from a Post or Comment. |
| `InterviewQuestion` | L5-derived | Specific reported interview question. |
| `Conflict` | derived | Marker node when conflict resolution triggers. |
| `HITLItem` | meta | Mirror of `hitl_queue` row for graph-side join. |
| `Dump` | meta | Mirror of `dump` row for provenance edges. |
| `UnresolvedEntity` | L5-derived | Mention that failed alias snap. |

## Graph edge types (V1 slice)

| Edge | From → To | Tier inherited from |
|---|---|---|
| `AUTHORED` | User → Post / Comment | L5 |
| `COMMENTED` | User → Comment | L5 |
| `REPLIED_TO` | Comment → Post / Comment | L5 |
| `BELONGS_TO_THREAD` | Post / Comment → Post (root) | L5 |
| `POSTED_IN_FORUM` | Post → Subreddit / SDNCategory | L5 |
| `MENTIONS_SCHOOL` | Post / Comment → School | L5 |
| `MENTIONS_PROGRAM` | Post / Comment → Program | L5 |
| `MENTIONS_METRIC` | Claim → Metric | L5 |
| `SUPPORTS` | Claim → Claim | L5 |
| `CONTRADICTS` | Claim → Claim | L5 |
| `REFERENCES_TOPIC` | Post / Comment / Claim → Topic | L5 |
| `HAS_ALIAS` | School / Program → Alias-string | L1 |
| `INVALIDATED_BY` | L5-Claim → L1-Metric / Claim | L5 (forum-side flag) |
| `SCHOOL_HAS_METRIC` | School → Metric | L1 |
| `SCHOOL_OFFERS_PROGRAM` | School → Program | L1 |
| `PROVENANCE` | * → Dump | meta |

Every edge above carries the property convention (top of file).

## Vector embeddings (V1 slice)

- One embedding per Post body, Comment body, Topic descriptor, and School canonical-name. BGE-small (384-d).
- Stored in the graph DB's native HNSW index (whichever wins the bake-off).
- Index parameters tuned in Phase 0.4 of the bake-off; default `M=16`, `ef_construction=200`, `ef_search=64` for first cut.
- Rebuilt nightly per R-005 R5 (HNSW degrades under deletions/updates).

## Canonical ID conventions

| Type | Pattern | Example |
|---|---|---|
| School | `school:<slug>` | `school:nyu_dental` |
| Program | `program:<school_slug>:<specialty_slug>` | `program:nyu_dental:endodontics` |
| User (Reddit) | `reddit:<sub>:<author>` | `reddit:DentalSchool:throwaway123` |
| User (SDN) | `sdn:<author>` | `sdn:doc_toothache` |
| Post (Reddit) | `reddit_post:<id>` | `reddit_post:hl06x` |
| Post (SDN) | `sdn_post:<thread_id>:<post_id>` | `sdn_post:1000053:13959604` |
| Topic | `topic:<slug>` | `topic:dat_prep` |
| Claim | `claim:<sha256_prefix>` | `claim:a1b2c3d4...` |
| Dump | `dump:<sha256_prefix>` | `dump:fe9d...` |

## Out-of-scope this slice (data-model deferrals)

- L2 / L3 / L4 nodes — schema slots reserved but not populated.
- `Anomaly` clusters surfaced via signed-graph community detection — computed offline but not yet first-class retrieval primitives.
- Logistic-regression user-credibility weights (V1.1).
- Web-verification responder edges (the slice emits `research_need` records, doesn't act on them).
- Cross-source user identity reconciliation (a future "is `reddit:DentalSchool:foo` the same person as `sdn:foo`?" inference is out of V1).
