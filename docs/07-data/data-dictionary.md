# Data Dictionary

> V1 product engine. Combines the V1 slice's local schema (in `docs/05-features/01-slice-trust-tier-canonicalize/data.md`) with the engine-wide types and reserved slots for V2 expansion. Source of truth for the canonical entity / edge / property model.

## Property convention (applies to every node + edge)

| Field | Type | Required | Description |
|---|---|---|---|
| `source_tier` | enum `L1`/`L2`/`L3`/`L4`/`L5` | yes | Trust ladder. Drives ranking + conflict resolution. |
| `rank` | enum `preferred`/`normal`/`deprecated` | yes on claim edges | Wikidata-style preference flag. L1 edges = `preferred` by default. |
| `references` | list[str] | yes on claim edges (≥1) | Citation back-pointers: source `dump_id`, `post_id`, etc. |
| `qualifiers` | dict[str, Any] | optional | Free-form context (e.g., `{"out_of_state": true}` on tuition). |
| `t_valid_from` | datetime UTC | yes | Wall-clock start of validity. |
| `t_valid_to` | datetime UTC \| NULL | yes (NULL = open-ended) | End of validity. |
| `t_ingest_from` | datetime UTC | yes | When the graph first held this version. |
| `t_ingest_to` | datetime UTC \| NULL | yes (NULL = still current) | Set when superseded. |
| `created_utc` | datetime UTC | yes | Wall-clock content creation time (e.g., Reddit `created_utc`). |
| `confidence` | float [0, 1] | yes | Extraction / claim confidence. L1 = 1.0; computed for L5. |
| `status` | enum (see below) | yes | Lifecycle state. Default `active`. |

### `status` enum
- `active` — current, queryable by default.
- `superseded` — replaced by a newer ingest; preserved for bitemporal "as-of" queries.
- `invalidated_by_official_data` — L1 clash flagged the (non-L1) claim. FR-6.1.
- `anomaly` — outlier preserved per A-032.
- `hitl_pending` — awaiting reviewer.
- `hitl_committed` — reviewer decided.
- `unresolved_entity` — alias snap failed (<0.75 similarity).
- `refused_l1_immutable` — attempted modification of an L1 node was rejected.
- `failed` — ingestion / extraction failure.

## Node taxonomy (V1 + V2 slots)

| Label | Trust tier(s) | V1? | Description |
|---|---|---|---|
| `School` | L1 | ✓ V1 | US dental school, canonical (ADEA). |
| `Program` | L1 | ✓ V1 | Residency / advanced-program (CODA SADV). |
| `CycleYear` | L1 | ✓ V1 | "2024-25" application/academic cycle. |
| `Metric` | L1 | ✓ V1 | Named yearly metric on a school (e.g., `tuition_resident`). |
| `SchoolAttribute` | L1 | ✓ V1 | Slow-changing structural attribute (city, state, founding_year). |
| `Post` | L5 | ✓ V1 | Reddit post or SDN top-of-thread post. Bodies → embedded chunks for retrieval. |
| `Comment` | L5 | ✓ V1 | Reddit comment (SDN treats follow-up posts as Posts; reserved). |
| `Thread` | L5 | ✓ V1 | Container with title + category for SDN; Reddit `link_id` group. |
| `User` | L5 | ✓ V1 | Namespaced `reddit:<sub>:<author>` or `sdn:<author>`. Carries derived `credibility` score. |
| `Subreddit` / `SDNCategory` | L5 | ✓ V1 | Forum container (`Subreddit: DentalSchool` etc.). |
| `Topic` | derived | ✓ V1 | Emergent from Stage-1 + community clustering (e.g., `Topic: DAT_prep`). |
| `Claim` | L5-derived | ✓ V1 | Atomic factual / opinion claim extracted from a Post or Comment. |
| `InterviewQuestion` | L5-derived | ✓ V1 | Specific reported interview question, linked to a `School`. |
| `Conflict` | derived | ✓ V1 | Marker when conflict resolution triggers; tracks resolution path. |
| `ResearchNeed` | derived | ✓ V1 | Queued for the outbound MCP `get_research_needs()` tool. |
| `HITLItem` | meta | ✓ V1 | Mirror of `hitl_queue` row, for graph joins. |
| `Dump` | meta | ✓ V1 | Mirror of `dump` row, for provenance edges. |
| `Alias` | meta | ✓ V1 | Alternative string name for a canonical entity. |
| `UnresolvedEntity` | L5-derived | ✓ V1 | Mention that failed alias-snap. |
| `Cluster` | derived | ✓ V1 (offline only) | Signed-graph community on opinion layer. V1 stores it but doesn't yet rank by it in retrieval. |
| `L2Document` | L2 | ✓ V1 | Unstructured authoritative page (ADEA blog, ADA news, ASDA blog). One node per HTML file, body tag-stripped. Materialized by `src/ingestion/adapters/l2_html.py`. |
| `CommercialDoc` | L4 | reserved V2 | Paid guide / third-party blog. |
| `StructuredNonOfficial` | L3 | reserved V2 | Non-authoritative numeric data. |
| `Page` | L1 | ✓ V1 (crawler) | A crawled web page from an L1 official domain (adea.org, ada.org, etc.). Key props: `url`, `title`, `source_tier=L1`, `retrieved_date`, `content_hash`. Materialized by `flows/website_crawl_worker.py`. |
| `Chunk` | L1 | ✓ V1 (crawler) | A text/table chunk extracted from a `Page`. Key props: `chunk_type` (text/table/pdf_text), `body`, `source_url`. Linked to Page via `CHUNK_OF` edge. |
| `MediaAsset` | L1/L5 | ✓ V1 (crawler) | An image, PDF, or file linked from a Page. |
| `ExternalRef` | any | ✓ V1 (crawler) | An outbound URL linked from a crawled Page. |
| `ForumConsensus` | derived | ✓ V1 | Per-school aggregate of forum-derived metric medians (n, p25, p50, p75, range). One node per school × metric type. Key props: `school_id`, `predicate_canonical`, `n`, `p50`, etc. Linked via `CONSENSUS_FOR` edge. Built by `cloud/resolve_and_persist.py`. |
| `SentimentAnnotation` | derived | ✓ V1 | Sentiment verdict (positive/negative/neutral) extracted from a Post or Comment by Pass 4. Key props: `verdict`, `confidence`, `post_id`. Linked via `ANNOTATES` edge. **Note:** this is *per-document polarity*, not stance-on-a-topic — see GAP-059 for stance clustering. |

## Edge taxonomy

| Edge | From → To | Direction | Tier | V1? | Notes |
|---|---|---|---|---|---|
| `AUTHORED` | User → Post / Comment | →  | L5 | ✓ | One edge per authorship. |
| `COMMENTED` | User → Comment | → | L5 | ✓ | Implied by AUTHORED on Comment; kept for query simplicity. |
| `REPLIED_TO` | Comment → Post / Comment | → | L5 | ✓ | Thread reconstruction via `parent_id`. |
| `BELONGS_TO_THREAD` | Post / Comment → Thread | → | L5 | ✓ | |
| `POSTED_IN_FORUM` | Thread → Subreddit / SDNCategory | → | L5 | ✓ | |
| `MENTIONS_SCHOOL` | Post / Comment → School | → | L5 | ✓ | Carries `confidence` from ER. |
| `MENTIONS_PROGRAM` | Post / Comment → Program | → | L5 | ✓ | |
| `MENTIONS_METRIC` | Claim → Metric | → | L5 | ✓ | When a claim references a specific L1 metric (e.g., NYU tuition). |
| `STATES_VALUE` | Claim → primitive value | (data edge) | L5 | ✓ | Claim's asserted value (e.g., "$40,000"); `qualifiers` hold context. |
| `SUPPORTS` | Claim → Claim | → | L5 | ✓ | Signed-graph positive edge. |
| `CONTRADICTS` | Claim → Claim | → | L5 | ✓ | Signed-graph negative edge. |
| `REFERENCES_TOPIC` | Post / Comment / Claim → Topic | → | L5 | ✓ | |
| `HAS_ALIAS` | School / Program → Alias | → | L1 | ✓ | |
| `INVALIDATED_BY` | L5-Claim → L1-Metric / Claim | → | L5 (forum-side flag) | ✓ | Set on conflict with L1. |
| `SCHOOL_HAS_METRIC` | School → Metric | → | L1 | ✓ | |
| `SCHOOL_OFFERS_PROGRAM` | School → Program | → | L1 | ✓ | |
| `IN_CLUSTER` | Claim → Cluster | → | derived | ✓ (offline) | Set nightly by signed-graph community detection. |
| `EMITS_RESEARCH_NEED` | Conflict → ResearchNeed | → | derived | ✓ | |
| `PROVENANCE` | * → Dump | → | meta | ✓ | Every materialized node links back to its source `Dump`. |
| `HITL_TARGET` | HITLItem → any entity | → | meta | ✓ | The thing the reviewer is deciding about. |
| `CHUNK_OF` | Chunk → Page | → | L1 | ✓ V1 (crawler) | Chunk extracted from a Page; ordered by `chunk_index`. |
| `LINKS_TO` | Page → ExternalRef | → | L1 | ✓ V1 (crawler) | Outbound URL found on a crawled Page. |
| `MENTIONS` | Page / Chunk → School / Program / any | → | L1 | ✓ V1 (crawler) | Entity mention detected in crawled content (entity-tagging pass). |
| `CONSENSUS_FOR` | ForumConsensus → School | → | derived | ✓ V1 | Links a per-school aggregate metric to the School node. |
| `ANNOTATES` | SentimentAnnotation → Post / Comment | → | derived | ✓ V1 | Pass-4 sentiment verdict linked to its source document. |
| `ASKED_AT` | InterviewQuestion → School | → | L5-derived | ✓ V1 | Links a reported interview question to the school. 1,951 edges (83% of school-tagged questions). |
| `SAME_AS` | School → School / Institution → School | ↔ | meta | ✓ V1 | Entity dedup bridge. 274 edges (51 school dup groups + 48 institutions). |
| `OFFERED_BY` | Program → Institution | → | L1 | ✓ V1 | Residency program offered by an institution. 817 edges. |
| `IN_SPECIALTY` | Program → Specialty | → | L1 | ✓ V1 | Program belongs to a specialty (Perio, Endo, OMFS, …). 817 edges. |

Every edge above carries the property convention.

## SQLite side store schema (V1)

See `docs/05-features/01-slice-trust-tier-canonicalize/data.md` for the per-slice tables. Engine-wide:

- `l1_school`, `l1_school_year_metric`, `l1_program` (per slice).
- `dump`, `alias`, `hitl_queue`, `extraction_cache`, `audit_log` (per slice, engine-wide).
- `model_call_log` (engine-wide, V1.x): per-call vendor + model + latency + cost.
- `cluster_run` (engine-wide, V1): nightly signed-graph community detection run results.

### documents.sqlite (bundle sidecar, 1.79 GB)

Thread-complete raw store built by `cloud/build_documents_sqlite.py`. Ships in the V1-June12 bundle.

```sql
CREATE TABLE documents (
    doc_id      TEXT PRIMARY KEY,   -- graph node id (reddit_post:<id>, reddit_comment:<id>, sdn_post:…)
    doc_type    TEXT,               -- 'reddit_post' | 'reddit_comment' | 'sdn_post'
    source      TEXT,               -- subreddit name or 'sdn'
    parent_id   TEXT,               -- comment → parent post/comment
    thread_id   TEXT,               -- root post id for the thread
    author      TEXT,
    created_iso TEXT,               -- ISO-8601 UTC
    score       INTEGER,
    url         TEXT,
    title       TEXT,               -- root posts only
    text        TEXT                -- full body
);
CREATE INDEX … ON documents(thread_id), (parent_id), (doc_type);
```

Contents: 3,325,014 rows = 877,128 posts + 1,953,599 comments + 288,294 SDN posts + 6,993 SDN metadata.
Search: currently LIKE-scan only. FTS5 virtual table planned (GAP-061).

### SemanticIndex (persisted embedding shards, 1.27 GB)

18 fp32 shards from `cloud/embed_posts.py`. 877,188 BGE-small (384-dim) vectors — **posts only** (comments not embedded). Read by `src/retrieval/semantic_index.py` `SemanticIndex` (34 ms warm query, cosine top-k). Sidecar `post_text.db` (0.51 GB) stores the raw post text for quotable snippets. Comments excluded — see GAP-061.

## ID conventions (canonical)

| Type | Pattern | Example |
|---|---|---|
| School | `school:<slug>` | `school:nyu_dental` |
| Program | `program:<school_slug>:<specialty_slug>` | `program:nyu_dental:endodontics` |
| CycleYear | `cycle:<YYYY-YY>` | `cycle:2024-25` |
| Metric | `metric:<school_slug>:<cycle>:<name>` | `metric:nyu_dental:2024-25:tuition_resident` |
| User (Reddit) | `reddit:<sub>:<author>` | `reddit:DentalSchool:throwaway123` |
| User (SDN) | `sdn:<author>` | `sdn:doc_toothache` |
| Post (Reddit) | `reddit_post:<id>` | `reddit_post:hl06x` |
| Post (SDN) | `sdn_post:<thread_id>:<post_id>` | `sdn_post:1000053:13959604` |
| Comment (Reddit) | `reddit_comment:<id>` | `reddit_comment:c2m0mgt` |
| Thread | `thread:<source>:<id>` | `thread:sdn:1000053`, `thread:reddit:hl06x` |
| Topic | `topic:<slug>` | `topic:dat_prep` |
| Claim | `claim:<sha256_prefix>` | `claim:a1b2c3d4` |
| Cluster | `cluster:<topic_slug>:<run_id>` | `cluster:dat_prep:run_20260520` |
| Dump | `dump:<sha256_prefix>` | `dump:fe9d1234` |
| ResearchNeed | `rn:<sha256_prefix>` | `rn:5e6f7g8h` |
| HITLItem | `hitl:<uuid4>` | `hitl:0193...` |
| Alias | `alias:<sha256_prefix>` | `alias:abcdef12` |
| UnresolvedEntity | `unres:<sha256_prefix>` | `unres:99887766` |
| L2Document | `l2_doc:<sha256_prefix[16]>` | `l2_doc:e9f1c2a3b4d5e6f7` |
| Page (crawler) | `page:<domain>:<url_sha256[:12]>` | `page:adea.org:3f1a9c2b4e7d` |
| Chunk | `chunk:<page_id>:<index>` | `chunk:page:adea.org:3f1a9c2b4e7d:0` |
| ForumConsensus | `consensus:<school_id>:<predicate>` | `consensus:school:nyu_dental:gpa_aa` |
| SentimentAnnotation | `sentiment:<post_or_comment_id>` | `sentiment:reddit_post:hl06x` |
| Specialty | `specialty:<slug>` | `specialty:endodontics` |
| Institution | `institution:<slug>` | `institution:columbia_presbyterian` |

ID generators live in `src/shared/ids.py`. Tests assert (a) IDs are deterministic from inputs, (b) ID collisions across types are impossible by design.

## Sensitive data inventory

| Field | Sensitivity | Reason | V1 handling | V2 handling |
|---|---|---|---|---|
| Reddit / SDN `author` | Pseudonymous | Public forum handles | Stored as-is; namespaced | Anonymization or hashing TBD if V2 goes external |
| ADEA / CODA Excel content | Licensed | Vendor-licensed dataset | Local-only; not externally republished | License-compliance review before any external surfacing |
| API keys | Critical secret | Vendor credentials | `.env`, never committed; `.env.example` references only | Same; plus rotation policy |
| Audit log contents | Internal | May contain quoted forum text | Local SQLite; not exposed externally | TBD |
| HITL reviewer decisions | Internal | Domain-expert notes | Local; tied to reviewer identity | Reviewer-PII handling TBD |

No PII collected: applicants' real names, emails, etc. are not in the corpus. (Forum handles are pseudonymous.)

## V2 reserved slots (design hints)

- `Person` super-node owning multiple namespaced `User` aliases (for cross-source identity reconciliation when V2 wants it).
- `LicenseRecord` edge type from `Dump` to a license-management table.
- `Tenant` super-node for V2 multi-tenant data partitioning.
- `RetentionPolicy` per-Dump for V2 GDPR / DMCA / takedown handling.

These slots aren't created in V1 but the schema design accommodates them without migration breaking.

## Schema-evolution policy

- New node / edge **types** require HITL approval per A-017 (non-negotiable #21).
- New **properties** on existing types: append-only via a migration script; old data left as-is (null).
- **Renaming** properties: add new, dual-write during transition, drop old after one release cycle.
- **Removing** types: not allowed without ADR.
