# Error Codes

> Source of truth for `ErrorCode` enum (`src/shared/errors.py`). Codes are part of the API contract; renaming or removing requires a deprecation cycle. New codes added with PR + this table updated in the same diff.

## Code format

`<CATEGORY>_<SPECIFIC>` (UPPER_SNAKE_CASE). Examples: `VALIDATION_FAILED`, `L1_IMMUTABLE_REJECT`, `GATEWAY_ALL_VENDORS_FAILED`.

## Catalog (V1)

| Code | Category | Caller-safe message | Thrown by | Tested by | Retry-safe? |
|---|---|---|---|---|---|
| `VALIDATION_FAILED` | Validation | "Input failed validation." | MCP boundary, ingestion, HITL | `tests/test_validation.py` | yes |
| `MANIFEST_INVALID` | Ingestion | "Dump manifest missing required fields or malformed." | `src/ingestion/api.py` | `test_ingestion.py::test_manifest_invalid` | yes |
| `HITL_DECISION_SCHEMA_INVALID` | HITL | "HITL decision YAML doesn't match the expected schema." | `src/hitl/cli.py` | `test_hitl_cli.py::test_decision_schema_invalid` | yes |
| `DUMP_DUPLICATE` | Ingestion | "Dump with identical content already ingested; returning prior receipt." | `src/ingestion/api.py` | `test_ingestion.py::test_dump_idempotent` | yes (it's a no-op) |
| `DUMP_ROLLBACK` | Ingestion | "Dump ingestion failed mid-pipeline; partial state rolled back." | `src/ingestion/api.py` | `test_ingestion_rollback.py` | no (state-dependent) |
| `ADAPTER_NOT_FOUND` | Ingestion | "No source adapter registered for this source_tier + schema_hint." | `src/ingestion/adapters/base.py` | `test_ingestion.py::test_no_adapter` | no |
| `ADAPTER_FAILED` | Ingestion | "Source adapter failed during normalization." | per-adapter | per-adapter test | no |
| `STAGE3_VENDOR_FAILURE` | Extraction | "Stage-3 API call failed after fallback chain exhausted." | `src/extraction/stage3_api.py` | `test_stage3_extraction.py` | yes |
| `STAGE3_SCHEMA_INVALID` | Extraction | "Stage-3 output failed Pydantic schema validation." | `src/extraction/stage3_api.py` | `test_stage3_extraction.py::test_schema_invalid` | yes (likely caller can retry with same input) |
| `EXTRACTION_TIMEOUT` | Extraction | "Stage-3 API call timed out." | gateway | `test_gateway.py::test_timeout` | yes |
| `GATEWAY_ALL_VENDORS_FAILED` | Gateway | "All configured vendors failed for this task." | `src/gateway/api.py` | `test_gateway.py::test_all_vendors_fail` | yes |
| `GATEWAY_TTL_NOT_PINNED` | Gateway | "Internal error: prompt-cache TTL not pinned (lint should have caught this)." | `src/gateway/api.py` | `test_gateway.py::test_ttl_pinning_runtime` | no (developer bug) |
| `GATEWAY_RATE_LIMITED` | Gateway | "Vendor rate limit; retry after backoff." | `src/gateway/api.py` | `test_gateway.py::test_rate_limit_retry` | yes |
| `GATEWAY_BUDGET_EXCEEDED` | Gateway | "Sweep budget exceeded." | `src/gateway/api.py` | `test_gateway.py::test_budget_exceeded` | no (operator decision needed) |
| `GATEWAY_VENDOR_FAILURE` | Gateway | "Vendor returned an error; check `context.vendor_code`." | `src/gateway/api.py` | per-vendor test | depends |
| `ER_BELOW_THRESHOLD` | ER | "Entity resolution similarity below auto-accept threshold." | `src/er/api.py` | `test_er.py::test_threshold_routing` | n/a (routes to HITL) |
| `ER_CANONICAL_INDEX_STALE` | ER | "Canonical alias index out of date; rebuild required." | `src/er/canonical_index.py` | `test_er.py::test_stale_index` | no (operator action) |
| `L1_IMMUTABLE_REJECT` | Conflict / Graph | "Attempted modification of L1 node refused." | `src/graph/client.py`, `src/conflict/resolver.py` | `test_security_l1_immutable.py` | no (programmer bug) |
| `LLM_JUDGE_NO_AGREEMENT` | Conflict | "LLM-as-judge cross-vendor calibration disagreed; escalating to HITL." | `src/conflict/llm_judge.py` | `test_conflict.py::test_judge_disagreement` | n/a |
| `HALO_HALFLIFE_MISSING` | Conflict | "Edge type has no half-life entry in HALO table." | `src/conflict/halo_table.py` | `test_conflict.py::test_halo_missing` | no |
| `GRAPH_NODE_NOT_FOUND` | Graph | "Referenced graph node not found." | `src/graph/client.py` | `test_graph.py::test_node_not_found` | no |
| `GRAPH_BITEMPORAL_INCONSISTENT` | Graph | "Bitemporal edge intervals overlap or are malformed." | `src/graph/bitemporal.py` | `test_bitemporal.py` | no |
| `GRAPH_DRIVER_UNAVAILABLE` | Graph | "Graph DB not reachable." | `src/graph/client.py` | `test_graph.py::test_driver_unavailable` | yes |
| `RETRIEVAL_TIMEOUT` | Retrieval | "Retrieval query exceeded latency budget." | `src/retrieval/api.py` | `test_retrieval.py::test_timeout` | yes |
| `RETRIEVAL_CITATION_MISSING` | Retrieval | "Internal error: retrieval result lacks `references`." | `src/retrieval/api.py` | `test_retrieval_citations.py` | no (programmer bug) |
| `HITL_ITEM_ALREADY_CLAIMED` | HITL | "Another reviewer claimed this item; use --force after timeout." | `src/hitl/queue.py` | `test_hitl_queue.py::test_already_claimed` | yes |
| `HITL_CLAIM_TIMEOUT` | HITL | "Claim timed out; item returned to pending." | `src/hitl/queue.py` | `test_hitl_queue.py::test_timeout` | yes |
| `HITL_DECISION_CONFLICTS_WITH_EXISTING` | HITL | "Decision conflicts with current graph state; review changes." | `src/hitl/cli.py` | `test_hitl_cli.py::test_decision_conflict` | yes (reviewer can re-decide) |
| `AUDIT_LOG_WRITE_FAILED` | Observability | **Critical** — audit log unwritable; process halting. | `src/observability/audit.py` | `test_audit_log.py::test_write_failure` | no |
| `SECRET_DETECTED_IN_OUTPUT` | Security | "Output contained secret pattern; blocked." | `src/observability/redact.py` | `test_redact.py` | no |
| `PROMPT_INJECTION_DETECTED` | Security | "Stage-3 output looked like a prompt-injection attempt." | `src/extraction/stage3_api.py` | `test_prompt_injection_corpus.py` | no |
| `SECURITY_PATH_OUTSIDE_SANDBOX` | Security | "Path outside allowed sandbox." | `src/shared/path_validation.py` | `test_mcp_tools.py::test_path_traversal` | no |
| `LICENSE_BLOCKED_DEPENDENCY` | Build | "Dependency has non-allowlist license." | `tools/license_check.py` | (CI gate) | n/a |

## HTTP-status mapping (for any future HTTP transport in V2)

| Category | HTTP status |
|---|---:|
| Validation / schema | 400 |
| L1_IMMUTABLE_REJECT | 403 |
| GRAPH_NODE_NOT_FOUND | 404 |
| HITL_ITEM_ALREADY_CLAIMED | 409 |
| GATEWAY_RATE_LIMITED | 429 |
| Most extraction / gateway / graph errors | 500 |
| GATEWAY_VENDOR_FAILURE | 502 |
| GATEWAY_BUDGET_EXCEEDED | 503 (intentionally) |
| Audit / security critical | 500 (with halting) |

V1 transport = stdio (MCP) + Python errors. V2 reopens HTTP mappings.

## Adding a new error code

1. Append a row to this table.
2. Add the code to `ErrorCode` enum in `src/shared/errors.py`.
3. Add the throwing site + test.
4. Update relevant module's docstring if it changes public-API behavior.
5. In PR description, justify why the new code is needed (vs reusing an existing one).

## Deprecation policy

- Mark a code `# DEPRECATED` in the enum but keep it functional for at least one release cycle.
- Replace internal call sites in the same PR; external API callers get the next release to migrate.
- Remove after the deprecation window with an ADR justifying the breaking change.

## Localization

V1 messages are English-only. V2 reopens (per-locale message catalogs). Codes themselves are stable across locales.
