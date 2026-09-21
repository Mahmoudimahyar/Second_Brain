# Gate Check

> ⚠️ **Historical snapshot, frozen 2026-05-20 (pre-implementation).** For current state see `docs/00-bootstrap/implementation-status.md`.

> Status of each gate per `docs/00-bootstrap/gates.md`. Updated 2026-05-20 after the R4 doc-completion round.

## 1. PRD Gate

| Item | Status | Source |
|---|---|---|
| Product summary exists | ✅ | `docs/01-core/product-vision.md` |
| Target users defined | ✅ | `docs/01-core/user-types.md` + `docs/02-product/personas.md` |
| MVP scope defined | ✅ | `docs/01-core/product-vision.md` § Success definition (V1) + `docs/02-product/roadmap.md` Phase 1 |
| Out-of-scope list defined | ✅ | `docs/01-core/out-of-scope.md` |
| User journeys defined | ✅ | `docs/02-product/user-journeys.md` (3 V1 journeys) |
| Functional requirements defined | ✅ | `docs/05-features/01-slice-trust-tier-canonicalize/requirements.md` FR-1..FR-11 |
| Non-functional requirements defined | ✅ | same file § Non-functional requirements (NFR-1..NFR-9) |
| Acceptance criteria testable | ✅ | same file § Acceptance criteria (AC-1..AC-10) + `test-plan.md` map |
| Blocking questions tracked | ✅ | `docs/00-bootstrap/unresolved-questions.md` |

**Gate 1 status: ✅ PASS.**

## 2. Architecture Gate

| Item | Status | Source |
|---|---|---|
| Tech stack selected | ✅ (except graph DB) | `docs/04-architecture/tech-stack.md` |
| Architecture documented | ✅ | `docs/04-architecture/system-overview.md` |
| Module boundaries documented | ✅ | `docs/04-architecture/module-boundaries.md` |
| Dependency rules documented | ✅ | `docs/04-architecture/dependency-rules.md` |
| Data model drafted | ✅ | `docs/07-data/data-dictionary.md` + slice `data.md` |
| API strategy drafted | ✅ | `docs/05-features/01-slice-trust-tier-canonicalize/api.md` + ADR-009 MCP framing |
| Auth/security strategy drafted | ✅ V1 light | `docs/12-security/security-model.md` + `docs/12-security/mcp-security.md` |
| Deployment strategy drafted | ✅ V1 local | `docs/10-operations/deployment.md` |
| ADRs written for major decisions | ✅ | ADR-001..ADR-011 in `docs/11-decisions/`. **ADR-001 = `accepted`** (Kùzu, ratified 2026-05-21 via bake-off). **ADR-010 = `accepted`** (Prefect 3 — ratified R5 per A-059). |

**Gate 2 status: ✅ PASS.**

## 3. Feature Packet Gate (for first vertical slice)

| Item | Status | Source |
|---|---|---|
| `README.md` | ✅ | slice packet |
| `requirements.md` | ✅ | slice packet |
| `api.md` | ✅ | slice packet |
| `data.md` | ✅ | slice packet |
| `ui-flow.md` if UI | N/A | V1 has no UI (HITL = CLI + YAML; web UI is V2) |
| `state-machine.md` if stateful | ✅ | slice packet (4 state machines: ingestion, conflict resolution, alias resolution, HITL queue) |
| `test-plan.md` | ✅ | slice packet |
| `context.md` | ✅ | slice packet |
| `plan.md` | ✅ | slice packet |

**Gate 3 status: ✅ PASS.**

## 4. Test Gate

| Item | Status | Source |
|---|---|---|
| Unit tests identified | ✅ | slice `test-plan.md` § AC-1..AC-10 + `docs/09-testing/test-matrix.md` |
| Integration tests identified | ✅ | same |
| Contract tests identified | ✅ | same (MCP tool contract tests) |
| E2E/browser tests identified | ✅ (E2E only; no browser) | `docs/09-testing/browser-validation.md` documents V1's CLI substitute |
| Browser console/network checks defined | N/A V1 | (no UI in V1) |
| Test data/fixtures defined | ✅ | `docs/09-testing/test-data.md` |

**Gate 4 status: ✅ PASS.**

## 5. Environment Gate

| Item | Status | Source |
|---|---|---|
| All required env vars listed in `.env.example` | ✅ | `/.env.example` written |
| User knows which values to provide | ✅ | `.env.example` annotated per var |
| No real secrets committed | ✅ | `.env` in `.gitignore`; `.env.example` is template only |
| Missing optional integrations documented | ✅ | `.env.example` blocks optional sections (graph-DB options behind bake-off) |

**Gate 5 status: ✅ PASS.**

## 6. GraphRAG Verification Gate (`tools/graphrag/verification-checklist.md`)

**Closed 2026-05-21.** `verify.py` against the live `tools/graphrag/` index returned **OVERALL: PASS** (19 pass / 4 V1-deferred skips / 0 fail). Report at `.agent/reports/graphrag-verification-2026-05-21.md`. Live index: 249 files → 2090 nodes + 1936 edges (snapshot `ffb3b684d536d9e4`).

| Item | Status |
|---|---|
| Docs parsed into DocPage/DocSection nodes | ✅ PASS (169 DocPages, 1378 DocSections) |
| Code parsed into CodeFile/Function/Class | ✅ PASS (34 CodeFiles, 183 Functions, 33 Classes) |
| Tests parsed into TestFile/TestCase | ✅ PASS (18 TestFiles, 156 TestCases) |
| Feature packets indexed | ✅ PASS (2 Features, 54 Reqs, 10 ACs) |
| Frontmatter metadata indexed | ✅ PASS (11/11 ADRs with status + date) |
| Feature→Requirement edges | ✅ PASS (54) |
| Requirement→AcceptanceCriterion edges | ✅ PASS (7) |
| Feature→Docs edges | ✅ PASS (16) |
| Feature→Code edges | ⚠️ SKIP (FEATURE_IMPLEMENTED_BY → V1.x; needs import resolution) |
| Code→Tests edges | ✅ PASS (33 TEST_COVERS_REQUIREMENT) |
| UIFlow→E2E tests | ⚠️ SKIP (N/A V1) |
| API→Endpoint handlers | ⚠️ SKIP (N/A V1) |
| DocSection→CodeFile/Symbol edges | ✅ PASS (45) |
| feature context retrieval | ✅ PASS (15 reqs for V1 slice) |
| symbol lookup | ✅ PASS |
| related tests retrieval | ✅ PASS (15 tests for FR-1.1) |
| docs-for-code retrieval | ✅ PASS |
| code-for-doc retrieval | ✅ PASS |
| Stale-docs detection | ✅ PASS |
| AGENTS.md GraphRAG/MCP wording | ✅ PASS |
| Fallback if GraphRAG unavailable | ✅ PASS |
| Retrieval logs stored | ✅ PASS (`tools/graphrag/logs/mcp.jsonl`) |
| Token usage measured | ✅ PASS |

**Gate 6 status: ✅ PASS.**

## Summary

| Gate | Status |
|---|---|
| 1 PRD | ✅ PASS |
| 2 Architecture | ✅ PASS (ADR-001 + ADR-010 docs-pending, scoped) |
| 3 Feature Packet | ✅ PASS |
| 4 Test | ✅ PASS |
| 5 Environment | ✅ PASS |
| 6 GraphRAG Verification | ✅ PASS (2026-05-21) |

**All 6 bootstrap gates PASS. V1 product code is unblocked subject only to ADR-001 ratification via the bake-off.**

## What unblocks coding

(historical note — Gate 6 closed 2026-05-21.)

**Bake-off and ADR-001:**
- The bake-off (`docs/05-features/bake-off-graph-db/`) is queued. It does not block PRD / Architecture / Feature Packet / Test / Environment gates, but **does block V1 product implementation** (no graph-DB pick = no concrete `src/graph/<engine>_client.py`).
- Bake-off itself is also tooling-adjacent (it writes harness scripts under `tools/bake_off/`). Same Mahyar go-ahead question applies.

**Pending Q's that don't block gates but inform V1 implementation:**
- Q-016 budget / HITL hours
- Q-021 crawler MCP endpoint inventory (`is_url_ingested`, `get_topic_state`, `get_pending_verifications`?)
- Q-023 subreddit pick for V1 slice (default r/DentalSchool)
- Q-024 more official data? (recommendation: not blocking)
- Q-025 prior GPT-4o-mini extraction code/outputs (recommendation: not blocking)
- Q-026 credibility split (recommendation: two parallel rubrics — ADR-008 already adopts this)

## Recommended next step

**Mahyar's call**: do (a) → (b) → (c) below.

(a) Decide on the GraphRAG MCP server question I raised earlier:
- **Option (a)**: I proceed with `tools/graphrag/` implementation as tooling/gate-prep (allowed per CLAUDE.md's "implement or connect"); + scripts under `tools/bake_off/` for the bake-off.
- **Option (b)**: Keep me on docs-only. Draft a step-by-step build plan for `tools/graphrag/` as a doc artifact; you (or another Mahyar-blessed pass) implements when ready.

(b) Answer Q-023 (subreddit pick) so the bake-off sample is concrete.

(c) Answer Q-016 (budget ranges) so we can pin the auto-accept threshold ablation strategy + cost-regression gate.

After (a)/(b)/(c) we're either coding (a-option-a) or further doc-finalized (a-option-b).
