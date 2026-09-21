# Documentation

> **Looking for how to use or extend SecBrain?** Start with the **[guide](guide/README.md)** —
> quickstart, concepts, architecture tour, adapters, MCP, configuration, CLI / REST reference, FAQ.
> What follows is the project's *design record*.

The docs are organised as numbered sections. The layout is load-bearing: the doc-lint gate and
the repo GraphRAG indexer address several of these paths directly, so files are not moved
casually.

## Start here

| If you want… | Read |
|---|---|
| **What actually runs today** (the single source of truth) | [`00-bootstrap/implementation-status.md`](00-bootstrap/implementation-status.md) |
| Why the project polices its own claims | [`00-bootstrap/why-drift-happened.md`](00-bootstrap/why-drift-happened.md) |
| The idea in one page | [`01-core/product-vision.md`](01-core/product-vision.md) |
| The rules that are never traded away | [`01-core/non-negotiables.md`](01-core/non-negotiables.md) |
| How the system fits together | [`04-architecture/system-overview.md`](04-architecture/system-overview.md) |
| Why each major choice was made | [`11-decisions/`](11-decisions/) — 26 ADRs |
| The vocabulary (tiers, passes, L1…L5) | [`01-core/glossary.md`](01-core/glossary.md) |

> **Reading status words.** `Decided` → `Built` → `Wired` → `Validated`. "Locked" and an ADR
> marked `accepted` both mean **Decided** — a choice was made — not that code runs. Only
> `implementation-status.md` says what is wired and validated; where another doc disagrees,
> the status file wins and the other doc is the bug.

## Map

| Section | Contents |
|---|---|
| [`guide/`](guide/) | **User-facing documentation.** The reference pages under `guide/reference/` are generated from the code. |
| [`00-bootstrap/`](00-bootstrap/) | Implementation status, drift post-mortem, gap register, assumptions, unresolved questions. [`kit/`](00-bootstrap/kit/) archives the bootstrap kit the repo was started from. |
| [`01-core/`](01-core/) | Vision, non-negotiables, glossary, user types, success metrics, out-of-scope. |
| [`02-product/`](02-product/) | Personas, user journeys, roadmap. |
| [`03-research/`](03-research/) | Research log and reports R-006 … R-010 (multi-source KGs, cost/accuracy, multi-vendor modularity, state-of-the-art review). |
| [`04-architecture/`](04-architecture/) | System overview, tech stack, dependency rules, error handling, performance budget, library decision matrix. |
| [`05-features/`](05-features/) | One **feature packet** per slice — requirements, API, data, state machine, plan, test plan, known issues — plus the V1.5 / V1.6 / V1.7 master briefs and the research-protocol spec. |
| [`06-api/`](06-api/) | Connector API reference and error codes. |
| [`07-data/`](07-data/) | Data dictionary and the registry of official (L1) sources. |
| [`08-ui/`](08-ui/) | Console information architecture, HITL flows, graph views; [`v1.5-redesign/`](08-ui/v1.5-redesign/) holds the design system and page designs. |
| [`09-testing/`](09-testing/) | Testing strategy, test matrix, test data. |
| [`10-operations/`](10-operations/) | Deployment and monitoring. |
| [`11-decisions/`](11-decisions/) | Architecture Decision Records ADR-001 … ADR-026, with templates. |
| [`12-security/`](12-security/) | Security model and MCP security. |
| [`13-observability/`](13-observability/) | Logging, audit log, LLM telemetry. |
| [`14-context-packs/`](14-context-packs/) | Historical — superseded by the feature packets. |

## Feature packets

| Packet | Slice |
|---|---|
| [`01-slice-trust-tier-canonicalize`](05-features/01-slice-trust-tier-canonicalize/) | V1 core: official data + one forum → trust-tier graph → conflict resolution → HITL → cited retrieval |
| [`02-slice-v1.5a-db-connector`](05-features/02-slice-v1.5a-db-connector/) | External database connectors, user-declared tiers, cross-graph entity mapping |
| [`03-slice-v1.5b-web-ui`](05-features/03-slice-v1.5b-web-ui/) | Operations console |
| [`04-slice-v1.5c-conflict-and-teams`](05-features/04-slice-v1.5c-conflict-and-teams/) | Web-verified conflict resolution, per-team views |
| [`05-slice-v1.6-website-crawler`](05-features/05-slice-v1.6-website-crawler/) | Polite staged website crawler (L0 sitemap → L1 entity-tagged → L2 full GraphRAG) |
| [`bake-off-graph-db`](05-features/bake-off-graph-db/) | Graph-database bake-off behind ADR-001 |

## Evidence

`implementation-status.md` cites validation reports (`.agent/reports/…`) and corpus-operations
tooling (`cloud/…`, `scripts/…`) row by row. Those artifacts are tied to a private corpus and live
in the private development repository; they are intentionally not part of this public snapshot.

## Historical documents

Files written before implementation began carry a dated **Historical** banner at the top
rather than being silently rewritten. They are kept because the decisions in them explain the
code; they are not descriptions of the current system.
