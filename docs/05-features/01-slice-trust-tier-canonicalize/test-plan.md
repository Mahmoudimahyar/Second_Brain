# Test Plan

> Maps every acceptance criterion from `requirements.md` to concrete test cases. TDD discipline per AGENTS.md: every test is failing-first; smallest correct code makes it pass; targeted before broader.

## Test types in scope for this slice

| Type | Framework | Used for |
|---|---|---|
| Unit | `pytest` | Module-level Python APIs (ingestion adapters, ER, conflict resolver, bitemporal writer, audit log, model gateway) |
| Integration | `pytest` + temp graph DB | Multi-module flows (e.g., dump → cascade → graph write); per-state-machine integration |
| Contract (MCP) | `pytest` + `mcp` SDK in test mode | MCP tool signatures + schemas (`query_graph`, `get_canonical_entity`, `register_dump`, `get_gaps`, `get_research_needs`) |
| Property-based | `hypothesis` | Bitemporal correctness, idempotent re-ingest, alias-resolution invariants |
| End-to-end | `pytest` + recorded HTTP responses | Full slice on a frozen 100-thread r/DentalSchool subsample |
| Eval (gold-set) | Custom `evals/` harness | F1 on 200-mention alias gold, citation traceability, sentiment accuracy |
| Cost regression | `pytest` + Langfuse fixture | Per-sweep cost stays under target |
| Lint / static | `ruff`, `mypy`, custom `lint_ttl_pinning.py` | `ttl: 3600` enforcement, vendor-SDK import ban, schema-pinning |

No browser tests in this slice — HITL UX is CLI + flat-file only (web UI is V2 per `out-of-scope.md`).

## Acceptance-criteria → test mapping (every AC from `requirements.md`)

### AC-1 — `register_dump` idempotency + receipt shape (FR-1.1)
- **Unit**: `test_ingestion.py::test_register_dump_returns_receipt_with_content_hashes`
- **Unit**: `test_ingestion.py::test_register_dump_idempotent_on_identical_content_hash` — second call returns same `dump_id`.
- **Property**: `test_ingestion_props.py::test_dump_receipt_round_trip` (hypothesis) — for any valid manifest, the receipt round-trips through serialize/deserialize.

### AC-2 — L1 ingest: ≥56 schools, ≥500 metrics, all properties (FR-1.2)
- **Integration**: `test_l1_excel_adapter.py::test_load_adea_report_2_2024_25` — load real Excel, assert row counts + property completeness.
- **Unit**: `test_l1_excel_adapter.py::test_t_valid_from_to_derived_from_cycle_year`.
- **Integration**: `test_l1_excel_adapter.py::test_canonical_school_names_extracted_unique` — assert no duplicate canonical IDs.

### AC-3 — Alias resolution F1 ≥ 0.92 (FR-2 + FR-3, NFR-4)
- **Eval**: `evals/alias_resolution.py` runs the BGE+DITTO pipeline against the 200-mention labeled gold set. Asserts F1 ≥ 0.92. Failures dump the confusion matrix for inspection.
- **Unit**: `test_er.py::test_threshold_routing` — auto-accept ≥ 0.90 / HITL 0.75-0.90 / reject < 0.75 routed correctly.
- **Unit**: `test_er.py::test_canonical_index_built_from_l1_aliases`.
- **Regression**: re-run the eval at every cascade-or-prompt change.

### AC-4 — HITL queue routing (FR-3 + FR-10)
- **Integration**: `test_hitl_routing.py::test_borderline_match_lands_in_queue` — feed a mention with predicted similarity 0.82; assert it lands as `pending` in `hitl_queue` table + matches `HITLItem` schema.
- **Unit**: `test_hitl_cli.py::test_pull_writes_yaml_file`.
- **Unit**: `test_hitl_cli.py::test_commit_writes_to_graph_and_audit_log`.
- **Property**: `test_hitl_props.py::test_state_machine_legal_transitions` — every legal transition succeeds; every forbidden transition raises `INVALID_TRANSITION`.

### AC-5 — Citation traceability ≥ 99% (FR-8.3)
- **Integration**: `test_retrieval_citations.py::test_every_result_has_references` — run a representative `query_graph(...)` call and assert every result has non-empty `references`.
- **Property**: `test_retrieval_citations_props.py::test_no_orphan_results` (hypothesis-generated queries; assert `≥99%` of returned results trace to source `dump_id` + `post_id`).

### AC-6 — Bitemporal correctness (FR-5)
- **Integration**: `test_bitemporal.py::test_as_of_past_date_returns_old_snapshot` — ingest a dump, mutate, re-ingest; query with `as_of=<between>` returns first snapshot; with `as_of=<after>` returns second.
- **Property**: `test_bitemporal_props.py::test_t_ingest_intervals_disjoint` — for any edge, the `t_ingest` intervals across superseding versions are disjoint.
- **Property**: `test_bitemporal_props.py::test_supersede_atomicity` — re-ingest sets prior `t_ingest_to` and new `t_ingest_from` to the same instant.

### AC-7 — L1 invalidation (FR-4.3 + FR-6.1)
- **Integration**: `test_conflict_l1_clash.py::test_forum_claim_invalidated_when_conflicts_with_l1` — synthesize a forum claim contradicting an L1 metric; assert forum claim's `status = invalidated_by_official_data`, L1 metric unchanged.
- **Unit**: `test_conflict_resolver.py::test_l1_node_update_rejected` — any direct `UPDATE` against an L1 node raises `L1_IMMUTABLE_REJECT`.

### AC-8 — Cost cascade observability (FR-2.4, FR-11.1, NFR-2, NFR-3)
- **Integration**: `test_extraction_cache.py::test_cold_then_warm_sweep` — first sweep records cost > 0; second sweep with identical inputs records ≥80% cache hits + ~0 new API spend.
- **Integration**: `test_audit_log.py::test_every_anthropic_call_has_ttl_pinned_3600`.
- **Lint**: `lint_ttl_pinning.py` fails on any call site that omits `ttl: 3600`.
- **Cost regression**: `tests/cost/test_v1_slice_sweep.py::test_sweep_under_budget` runs a recorded fixture of the V1 slice extraction; asserts total cost < $25.

### AC-9 — GraphRAG verification (gate #6)
- **External**: `tools/graphrag/verification-checklist.md` is run as a separate gate before this slice's product engine starts. Re-confirmed at slice completion that the repo MCP server is still running + verification still passes.

### AC-10 — Verification Before Completion report
- **Process step**: `/.agent/reports/v1-slice-01.md` is written + reviewed before the slice is marked done.

## Non-functional tests

### NFR-1 — Retrieval latency
- **Performance**: `tests/perf/test_query_graph_p95.py` — runs 100 representative queries from the test corpus, asserts p95 < 250 ms; `get_canonical_entity` p95 < 50 ms.
- **Regression**: re-run on every graph-DB schema change.

### NFR-2 — Cost
- Covered by AC-8.

### NFR-3 — Cache efficiency
- Covered by AC-8.

### NFR-4 — Accuracy
- Covered by AC-3 + AC-5.

### NFR-5 — Reliability (atomic ingestion)
- **Integration**: `test_ingestion_rollback.py::test_partial_dump_rolls_back` — inject a Stage-3 failure mid-ingest; assert no partial graph writes commit; `dump.status = failed`.

### NFR-6 — Observability
- **Lint**: 100% audit-log coverage on API + retrieval + HITL call sites enforced via a `pytest` collection hook that diffs `audit_log` rows against call counts.

### NFR-7 — Security
- V1 internal-only. No PII anonymization tested (V2).

### NFR-8 — Reproducibility
- Covered by AC-8 (cache hit).

### NFR-9 — Test coverage
- **CI gate**: `pytest --cov=src --cov-fail-under=80`.

## Test data + fixtures

### Synthetic fixtures
- `tests/fixtures/synthetic_threads.jsonl` — 100 hand-crafted thread shapes covering common alias variations, conflict patterns, edge cases. Used everywhere unit / integration tests need stable inputs.
- `tests/fixtures/synthetic_l1.sqlite` — frozen mini-ADEA with 5 schools + 50 metrics + 10 programs.
- `tests/fixtures/synthetic_hitl_items.jsonl` — borderline / conflict / new-type-proposal exemplars.

### Real-data fixtures (sampled from `External Data\`)
- `tests/fixtures/r_dentalschool_100.jsonl` — 100-thread frozen subsample of r/DentalSchool (deterministic seed). Used in E2E tests.
- `tests/fixtures/sdn_predental_100.jsonl` — 100-thread frozen subsample from SDN Pre-Dental category.
- `tests/fixtures/adea_r2_2024_25_mini.xlsx` — synthetic minimal Excel mimicking ADEA Report 2 schema (no real data; used for L1 adapter unit tests).

### Recorded vendor responses
- `tests/fixtures/vlcr/` — VCR-style recordings of Anthropic + OpenAI + Gemini responses for deterministic integration tests. Re-record only when prompts or schemas change.

### Gold sets
- `evals/gold/alias_resolution_v1_200.jsonl` — 200 hand-labeled school/program mentions (variants + Canadian decoys + undergrad-college decoys + misspellings). Used to assert AC-3 F1.
- `evals/gold/sentiment_v1_100.jsonl` — 100 hand-labeled sentiment exemplars from r/DentalSchool. Used to gate Stage-3 sentiment regression.
- `evals/gold/interview_q_v1_50.jsonl` — 50 hand-labeled reported-interview-question exemplars.

Building the gold sets is part of Phase 10 of `plan.md`.

## Test matrix overview

| Phase (per `plan.md`) | Unit | Integration | Contract | Property | E2E | Eval | Lint |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| 1 — L1 ingestion | ✓ | ✓ | | ✓ | | | |
| 2 — L5 ingestion | ✓ | ✓ | | ✓ | | | |
| 3 — Stage 1 filter | ✓ | | | | | ✓ | |
| 4 — Stage 2 ER | ✓ | ✓ | | | | ✓ | |
| 5 — Stage 3 API | ✓ | ✓ | | | ✓ | ✓ | ✓ |
| 6 — Conflict + bitemporal | ✓ | ✓ | | ✓ | | | |
| 7 — Retrieval MCP | ✓ | ✓ | ✓ | ✓ | ✓ | | |
| 8 — HITL CLI | ✓ | ✓ | | ✓ | | | |
| 9 — Audit + lint | ✓ | ✓ | | | | | ✓ |
| 10 — Acceptance + gold | | | | | ✓ | ✓ | |
| 11 — Verification report | (process step) | | | | | | |

## Test invariants (always-on across the slice)

Across **every** test that touches the gateway:
- **TI-1**: every Anthropic call site uses `ttl: 3600` (asserted by `lint_ttl_pinning.py` + a `pytest` fixture that monkeypatches the gateway and fails if any call omits the TTL).
- **TI-2**: no vendor-specific SDK import in product code (`ruff` rule against `import anthropic`, `import openai`, `import google.genai` outside `src/gateway/` and `tests/`).
- **TI-3**: every `audit_log` row written by tests has `kind`, `ts`, `fields_json` set.
- **TI-4**: every retrieval result in tests has non-empty `references`.

Across **every** test that touches the graph:
- **TI-5**: every edge has bitemporal 4-tuple set (`t_valid_from`, `t_valid_to`, `t_ingest_from`, `t_ingest_to`).
- **TI-6**: L1 nodes have `rank=preferred`, `source_tier=L1`, never mutated.

## CI / verification gates

Before merging any slice work:
1. `pytest --cov=src --cov-fail-under=80` passes.
2. `ruff check . && mypy src/` clean.
3. `python tools/lint_ttl_pinning.py` clean.
4. AC-3 gold-set F1 ≥ 0.92.
5. AC-5 citation traceability ≥ 99%.
6. AC-8 cost regression < $25.
7. NFR-1 latency regression p95 < 250 ms / 50 ms.

Failure of any of the above blocks merge per AGENTS.md repair budget (5 cycles unit/integration, 3 cycles E2E, 2 cycles full).

## Open test dependencies

- Gold-set construction (200 + 100 + 50 examples) is a manual labeling task; Mahyar's time required. Estimated 4-6 hours total for V1.
- Vendor API keys (Anthropic + OpenAI + Google) must be provisioned for the cross-vendor LLM-as-judge tests (FR-6.6).
- The graph-DB bake-off winner (ADR-001) determines which integration tests need a temp instance (LadybugDB embedded = simple; Graphiti+Neo4j = needs Docker; Postgres+AGE = needs Postgres test container).
