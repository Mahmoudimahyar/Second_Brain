# Slice-Local Decisions

> Slice-local supplements to the global ADRs. Each row is a decision that this slice introduces or refines beyond the architecture defaults. ADR-level decisions live in `docs/11-decisions/`.

| ID | Decision | Rationale | Reference |
|---|---|---|---|
| SD-001 | **L5 source for V1 slice = r/DentalSchool** | Smallest on-topic subreddit (274K records); cleanest signal for dental-school admissions; lowest cost to fully sweep within V1 budget. Alternative r/predental (434K) and SDN Pre-Dental subset (~12K threads filtered) remain available for V1.x. | A-045, Q-023 |
| SD-002 | **L1 source for V1 slice = ADEA Report 2, 5 most-recent files (2020-21 → 2024-25)** | Report 2 (Tuition / Admission / Attrition) carries the metrics most often referenced in L5 (tuition, DAT, GPA, acceptance rates). 5 years is enough temporal coverage to demonstrate HALO decay; recent years to keep the slice's L1 ↔ L5 overlap meaningful. | A-044 |
| SD-003 | **L5 cross-validation sample for V1 = 1,000 SDN "Pre-Dental" category threads** | Exercises the SDN-flavor metadata path (no upvote signal — see A-043). Without this, the ER + ingestion code might accidentally hard-code Reddit-only assumptions. Sample size kept small to keep slice fast. | A-043 |
| SD-004 | **Author namespacing = `reddit:<sub>:<author>` and `sdn:<author>`** | Reddit author handles do not span subreddits in the data inventory; SDN handles do not span Reddit. Cross-source identity reconciliation is V2. | A-043 |
| SD-005 | **ER auto-accept threshold = 0.90; HITL 0.75-0.90; reject < 0.75 (initial)** | Per FR-3.1..FR-3.4. Pin via first-500-HITL ablation in Phase 4. Initial thresholds are placeholders; updated post-ablation. | FR-3, GAP-028 |
| SD-006 | **V1 slice uses Stage-3 model = Anthropic Haiku 4.5 only** | Per-task matrix says Haiku is primary. V1 slice does NOT exercise the Gemini Flash-Lite or GPT-4o-mini fallback paths in production; switch criteria are tested in unit tests against recorded responses, not against live alternates. Activate alternates if/when AC-3 or AC-8 fails. | A-050, ADR-003 addendum |
| SD-007 | **LLM-as-judge — NOT used in V1 slice** | Same-tier same-year tie-breaks need 3-vendor accounts to be live (A-052). V1 slice routes irreducible ambiguity straight to HITL. LLM-as-judge becomes active in V1.x once all 3 vendor accounts are provisioned. | A-031, A-052 |
| SD-008 | **No signed-graph community detection retrieval primitive in V1 slice** | Clustering runs offline (nightly) and writes `cluster_id` properties to the graph. `query_graph` does NOT yet rank by cluster — clusters are surfaced only via `include_anomalies` flag on opinion-layer queries. Full signed-graph retrieval primitive is V1.x. | system-overview.md §4, requirements.md "Out of scope" |
| SD-009 | **HITL UX = CLI + flat YAML files (no web UI)** | Web UI is V2 per `out-of-scope.md`. CLI + YAML satisfies all V1 acceptance criteria (AC-4); reviewer overhead is acceptable for V1 internal use. | A-021, Q-015 |
| SD-010 | **HALO half-life table for V1 slice** is V1 hand-set, populated in `src/conflict/halo_table.py` | Per A-019. Initial values: tuition 1y, avg_DAT 2y, avg_GPA 2y, interview_format 3y, interview_question_reported 3y, program_requirement 2y, founding_year ∞, opinion_sentiment 6mo, applicant_anecdote 2y, policy_advice 1y. Update procedure: HITL escalation when retrieval ranking surfaces clearly-stale results. | A-019 |
| SD-011 | **User-credibility rubric (V1) — 10 features Reddit / 7 features SDN, hand-weighted** | Per A-033. The two parallel rubrics avoid contaminating Reddit-scored claims with SDN-flavored aggregation and vice versa. V1.1 upgrades to logistic regression. | A-033, A-043 |
| SD-012 | **Outlier preservation — `Status: Anomaly` always; `prescient_correct` recorded but not yet boosted in ranking** | Per A-032. Anomalies are queryable via `include_anomalies=True`. The `prescient_correct` retroactive credit becomes a rubric weight in V1.1 once we have at least a few months of L1/L2 confirmations to calibrate against. | A-032 |
| SD-013 | **Conflict-resolution web-verification trigger emits `research_need` records but does NOT call any crawler** | The crawler is a separate system (A-021). V1 slice writes `research_need` rows; the crawler reads via `get_research_needs()`. No back-channel auto-fetch from V1. | A-021 |
| SD-014 | **Embedding model frozen at BGE-small (`BAAI/bge-small-en-v1.5`) for V1 slice** | Per ADR-003 / tech-stack.md. Multilingual / Voyage-3-large upgrades deferred unless recall fails. | A-029 |
| SD-015 | **MCP transport = stdio only** | V1 internal use; single workstation. Per ADR-009. Streaming HTTP transport considered V2. | A-023 |
| SD-016 | **Test gold-set labeling is Mahyar's work, not Claude's** | Labels are domain truth; Claude cannot decide what counts as a valid match for borderline cases ("Penn Dental" → "University of Pennsylvania School of Dental Medicine" — confident; "P. Dental" → which Penn? — needs Mahyar). Labeling effort: ~4-6 hours total across the 3 gold sets. | test-plan.md "Open dependencies" |
| SD-017 | **Failed dump rollback uses Python transactional context manager + temp staging table** | Atomic write semantics from FR-1.1 / NFR-5. Choice deferred to Phase 1 of plan.md implementation if graph DB has native multi-statement transaction support; else stage-then-swap. | NFR-5 |
| SD-018 | **Slice does not write its own ADRs**; it extends ADR-001..ADR-011 with the SD-* rows above | ADRs are architectural; SDs are slice-local refinements. If an SD here graduates to a global architectural rule, promote it to an ADR via ADR-template. | — |

## Decisions deferred from this slice

- Which orchestrator (Prefect / Dagster / plain Python) — addressed at V1 implementation start; depends on whether sweeps are recurring or one-off. ADR-010 slot reserved.
- HITL web UI design — V2.
- Cross-vendor LLM-as-judge calibration set — V2.
- Crawler integration test harness — depends on a runnable crawler being available.
- Signed-graph community detection as a retrieval primitive — V1.x once nightly clustering pipeline stabilizes.

## How to extend this file

Add a new SD-* row when:
- A V1-implementation choice deviates from the architecture default in `system-overview.md` or `tech-stack.md`.
- A threshold / parameter is pinned for this slice (e.g., similarity thresholds, HALO half-lives).
- A V2 deferral is encoded for clarity.

Do NOT add an SD-* row for choices that belong in an ADR (architectural, repo-wide impact); promote those to `docs/11-decisions/`.
