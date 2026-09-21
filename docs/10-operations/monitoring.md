# Monitoring

> V1 single-workstation, no production-grade SLOs. Monitoring is Mahyar's periodic review + a `make dashboard` summary. V2 reopens with real SLOs + paging.

## What gets monitored (V1)

| Signal | Source | Cadence | Owner |
|---|---|---|---|
| Cost per sweep | `audit_log` `extraction_call.cost_usd` aggregated | Per-sweep + weekly | Mahyar |
| Cache hit rate | `audit_log` `extraction_call.cache_hit` | Per-sweep | Mahyar |
| Vendor mix + failover events | `audit_log` `extraction_call.vendor` + `vendor_failover` | Weekly | Mahyar |
| Retrieval p95 latency | `audit_log` `retrieval_call.latency_ms` | Per-sweep | CI test |
| HITL queue depth | live SQLite query | Per-session | Mahyar |
| HITL clear rate | `audit_log` `hitl_committed` events | Daily-during-sessions | Mahyar |
| ER accept/HITL/reject distribution | `audit_log` `er_decision.route` | Per-sweep | Mahyar |
| Conflict-resolution path skew | `audit_log` `conflict_resolved.resolution_path` | Per-sweep | Mahyar |
| Error rate | `audit_log` `kind="error"` count | Per-sweep | Mahyar |
| L1 immutability violations | `audit_log` `kind="critical"` + `L1_IMMUTABLE_REJECT` | continuous (should be 0) | Mahyar + CI |
| Audit-log write failures | `audit_log` (sentinel row) or stderr | continuous (should be 0) | Mahyar |

## `make dashboard` (V1 implementation deliverable)

A script that aggregates the signals above into a single-page summary:
- Markdown or static HTML, written to `dashboards/<timestamp>.md`.
- Run after every sweep + on demand.
- Contents (one section per signal):
  - Current value.
  - Trend vs last 7 sweeps.
  - Threshold violations (if any).
- Linked from `/.agent/reports/` for slice-completion reports.

## Heuristic thresholds (V1)

These are not formal SLOs — they're "Mahyar should investigate if exceeded":

| Signal | Threshold | If exceeded |
|---|---|---|
| V1 slice sweep cost | > $25 | Investigate cache-hit failure or vendor-pricing drift. |
| V1 full corpus sweep cost | > $300 | Re-eval per-task matrix; consider Gemini 2.5 Flash-Lite switch. |
| Cache hit (warm sweep) | < 50% | Cache key drift — investigate prompt-version churn. |
| Vendor failover | > 1% of calls | Vendor health concern; consider re-ordering fallback chain. |
| ER `hitl` route | > 20% of mentions | Threshold too strict; ablate auto-accept / reject bands. |
| HITL queue depth | > 1000 | Backlog; throttle ingestion. |
| Retrieval p95 latency | > 250 ms (regression > 10%) | Query optimization; HNSW tuning; graph schema review. |
| Error rate | > 1% of calls | Inspect `error_code` distribution; fix root cause. |
| L1 immutability violation | any | **Critical** — halt + investigate + add regression test. |
| Audit-log write failure | any | **Critical** — halt; integrity issue. |

## Logs storage

| Source | Where | Retention | Rotation |
|---|---|---|---|
| structlog `info+` | `logs/engine.jsonl` | Indefinite (V1 single-user; small enough) | Daily rotation; gzip after 7 days |
| structlog `debug` | stderr only; not persisted | n/a | n/a |
| `audit_log` (SQLite) | `data/sqlite/engine.db` | Indefinite | n/a (relational) |
| Langfuse traces | Langfuse host (local or cloud) | Per Langfuse retention config | per Langfuse |
| MCP tool calls (`tools/graphrag/`) | `tools/graphrag/logs/mcp.jsonl` | Indefinite (small) | Daily rotation |

V2 considers external log shipping (Loki, Datadog, etc.) for multi-machine deployments.

## Alerts (V1)

None automated. Mahyar reviews `make dashboard` output post-sweep. The heuristic thresholds above tell him where to look first.

V2 introduces automated alerts via PagerDuty / Opsgenie / equivalent. V2 must address:
- Multi-tenant alert routing.
- Per-tenant SLO definitions.
- Escalation policies.
- On-call rotations.

## Dashboards

V1 dashboard (per `make dashboard`):
- Single Markdown / HTML page per sweep.
- Sections: Cost / Cache / Latency / HITL / ER / Conflicts / Errors / Vendor mix.
- Lives in `dashboards/`.

V2 additions:
- Per-tenant dashboard.
- Time-series graphs (Grafana on Prometheus / VictoriaMetrics).
- Public status page (optional).

## Incident playbook (V1, informal)

When a heuristic threshold is exceeded:
1. **Capture state**: snapshot `data/sqlite/engine.db` + `audit_log` window of interest.
2. **Read audit log** for the time window.
3. **Identify root cause** (vendor failure, prompt drift, schema drift, code bug).
4. **Halt incoming ingestion** if the issue could propagate (e.g., L1 violation, cache poisoning).
5. **Fix root cause** in code + tests.
6. **Add regression test** that would have caught it.
7. **Document** in `docs/05-features/<slice>/known-issues.md` + (if architectural) update relevant ADR.
8. **Resume ingestion** + monitor for recurrence.

V2 reopens this as a formal incident-response process.

## What V1 does NOT monitor (deferred)

- Multi-host health (single workstation).
- Cross-tenant noisy-neighbor.
- DDoS / abuse detection (V1 internal).
- SLO compliance (V1 doesn't publish SLOs).
- Compliance / regulatory reporting.
