# Performance Budget

> V1 targets. Concrete. Measured in CI. Regressions fail the gate.

## Retrieval (NFR-1)

| Endpoint | p50 | p95 | p99 | Notes |
|---|---:|---:|---:|---|
| `query_graph` (V1 sample, traversal_depth=3) | ≤ 80 ms | ≤ **250 ms** | ≤ 500 ms | Hard CI gate at p95. |
| `get_canonical_entity` | ≤ 15 ms | ≤ **50 ms** | ≤ 100 ms | Hard CI gate at p95. |
| `search_by_topic` (V1.x) | ≤ 150 ms | ≤ 400 ms | ≤ 800 ms | Soft target. |
| `get_topic_consensus` (V1.x) | ≤ 200 ms | ≤ 600 ms | ≤ 1500 ms | Soft target; depends on cluster freshness. |

Measurement: `tests/perf/test_query_graph_p95.py` runs 100 representative queries warmed; reports percentiles to `tests/results/perf/`.

## Ingestion

| Operation | Throughput target | Notes |
|---|---|---|
| `register_dump` validation + raw-store | ≥ 100 manifests/min | Network-bound for content-hashing on large payloads; SSD-bound otherwise. |
| L1 Excel adapter | ≤ 30 sec / Excel file (typical ADEA Report size) | Single-threaded; openpyxl is the bottleneck. |
| L5 Reddit JSONL adapter | ≥ 5,000 records/sec on Mahyar's workstation | Streaming + orjson + Pydantic. |
| L5 SDN per-thread JSONL adapter | ≥ 1,000 threads/sec | Per-thread file open cost dominates. |
| Stage 1 (spaCy + GLiNER2 filter) | ≥ 200 docs/sec on GTX 1080 | GLiNER batch size 32 / 64. |
| Stage 2 (BGE-small + DITTO ER) | ≥ 100 mentions/sec | BGE batch + DITTO batch. |
| Stage 3 API (Haiku 4.5 batch + cache warm) | ≥ 50 reqs/min effective (batch + cache hit absorbed) | Cold sweeps slower; warm reruns ≥ 500/min. |

## Cost (NFR-2)

| Workload | Target | Hard cap |
|---|---:|---:|
| V1 slice full sweep (r/DentalSchool + 5 ADEA files) | < $20 | $25 |
| V1 slice warm rerun (with cache) | < $3 | $5 |
| V1 full corpus sweep (all forum + all L1) | $80-$300 | $400 (re-evaluate at $300) |
| Per Stage-3 thread cost (median) | < $0.0001 | $0.001 |
| Per LLM-as-judge call (3-vendor, when used) | < $0.005 | $0.01 |

Cost regression test in `tests/cost/test_v1_slice_sweep.py` runs a recorded fixture + asserts under hard cap.

## Cache hit rate (NFR-3)

| Sweep | Target |
|---|---:|
| Cold sweep | ≥ 0 (no prior cache; baseline) |
| Warm sweep with identical inputs | ≥ **80%** |
| Warm sweep with new prompt version | 0 by design — invalidates cache by key |

## Graph DB

| Operation | Target | Notes |
|---|---|---|
| Bulk-load V1 sample (~10K nodes / 30K edges) | ≤ 60 sec | Bake-off metric M1. |
| 1-hop traversal | ≤ 5 ms p95 | Hot cache. |
| 3-hop traversal (representative) | ≤ 250 ms p95 | Bake-off metric M2 — also the `query_graph` p95 target. |
| HNSW recall@10 | ≥ **0.85** | Bake-off metric M3. Hard CI gate. |
| Nightly cluster rebuild (signed-graph community detection) | ≤ 10 min on V1 corpus | Offline job; not user-facing. |

## Memory

| Component | Target | Hard cap |
|---|---:|---:|
| Total Python process RSS during sweep | < 16 GB | 32 GB |
| GPU VRAM usage (spaCy + GLiNER2 + BGE + DITTO) | < 6 GB | 8 GB |
| SQLite side store on disk after V1 slice | < 1 GB | 5 GB |
| Graph DB on disk after V1 slice | < 5 GB | 20 GB |

GPU VRAM is the binding constraint (Pascal 8 GB total). If models OOM, swap to CPU for the leakiest one (BGE-small can run CPU at ~200 chunks/sec).

## Audit log

| Operation | Target |
|---|---|
| `audit_log` write latency | ≤ 1 ms p95 (SQLite-WAL) |
| `audit_log` query for last-24h sweep summary | ≤ 500 ms |
| `audit_log` size after V1 slice | ≤ 500 MB |

## HITL

| Operation | Target |
|---|---|
| `hitl pull` (writes YAML) | ≤ 200 ms p95 |
| `hitl commit` (writes to graph + audit) | ≤ 500 ms p95 |
| Per-item reviewer wall-clock (synthetic) | ≤ 1 min median (synthetic); ≤ 2 min median (real, with thread-context read) |

## Lint / test / CI

| Operation | Target | Hard cap |
|---|---:|---:|
| Full pytest (V1 slice) | ≤ 5 min | 10 min |
| `ruff check` | ≤ 5 sec | 15 sec |
| `mypy --strict src/` | ≤ 30 sec | 60 sec |
| `lint_ttl_pinning.py` | ≤ 5 sec | 15 sec |

## Regression gates

Any PR that worsens a hard-cap metric by > 10% fails the gate. Soft-target regressions trigger a warning + a comment from the bot (when CI exists).

## Where budgets live (single sources of truth)

- This file = repo-wide budget.
- Slice-local refinements (e.g., V1-slice cost cap of $25) = `docs/05-features/01-slice-trust-tier-canonicalize/requirements.md` NFR section + `test-plan.md`.
- Real measured values = `tests/results/perf/`, `tests/results/cost/`, `evals/results/`.

## V2 budget changes (preview)

V2 may relax some V1 budgets (e.g., total memory) and tighten others (e.g., per-tenant cost cap). V2 reopens this document.
