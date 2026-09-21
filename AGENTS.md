# AGENTS.md

This file defines how coding agents must work in this repository.

## Mission

Build production-quality software with:
- accurate implementation
- low token usage
- clean modular code
- structured documentation
- test-driven development
- browser-validated UI
- GraphRAG/MCP-assisted context retrieval

## Operating principles

- Do not code before understanding the relevant feature.
- Use docs as contracts, not suggestions.
- Use GraphRAG/MCP context tools before broad repo exploration.
- Prefer small, focused diffs.
- Write or update tests before implementation.
- Validate behavior with automated tests.
- For UI changes, validate in browser and check console/network errors.
- Update docs whenever behavior, API, data, or UI flow changes.
- Do not silently invent requirements.
- Track assumptions and unresolved questions.

## Commands

```bash
pip install -e ".[dev]"                 # everything the test suite needs; no API keys required
pytest                                  # full suite (~1 min); `pytest tests/<area>` for targeted runs
ruff check src flows tools --select F,E9   # blocking in CI (full `ruff check .` is a ratchet)
mypy src tools                          # strict; informational until clean
secbrain-doc-lint                       # docs must not claim more than the code does
cd web && pnpm install && pnpm typecheck && pnpm test   # console (Node 22+, pnpm 11+)
```

## Discovery workflow

When requirements are unclear:
1. Ask focused questions.
2. Record confirmed facts in docs.
3. Record assumptions in `/docs/00-bootstrap/assumptions.md`.
4. Record unresolved questions in `/docs/00-bootstrap/unresolved-questions.md`.
5. Research best practices when making architecture, security, testing, AI, database, deployment, or stack decisions.
6. Do not start implementation until the next feature slice is clear enough to test.

## Context discipline

- Do not read the entire repo unless necessary.
- Prefer feature `context.md` files.
- Prefer exact linked docs over semantic guessing.
- Prefer summaries and file maps before raw code.
- Read only the smallest relevant file ranges.
- If more than 8 files seem necessary, create a plan first.
- Use targeted tests before full-suite tests.

## Before coding

1. Identify the feature.
2. Read the feature packet.
3. Use context tools if available:
   - `search_codebase`
   - `explain_feature`
   - `plan_change`
   - `get_feature_packet`
   - `get_related_tests`
   - `get_docs_for_code`
4. Create/update a task brief in `/.agent/tasks`.
5. Write/update tests before implementation.
6. Confirm required environment variables are documented in `.env.example`.

## TDD workflow

1. Write failing tests first.
2. Implement the smallest correct change.
3. Run targeted tests.
4. Run broader tests.
5. For UI changes, run browser validation.
6. Fix failures within repair budget.
7. Update docs.
8. Produce validation report.

## Repair budget

- Unit/integration failures: max 5 repair cycles.
- E2E/browser failures: max 3 repair cycles.
- Full-suite failures: max 2 repair cycles.

If still failing, stop and write a failure report with:
- what failed
- commands run
- logs
- attempted fixes
- likely root cause
- recommended next step

## Clean code rules

- Prefer clarity over cleverness.
- Use descriptive names.
- Use domain terms from `/docs/01-core/glossary.md`.
- Keep functions small and single-purpose.
- Avoid hidden side effects.
- Use explicit input/output types.
- Avoid large files.
- Avoid deeply nested logic.
- Avoid premature abstraction.
- Make invalid states impossible when practical.
- Keep business logic out of UI components.
- Keep database logic out of UI components.
- Keep feature internals private.
- Do not introduce dependencies without justification.
- Do not mix unrelated refactors with feature work.

## Documentation rules

Update docs when:
- requirements change → `requirements.md`
- API changes → `api.md`
- data model changes → `data.md`
- UI behavior changes → `ui-flow.md`
- tests change materially → `test-plan.md`
- architecture changes → ADR required
- known issue discovered → `known-issues.md`
- environment variables are added → `.env.example`

## Dependency rules

Do not add a new dependency unless:
- existing stack cannot reasonably solve the problem
- the dependency is actively maintained
- security/license risk is acceptable
- the tradeoff is documented
- the dependency is added intentionally, not casually

## Human approval required

Require explicit user approval for:
- auth/session architecture changes
- payment logic
- destructive migrations
- permission model changes
- production deployment config
- secrets/config handling
- major dependency changes
- architecture decisions that affect multiple modules

## Done means done

A task is complete only when:
- acceptance criteria are satisfied
- relevant tests pass
- typecheck passes
- lint passes
- browser validation passes if UI changed
- console/network errors are checked if UI changed
- **the capability is WIRED**: invoked from the real end-to-end entrypoint (CLI / Prefect flow / API route), not only from tests. A module wired with `None`/no-op/stub is **NOT done** — log it as a gap and leave its status `Built` (see §Wiring Gate below)
- **its row in `docs/00-bootstrap/implementation-status.md` is updated** with the non-test wiring site (`file:line`)
- docs are updated **and reconciled** (no doc says "done/Locked" for something below `Wired`)
- validation report is written
- no unrelated files were changed


---

## Project mode discipline

Before creating docs or coding, determine the project mode.

Do not assume the user is building a full business/product.

Supported modes:
- product_business
- internal_tool
- developer_tool
- cli_tool
- api_service
- library_package
- research_prototype
- automation_script
- data_pipeline
- ai_agent_system
- landing_page_only
- unknown

Use docs/00-bootstrap/doc-activation-matrix.md to decide which docs are required, optional, or skipped.

Do not create marketing/sales/pricing/competitor/customer-segmentation docs unless the selected mode requires them or the user explicitly requests them.

If the user is building a tool, prioritize:
- tool purpose
- user workflow
- inputs/outputs
- commands/API
- config/env
- error handling
- tests
- run instructions
- DevEx
- reliability


---

## Mandatory skill system

Before any substantive action, choose and follow a skill from PROMPTS/SKILLS.

Required first step:
- Read PROMPTS/SKILLS/00_USING_SKILLS_DISPATCHER.md

Do not freestyle when a skill applies.

Common triggers:
- unclear idea → Brainstorming
- multi-step task → Writing Plans
- existing plan → Executing Plans
- implementation → Test-Driven Development
- bug/failing test → Systematic Debugging
- about to claim complete → Verification Before Completion
- major completed chunk → Requesting Code Review
- reviewer feedback → Receiving Code Review
- large/risky feature → Using Git Worktrees
- parallelizable tasks → Dispatching Parallel Agents
- UI exploration → Visual Companion
- documentation → Documenting
- deploy/migration/performance/security → Deploy/Migrate/Optimize/Audit

Do not claim success without evidence.


---

## Continuous research and gap detection

Before major decisions, use:
- PROMPTS/ROLE_HARNESSES/16_STATE_OF_THE_ART_RESEARCH_HARNESS.md
- PROMPTS/ROLE_HARNESSES/17_GAP_DETECTION_HARNESS.md
- PROMPTS/ROLE_HARNESSES/18_RESEARCH_TO_DECISION_PIPELINE.md

The agent must continuously identify:
- missing requirements
- weak assumptions
- unclear architecture
- incomplete UI flows
- untested behavior
- missing env vars
- missing docs
- missing security/privacy decisions
- missing GraphRAG/MCP implementation details

Do not proceed to coding with blocking gaps.

## Research rule

Research must feed a decision:
research → recommendation → ADR/docs → tests → implementation rule.

## GraphRAG rule

Do not claim GraphRAG is active unless:
- MCP server is implemented or connected
- indexing runs
- retrieval tools work
- Claude Code can use the tools
- verification checklist passes


---

# Anti-drift gates (added 2026-05-29)

> Why: a review found "Locked"/"accepted" capabilities (HALO ranking, signed-graph
> consensus, 3-vendor judge, hybrid retrieval, bitemporal supersede) that were unit-built
> but never wired into the running pipeline, plus ADRs whose "Related code" files do not
> exist. Root cause and evidence: `docs/00-bootstrap/why-drift-happened.md`. These gates
> exist so it does not recur. They are non-negotiable.

## Wiring Gate (the most important rule in this file)

A capability is **not done at `Built`** (module exists + unit tests pass). It is done only
at **`Wired`**: there is a **non-test call site** in the real entrypoint
(`src/cli.py`, a `flows/*.py` Prefect flow, or a `src/web/routes/*` API route) that invokes
it on the real path. Before claiming done:
1. Name the wiring site as `file:line`. If you cannot, it is not done.
2. Grep for **stub wiring**: a collaborator constructed with `None`/no-op (e.g.
   `ConflictResolver()` with no judge), or a type that is referenced but never constructed
   (e.g. `HybridIndex`). Stub wiring = not done = a gap, not a completion.
3. Confirm every file an ADR lists under "Related code" actually exists.
4. Move the capability's row in `docs/00-bootstrap/implementation-status.md` to `Wired`
   (or `Validated` if you also ran it on real `External Data/`).

## Status discipline

Use the four-state vocabulary from `implementation-status.md` everywhere:
`Decided` → `Built` → `Wired` → `Validated`.

- "Locked" and ADR `accepted` mean **`Decided` only** — never "implemented".
- Every non-negotiable and every "Locked" table row must cite the **enforcement site**
  (`file:line`) or be explicitly marked a **target** (not-yet-enforced).
- `implementation-status.md` is the single source of truth. If an ADR / tech-stack /
  system-overview disagrees with it, **the status file wins** and the others are bugs to fix.

## No horizontal expansion before vertical validation

Do **not** start a new feature area (a new connector, a new UI surface, a new pass, a new
slice) while the **current core vertical slice is below `Validated`** on real data. The V1
core slice is: *ADEA L1 + one subreddit → trust-tier graph → conflict resolution → HITL →
cited retrieval*, run end-to-end on `External Data/`. Breadth is not progress while the
core is stubbed. If tempted to expand, instead finish wiring + real-data validation.

## Small diffs; no mega-commits

- One slice (or one work package) per commit/PR. Never squash an entire release into a
  single commit — a 700-file diff cannot be reviewed and hides wiring gaps.
- After each work package, run the "review your own diff as a skeptical senior engineer"
  pass (CLAUDE.md) on a diff small enough to actually read.

## Research must be live-verified before `accepted`

An ADR may not move from `proposed` to `accepted` while any load-bearing citation is
marked `[needs live verification]`. SOTA claims (cost, "nobody does X", "tool Y is SOTA")
must be confirmed against live sources (WebSearch/WebFetch) with a dated citation. See
`docs/03-research/research-protocol.md`.

## Definition-of-done checklist (paste into every validation report)

- [ ] Acceptance criteria met
- [ ] Unit + integration tests green (integration test exercises the **real wiring**, not a mock-only path)
- [ ] typecheck + lint clean
- [ ] **Wiring site cited (`file:line`) in the validation report**
- [ ] **No stub wiring** (no `None`/no-op collaborators; no referenced-but-unconstructed types)
- [ ] **ADR "Related code" files all exist**
- [ ] Ran on real `External Data/` (or stated explicitly why not) → status `Validated` vs `Wired`
- [ ] `implementation-status.md` row updated
- [ ] Docs reconciled (nothing claims "done/Locked" below `Wired`)
- [ ] Diff is small enough to review; reviewed as skeptical senior engineer
