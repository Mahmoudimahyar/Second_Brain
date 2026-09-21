# Testing Strategy

> V1 product engine. Test types, validation order, and discipline. Per-slice test plans (e.g., V1 slice) extend this with feature-specific cases.

## Test types used in V1

| Type | Framework | Used for |
|---|---|---|
| **Typecheck** | `mypy --strict src/` | Public API typing; structural invariants |
| **Lint** | `ruff check`, `lint_ttl_pinning.py`, `ruff format --check` | Style + custom rules (vendor-SDK ban, TTL pinning) |
| **Unit** | `pytest` | Module-level Python APIs; pure logic |
| **Integration** | `pytest` + temp graph/SQLite | Multi-module flows; per-state-machine paths |
| **Contract (MCP)** | `pytest` + `mcp` SDK in test mode | MCP tool signatures + schemas; backward-compat |
| **Property-based** | `hypothesis` | Bitemporal correctness, content-hash idempotency, transition-table legality |
| **End-to-end** | `pytest` + frozen real-data subsamples | Full slice on r/DentalSchool 100-thread subsample |
| **Eval (gold-set)** | `evals/` custom harness | F1 on labeled mention / sentiment / interview-Q sets |
| **Cost regression** | `pytest` + Langfuse fixture | Per-sweep cost under hard cap |
| **Performance regression** | `pytest-benchmark` (or `tests/perf/` custom) | NFR-1 p95 latency |
| **Security negative** | `pytest` | L1 immutability, vendor-SDK ban, audit-log append-only, TTL pinning |
| **Smoke** | `pytest -m smoke` | Fast subset for pre-commit + post-deploy checks |

**Browser tests are NOT used in V1.** HITL UX is CLI + flat YAML; no web UI until V2. The scaffolded `browser-validation.md` applies *only if* a UI surface lands in scope; not now.

## Principle

Test **behavior**, not implementation trivia. A test should survive a refactor that doesn't change observable behavior.

## Validation order (CI gate)

1. **Lint** (`ruff check`, `lint_ttl_pinning.py`) — fastest; catches structural issues.
2. **Typecheck** (`mypy --strict src/`) — fast; catches API drift.
3. **Unit tests** — `pytest -m unit` (≤ 1 min).
4. **Integration tests** — `pytest -m integration` (≤ 3 min).
5. **Contract tests** — `pytest -m contract` (MCP tool schemas).
6. **Property-based tests** — `pytest -m property` (longer; hypothesis-generated).
7. **End-to-end** — `pytest -m e2e` (5+ min on real subsample).
8. **Eval suite** — `pytest -m eval` (longest; runs against gold sets + may call API).
9. **Cost + perf regression** — `pytest -m regression`.

`make ci` runs steps 1-7 + 9. Eval runs nightly or pre-release (it costs real API tokens).

## Repair budget (per AGENTS.md)

- Unit / integration failures: max **5** repair cycles.
- E2E / property failures: max **3** repair cycles.
- Full-suite failures: max **2** repair cycles.

After exhausting the budget: stop, write a failure report under `/.agent/reports/`, surface to Mahyar.

## Coverage gates

- **`pytest --cov=src --cov-fail-under=80`**: 80% line coverage on `src/`. CI gate.
- **100%** coverage required on:
  - `src/gateway/` (vendor abstraction — must be exhaustively tested).
  - `src/conflict/resolver.py` (the 6-step order is safety-critical).
  - `src/observability/audit.py` (audit log integrity).
  - `src/graph/bitemporal.py` (bitemporal correctness).
- Coverage exclusions documented in `pyproject.toml` `[tool.coverage]`.

## Test data discipline

- **Synthetic fixtures** (deterministic, version-controlled) for unit + integration.
- **Real-data subsamples** (frozen via deterministic seed) for E2E.
- **Recorded vendor responses** (VCR-style) for cross-vendor switch tests — re-record when prompts/schemas change.
- **Gold sets** (hand-labeled) for eval — `evals/gold/*.jsonl`.

See `test-data.md` for the catalog + how to add new fixtures.

## Mocking rules

- **Mock vendor APIs only at the gateway boundary.** Tests for `src/conflict/resolver.py` should not mock `openai.chat.completions.create()` directly — they should call through the gateway's test-mode adapter (`src/gateway/test_adapter.py`).
- **No mocking of stdlib** (datetime, uuid). Use `freezegun` for time.
- **No mocking of structlog logger** — assert on actual log records via `pytest`'s `caplog`.
- **Mock external HTTP via `respx`** at the httpx layer, not at the application layer.

## Test invariants (always-on)

Per slice `test-plan.md`:
- TI-1: every Anthropic call uses `ttl: 3600`.
- TI-2: no vendor-specific SDK imports in product code.
- TI-3: every `audit_log` row has required fields.
- TI-4: every retrieval result has non-empty `references`.
- TI-5: every edge has bitemporal 4-tuple.
- TI-6: L1 nodes have `rank=preferred`, `source_tier=L1`, never mutated.

These are enforced via fixtures that wrap the gateway + graph client and assert at teardown.

## Eval suite specifics

Each eval module under `evals/`:
- Loads a gold-set JSONL.
- Runs the relevant pipeline (Stage 2 ER, Stage 3 sentiment, Stage 3 interview-Q).
- Computes F1 / precision / recall.
- Writes results to `evals/results/<date>/<eval_name>.json`.
- CI gate: F1 must meet the target in `success-metrics.md` Quality table.

Gold sets are version-controlled. New gold examples are PR-able (and **must** include a justification for the label).

## How a new test is added

1. **Failing-first** — write the test against the desired behavior, run it, watch it fail.
2. **Smallest correct change** — implement just enough code to pass.
3. **Targeted tests** — run only the new test + nearby ones during iteration.
4. **Broader tests** — once the new test passes, run the broader suite for that module.
5. **Lint + typecheck** — clean before commit.
6. **PR** — description includes "what behavior does this test prove?"

## Reviewer checklist (for PRs touching tests)

- Does the test prove a **behavior** (not a private implementation choice)?
- Are negative cases covered (errors, vendor failures, threshold-borderline)?
- Is the test deterministic (no relying on wall-clock, network, random without seed)?
- Are fixtures reused appropriately (no duplicate inline setup)?
- Are test names descriptive (`test_<behavior>_when_<condition>`)?

## V2 reopens

- Browser validation (when a web UI lands).
- Cross-tenant test isolation.
- Multi-region / network-partition tests.
- Load testing at production scale.
