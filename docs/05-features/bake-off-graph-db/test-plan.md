# Test Plan

## The five measurements

### M1 — Bulk-load time
**What:** wall-clock to insert the full 10K-node / 30K-edge sample with all properties (`source_tier`, `rank`, `references`, `qualifiers`, `t_valid_*`, `t_ingest_*`, `created_utc`) and build the HNSW vector index over 50K embedded chunks.
**How:** time the entire load script per candidate; warm cache OK.
**Pass/fail:** none alone; ranked relative.
**Direction:** lower = better.
**Recording format:** seconds + peak RSS + final disk MB.

### M2 — 3-hop traversal latency
**What:** median + p95 wall-clock per query over 100 runs (warm cache after 5 warm-ups).
**How:** each candidate runs the same logical query expressed in its native dialect. Single client, no concurrency.
**Pass/fail:** **p95 ≤ 250 ms** to be considered V1-viable; **p95 ≤ 50 ms** is excellent.

**The five queries (Q-A through Q-E):**

#### Q-A — Trust-tier-aware school lookup
"Given an L1 University by canonical name, return the top 10 L5 Posts that mention it, ranked by author credibility × HALO decay on `MENTIONS_UNIVERSITY.t_valid_from`, restricted to `source_tier ∈ {L1, L2, L5}` and `t_valid_*` overlapping 2024-2026."
Hops: University → Post → User credibility lookup (1 hop + 1 hop + property aggregation).

#### Q-B — Interview-question harvester
"For University X, return all `interview_question_reported` edges with `rank ∈ {preferred, normal}`, grouped by month of `t_valid_from`, with the originating Post and the author's credibility score."
Hops: University → Edge with property filter → Post → User.

#### Q-C — Conflict candidates
"Find all (Topic, Year) pairs where SUPPORTS edges and CONTRADICTS edges both exist within 6 months of each other, exclude any topic where an L1 anchor edge exists with conflicting `rank: preferred`."
Hops: Topic → SUPPORTS Posts × Topic → CONTRADICTS Posts × Topic → L1 anchor edges.

#### Q-D — User-trajectory cross-section
"For all Users who AUTHORED at least 10 Posts between 2019 and 2024, return their post-count per year and the set of Universities they referenced. Filter to credibility > 0.5."
Hops: User → AUTHORED Posts (year-binned) → MENTIONS_UNIVERSITY edges.

#### Q-E — Opinion-consensus snapshot
"For Topic Y as of 2024-09-01, return the largest signed-graph cluster of SUPPORTS edges and the largest cluster of CONTRADICTS edges (clusters precomputed and stored as `cluster_id` properties)."
Hops: Topic → SUPPORTS / CONTRADICTS edges with `t_valid_from ≤ 2024-09-01 ≤ t_valid_to` → cluster aggregation.

### M3 — HNSW recall@10
**What:** for 500 held-out queries, retrieve the top-10 nearest chunks via each candidate's HNSW; compute recall against the brute-force exact-cosine top-10.
**How:** identical 384-d BGE-small embeddings across all candidates; default HNSW parameters per engine (no tuning round 1).
**Pass/fail:** **recall@10 ≥ 0.85** to be considered V1-viable. Excellence threshold 0.95.
**Direction:** higher = better.

### M4 — Bitemporal-edge ergonomics
**What:** subjective 1-5 score on how natural bitemporal queries are.
**Rubric:**

| Score | Criterion |
|---:|---|
| 5 | Native first-class — query language has built-in temporal operators; bitemporal filtering is a 1-line predicate |
| 4 | Library-supported — Graphiti / similar wraps it cleanly, < 5 lines |
| 3 | Property-based but ergonomic — standard `WHERE t_valid_from <= $x AND ($x <= t_valid_to OR t_valid_to IS NULL)` works |
| 2 | Property-based and awkward — needs sub-queries or CTEs for common cases |
| 1 | Hostile — can't be expressed without procedural extensions |

Score each candidate. Take the average over Q-A, Q-C, and a "give me the graph as it was on 2023-05-01" reconstruction query.

### M5 — Ops complexity
**What:** subjective 1-5 score on running the engine.
**Rubric:**

| Score | Criterion |
|---:|---|
| 5 | Embedded — one Python `pip install`, no separate process |
| 4 | One process, no JVM, simple config (e.g., DuckDB-style) |
| 3 | Standalone server but lightweight (Postgres) — fits in existing infra |
| 2 | JVM-based server with non-trivial heap tuning |
| 1 | Multi-service, manual schema migration tooling, fragile install |

## Weighting

Per `README.md`:

| Metric | Weight |
|---|---:|
| M1 bulk-load | 0.20 |
| M2 3-hop latency | 0.25 |
| M3 HNSW recall@10 | 0.20 |
| M4 bitemporal ergonomics | 0.20 |
| M5 ops complexity | 0.15 |

## Scoring formula

For each candidate `c`:

```
normalize(M_k, c) = (M_k(best) - M_k(c)) / (M_k(best) - M_k(worst))   # lower-better metrics
              or = (M_k(c) - M_k(worst)) / (M_k(best) - M_k(worst))   # higher-better metrics
score(c) = Σ_k weight(k) * normalize(M_k, c)
```

Candidate with highest `score(c)` wins. If the gap between #1 and #2 is < 0.10, ops complexity (M5) is tiebreaker.

## Acceptance criteria for the bake-off itself

- [ ] All 5 metrics recorded for at least 2 of 3 candidates (1 DNF allowed).
- [ ] At least one candidate exceeds V1-viable thresholds (M2 p95 ≤ 250 ms AND M3 recall@10 ≥ 0.85).
- [ ] Winner has a justified margin (or M5 tiebreaker explicitly invoked).
- [ ] ADR-001 written + accepted.
- [ ] Real-data follow-up booked if the bake-off ran on synthetic.

## What we don't measure (and why)

- **Concurrent-write throughput** — V1 is single-writer; V2 concern.
- **Cross-region replication / HA** — V2 concern.
- **Index tuning ceiling** — round 1 defaults are sufficient to compare; tuning the winner is a follow-up task.
- **Subjective DX of the query language** beyond M4 — too noisy for a 1-2 day budget; revisit if winner has a sharp dev-experience cliff.
- **Cost** — all three are free OSS for our V1 use; rough hosting costs are folded into M5 ops-complexity.
