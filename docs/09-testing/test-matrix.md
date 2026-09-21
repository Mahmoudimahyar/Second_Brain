# Test Matrix

> Per-feature × per-requirement × per-test-type coverage map. Filled out as features land. V1 slice rows are populated from `docs/05-features/01-slice-trust-tier-canonicalize/test-plan.md`.

## Engine-wide invariants (always-on, asserted by fixtures)

| Invariant | Unit | Integration | Property | Security | Lint |
|---|:-:|:-:|:-:|:-:|:-:|
| L1 nodes immutable (FR-4.3) | | ✓ | | ✓ | |
| Vendor-SDK-import ban (A-046) | | | | ✓ | ✓ |
| Prompt-cache `ttl: 3600` (A-036) | ✓ | ✓ | | ✓ | ✓ |
| Audit log append-only (NFR-6) | ✓ | ✓ | | ✓ | |
| Bitemporal 4-tuple on every edge (A-027) | ✓ | ✓ | ✓ | | |
| Citation traceability ≥ 99% (FR-8.3) | | ✓ | ✓ | | |
| No circular imports (module boundaries) | | | | | ✓ |
| Public-API stability (boundary tests) | | | | | ✓ |

## V1 slice (01-slice-trust-tier-canonicalize)

| Feature | Requirement | Unit | Integration | Contract (MCP) | Property | E2E | Eval | Cost | Perf | Security | Notes |
|---|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|---|
| Ingestion plane | FR-1.1 `register_dump` idempotency | ✓ | ✓ | ✓ | ✓ | | | | | | Maps to AC-1 |
| L1 Excel adapter | FR-1.2 ADEA Report 2 → SQLite | ✓ | ✓ | | | | | | | | AC-2 |
| L5 Reddit adapter | FR-1.3 thread reconstruction | ✓ | ✓ | | ✓ | ✓ | | | | | |
| L5 SDN adapter | FR-1.4 Pre-Dental subset | ✓ | ✓ | | | | | | | | SD-003 |
| Author namespace | FR-1.5 reddit/sdn collision-free | ✓ | | | ✓ | | | | | | A-043 |
| Stage 1 filter | FR-2.1 GLiNER2 zero-shot | ✓ | | | | | ✓ | | ✓ | | Recall ≥ 0.95 on positive set |
| Stage 2 ER | FR-2.2 BGE+DITTO | ✓ | ✓ | | | | ✓ | | | | AC-3 (F1 ≥ 0.92) |
| Stage 3 API | FR-2.3 Haiku 4.5 + BAML | ✓ | ✓ | | | ✓ | ✓ | ✓ | | ✓ | AC-8, TI-1 |
| Extraction cache | FR-2.4 content-addressable | ✓ | ✓ | | ✓ | | | ✓ | | | AC-8 |
| TTL pinning | FR-2.5 ttl: 3600 enforced | ✓ | ✓ | | | | | | | ✓ | TI-1, A-036 |
| ER thresholds | FR-3.1-FR-3.4 | ✓ | ✓ | | | | ✓ | | | | SD-005 |
| HITL routing | FR-3.5, FR-10 | ✓ | ✓ | | ✓ | | | | | | AC-4 |
| Trust-tier schema | FR-4.1-FR-4.2 | ✓ | ✓ | | ✓ | | | | | | A-028 |
| L1 immutability | FR-4.3 reject UPDATE | ✓ | ✓ | | | | | | | ✓ | AC-7 |
| Bitemporal edges | FR-5.1-FR-5.3 | ✓ | ✓ | | ✓ | | | | | | AC-6 |
| Conflict resolver | FR-6.1-FR-6.6 6-step order | ✓ | ✓ | | | ✓ | | | | | AC-7 + |
| User-credibility (Reddit) | FR-7.1 | ✓ | ✓ | | | | | | | | A-033 |
| User-credibility (SDN) | FR-7.2 | ✓ | ✓ | | | | | | | | A-033, A-043 |
| Outlier preservation | FR-7.5 Status=Anomaly | ✓ | ✓ | | | | | | | | A-032 |
| Retrieval MCP `query_graph` | FR-8.1 | ✓ | ✓ | ✓ | ✓ | ✓ | | | ✓ | | AC-5, NFR-1 |
| Retrieval MCP `get_canonical_entity` | FR-8.2 | ✓ | ✓ | ✓ | | | | | ✓ | | NFR-1 |
| Citations | FR-8.3 ≥ 99% | | ✓ | | ✓ | | | | | | AC-5 |
| Outbound MCP `register_dump`, `get_gaps`, `get_research_needs` | FR-9 | ✓ | ✓ | ✓ | | | | | | | |
| HITL CLI `pull`/`commit` | FR-10.1-FR-10.3 | ✓ | ✓ | | ✓ | | | | | | AC-4 |
| Audit log (extraction) | FR-11.1 | ✓ | ✓ | | | | | | | ✓ | TTL field |
| Audit log (retrieval) | FR-11.2 | ✓ | ✓ | | | | | | | | |
| Audit log (HITL) | FR-11.3 | ✓ | ✓ | | | | | | | | |
| Latency `query_graph` | NFR-1 p95 < 250 ms | | | | | | | | ✓ | | |
| Latency `get_canonical_entity` | NFR-1 p95 < 50 ms | | | | | | | | ✓ | | |
| Cost | NFR-2 V1 slice < $25 | | | | | | | ✓ | | | AC-8 |
| Cache hit | NFR-3 warm ≥ 80% | | ✓ | | | | | ✓ | | | AC-8 |
| Atomic ingestion | NFR-5 rollback on failure | ✓ | ✓ | | | | | | | | |
| Audit coverage | NFR-6 100% call sites | ✓ | ✓ | | | | | | | ✓ | TI-3 |
| Reproducibility | NFR-8 deterministic outputs | ✓ | ✓ | | ✓ | | | | | | AC-8 |
| Coverage | NFR-9 ≥ 80% | | | | | | | | | | CI gate |

## Future features (placeholders)

| Feature | Slice | Notes |
|---|---|---|
| L2 unstructured-truth adapter | V1.x | Adds new row block when implemented |
| Signed-graph community detection retrieval | V1.x | Today: offline only |
| Cross-vendor LLM-as-judge (3-vendor in production) | V1.x | Activates per A-052 once accounts provisioned |
| User-credibility logistic regression | V1.1 | Replaces hand-weighted rubric |
| Distillation pipeline | V2 | Cost-reduction lever per R-008 |
| Web HITL UI | V2 | Adds browser-validation rows |

## How to add a row

When a new feature lands, add one row per (feature, requirement) pair. Mark with `✓` the test types that cover that requirement. Tests should reference the requirement ID in their docstring so the matrix is searchable.

## How to verify the matrix

A `tools/check_test_matrix.py` script (TBD at implementation) cross-references this file with actual test definitions; flags requirements that have no test coverage. Run during PR review.
