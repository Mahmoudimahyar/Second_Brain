# GraphRAG Verification Harness

> Maps each item in `tools/graphrag/verification-checklist.md` to a concrete automated check. Passing every check = gate #6 closed.

## How the harness runs

A single CLI: `python tools/graphrag/verify.py`.

Steps:
1. Ensure index is fresh: `python tools/graphrag/index.py --incremental`.
2. Spin up MCP server in test mode (in-process, not stdio).
3. Run every check below.
4. Emit a verification report under `/.agent/reports/graphrag-verification-<YYYY-MM-DD>.md`.
5. Exit code 0 on all-pass; non-zero on any fail.

## Per-checklist-item harness

### Ingestion

#### ✅ docs are parsed into DocPage/DocSection nodes
- **Check**: `tools/graphrag/parsers/markdown.py` test fixtures + integration on `docs/01-core/product-vision.md` produces N `DocPage` (1) + ≥ M `DocSection` (≥ 5).
- **Test**: `tests/graphrag/test_markdown_parser.py::test_full_repo_docs_parsed`.
- **Threshold**: 100% of `.md` files under `docs/` produce at least 1 `DocPage`.

#### ✅ code is parsed into CodeFile/Function/Class nodes
- **Check**: AST parser on `src/`, `tests/`, `tools/` produces `CodeFile` + child `Function` + `Class` for at least one canonical file (when code lands).
- **Test**: `tests/graphrag/test_python_parser.py::test_extract_functions_and_classes`.
- **V1 caveat**: Until V1 product code is implemented, only `tools/graphrag/` own Python files exist. The check still passes against those.

#### ✅ tests are parsed into TestFile/TestCase nodes
- **Check**: `tools/graphrag/parsers/test_file.py` extracts every `test_*` function from `tests/` directories + reads docstring tags (AC-/FR-/NFR-).
- **Test**: `tests/graphrag/test_test_parser.py::test_extract_test_cases_with_tags`.

#### ✅ feature packets are indexed
- **Check**: `docs/05-features/01-slice-trust-tier-canonicalize/` produces 1 `Feature` + ≥ 11 `DocPage` + ≥ 9 `Requirement` (FR-1..FR-11) + ≥ 9 `AcceptanceCriterion`.
- **Test**: `tests/graphrag/test_feature_packet_parser.py::test_v1_slice_extraction`.

#### ✅ frontmatter metadata is indexed
- **Check**: ADRs have frontmatter-ish header (`Status:`, `Date:`); parser extracts to `ADR.status` + `ADR.date`.
- **Test**: `tests/graphrag/test_adr_parser.py::test_status_and_date_extracted`.

### Edges

#### ✅ Feature → Requirement
- **Check**: `FEATURE_HAS_REQUIREMENT` edges exist from `feature:01-slice-trust-tier-canonicalize` to all 9+ FR/NFR nodes.
- **Test**: `tests/graphrag/test_edges.py::test_feature_requirement_links`.

#### ✅ Requirement → AcceptanceCriterion
- **Check**: `REQUIREMENT_HAS_ACCEPTANCE_CRITERION` edges from the slice's FR-/NFR nodes to all AC-1..AC-10 per `test-plan.md` mapping.
- **Test**: `tests/graphrag/test_edges.py::test_requirement_ac_links`.

#### ✅ Feature → Docs
- **Check**: `FEATURE_DOCUMENTED_BY` edges from the V1 slice Feature to every `.md` under `docs/05-features/01-slice-trust-tier-canonicalize/`.
- **Test**: `tests/graphrag/test_edges.py::test_feature_documented_by`.

#### ✅ Feature → Code
- **Check**: `FEATURE_IMPLEMENTED_BY` edges from the V1 slice to expected `src/<area>/` directories named in `plan.md`.
- **Test**: `tests/graphrag/test_edges.py::test_feature_implemented_by`. (V1 caveat: code path mostly absent until V1 product implementation lands; checks "plan.md mentions src/<x>/" rather than "file exists" pre-implementation.)

#### ✅ Code → Tests
- **Check**: `TEST_COVERS_FUNCTION` from `tests/graphrag/test_markdown_parser.py::test_X` to the function under test.
- **Test**: `tests/graphrag/test_edges.py::test_test_covers_function`.

#### ✅ UIFlow → E2E tests
- **Check**: N/A in V1 (no UI). Test asserts that no `UIFlow` nodes exist (preserved for V2).
- **Test**: `tests/graphrag/test_edges.py::test_no_uiflows_in_v1`.

#### ✅ API → Endpoint handlers
- **Check**: N/A V1 (no HTTP endpoints).
- **Test**: `tests/graphrag/test_edges.py::test_no_endpoints_in_v1`.

#### ✅ DocSection → CodeFile/Symbol
- **Check**: `DOC_SECTION_REFERENCES_CODE` populated wherever a DocSection contains a backtick-wrapped reference to a known code symbol or file path.
- **Test**: `tests/graphrag/test_edges.py::test_doc_section_references_code` — uses `docs/04-architecture/system-overview.md` (which references `src/gateway/api.py` etc.).

### Retrieval

#### ✅ feature context retrieval works
- **Check**: `explain_feature("01-slice-trust-tier-canonicalize")` returns ≥ 9 requirements + ≥ 1 README + ≥ 5 expected files + ≥ 3 ADRs linked + ≥ 1 known issue.
- **Test**: `tests/graphrag/retrieval/test_explain_feature.py::test_v1_slice_explanation_completeness`.

#### ✅ symbol lookup works
- **Check**: `find_symbol("LLMClient")` returns the class node (when V1 product code lands; pre-implementation: returns 0 results — test asserts behavior correct).
- **Test**: `tests/graphrag/retrieval/test_find_symbol.py::test_find_known_class`.

#### ✅ related tests retrieval works
- **Check**: `get_related_tests("FR-2.3")` (Stage-3 API requirement) returns ≥ 1 test once V1 product implementation lands.
- **Test**: `tests/graphrag/retrieval/test_get_related_tests.py::test_via_requirement`.

#### ✅ docs-for-code retrieval works
- **Check**: `get_docs_for_code("src/gateway/api.py")` returns the slice's `api.md` + `tech-stack.md` Model-gateway section + ADR-011.
- **Test**: `tests/graphrag/retrieval/test_get_docs_for_code.py::test_gateway_docs`.

#### ✅ code-for-doc retrieval works
- **Check**: `get_code_for_doc("docs/04-architecture/system-overview.md")` returns the ≥ 5 code paths referenced in that doc.
- **Test**: `tests/graphrag/retrieval/test_get_code_for_doc.py::test_system_overview_refs`.

#### ✅ stale docs detection exists or is planned
- **Check**: `find_stale_docs(["src/gateway/api.py"])` returns a list of DocSection candidates older than the code.
- **Test**: `tests/graphrag/retrieval/test_find_stale_docs.py::test_returns_candidates_or_empty_for_fresh_repo`.
- **V1 caveat**: Without V1 code, this is mostly a smoke test (no real stale docs to find yet).

### Agent usage

#### ✅ AGENTS.md tells agents to use GraphRAG/MCP before broad reads
- **Check**: Plain string search of `AGENTS.md` for the phrase "GraphRAG" or "MCP context" in the "Context discipline" section.
- **Test**: `tests/graphrag/test_agents_md_contract.py::test_agents_references_graphrag`.

#### ✅ fallback behavior exists if GraphRAG is unavailable
- **Check**: The MCP server fails gracefully when its index is missing; the coding agent falls back to Glob/Grep/Read.
- **Test**: `tests/graphrag/test_mcp_contract.py::test_missing_index_returns_clear_error` — start MCP with no index; assert all tools return `INDEX_MISSING` rather than crashing.

#### ✅ retrieval logs are stored
- **Check**: After running each tool once, `tools/graphrag/logs/mcp.jsonl` contains an entry per call with required fields.
- **Test**: `tests/graphrag/test_mcp_contract.py::test_every_call_logged`.

#### ✅ token usage is measured
- **Check**: Each MCP tool response includes a `total_tokens_returned` field (sum of `len(snippet)` approximated as tokens via tiktoken / heuristic).
- **Test**: `tests/graphrag/test_mcp_contract.py::test_token_count_in_response`.
- **Rationale**: lets the coding agent budget context spend.

## Verification report format

Output of `python tools/graphrag/verify.py` → `/.agent/reports/graphrag-verification-<YYYY-MM-DD>.md`:

```markdown
# GraphRAG Verification — YYYY-MM-DD

## Result

OVERALL: PASS | FAIL

## Snapshot

- snapshot_id: <hash>
- commit_sha: <hash>
- index_built_at: <timestamp>

## Per-check results

| Check | Status | Notes |
|---|---|---|
| docs parsed into DocPage/DocSection | ✅ PASS | 47 DocPages, 312 DocSections |
| code parsed | ✅ PASS | ... |
| tests parsed | ✅ PASS | ... |
| ... (one row per checklist item) ... |
| **All checks** | **✅ PASS** | gate #6 closed |

## Failures (if any)

(detailed traceback per failed check)

## Next action

(if PASS) → V1 product implementation can begin per `docs/05-features/01-slice-trust-tier-canonicalize/plan.md`.
(if FAIL) → triage failed checks; fix; rerun.
```

## When to rerun

- After every `tools/graphrag/index.py --full` run.
- After every commit that touches `tools/graphrag/` source code.
- As part of CI (when CI exists; V1 manual).
- Before declaring V1 product implementation "ready to start."

## V1 caveats

- Several "code"-side checks (`find_symbol`, `get_related_tests` via Function) depend on V1 product code existing. Pre-implementation, these checks pass with "0 results" assertions (verifying the *plumbing* works), not "N results" assertions.
- The harness handles this via a `--strict` flag: `--strict` requires V1 code to be present (post-V1-implementation reverification); default (no flag) accepts the pre-implementation state.

## Done means done

Gate #6 is closed when:
1. `python tools/graphrag/verify.py` returns exit 0.
2. The verification report is written + linked from `docs/00-bootstrap/bootstrap-status.md`.
3. `docs/00-bootstrap/gate-check.md` Gate 6 status updates to `✅ PASS`.
