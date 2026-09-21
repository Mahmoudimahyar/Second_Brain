# Project Mode

## Selected mode

**V1 primary:** `ai_agent_system`
**V1 overlay:** `data_pipeline` (ingestion + ETL subsystem)
**V2 reframe:** `developer_tool` — once the source-handler interface generalizes for other companies' data dumps. This is the **separate-from-DentistJourney generic knowledge-engine tool**; DentistJourney is one downstream consumer, not the product.

Confirmed by Mahyar in round 1: "This will be seperate code repo from DentistJourney. We want to build the tool in a way that not only is used by DentistJourney, but also it can be used by other companies as well." V1 internal-only.

## Why this mode

V1 deliverable is an orchestrated set of specialized agents (ingestion, alias resolution, conflict resolver, web-verification, HITL queue) over a graph store + cascade extraction pipeline. Public-facing API surface is deferred to V2. The system's reusability principle (source-pluggable, trust-tier-aware) is a V1 architecture constraint even though V1 ships internal-only.

## Required documentation groups (per doc-activation-matrix.md)

For `ai_agent_system`:

- `00-bootstrap` — Required
- `01-core` — Required (product vision, glossary, user types, success metrics, out-of-scope, non-negotiables)
- `03-research` — Required (research log + research-protocol)
- `04-architecture` — Required (system overview, tech stack, module boundaries, dependency rules, error handling, performance budget, library decision matrix)
- `05-features` — Required (one feature packet per first vertical slice)
- `07-data` — Required (memory/RAG present) (data dictionary, migration rules)
- `09-testing` — Required (testing strategy, browser validation if HITL UI exists, test data, test matrix)
- `10-operations` — Required (deployment, monitoring)
- `11-decisions` — Required (ADRs per major decision)
- `12-security` — Required (security model, MCP security) — light for V1 (internal-only), expanded for V2
- `13-observability` — Required (trace/logging for retrieval + extraction)
- `14-context-packs` — Required (GraphRAG context packs)

Plus `data_pipeline` overlay reinforcements: data sources, schemas, transformations, lineage, validation rules, failure modes, observability, tests.

## Optional / light documentation groups

- `02-product` — Light: light personas + light user-journeys ONLY (one persona = "internal ingestion operator + HITL reviewer"; one journey = "data drop → graph → query"). Pricing/positioning/competitors **SKIPPED**.
- `06-api` — If relevant: yes once a retrieval/MCP API is exposed for V1 consumers.
- `08-ui` — If UI: yes — HITL review console is in V1 scope.
- `15-marketing` — **SKIP** per Mahyar's standing rule. Downstream marketing-content-generation agent is a V2 product feature, lives in `docs/05-features/*`, not in `docs/15-marketing/*`.

## Skipped documentation groups

Never written for this project mode; the empty scaffold files were removed on 2026-09-20.

- `docs/02-product/pricing.md`
- `docs/02-product/positioning.md`
- `docs/02-product/competitors.md`
- `docs/15-marketing/messaging.md`
- `docs/15-marketing/channel-strategy.md`
- `docs/15-marketing/content-system.md`

## User preference notes

- Plain-text question rounds, no structured-question UI (memory: [[feedback-no-structured-question-ui]]).
- Hard hardware ceiling: GTX 1080 8 GB VRAM + 64 GB RAM.
- Prior GPT-4o-mini extraction unsatisfactory — accuracy is the bottleneck.
- Cost-aware cascade is a design layer, not a nice-to-have.
- ADEA SQL is immutable L1 ground truth; never overwrite from L2-L5 extractions.
- Source-pluggable from V1 (different source types ≠ hardcoded for Reddit).
- V1 internal only; V2 generalizes externally.

## Mode-specific success criteria (V1)

- Agent roles documented and bounded (`docs/04-architecture/system-overview.md` + per-agent feature packets).
- Tool permissions catalog (`docs/12-security/mcp-security.md`).
- Memory/retrieval: GraphRAG over cleaned graph + structured SQL queries over L1 ground truth (`docs/07-data/data-dictionary.md`, `tools/graphrag/schema.md`, `tools/graphrag/retrieval-policy.md`).
- Eval suite: extraction precision/recall, alias-resolution F1, conflict-resolution correctness on labeled gold set, citation-traceability ≥ 99%, retrieval recall@k.
- Safety: no overwrite of L1 nodes; source-tier attribution on every retrieval; trace/logging for every extraction.
- Cost ceiling: TBD (Q-007 round 2).
- Trust-ladder + multi-layer graph + source-pluggable interface honored across architecture.

## Last reviewed

2026-05-20 — round 1 confirmed mode reframe (separate repo, V1 internal, V2 developer_tool, downstream agents = V2).
