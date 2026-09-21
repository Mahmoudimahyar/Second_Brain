# Success Metrics

> Three levels: **Product** (does it deliver what users need?), **Engineering** (is it well-built?), **Quality** (is the data trustworthy?). V1 targets are concrete; V2 ranges left open.
>
> ⚠️ **Metric meaningfulness (added 2026-05-29).** A target is only meaningful if its measurement can actually fail. Two caveats: (1) **Alias-resolution F1 currently reads 1.000 on a *verbatim-substring* gold set** (GAP-044) — it cannot fail on that distribution, so the ≥0.92 gate is **not yet meaningful**; V1.7 rebuilds the gold set with adversarial/fuzzy/abbreviation/misspelling cases before this metric counts. (2) Several gates (citation-traceability ≥99%, retrieval p95, conflict-surfacing) depend on capabilities that are **decided but not yet wired** (see `implementation-status.md`) — they become live gates only once those are `Wired`. (3) The "< $25 / sweep" cost figure is a **tripwire, not a hard cap** (see non-negotiables #23).

## Product metrics

| Metric | V1 target | Measurement | Owner |
|---|---|---|---|
| Time-to-first-graph (new domain → queryable graph) | ≤ 2 weeks (post Phase 0 gates) for a new subreddit + L1 source pair | Calendar days from `register_dump` first call to `query_graph` returning ≥ 100 cited results | Ingestion operator |
| End-to-end V1 slice sweep cost | < **$25** | Sum of `cost_usd` in `audit_log` for one r/DentalSchool sweep | Audit log + Langfuse |
| Source-tier mix at retrieval | Every `query_graph` result shows `source_tier` (L1 distinct from L5); a PM can tell official vs community at a glance | Manual UX check + automated test on result shape | PM journey |
| Citation traceability | ≥ **99%** of retrieval results have non-empty `references` | `tests/test_retrieval_citations.py` | CI gate |
| Conflict surfacing | 100% of L1 ↔ L5 contradictions produce `Status: Invalidated_by_Official_Data` markers (no silent L1 overwrites) | Integration test + audit-log sample | CI gate |

## Engineering metrics

| Metric | V1 target | Measurement | Owner |
|---|---|---|---|
| Test pass rate (CI) | 100% on `main` | `pytest` exit code | CI |
| Test coverage | ≥ **80%** line coverage on `src/` | `pytest --cov` | CI gate |
| Typecheck pass | clean | `mypy src/` | CI gate |
| Lint pass | clean | `ruff check .` + `lint_ttl_pinning.py` | CI gate |
| Retrieval p95 latency | `query_graph` < **250 ms**, `get_canonical_entity` < **50 ms** | `tests/perf/` | CI gate |
| Repair budget compliance | ≤ 5 cycles unit/integration, ≤ 3 cycles E2E, ≤ 2 cycles full-suite per AGENTS.md | Manual track in `/.agent/reports/` | Implementer |
| Token usage per task | Tracked per task in `audit_log` via Langfuse | Continuous | Observability |
| Cache hit rate (warm sweep) | ≥ **80%** | `audit_log` over a warm sweep | Cost regression test |

## Quality metrics

| Metric | V1 target | Measurement | Owner |
|---|---|---|---|
| Alias-resolution F1 | ≥ **0.92** on 200-mention labeled gold set | `evals/alias_resolution.py` | Eval CI gate |
| Sentiment classification F1 | ≥ **0.85** on 100-example labeled gold set | `evals/sentiment.py` | Eval CI gate |
| Interview-question extraction precision | ≥ **0.90** on 50-example labeled gold set | `evals/interview_q.py` | Eval CI gate |
| L1 immutability | **100%** — zero L1 nodes mutated post-ingest | Audit-log invariant test | CI gate |
| Bitemporal correctness | **100%** of supersede operations set `t_ingest_to` + `t_ingest_from` atomically | `tests/test_bitemporal_props.py` (hypothesis) | CI gate |
| Outlier preservation | **0** outlier claims deleted; all flagged `Status: Anomaly` and queryable via `include_anomalies` | Integration test | CI gate |
| HITL throughput | ≥ **50 items/hour** synthetic / **20-30 items/hour** real (V1 reviewer overhead) | Time-and-motion measurement during gold-set labeling | Reviewer journey |

## Audit / safety metrics

| Metric | V1 target | Measurement |
|---|---|---|
| % LLM calls with `ttl: 3600` pinned | **100%** | `lint_ttl_pinning.py` + audit-log filter |
| % vendor-locked imports in product code | **0** | `ruff` rule |
| % HITL decisions audit-logged | **100%** | `audit_log` row count == `hitl commit` count |
| % retrieval calls audit-logged | **100%** | same |

## Out of scope this slice (deferred to V1.x / V2)

- A/B comparison of Gemini 2.5 Flash-Lite vs Haiku 4.5 on a held-out eval set (V1.x).
- Cross-vendor LLM-as-judge calibration set (V2).
- Logistic-regression user-credibility upgrade (V1.1).
- Distillation pipeline (V2).
- Public-facing SLA / uptime / availability metrics (V2).

## How metrics roll up

- **Per-sweep dashboard**: Langfuse + a `make dashboard` script that aggregates `audit_log` + Langfuse data into a 1-page summary (cost, latency, cache-hit, F1 on gold sets, HITL queue depth).
- **Per-CI run**: GitHub Actions (or local equivalent) reports pass/fail for each gate metric above.
- **Per-release**: a `RELEASE.md` summary that lists all metric values at the time of cut.

## Where metric values live

- Test-time + CI: stored in `tests/results/` (gitignored) and printed in CI summary.
- Production: SQLite `audit_log` + Langfuse hosted dashboard.
- Eval: `evals/results/<date>/<eval_name>.json`.

## When to revise targets

- After **the first full V1 slice run** (post Phase 10 of `plan.md`): replace placeholder targets above with empirically-grounded ones.
- After **gold-set labeling**: F1 targets may shift if the gold set reveals systematic issues (e.g., DITTO struggles on specific alias families).
- After **the first HITL session**: throughput target updates based on real reviewer pace.
