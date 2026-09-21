# Error Handling

> Python project. Structured errors with stable codes. No silent swallowing. No secret leaks. The error catalog lives in `docs/06-api/error-codes.md` (single source of truth — TBD next batch); this file is the **policy**.

## Principles

1. **Structured errors only.** No bare `raise Exception("...")`. Use `StructuredError` from `src/shared/errors.py`.
2. **Stable error codes** from a single enum (`ErrorCode` in `src/shared/errors.py`). Codes are part of the API contract; renaming requires a deprecation cycle.
3. **Safe messages to users.** Caller-facing `message` strings never contain secrets, raw API keys, full prompts (which may contain forum text), or unmitigated stack traces.
4. **Safe diagnostic context.** `context` dict holds fingerprints (content-hashes, IDs, model names) — never the raw payload.
5. **Never log secrets.** Log redactors strip Anthropic / OpenAI / Google API keys + Postgres / Neo4j passwords from log lines.
6. **Never swallow.** `except Exception: pass` is a CI failure. If you genuinely want to ignore an error, catch the *specific* exception class and add an inline comment with the WHY.

## Error shape

```python
# src/shared/errors.py
class StructuredError(Exception):
    code: ErrorCode             # enum; stable across releases
    message: str                # safe, human-readable
    context: dict[str, Any]     # safe diagnostic fields
    retry_safe: bool            # caller can retry without dedup risk
    cause: Exception | None     # original exception, if any

    def to_dict(self) -> dict:
        return {
          "error_code": self.code.value,
          "message": self.message,
          "context": self.context,
          "retry_safe": self.retry_safe,
        }
```

API responses (MCP + Python) include `to_dict()` shape. Internal logs include `cause` (chained).

## Error catalog (high-level categories)

Detail per code in `docs/06-api/error-codes.md`. Categories:

| Category | Example codes |
|---|---|
| Validation | `VALIDATION_FAILED`, `MANIFEST_INVALID`, `HITL_DECISION_SCHEMA_INVALID` |
| Ingestion | `DUMP_DUPLICATE`, `DUMP_ROLLBACK`, `ADAPTER_NOT_FOUND`, `ADAPTER_FAILED` |
| Extraction | `STAGE3_VENDOR_FAILURE`, `STAGE3_SCHEMA_INVALID`, `EXTRACTION_CACHE_MISS`, `EXTRACTION_TIMEOUT` |
| Gateway | `GATEWAY_ALL_VENDORS_FAILED`, `GATEWAY_TTL_NOT_PINNED`, `GATEWAY_RATE_LIMITED`, `GATEWAY_BUDGET_EXCEEDED` |
| ER | `ER_BELOW_THRESHOLD`, `ER_CANONICAL_INDEX_STALE` |
| Conflict | `L1_IMMUTABLE_REJECT`, `LLM_JUDGE_NO_AGREEMENT`, `HALO_HALFLIFE_MISSING` |
| Graph | `GRAPH_NODE_NOT_FOUND`, `GRAPH_BITEMPORAL_INCONSISTENT`, `GRAPH_DRIVER_UNAVAILABLE` |
| Retrieval | `RETRIEVAL_TIMEOUT`, `RETRIEVAL_CITATION_MISSING` |
| HITL | `HITL_ITEM_ALREADY_CLAIMED`, `HITL_CLAIM_TIMEOUT`, `HITL_DECISION_CONFLICTS_WITH_EXISTING` |
| Observability | `AUDIT_LOG_WRITE_FAILED` |
| Security | `SECRET_DETECTED_IN_OUTPUT`, `PROMPT_INJECTION_DETECTED` |

## Retry semantics

- `retry_safe = True` means the caller can re-invoke with the same inputs and reach the same dedup behavior (cache key, idempotency token). Examples: `GATEWAY_RATE_LIMITED`, `EXTRACTION_TIMEOUT`.
- `retry_safe = False` means re-invocation has side effects (partial graph writes, etc.) — caller must reconcile state first. Examples: `DUMP_ROLLBACK`, `GRAPH_BITEMPORAL_INCONSISTENT`.

## Vendor-failure handling (gateway-specific)

The gateway implements a fallback chain per the per-task matrix in `tech-stack.md`. Vendor errors:
- `429` rate limit → exponential backoff, retry within same vendor (≤ 3 attempts), then fail over to next vendor in chain.
- `5xx` server error → fail over immediately to next vendor.
- `4xx` other → no failover (likely caller-side mistake); raise `GATEWAY_*` with vendor's original code in context.
- All-vendors-failed → `GATEWAY_ALL_VENDORS_FAILED` with full chain trace in `context`.

## Audit-log handling

Every `StructuredError` that crosses an API boundary is audit-logged with `kind = "error"` + `fields_json = error.to_dict() + diagnostic context`. If audit-log write itself fails (`AUDIT_LOG_WRITE_FAILED`), the process logs to stderr + halts gracefully — audit integrity is a non-negotiable.

## L1 immutability error

Any code path that attempts to mutate an L1 node raises `L1_IMMUTABLE_REJECT` immediately at the graph-client level. No silent fall-through. This is a non-negotiable safety guarantee tested in `tests/security/test_l1_immutable.py`.

## TTL-pinning error

Any LLM call site that omits `ttl: 3600` raises `GATEWAY_TTL_NOT_PINNED` at call time + fails the `lint_ttl_pinning.py` static check at PR time. The static check is the primary defense; the runtime check is belt-and-braces.

## Boundary handling

| Boundary | Error policy |
|---|---|
| MCP tool inbound | Pydantic validate args; on failure raise + serialize to `to_dict()` MCP response. |
| MCP tool outbound (to crawler) | If crawler unreachable, mark `research_need` as `pending_dispatch` rather than failing the caller. |
| HITL CLI | Validation errors print human-readable + non-zero exit. |
| Tests | Test failures surface the structured error; assertion messages include `code` + safe `context`. |

## Logging policy

- `structlog` with JSON renderer.
- Levels: `debug`, `info`, `warning`, `error`, `critical`.
- `info` for state transitions, successful ingest/extract/retrieve.
- `warning` for retries, vendor failovers, threshold-borderline cases.
- `error` for `StructuredError` raised; `critical` for `AUDIT_LOG_WRITE_FAILED` and L1-immutability violations (these should be impossible — log + halt).
- Secret-redaction filter on every logger before output.

## Don'ts (explicit anti-patterns)

- ❌ `except Exception as e: print(e)` — silent + insecure.
- ❌ `raise ValueError("bad input")` — bare string, no code.
- ❌ `logger.error("API failed", exc_info=True)` with no redaction — may leak secrets.
- ❌ `return None` instead of raising on failure paths — caller can't distinguish "no data" from "error."
- ❌ Catching `BaseException` (catches KeyboardInterrupt, SystemExit) without explicit reason.
- ❌ `assert <user-input check>` — `assert` is for invariants, not validation. (Disabled in `-O` Python.)
