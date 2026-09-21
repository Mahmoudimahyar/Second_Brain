# ADR-010: Pipeline Orchestrator — Prefect 3

Status: **accepted** (R5 revision; supersedes the prior "pending — V1.x decision")
Date: 2026-05-20

## Context

R5: Mahyar confirmed updates are **daily**. Daily incremental re-ingest of Reddit / SDN dumps + periodic ADEA / CODA refreshes mean the engine needs real scheduling, retries, and observability — not ad-hoc CLI invocations.

The original ADR-010 left this pending; that was correct when the assumption was "one-off sweeps with maybe periodic refreshes." With daily updates, deferring the orchestrator decision creates technical debt (we'd hand-roll cron + retries + dashboards anyway).

R-009's tech-stack review listed three candidates: plain Python + asyncio, Prefect 3, Dagster.

## Decision

**Prefect 3** as the V1 orchestrator.

Why Prefect over the alternatives:

| Criterion | Prefect 3 | Plain Python | Dagster |
|---|---|---|---|
| Python-native | ✅ | ✅ | ✅ |
| Scheduler (daily, weekly, ad-hoc) | ✅ built-in `Deployment` schedules | ❌ rely on OS cron | ✅ via `Schedule` |
| Retry policy + backoff | ✅ per-task decorator | ❌ hand-roll | ✅ |
| Observability dashboards (local) | ✅ Prefect UI on `http://localhost:4200` | ❌ | ✅ |
| Task-graph DAG visualization | ✅ | ❌ | ✅ (asset graph) |
| Asset-oriented model (rebuild derived state) | partial via `Tasks` | ❌ | ✅ excellent |
| Footprint on workstation | low (single Python process + SQLite-backed state store) | trivial | medium (more components) |
| V2 cloud-deploy story | Prefect Cloud / self-hosted | rewrite | Dagster Cloud / OSS |
| Learning curve | low | trivial | medium-high |

**Decision rule**: V1 single-workstation + daily cadence + relatively-flat task graph favors Prefect. Dagster's asset-orientation would be nicer for the "graph = derived from audit log" mental model but the operational complexity isn't justified at V1 scale.

## Architecture impact

- A `flows/` directory under repo root (or `src/orchestration/flows/`) holds Prefect flow definitions.
- Per-pass flows:
  - `flows/pass1_structural.py` — daily structural-graph incremental.
  - `flows/pass2_labels.py` — runs after Pass 1; very fast.
  - `flows/pass3_clustering.py` — embeddings + clustering; weekly full rebuild + daily incremental.
  - `flows/pass4_llm.py` — daily incremental on filtered survivors.
  - `flows/pass5_indexing.py` — refresh retrieval indexes (HNSW, BM25, summaries).
- Each flow defines retries (e.g., 3× exponential backoff on vendor API failures), timeouts, and observability hooks (Langfuse + Prefect logs).
- A `flows/full_sweep.py` composes all 5 passes for one-shot full-corpus runs.
- A `flows/repo_graphrag_index.py` triggers `tools/graphrag/index.py --incremental` after every git commit (via the git-hook → Prefect deployment trigger).

Prefect state store: local SQLite (`.prefect/orion.db`). V2 considers Postgres for multi-host.

## Consequences

- One new dependency: `prefect>=3.x`. Approval-required per `dependency-rules.md` (it's an orchestration framework; counts as Tier 1).
- One additional process to run: `prefect server start` (local) or `prefect worker start`. Default: run the worker as a background process; UI is on demand.
- Existing CLI entrypoints (`python -m src.cli sweep ...`) still work — they invoke flows directly. The orchestrator wraps them with scheduling + observability.
- Cron-style scheduling is declarative: `Deployment.schedule = CronSchedule(cron="0 4 * * *")` for 4 AM daily.
- Failed runs are visible in Prefect UI; manual retry is one click.
- Retry budget per `plan.md` is encoded as Prefect task `retries=` + `retry_delay_seconds=` parameters.
- V2 considers: Prefect Cloud / self-hosted on cloud; or migration to Dagster if asset-orientation becomes valuable as data lineage grows.

## Alternatives considered

- **Plain Python + asyncio**: rejected once daily cadence locked. Without orchestration, we'd hand-roll cron-on-Windows (Task Scheduler), retry loops, dashboards. Time saved by Prefect > Prefect's overhead.
- **Dagster**: rejected for V1 due to operational complexity. The asset-oriented model is genuinely better for our graph-as-derived-state shape, but V1 doesn't need it yet. Revisit at V2.
- **Airflow**: rejected — heavyweight ops; multi-process default; overkill at our scale.
- **Apache Beam**: rejected — stream-processing model doesn't match our batch-incremental cadence.
- **Temporal**: rejected — heavy + workflow-orchestration-as-a-service vibe; V2 maybe.
- **GitHub Actions / repo CI as scheduler**: rejected — V1 is internal-only; no GitHub triggers.

## Implementation order

1. `pip install prefect` once V1 product code starts.
2. `prefect server start` runs the local UI on first use.
3. Each pass flow is a Python function decorated `@flow`; tasks `@task`.
4. Deployments via `prefect deployment build` for daily schedules.
5. Langfuse integration in `src/gateway/` writes regardless of orchestrator; Prefect just orchestrates.

## Related docs

- `docs/04-architecture/tech-stack.md` Orchestration section
- `docs/05-features/01-slice-trust-tier-canonicalize/plan.md` (5-pass implementation order; Prefect adoption in Phase 1 Phase-0 setup)
- `docs/00-bootstrap/assumptions.md` (R5 added the daily-update assumption that motivates this ADR)
- `docs/10-operations/deployment.md` (will get a Prefect-startup section at V1 implementation start)

## Related code

- `flows/` directory (V1 implementation deliverable)
- `prefect.yaml` (deployment config)
- `.prefect/` (Prefect state store; created at runtime, gitignored)
