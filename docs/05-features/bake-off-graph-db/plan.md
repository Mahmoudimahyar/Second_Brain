# Plan

Sequential phases. Total wall-clock target: **1-2 days**. Each phase has a hard go/no-go gate.

## Phase 0 — Prep (~3 hours, one-time)

### 0.1 Asset access — RESOLVED (R3)
Data lives at `<repo>\External Data\`. See `docs/00-bootstrap/source-documents.md` for the full inventory:
- L5 forum: SDN (173K threads + per-thread JSONL files) + Reddit (3 subreddits, ~2.34M posts+comments).
- L1 official: ADEA Survey of Dental Education (10 years) + CODA Survey of Advanced Dental Education (10 years), all as `.xlsx`.

### 0.2 Bake-off sample — concrete pick
**Proposed (pending Q-023):**
- **L5 source**: **r/DentalSchool** — smallest subreddit at 274K records (34K posts + 239K comments), most on-topic for dental-school applicants. Alternative: r/predental (434K records) if Mahyar prefers more applicant focus.
- **L1 source**: 5 most-recent ADEA Report 2 files (Tuition / Admission / Attrition 2020-21 → 2024-25). Loaded into SQLite as `l1_school_year_metrics` table.
- **Subgraph target**: ~10K nodes, ~30K edges after first-pass extraction. If r/DentalSchool yields too many or too few after Stage-1 filter, subsample by `created_utc` quartile to hit ~10K.

### 0.3 Sample-prep script (write before bake-off)
- `scripts/bake_off/load_l1.py` — read 5 ADEA Excel files via openpyxl/pandas; normalize school names against an inline canonical list (we'll bootstrap one from the ADEA "School" column unique values); write to `data/bake_off/l1.sqlite` with tables `school`, `school_year_metric`, `program`.
- `scripts/bake_off/extract_l5_sample.py` — read `r_DentalSchool_posts.jsonl` + `r_DentalSchool_comments.jsonl`; reconstruct threads via `link_id`; first-pass Stage-1 filter (GLiNER2 "does this mention a dental school?"); sample to ~5K posts + ~3.5K users + ~1K topics; write to `data/bake_off/l5_sample.jsonl`.
- `scripts/bake_off/build_subgraph.py` — combine L1 + L5 into a unified node+edge dataset with **all the V1 properties on every edge**: `source_tier` (L1/L5), `rank` (preferred/normal/deprecated), `references` (source-ID list), `qualifiers` (dict), `t_valid_from`, `t_valid_to`, `t_ingest_from`, `t_ingest_to`, `created_utc`. Write as Parquet or JSONL (whichever is easier per-engine to bulk-load).

### 0.4 Embedding store
- BGE-small (`sentence-transformers/all-MiniLM-L6-v2` or `BAAI/bge-small-en-v1.5`) over ~50K text chunks (Post bodies, Comment bodies, Topic descriptors).
- Pre-compute brute-force exact nearest-10 for a 500-query held-out set.

### 0.5 Test harness scaffolding
- One entrypoint per candidate (`run_ladybug.py`, `run_graphiti_neo4j.py`, `run_postgres_age.py`).
- Shared YAML config of queries.
- Shared CSV writer (`results/<candidate>.csv`).

**Phase 0 exit gate:** sample data + embeddings + harness ready; sanity-checked on one candidate.

---

## Phase 1 — Install + load (~4 hours, can run candidates in parallel)

For each candidate:

1. Install engine on Mahyar's workstation (record install minutes).
2. Define schema (node labels, edge types, HNSW vector index, property indexes for `source_tier` + `t_valid_*`).
3. Bulk-load the sample. Record: **bulk-load wall-clock**, **steady-state RAM**, **disk footprint**, **any failures**.
4. Sanity query: `MATCH (u:University {canonical_name: 'UCSF Dental'}) RETURN u` returns < 100 ms.

### Candidate-specific notes

**LadybugDB:**
- Install: `pip install ladybugdb` (verify naming via live search if it fails).
- Schema: COPY FROM CSV/Parquet bulk-load; HNSW via `CALL CREATE_HNSW_INDEX(...)`.
- Bitemporal: edge property add (no native support).

**Graphiti + Neo4j Community:**
- Install: Docker Compose for Neo4j 5.x + `pip install graphiti-core`.
- Schema: Graphiti's `Episode` / `Entity` / `Edge` model — bitemporal native.
- Bulk-load via `add_episode_bulk(...)`. Fall back to direct Neo4j `LOAD CSV` if too slow.
- HNSW: Neo4j 5 `db.index.vector.createNodeIndex`.

**Postgres + Apache AGE + pgvector:**
- Install: Postgres 16 + `CREATE EXTENSION age` + `CREATE EXTENSION vector`.
- Schema: AGE labels + pgvector column; HNSW `USING hnsw (embedding vector_cosine_ops)`.
- Bulk-load via `COPY`.
- Bitemporal: SQL columns + view helpers.

**Phase 1 exit gate:** all three loaded + sanity-querying. ~1 hour debug ceiling per candidate before DNF.

---

## Phase 2 — Run the measurement suite (~3-4 hours)

Run the shared YAML query suite against each candidate. See `test-plan.md` for query bodies. Capture M1-M5.

**Phase 2 exit gate:** all 5 metrics recorded for surviving candidates in `results/<candidate>.csv`.

---

## Phase 3 — Score + decide (~1-2 hours)

1. Normalize each metric to 0-1.
2. Apply weights (bulk-load 0.20, 3-hop 0.25, recall@10 0.20, bitemporal 0.20, ops 0.15).
3. Produce weighted totals.
4. Fill `decisions.md`.
5. Write `docs/11-decisions/ADR-001-graph-db.md` (`Accepted`).

**Phase 3 exit gate:** ADR-001 in repo; GAP-027 closed; bootstrap-status `Tech stack — picks landed` checked.

---

## Risk register (updated R3)

| Risk | Mitigation |
|---|---|
| LadybugDB install / packaging issues | Time-box 1 hour → DNF if no progress |
| Graphiti + Neo4j memory pressure on workstation | Limit Neo4j heap to 8 GB; LLM offline during bake-off |
| Postgres AGE Cypher coverage gap on a key query | Score `DNF` on the affected query + weight ops penalty |
| Real r/DentalSchool data too sparse / too dense | Adjust subsampling rule by `created_utc` quartile to hit ~10K |
| Sample doesn't exercise SDN flavor (no upvote signal) | V1 *slice* uses Reddit; for bake-off, fold in 1K SDN posts from `sdn_thread_metadata.jsonl` `category = "Pre-Dental"` to verify schema handles both metadata shapes |
| All three roughly equivalent | M5 ops complexity tiebreaker |

---

## Estimated time

| Phase | Hours |
|---:|---|
| 0 — Prep | 3 |
| 1 — Install + load | 4 |
| 2 — Measure | 3-4 |
| 3 — Decide + ADR | 1-2 |
| **Total** | **11-13 hours** spread over 1-2 calendar days |

## Owner sequence

1. **Mahyar**: confirm bake-off sample pick (Q-023: r/DentalSchool default, or pick alternative). Confirm bake-off plan as-is.
2. **Claude**: write scripts + harness, run Phase 0-2.
3. **Mahyar**: review Phase 2 numbers, ratify ADR-001.
4. **Claude**: write ADR-001, close GAP-027, unblock downstream ADRs.
