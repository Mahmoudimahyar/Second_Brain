---
adr: 012
title: Multi-level graph views — three retrieval contracts for one underlying graph
status: accepted
date: 2026-05-24
deciders: Mahyar, Claude
supersedes:
superseded_by:
revision_history:
  - 2026-05-24 — proposed.
  - 2026-05-25 — accepted. V1.5b shipped `query_graph_structural`, `query_graph_clusters`, `query_graph_analyzed`, `query_graph_crosslinks` per spec. No drift; the Sigma.js WebGL canvas implementation is V1.6 polish (gap audit HIGH-1, slated for W2-1).
---

# ADR-012 — Multi-level graph views

## Context

V1 ships a single retrieval surface: `query_graph(query, source_tier_min, time_range, as_of, traversal_depth)`. The graph it queries has three semantically distinct sub-structures that V1 produces but doesn't name:

- **Level A — structural** — produced by Pass 1: users, posts, comments, threads, subreddits + AUTHORED / REPLIED_TO / BELONGS_TO_THREAD / POSTED_IN_FORUM / UPVOTED. Deterministic, no LLM.
- **Level B — clusters** — produced by Pass 2 + Pass 3: Topic + Cluster nodes + IN_CLUSTER / REFERENCES_TOPIC edges + cluster summaries.
- **Level C — analyzed** — produced by Pass 4 + conflict resolver + (V1.5) cross-graph linker: sentiment / interview-Q / conflict-candidate extractions + MENTIONS_SCHOOL / SUPPORTS / CONTRADICTS / SAME_AS / status flags.

In V1, all three live in the same graph and `query_graph` returns whatever matches the query regardless of which level produced it. This is fine for an MCP-callable coding agent but wrong for a human-facing UI: the user wants to look at "the Reddit graph of who-replied-to-whom" or "the cluster landscape" or "the analyzed claim graph" as **distinct surfaces** without having to filter the same firehose differently.

V1.5-R1 confirmed: **three separate views/tabs/routes** in the web UI. That requires three separate retrieval contracts at the API layer so the views stay independent — without it, the UI tabs would each be re-shaping the same `query_graph` response, drifting in semantics and performance.

## Decision

Introduce three retrieval methods on `RetrievalService`, each backed by a level-specific subgraph selector and ranking policy, all sharing the underlying graph store:

1. `query_graph_structural(query, time_range, as_of, traversal_depth) -> StructuralResult` — returns User / Post / Comment / Thread / Subreddit nodes only. Edges restricted to the Pass-1 set. No LLM-derived properties. Pass-1 fuzzy-matched canonical references are kept (so a Post node still carries `mentions_school_id` if Pass 1 found one).
2. `query_graph_clusters(query, time_range, as_of) -> ClusterResult` — returns Topic + Cluster nodes + IN_CLUSTER / REFERENCES_TOPIC edges + (read-only) member counts. Posts/comments are returned only as cluster membership weights, not as primary results.
3. `query_graph_analyzed(query, source_tier_min, time_range, as_of, traversal_depth, include_anomalies) -> AnalyzedResult` — V1's existing `query_graph`, renamed. Returns all node types, all edges, all extractions, with the existing trust-tier + bitemporal + rank ranking.

Each result type is a distinct Pydantic schema. UI views call one method; do not mix.

Underlying graph stays single. Level-segmentation is implemented as named subgraph filters in `src/retrieval/level_filters.py`. Same ranking weights, citation policy, audit logging.

A fourth method `query_graph_crosslinks(source_tier_min, time_range, as_of) -> CrossLinkResult` returns only `SAME_AS` + future cross-graph link types (V1.5a output). Used by the per-team dashboards to drill from a forum mention to its DB anchor.

## Consequences

**Positive:**
- Each UI view has a stable, narrow contract. Independent perf tuning per level (Level A can preload the whole structural subgraph in-memory for a forum; Level C must stream).
- `query_graph_clusters` becomes the natural entry point for the cluster-review HITL flow (V1.5b) — it's a level-typed surface, not a hand-rolled query.
- Per-team dashboards (V1.5c) call `query_graph_analyzed` with stricter `source_tier_min` and tighter ranking weights without needing UI-side filtering.
- Audit log gains a `view_level` dimension, making per-level cost + latency observable in Langfuse.
- Level A's deterministic-only contract is a strong promise to the user: "this view never lies about authorship or threading."

**Negative:**
- Three contracts, three sets of Pydantic schemas, three sets of test cases. ~20% more code surface than a single retrieval method with discriminated unions.
- Edge cases at level boundaries: a Pass-4 sentiment extraction "lives" in Level C but references a Pass-1 post node; the UI must reach across surfaces to render that linkage. Solved by always returning node IDs cross-referenceable across the three contracts.
- `query_graph_clusters` doesn't actually need bitemporal `as_of` for V1.5 (clusters are recomputed weekly), but we keep the parameter for consistency.

**Neutral:**
- V1's `query_graph` becomes a thin alias for `query_graph_analyzed`. Existing tests + callers don't change.
- MCP surface gains three new tools (one per level). Tier 1 per ADR-011.

## Alternatives considered

- **Single `query_graph(..., level='A'|'B'|'C')`** — rejected. The level parameter would silently change the result shape, making typed clients (Zod / Pydantic) awkward and forcing union types in the UI.
- **GraphQL surface with per-level fragments** — rejected for V1.5 (adds a new tech to the stack mid-stride). Possibly V2 if multi-tenant API surface becomes important.
- **Materialized views per level** — rejected for V1.5. The graph is small enough that filtered queries on the single store outperform maintaining separate stores. Reconsider in V2 if scale demands.

## Implementation

V1.5a + V1.5b deliverables. V1.5a adds the level-typed retrieval methods + tests. V1.5b's UI is the first consumer.

```
src/retrieval/
  api.py                  # query_graph_structural, query_graph_clusters, query_graph_analyzed, query_graph_crosslinks
  level_filters.py        # subgraph selector functions per level
  schemas.py              # StructuralResult, ClusterResult, AnalyzedResult, CrossLinkResult
  ranking.py              # unchanged; ranking policy shared across levels
  rrf.py                  # unchanged
src/retrieval/mcp/inbound.py  # four MCP tool handlers
```

## References

- `docs/04-architecture/system-overview.md` §6 (current Pass-5 retrieval plane)
- `docs/05-features/01-slice-trust-tier-canonicalize/api.md` (V1 `query_graph` contract)
- V1.5-R1 question round, 2026-05-24
