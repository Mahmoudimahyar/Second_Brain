---
adr: 015
title: Cross-graph entity mapping — auto-suggest + HITL approval, reuses V1 alias-resolution stack
status: accepted
date: 2026-05-24
deciders: Mahyar, Claude
supersedes:
superseded_by:
revision_history:
  - 2026-05-24 — proposed.
  - 2026-05-25 — accepted. V1.5a shipped `CrossGraphLinker` reusing the V1 alias-resolution stack; 100-pair gold set scored F1 0.9505 (gate 0.92). `SAME_AS` edge type, HITL routing for 0.75–0.90 confidence, multi-way cluster transitive-closure-at-read-time all live. No drift.
---

# ADR-015 — Cross-graph entity mapping

## Context

V1's entity-resolution layer (FR-3) snaps L5 mentions to L1 canonical entities **within one ingest's universe**. When the user adds an external DB connector via V1.5a, the connector materializes a new universe of entities — its own `School`, `Program`, etc. nodes. These must link to the existing graph: the same NYU that ADEA L1 names "New York University College of Dentistry" might be in the user's DB as "NYU Dental" with `id = 27`, and Reddit threads talk about it as "NYU", "NYU Dental", "the dental school at NYU."

We need a cross-graph mapping mechanism that:
1. Doesn't degrade V1's existing F1 ≥ 0.92 alias resolution.
2. Honors the trust-tier ordering — an L2 DB's "NYU Dental" linking to an L1 ADEA entity must not overwrite the L1 entity.
3. Surfaces low-confidence matches for HITL approval, not silent merging.
4. Is bidirectional in semantics (`SAME_AS` edges).

## Decision

**Reuse the V1 alias-resolution pipeline (BGE-small HNSW blocking + DITTO/DistilBERT reranker) in a new cross-source mode. Add `SAME_AS` as a bitemporal edge type. Route low-confidence matches to a new `cross_graph_link` HITL item type. Use thresholds identical to V1 alias resolution: auto-accept ≥ 0.90, HITL 0.75–0.90, reject < 0.75.**

Specifically:

1. **`src/er/cross_graph.py`** introduces `CrossGraphLinker.link(new_node, existing_universe) -> list[CrossGraphLinkCandidate]`. Reuses `BgeSmallEmbedder` and the DITTO reranker that V1 ships in `src/er/`.
2. **Cross-source mode** turns off the within-document mention-extraction (Pass 1) front-end and treats the input as an already-structured entity with `name`, `aliases`, `type`. Skips spaCy / GLiNER2.
3. **`SAME_AS` edge type** added to the graph schema with the standard property convention: `source_tier` (composite — both endpoint tiers stored), `rank`, `references` (citing both side's source rows / posts), `qualifiers`, bitemporal 4-tuple, `confidence`.
4. **Auto-accept ≥ 0.90** writes a `SAME_AS` edge. Both endpoints retain their own `source_tier` and node identity; the edge represents the equivalence claim.
5. **HITL 0.75–0.90** enqueues a `cross_graph_link` item with item_type-specific payload (both nodes' properties, similarity scores, sample mentions). Reviewer's verdicts: `accept` / `reject` / `defer` / `propose_alias` (the reviewer can propose adding the rejected side's name as a new alias of the canonical entity without committing the equivalence).
6. **Reject < 0.75** creates no edge. The new entity stands as its own canonical until / unless future ingests bring more candidates.
7. **Direction** — `SAME_AS` is semantically symmetric. Storage is single-edge with canonical-ordering-by-node-id. Retrieval auto-mirrors.
8. **Multi-way clusters** — if A `SAME_AS` B, and B `SAME_AS` C, then A `SAME_AS` C is implied. V1.5a does not auto-materialize the transitive edge; queries do transitive closure at read-time. V1.6 may materialize for perf.
9. **Trust-tier interaction** — when the resolved cluster spans multiple tiers, the L1 endpoint retains canonical status. Cross-graph `SAME_AS` edges never elevate an L2/L3/L4/L5 entity to L1; the tier is per-node, not per-cluster.
10. **Gold set** — 100-pair `evals/gold/v1.5a-cross-graph.jsonl` covering:
    - ADEA L1 ↔ external Postgres school table (~40 pairs)
    - ADEA L1 ↔ Reddit alias mentions (~30 pairs — regression on V1 alias gold)
    - external Postgres ↔ Reddit (~30 pairs — new direction)
    F1 ≥ 0.92 gate.

## Consequences

**Positive:**
- Reuses the proven V1 stack instead of inventing new ER infrastructure. Lowest risk.
- Threshold parity with V1 keeps HITL routing predictable.
- `SAME_AS` is a clean, well-understood graph primitive — standard in semantic web (`owl:sameAs`).
- Bitemporal `SAME_AS` lets us "unlink" entities (e.g., on HITL reject after-the-fact) without destroying history.
- Per-tier preservation prevents tier escalation accidents.

**Negative:**
- Three-graph mapping (ADEA + DB + forum) requires three pairwise pipelines. ~3x the matching workload per ingest. Mitigated by HNSW blocking + cached embeddings.
- Transitive closure at read-time costs query latency for big clusters. Acceptable for V1.5; materialize in V1.6 if perf demands.
- The reviewer's `propose_alias` verdict is new HITL semantics — the reviewer can split "this is an alias of X" from "this is the same entity as X." Requires UI affordance + clear copy.

**Neutral:**
- V1's alias-resolution code stays unchanged; cross-graph is a wrapper, not a fork.
- The 0.75 / 0.90 thresholds are V1 carryovers; calibrate post-launch if F1 drifts.

## Alternatives considered (and rejected)

- **Build a new GNN-based aligner** (per 2025-2026 SOTA arxiv work like SubGraph Networks for cross-graph alignment). Rejected for V1.5a: not enough labeled data; over-engineering for current scale.
- **Use only embedding cosine (skip DITTO reranker)**. Rejected: DITTO catches the hard cases (negation, partial overlap) that pure cosine misses.
- **Auto-merge identical-name entities silently**. Rejected: dangerously aggressive; one of the V1 design invariants is that merges are explicit decisions, not coincidences.
- **Per-entity-type custom matchers** (one for schools, one for programs, etc.). Rejected for V1.5a: the entity-property dictionary already differentiates; keep one matcher.

## Implementation

V1.5a, Phase 5. Tests in `tests/er/test_cross_graph.py`.

V1.5b UI: `/hitl/crosslinks` page renders cross-graph candidates with side-by-side evidence.

## References

- V1 FR-3 alias resolution
- ADR-005 trust-tier schema (preserved)
- `docs/05-features/02-slice-v1.5a-db-connector/requirements.md` FR-1.5a-5
- V1.5-R1 (cross-graph mapping confirmed via "Recommended bundle")
- 2025 arxiv: cross-source alignment with subgraph networks (informed approach; not used directly)
