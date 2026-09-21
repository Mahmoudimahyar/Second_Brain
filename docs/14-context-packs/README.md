# Context Packs

> ⚠️ **Historical (written 2026-05-20).** The GraphRAG MCP server this file calls "not yet implemented" was built and verified — see `tools/graphrag/` and `.agent/reports/graphrag-verification-*.md`. The context packs specified below were never written; the feature packets under `docs/05-features/` fill that role.

> Context packs give coding agents the smallest useful context for a feature or domain. Per `ai_agent_system` mode, this directory is Required.

## Two layers of context retrieval

1. **`tools/graphrag/` MCP context server** — the primary retrieval mechanism. Indexes the SecBrain repo (docs, code, tests, feature packets) and exposes retrieval tools the coding agent uses before broad file reads (per CLAUDE.md). This is gate #6 — not yet implemented.
2. **Context packs (this directory)** — hand-curated bundles for specific scenarios. Used when the agent needs to start a task with a known minimum set of docs in context, without depending on a retrieval round trip. Effectively pre-seeded retrievals.

When `tools/graphrag/` is live, most context-needs are answered by `search_codebase()` / `get_feature_packet()` / `get_related_tests()`. Context packs remain useful for:
- Multi-doc "starter kits" for major workstreams (e.g., "starting V1 implementation").
- Off-the-record context that doesn't fit cleanly in the graphRAG schema.
- Compact maps for an agent fresh from compaction.

## Pack format

Each pack lives in its own subdirectory: `docs/14-context-packs/<pack-name>/`. Files:

| File | Content |
|---|---|
| `README.md` | When to use this pack; one-sentence purpose. |
| `required-reading.md` | Ordered list of docs the agent should read first (with file paths). |
| `related-code.md` | Code roots + key modules the pack covers. |
| `related-tests.md` | Pointers to relevant test files + gold sets. |
| `common-tasks.md` | The 3-5 most-likely tasks in this domain + how to start each one. |
| `known-traps.md` | Footguns, brittle integrations, surprising behaviors discovered during implementation. |

## V1 packs (to be created at V1 implementation start)

| Pack | When to use |
|---|---|
| `v1-slice-implementation` | Starting Phase 1+ of `docs/05-features/01-slice-trust-tier-canonicalize/plan.md`. |
| `graph-db-bake-off` | Executing `docs/05-features/bake-off-graph-db/` (separate from V1 product implementation). |
| `gateway-multi-vendor` | Implementing or modifying `src/gateway/` (ADR-011). |
| `bitemporal-correctness` | Anything touching `src/graph/bitemporal.py` or `t_valid_*` / `t_ingest_*` semantics. |
| `hitl-cli` | Implementing or modifying the HITL CLI (`src/hitl/`). |
| `extraction-cascade` | Modifying any of Stage 1 / 2 / 3 (`src/extraction/`). |
| `tools-graphrag-build` | Implementing the repo MCP context server itself. |

These are spec'd here as future work; their full content lives under their respective subdirectories once written.

## Context-budget principle

Each pack aims to enable a focused task without dragging in the whole repo. Targets:
- ≤ 8 docs in `required-reading.md`.
- ≤ 10 code paths in `related-code.md`.
- ≤ 5 task starters in `common-tasks.md`.

If a pack would need more, split it.

## Adding a pack

1. Create the subdirectory.
2. Fill the 6 files above.
3. Link from this README.
4. When `tools/graphrag/` is live, the pack also gets indexed as a `ContextPack` node so the agent can `get_context_pack(name)` directly.
