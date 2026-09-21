# Security Model

> **V1 = internal-only, single-user (Mahyar's workstation).** The bulk of multi-tenant / external-facing security work is deferred to V2 per `docs/01-core/out-of-scope.md`. This file documents V1's actual posture + the V2 reopen plan.

## V1 posture

### Scope of V1 security

- **Single user**: Mahyar.
- **Single workstation**: GTX 1080 + 64 GB RAM Windows 11 box.
- **No external network exposure** of the V1 product engine MCP. Stdio transport only.
- **No multi-tenant isolation**: there's no second tenant.
- **No public consumer UI**: the V1 product engine is the backend that DentistJourney (separate repo) will eventually consume.
- **Data sources used in V1 (per `External Data\`)** are personally / institutionally licensed by Mahyar for internal evaluation; not redistributed externally in V1.

### Threats actually in scope for V1

1. **Accidental credential leak** to git / logs / audit-log dumps.
2. **L1 immutability violation** — code path that mutates an L1 node. Highest-severity logical safety issue.
3. **Vendor SDK lock-in** that ties product code to one vendor (security-adjacent: limits ability to rotate vendors on compromise).
4. **Prompt-injection / data-exfiltration through extraction** — a malicious forum post crafted to bend the Stage-3 LLM into emitting sensitive instructions. Low-probability against a private internal pipeline, but the audit log captures inputs, so a trace exists.
5. **Loss of audit-log integrity** — without an append-only audit log, the system can't be debugged or held to its non-negotiables.
6. **Accidental destructive ingestion** — re-running ingest with corrupted dumps and overwriting good state. Mitigated by content-hash idempotency + atomic dump rollback + bitemporal preservation.

### Threats explicitly out of scope for V1 (reopened in V2)

- External authentication / authorization.
- Multi-tenant data isolation.
- Network-level attack surface.
- DDoS resistance.
- DMCA / takedown / GDPR right-to-be-forgotten on forum-author content.
- Public abuse-reporting flows.
- Detailed PII handling (forum authors are pseudonymous; the V2 reopen handles this seriously).

## Principles

1. **Validate all external input.** Manifests, MCP tool arguments, HITL YAML files are validated via Pydantic.
2. **Never trust forum content.** Stage-3 prompts are constructed with explicit instruction-isolation. No forum text is concatenated into a system prompt; it goes inside a `<user_content>` block. Extracted output is Pydantic-validated.
3. **Never log secrets**, API keys, raw `.env` content, or sensitive HITL reviewer notes that contain identifiers.
4. **Audit log is append-only.** Schema enforces no UPDATE / DELETE on `audit_log` rows.
5. **L1 immutability is a hard rule** (non-negotiable #1). The data layer rejects any UPDATE / DELETE on `source_tier = L1` nodes with `L1_IMMUTABLE_REJECT` error.
6. **No `eval()` / `exec()` / `pickle` over the wire** anywhere in product code.
7. **Cache-key collisions can't expose cross-source data.** Content-addressable cache keys include `prompt_id` + `prompt_version` + `schema_hash` + `model` + `model_version`, so an old cached extraction can't accidentally be served for a new prompt or model.

## Secrets management (V1)

- `.env` file at repo root, gitignored. Loaded via `python-dotenv` or direct `os.getenv`.
- `.env.example` checked in (no real secret values).
- Secrets in scope for V1:
  - `ANTHROPIC_API_KEY`
  - `OPENAI_API_KEY`
  - `GOOGLE_API_KEY` (or `GEMINI_API_KEY` per Vertex/AI Studio)
  - `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_HOST`
  - Graph-DB connection strings (depending on bake-off winner — e.g., `NEO4J_PASSWORD`, `POSTGRES_PASSWORD`).
- Rotation policy: manual, per Mahyar's discretion. V2 introduces automated rotation reminders.
- Never embed secrets in BAML prompt files; the gateway reads keys from env at call-time.

## Roles + permissions (V1)

V1 has one human role:

| Role | Permissions |
|---|---|
| Mahyar (operator + reviewer) | Read/write everywhere. Only auth is "you have access to the workstation." |

V2 reopens with explicit roles: operator, reviewer, downstream-consumer, tenant-admin, system-admin.

## Sensitive data inventory

See `docs/07-data/data-dictionary.md` for the full table. Highlights:
- API keys (critical).
- Licensed ADEA / CODA content (V1 internal use only).
- Forum-author pseudonyms (low sensitivity in V1; revisit in V2).
- Audit-log contents (may quote forum text — internal only).

## MCP security (cross-references `tools/mcp/security.md` + `docs/12-security/mcp-security.md`)

V1 MCP transport = stdio only. Implications:
- No network exposure.
- Process-isolation is the security boundary (whatever can read the stdio pipes can call the tools).
- No auth needed inside MCP tool implementations; the process boundary IS the auth.

V2 reopens MCP security:
- Transport options (streaming HTTP, SSE).
- Per-tool auth.
- Per-call rate limiting.
- Per-tool argument sanitization (some V1 sanitization is already in place via Pydantic on tool inputs).

Detailed MCP-tool-level security rules live in `docs/12-security/mcp-security.md`.

## Prompt-injection mitigation (V1)

The cascade extraction Stage 3 is the only place forum text reaches an LLM. Defenses (all in V1):

1. **Instruction isolation**: BAML prompts explicitly separate `<system_instruction>` (immutable, hashed) from `<user_content>` (forum text). The schema-aligned parser rejects outputs that look like attempts to redefine the system instruction.
2. **Output schema enforcement**: every Stage-3 output is Pydantic-validated. A model trying to emit free-form "ignore previous instructions" text will fail the schema.
3. **Constrained decoding** for any local-model path (XGrammar) so the model can't emit out-of-schema tokens at all.
4. **No tool-use granted to Stage-3 LLM**: Stage 3 is purely extractive. It does not have `bash`, `Read`, `Write`, or any other tool exposed.
5. **Audit-log captures inputs**: every Stage-3 call writes the hashed input + cache key, so prompt-injection attempts are traceable post-hoc.
6. **Random-sample audit** (per `plan.md` Phase 9): 1-2% of Stage-3 outputs are spot-checked weekly against their inputs to catch silent injection successes.

## Negative tests (per AGENTS.md security principle)

The test suite explicitly includes:
- `tests/security/test_l1_immutable.py` — UPDATE / DELETE against an L1 node is rejected.
- `tests/security/test_vendor_lockin.py` — vendor SDK imports outside `src/gateway/` fail the import-ban lint.
- `tests/security/test_ttl_pinning.py` — any LLM call site without `ttl: 3600` fails the lint.
- `tests/security/test_audit_log_append_only.py` — UPDATE / DELETE against `audit_log` rows is rejected at the writer level.
- `tests/security/test_prompt_injection_corpus.py` — runs Stage-3 on a small corpus of known prompt-injection patterns; asserts none of them produce a schema-valid output that leaks the system prompt.

## V2 reopen plan (preview)

When the engine moves to external use, this entire document is rewritten. V2 changes will at minimum include:
- External authentication (vendor TBD: OIDC / SSO / token-based).
- Per-tenant data isolation.
- Network transport security (TLS, mTLS where appropriate).
- Rate limiting per tool + per tenant.
- DMCA / GDPR right-to-be-forgotten handling for forum-author content.
- Detailed PII inventory + anonymization options for license-sensitive deployments.
- Public abuse-reporting + incident-response process.

V2 design must answer:
- How does an external operator submit a dump without exposing their data to other tenants?
- How does a downstream agent prove its identity to call retrieval MCP tools?
- How does the system enforce per-tenant cost ceilings?

These are out of V1 scope; the V2 reopen will draft a fresh threat model document.

## Audit / incident process (V1)

V1 has no formal incident process beyond Mahyar's own monitoring. When something unexpected happens:
1. Read `audit_log` for the relevant time window.
2. Reconstruct state from `audit_log` + raw dumps.
3. Fix the root cause in code.
4. Add a regression test.
5. Document in `known-issues.md` (slice-local or repo-wide as appropriate).
