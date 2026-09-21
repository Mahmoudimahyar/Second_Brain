# Observability

> V1 single-workstation; observability is heavy on local audit + LLM telemetry. V2 reopens for distributed tracing + multi-tenant dashboards.

## Three pillars (V1)

1. **Audit log** — append-only SQLite table; source of truth; every extraction / retrieval / HITL decision / ingestion event recorded.
2. **LLM telemetry** — Langfuse; per-call cost + latency + cache-hit + vendor breakdown.
3. **App logs** — structlog → JSON; replayable but not authoritative for state.

## Events

| Event | Source | Captured in | Fields |
|---|---|---|---|
| `dump_received` | ingestion | audit_log | `dump_id`, `source_tier`, `manifest`, `content_hashes`, `t_ingest_from` |
| `dump_state_transition` | ingestion lifecycle | audit_log | `dump_id`, `from`, `to`, `reason`, `ts` |
| `extraction_call` | gateway | audit_log + Langfuse | `thread_content_hash`, `prompt_id`, `prompt_version`, `schema_hash`, `vendor`, `model`, `model_version`, `cache_hit`, `cache_key`, `ttl_pinned`, `input_tokens`, `output_tokens`, `cached_input_tokens`, `cost_usd`, `latency_ms` |
| `er_decision` | entity resolver | audit_log | `mention`, `chosen_canonical_id`, `confidence`, `route` (`auto_accept`/`hitl`/`reject`) |
| `conflict_resolved` | conflict resolver | audit_log | `claim_id`, `resolution_path` (which of the 6 steps), `outcome`, `affected_edges` |
| `retrieval_call` | retrieval MCP | audit_log + Langfuse | `query_text`, `result_count`, `latency_ms`, `traversal_depth`, `time_range`, `as_of`, `source_tier_min` |
| `hitl_pulled` | HITL CLI | audit_log | `item_id`, `claimed_by`, `claimed_at` |
| `hitl_committed` | HITL CLI | audit_log | `item_id`, `decision`, `reviewer_notes_hash`, `committed_at`, `diff` |
| `hitl_escalated` | HITL CLI | audit_log | `item_id`, `escalation_reason` |
| `research_need_emitted` | conflict resolver | audit_log | `rn_id`, `topic`, `conflicting_claim_hash`, `suggested_sources` |
| `bitemporal_supersede` | graph writer | audit_log | `edge_id_old`, `edge_id_new`, `t_ingest_to_old`, `t_ingest_from_new` |
| `vendor_failover` | gateway | audit_log + Langfuse | `task_id`, `attempted_vendor`, `failure_code`, `fallback_vendor` |
| `error` (any `StructuredError` at boundary) | various | audit_log | `error_code`, `safe_message`, `context`, `retry_safe`, `cause_class` |

## Logs (app-level)

structlog → JSON renderer → stderr + file (`logs/engine.jsonl`, rotated daily).

Levels:
- `debug` — verbose inner-loop (development only; not in audit_log).
- `info` — significant events (mirror of audit_log events; redundant but useful for live monitoring).
- `warning` — vendor retries, threshold-borderline cases.
- `error` — structured errors raised at boundaries.
- `critical` — invariant violations (audit-log write failure, L1-immutability violation). Halts the process.

Every log line is JSON with `ts`, `level`, `module`, `event`, plus event-specific fields. Secrets are redacted via the structlog processor `src/observability/redact.py`.

## Metrics

Derived from `audit_log` + Langfuse (no separate Prometheus / StatsD in V1):

| Metric | Source | Aggregation | Use |
|---|---|---|---|
| Per-sweep total cost | audit_log `extraction_call.cost_usd` | sum | Cost regression test (NFR-2) |
| Per-sweep cache hit rate | audit_log `extraction_call.cache_hit` | mean | NFR-3 |
| Per-query p95 latency | audit_log `retrieval_call.latency_ms` | p95 | NFR-1 |
| HITL queue depth | live SQLite query | count | Reviewer pacing |
| HITL clear rate | audit_log `hitl_committed` events | count per day | Throughput |
| Vendor mix | audit_log `extraction_call.vendor` | count by vendor | Diversification check |
| Failover rate | audit_log `vendor_failover` | count | Vendor health |
| ER accept/HITL/reject rate | audit_log `er_decision.route` | distribution | Threshold tuning (SD-005) |
| Conflict-resolution-path distribution | audit_log `conflict_resolved.resolution_path` | distribution | A-011 health |

A `make dashboard` script (V1 implementation) renders these to a static HTML or markdown summary from `audit_log` + Langfuse.

## Alerts

V1: no automated paging. Manual periodic review by Mahyar.

Heuristics Mahyar checks weekly (or at every sweep completion):
- Total cost > $25 on V1 slice (or > $300 on full corpus) → investigate.
- Cache hit rate < 50% on warm sweep → cache key drift; investigate.
- Vendor failover events > 1% of calls → vendor health concern.
- ER `hitl` route > 20% of mentions → threshold too strict; ablate.
- HITL queue depth > 1000 → backlog; throttle ingestion until cleared.
- Conflict-resolution path skew (e.g., 90% landing in HITL) → resolver bug or trust-tier mis-config.

V2 reopens automated alerting.

## Audit trail (replay)

The system is designed so that:
- `audit_log` + raw `data/dumps/` payloads are sufficient to **rebuild the entire graph state** from scratch (modulo non-deterministic clustering ordering).
- `extraction_cache` is a derived performance artifact, not state; safe to drop and rebuild.
- The graph DB itself is a query-side cache of `audit_log` + dumps. Disaster recovery rebuilds it.

A `tools/replay_audit_log.py` (TBD at V1 implementation) walks `audit_log` chronologically and re-emits graph writes; idempotency checks ensure no drift between replay and original.

## Langfuse integration

- Self-hosted (Docker compose) or cloud (Mahyar's choice). Default: local for V1.
- Every `LLMClient.complete()` call writes a Langfuse trace with the same fields as the `audit_log` row.
- Langfuse dashboards: per-day cost + latency + cache-hit + vendor breakdown.
- Configured via `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_HOST` env vars.

## Trace fields per extraction call (mirrors system-overview.md §9)

```
{
  "thread_content_hash": "...",
  "prompt_template_id": "stage3_sentiment_v1",
  "prompt_version": 3,
  "schema_hash": "...",
  "vendor": "anthropic",
  "model": "claude-haiku-4-5",
  "model_version": "claude-haiku-4-5-20251001",
  "cache_hit": true,
  "cache_key": "sha256:...",
  "ttl_pinned": 3600,                    # lint-enforced; must be 3600
  "input_tokens": 1234,
  "output_tokens": 56,
  "cached_input_tokens": 1100,
  "cost_usd": 0.0007,
  "latency_ms": 412,
  "task_id": "stage3.sentiment",
  "fallback_attempted": false,
  "ts": "2026-05-20T12:34:56Z",
  "audit_id": "..."
}
```

## OpenTelemetry (deferred)

V1 does NOT use OTel — overkill on a single workstation. V2 (when distributed) reopens with OTel-instrumented gateway + retrieval MCP for cross-service trace propagation.

## Observability discipline (rules)

1. Every API call writes both an `audit_log` row and a Langfuse trace.
2. Every state-machine transition writes an `audit_log` row.
3. Every error at a boundary writes an `audit_log` row with `kind = "error"`.
4. Logs and audit-log must never contain secrets. Redaction processor enforced.
5. Log levels match severity exactly (no `debug` for production-significant events; no `error` for retryable conditions).

## V2 reopen plan

- Distributed tracing across ingestion / extraction / retrieval workers.
- Multi-tenant dashboards (per-tenant cost, per-tenant queue, per-tenant SLA).
- Pager integration (PagerDuty, Opsgenie, or equivalent).
- Audit log replicated externally for disaster recovery.
- Long-term metric storage (Prometheus / VictoriaMetrics).
