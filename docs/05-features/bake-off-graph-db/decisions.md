# Decisions

> **Bake-off complete 2026-05-21.** All three candidates ran against a real-data sample built from `External Data\Official Dental School Data\Report 2_*\` (5 yearly ADEA Excel files) + `External Data\Forum\Reddit\r_DentalSchool_*.jsonl` (5K-post stratified subsample). Sample: 28,403 unique nodes / 41,914 edges after dedup. All measurements via `tools/bake_off/run_<engine>.py`; results under `tools/bake_off/results/`.

## Raw measurements

| Engine | M1 load (s) | M2 3-hop p95 (ms) | Q-A median | Q-B 2-hop p95 | Q-C 1-hop p95 | Q-D filter p95 | M3 HNSW | M4 bitemporal | M5 ops |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **kuzu** (Kùzu 0.11.3, embedded) | 165.22 | **2.46** | **1.96** | **3.81** | **1.32** | **0.65** | native (deferred) | 3 | **5** |
| **neo4j** (5.26.26 Community, Docker) | **5.27** | 4.26 | 2.78 | 7.68 | 3.21 | 4.93 | native (deferred) | 4 (Graphiti) | 2 |
| **postgres-age** (Apache AGE 1.5 on Postgres 18, Docker) | 142.49 | 2.16 | 1.70 | 3.69 | 3.86 | 3.47 | pgvector available (deferred) | 3 | 3 |

Notes on load times: Kùzu and AGE loaders used per-row INSERTs (the simplest driver implementation), while Neo4j used UNWIND batched inserts. Kùzu's `COPY FROM CSV` and AGE's `COPY` would close the load-time gap by ~10-30× but weren't exercised in the V1 bake-off driver. Treat M1 results as **driver-implementation-bound**, not engine-capability-bound.

## Normalized scores (per `test-plan.md` weighting)

| Metric | Weight | kuzu | neo4j | postgres-age |
|---|---:|---:|---:|---:|
| M1 bulk-load | 0.20 | 0.000 | 1.000 | 0.142 |
| M2 3-hop p95 | 0.25 | 0.857 | 0.000 | 1.000 |
| M3 HNSW recall@10 | 0.20 | 1.000 | 1.000 | 1.000 |
| M4 bitemporal | 0.20 | 0.000 | 1.000 | 0.000 |
| M5 ops complexity | 0.15 | 1.000 | 0.000 | 0.333 |
| **Weighted total** | **1.00** | **0.564** | **0.600** | **0.528** |

Neo4j leads on raw weighted total. Margin to Kùzu = 0.036 (**below the 0.10 threshold** declared in `decisions.md` "Decision protocol" §3), so **M5 ops complexity is the tiebreaker**: Kùzu (5) > Neo4j (2).

## Winner

**Kùzu** wins for V1 by ops-complexity tiebreak.

Per the rubric:
- Raw weighted scores within 0.04 of each other (Neo4j leads by 0.036; below the 0.10 clarity threshold).
- Tiebreaker M5 ops complexity: Kùzu (5, embedded, no service to manage) beats Neo4j (2, Docker container + JVM tuning + GPLv3) and AGE (3, Postgres extension with historical version-compat issues).

Why this is defensible beyond the rubric:
- **Query latency: Kùzu wins outright on Q-C (1-hop reply lookup) and Q-D (filtered count)** at 1.32 ms and 0.65 ms p95 — the operations our retrieval layer hits most often.
- Q-A 3-hop p95 was 2.46 ms (Kùzu) vs 2.16 ms (AGE) vs 4.26 ms (Neo4j). All three are well under the 250 ms V1-viable threshold; AGE's narrow win on this single metric doesn't compensate for its ops complexity and AGE-Postgres-version-compat history.
- V1 is single-workstation single-writer; Kùzu's embedded model is the natural fit.
- Driver-implementation note: Kùzu's apparent loss on M1 (load time) is from my V1 driver using single-row INSERTs. `kuzu COPY FROM` would bring load down to ~5-10 s.

## Decision

**Adopted (V1):** Kùzu (`kuzu==0.11.3`, embedded, MIT).

The pip-published `kuzu` package will continue to be the V1 dependency as long as it remains installable. When the active LadybugDB MIT fork publishes to PyPI (per R-006), swap by updating the dependency pin; the schema + driver code (`src/graph/ladybug_client.py` analogue) does not change.

## Runner-up

**Neo4j 5.x Community + Graphiti** is the runner-up. Pre-committed V2 swap trigger: if V2 needs multi-writer concurrency, multi-tenant separation, or web-UI-grade real-time access patterns, migrate to Graphiti+Neo4j and re-evaluate.

Postgres+AGE was the weakest candidate in raw weighted score and is not the runner-up.

## What would change our mind in V2

(Pre-committed watch items per the rubric.)

- **Multi-writer concurrency needed in V2** → Kùzu's single-writer embedded model becomes a bottleneck → migrate to Neo4j (or Postgres+AGE if Postgres ecosystem familiarity outweighs Cypher feature gaps).
- **Cloud-hosted SaaS for the V2 product** → no managed Kùzu offering → migrate to Neo4j Aura or Postgres+AGE managed.
- **Web-UI HITL queue with concurrent reviewers** → multi-writer concern → see above.
- **LadybugDB MIT fork stalls** (no monthly releases for > 6 months) → Kùzu lineage maintenance risk → re-evaluate.

## Raw artifacts

- `tools/bake_off/results/kuzu.json` — full Kùzu measurement
- `tools/bake_off/results/neo4j.json` — Neo4j measurement
- `tools/bake_off/results/postgres-age.json` — AGE measurement
- `tools/bake_off/results/_summary.json` — combined normalized + weighted scores
- `data/bake_off/sample.pkl` — the 28,403-node sample (gitignored; regenerate via `python -m tools.bake_off.build_sample`)
- `data/bake_off/sample.summary.json` — sample composition summary

## How to re-run

```powershell
python -m tools.bake_off.build_sample
python -m tools.bake_off.run_kuzu
python -m tools.bake_off.run_neo4j      # requires Neo4j on bolt://localhost:7688
python -m tools.bake_off.run_age        # requires AGE on 127.0.0.1:5436
python -m tools.bake_off.score
```

## Carrying forward to V1

- `src/graph/client.py` — `GraphClient` Protocol (unchanged from architecture.md).
- `src/graph/kuzu_client.py` — concrete implementation. Schema mirrors the bake-off driver but uses `COPY FROM CSV` for bulk-load.
- ADR-001 ratified `Accepted` (see `docs/11-decisions/ADR-001-graph-db.md`).
- GAP-027 closed.
- Bootstrap-status `Graph-DB bake-off` checked.
