# MCP Security Rules

> MCP / context tools are privileged. Treat them as a loaded gun. Per CLAUDE.md + tools/graphrag/MCP_SERVER_REQUIREMENTS.md + R-009 (three-tier policy).

## Two distinct MCP deployments (DO NOT confuse)

1. **`tools/graphrag/` — Repo MCP context server.** Indexes the SecBrain repo (docs, code, tests). Consumed by Claude Code. Sandbox = repo root. **Read-only by default**.
2. **V1 product engine MCP.** Indexes ingested dental data. Inbound retrieval + outbound to crawler. Sandbox = V1 product-engine process. **Read-only for retrieval; write-only on `register_dump` (idempotent + atomic)**.

Both are stdio in V1. V2 reopens transport.

## Cross-deployment rules

### Least-privilege

- Every MCP tool exposes the **minimum** capability needed by its caller.
- No tool grants arbitrary shell execution from caller-controlled input.
- No tool grants access outside its declared sandbox path.
- No tool returns secrets or `.env` content in its response payload.
- Read-only by default. Write tools require explicit caller approval at the design level (added per ADR).

### Approval-required actions

These require explicit user approval (Mahyar) — even when a tool exists for them:
- `register_dump` accepting an L1 manifest → Mahyar reviews the manifest before accepting (V1 = manual review; V2 may add a signature scheme).
- Any new MCP tool with write capability → ADR + tests + threat-model entry before merge.
- Any MCP tool that accepts user-controlled file paths → path validation + sandbox enforcement tested explicitly.

### Logging

- Every MCP tool call writes an `audit_log` row with: tool name, caller identity (process / agent ID where available), input fingerprint (content-hash, not raw payload), output fingerprint, latency, error code if any.
- No tool logs raw secrets; redaction processor enforced.
- Audit log is append-only.

## `tools/graphrag/` MCP server specifics

(per `tools/graphrag/MCP_SERVER_REQUIREMENTS.md`)

- **Server type**: stdio.
- **Sandbox**: repo root (`<repo>\`). No file access outside.
- **Read-only tools** (V1 baseline):
  - `search_codebase(query)`
  - `explain_feature(feature)`
  - `find_symbol(symbol)`
  - `get_feature_packet(feature)`
  - `get_related_tests(target)`
  - `get_docs_for_code(file_or_symbol)`
  - `get_code_for_doc(doc_path)`
- **Write tools** (V2 only): TBD; would require explicit approval flow.
- **Secrets policy**: never returns `.env`, never returns file content matching `*.env*` / `*.key` / `*.pem` / `*.secret` / `*.credential`. Path validation rejects parent-traversal (`..`).
- **Logging**: every tool call → `tools/graphrag/logs/mcp.jsonl`.

## V1 product engine MCP specifics

### Inbound tools (consumed by Claude Code, future agents)

| Tool | Read/Write | Approval? | Sensitive returns? |
|---|---|---|---|
| `query_graph` | R | no | Returns post / comment text from L5. **Forum content is licensed; treat as internal-only in V1**. |
| `get_canonical_entity` | R | no | Returns L1 canonical entity + alias list. Public-ish data. |
| (V1.x) `search_by_topic` | R | no | Same caveat as `query_graph`. |
| (V1.x) `get_user_credibility` | R | no | Returns derived credibility score for a forum author. Pseudonymous but be careful in V2 external. |
| (V1.x) `get_topic_consensus` | R | no | Aggregated cluster summary. |

### Outbound tools (the engine calls these against the separate crawler system)

| Tool | Read/Write | Approval? | Sensitive sends? |
|---|---|---|---|
| `register_dump` | W (atomic) | yes (manifest review V1) | Yes — the engine receives raw payloads; validates manifest before storing. |
| `get_gaps` | R | no | Returns gap descriptors; no raw forum content. |
| `get_research_needs` | R | no | Returns research-need records (topic + conflict candidates). No PII. |
| (V1.x) `is_url_ingested` | R | no | Boolean. |
| (V1.x) `get_topic_state` | R | no | Aggregated state summary. |
| (V1.x) `get_pending_verifications` | R | no | Conflict candidates. |

### Argument validation

Every inbound tool argument is validated by Pydantic schemas at the MCP boundary. Invalid arguments → `VALIDATION_FAILED` error returned to caller (per `error-handling.md`).

Specifically dangerous patterns explicitly rejected:
- File paths with parent-traversal (`..`).
- SQL-injection-style strings in query parameters (parameter-bound queries enforced in `src/retrieval/`).
- LLM-prompt-injection markers in `query` text (instruction-isolation in BAML prompts; see `security-model.md`).
- Arbitrary regex patterns (could DoS) — query language pre-compiled, no eval at runtime.

### Path validation

Any tool that accepts a path validates it against the sandbox:
```python
def validate_path(p: Path, sandbox: Path) -> Path:
    p = p.resolve(strict=True)
    if not p.is_relative_to(sandbox):
        raise StructuredError(
            code=ErrorCode.SECURITY_PATH_OUTSIDE_SANDBOX,
            message="Path outside allowed sandbox.",
            context={"path_attempt_hash": content_hash(str(p))},
            retry_safe=False,
        )
    return p
```

### Secrets exposure

- MCP tool responses never include `.env` values, raw API keys, or DB credentials.
- A grep-based pre-merge check (`tools/check_secrets_in_responses.py`) runs over recorded MCP test responses to catch accidental exposure.

### Negative tests

`tests/security/test_mcp_tools.py`:
- Path-traversal attempts rejected.
- SQL-injection-style query parameters do not affect graph behavior.
- Prompt-injection markers in retrieval queries don't escalate privileges.
- Calls without valid arguments return `VALIDATION_FAILED`.
- Calls return-payload audit confirms no `.env` / no API-key patterns in responses.

## Allowlist principle

The set of MCP tools exposed at any moment is **explicit and small**. Adding a tool requires:
1. ADR (architectural impact).
2. Negative tests (path / injection / secrets).
3. Audit-log integration.
4. Sandbox declaration.
5. Mahyar approval at PR review.

Removing a tool is easy — just drop the registration; no compat shim required since V1 is internal.

## Rate limiting (V1)

V1 single-workstation = no rate limiting needed. The process boundary IS the limit. V2 reopens.

## V2 reopen

V2 adds:
- Transport options (streaming HTTP, SSE).
- Per-tool auth (which agent can call which tool).
- Per-tenant rate limiting + quotas.
- Per-call argument sanitization at a tighter bar.
- DMCA / GDPR takedown handling on returned forum content.
- Network ACLs.
- Periodic threat-model review.
