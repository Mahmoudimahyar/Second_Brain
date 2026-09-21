# Code Quality Principles

> Python project. Discipline-first. The rules below extend the generic principles with V1-specific enforcement.

## Clarity

- Code must be easy to read before it is clever.
- Use descriptive names: `extracted_school_mentions` not `data`; `apply_temporal_decay` not `do_it`.
- Avoid vague names like `data`, `item`, `temp`, `info`, `obj`, `handle*`, `process*`.
- Prefer straightforward control flow over nested conditionals + early returns.
- Keep functions small (target ≤ 30 lines; hard cap 80 unless explicitly justified).
- Keep files focused (one cohesive responsibility per file).
- Module-level docstrings explain *what this module is for*; function docstrings explain *what it does* and *invariants assumed*.

## Explicit contracts

- All public APIs (per `module-boundaries.md`) have typed inputs and outputs.
- Pydantic models for any structured data crossing a module boundary.
- Validate external inputs (MCP tool args, HITL YAML, dump manifests) at the boundary, not deep in business logic.
- Return structured errors (`StructuredError` from `src/shared/errors.py`), never bare strings.
- Public functions document invariants assumed (e.g., "input must be UTC; behavior undefined otherwise").

## Modularity (cross-references `module-boundaries.md`)

- Each module owns its internals; only public symbols cross boundaries.
- Expose public symbols via `__init__.py` re-exports; never import from `_private` files outside the module.
- Avoid cross-module internal imports — they're banned at lint level.
- `src/shared/` holds only TRULY generic utilities (timestamps, hashing, IDs, errors). Anything domain-aware lives in a feature module.
- **Do not create shared abstractions prematurely.** Three call sites = candidate for extraction; two = inline.

## Testing (cross-references `docs/09-testing/testing-strategy.md`)

- Every behavior change requires tests.
- Test public behavior, not private implementation trivia.
- Include negative / error-path tests (especially: invalid inputs, vendor failures, L1 immutability violations).
- Use fixtures / builders for repeated setup (`tests/fixtures/`).
- Coverage target: ≥ 80% line coverage on `src/`. CI gate.
- Property-based tests for invariants: bitemporal correctness, content-hash idempotency, transition-table legality.

## Error handling (cross-references `error-handling.md` + `docs/06-api/error-codes.md`)

- Use structured errors with stable codes from `src/shared/errors.py`.
- Include safe diagnostic context (input fingerprints, not raw secrets).
- Never expose secrets in error messages, log lines, or audit-log fields_json.
- Never swallow errors silently. `except Exception: pass` is a CI failure.
- Vendor-level errors (Anthropic 5xx, OpenAI rate limit) bubble through the gateway and become `GATEWAY_VENDOR_FAILURE` with the original error in `context`.

## Maintainability

- Small, reviewable diffs. Aim for < 400 lines net change per PR.
- No unrelated refactors mixed with feature work.
- No dependency additions without justification (per `dependency-rules.md`).
- No duplicated business rules. If the same threshold appears in two places, it's a constant in `src/shared/` or a feature config.
- No hidden global state unless explicitly approved (and audited via a singleton module).

## V1-specific enforcement rules (CI-gated)

These are non-negotiable lints / tests. PR fails on any violation.

| Rule | Enforced by | Spec |
|---|---|---|
| `ttl: 3600` mandatory on every Anthropic cache-write call | `tools/lint_ttl_pinning.py` (also imported as `src/observability/lint_ttl.py`) | GAP-031, A-036 |
| Vendor SDK imports forbidden outside `src/gateway/` | `ruff` rule (custom `flake8-tidy-imports` config) | A-046, non-negotiable #9 |
| L1 nodes immutable | Data-layer code path + `tests/security/test_l1_immutable.py` | Non-negotiable #1 |
| Append-only audit log | Data-layer code path + `tests/security/test_audit_log_append_only.py` | Non-negotiable #4 |
| No `pickle` over the wire | `ruff` rule | Security |
| No `eval()` / `exec()` | `ruff` rule | Security |
| No `print()` in `src/` | `ruff` rule (`structlog` only) | Observability |
| Public APIs are typed | `mypy --strict src/` | Contracts |
| No circular imports | `tests/test_import_graph.py` (AST walk) | Modularity |
| No `print` / `pprint` debugging code merged | `ruff` | Discipline |
| No commented-out code | manual review (informal) | Cleanliness |

## Style

- `ruff format` (Black-compatible) — no manual formatting decisions.
- `ruff check` — comprehensive lint.
- `mypy --strict` for `src/`; `mypy` (non-strict OK) for `tests/`.
- Imports ordered by `ruff` (stdlib → third-party → first-party).
- Line length 100.

## Docstring policy

- **Module**: 1-2 sentence purpose statement at top of every file.
- **Public function / class**: full docstring (Google style or NumPy style — pick one in implementation, document choice).
- **Internal / private**: docstring only if non-obvious. Most internals shouldn't need docstrings if names are good.

## Comment policy (per CLAUDE.md global rules)

- Default to writing no comments.
- Only add a comment when the WHY is non-obvious: a hidden constraint, a subtle invariant, a workaround for a specific bug, behavior that would surprise a reader.
- Don't explain WHAT the code does (names already do that).
- Don't reference the current task, fix, or callers — those rot.
- For TTL-pinning, vendor-SDK-import-ban, L1-immutability: a brief inline `# Non-negotiable #N — see docs/01-core/non-negotiables.md` when the constraint isn't obvious from the code.

## Refactor policy

- A bug fix doesn't need surrounding cleanup. Resist scope creep.
- A one-shot operation doesn't need a helper. Don't design for hypothetical future requirements.
- Three similar lines is better than a premature abstraction.
- No half-finished implementations. If a function is started and not finished, it's not merged.

## Reviews + pull requests

- Author writes a self-review checklist in the PR description (per AGENTS.md "Done means done").
- Reviewer (or author if solo) walks the diff as a skeptical senior engineer.
- Every PR includes a link to the test(s) that prove the change works.
- Every architectural deviation from `system-overview.md` / `tech-stack.md` requires either an ADR or an SD-* row in the slice's `decisions.md`.
