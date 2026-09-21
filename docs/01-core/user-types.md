# User Types

> V1 = internal-only. V2 generalizes for external companies. Light per `ai_agent_system` mode (`docs/00-bootstrap/doc-activation-matrix.md`).

## V1 user types

| User type | Description | Primary goals | Pain points | V1 permissions | V1 MCP surfaces used |
|---|---|---|---|---|---|
| **Ingestion operator** | The person (Mahyar in V1) who configures sources, runs ingestion sweeps, monitors the pipeline. | Get clean trust-tier-attributed graph from raw dumps; minimize cost; catch failures early. | Vendor lock-in fears; opaque LLM behavior; cost overruns; brittle alias resolution. | Full read/write on graph + side store + audit log; can re-run sweeps; can edit prompts. | All inbound + outbound MCP, plus all Python APIs. |
| **HITL reviewer** | The person (Mahyar V1; contracted dental-admissions expert V1.x+) who arbitrates the queue items the system can't resolve automatically. | Make defensible accept/reject calls on borderline alias matches + conflict tie-breaks + new node/edge type proposals. | Slow CLI; ambiguous evidence; no time to read full thread context; reviewer burnout. | Read on graph + audit log; write on `hitl_queue`. | HITL CLI (Tier 0 — Python API + flat YAML files). |
| **Downstream human consumer** | Product manager / marketer / internal analyst (eventually DentistJourney's team) who queries the graph to derive insights. | Find market gaps; surface pain points; pull aggregated stats; cite sources. | Untrusted answers without citations; can't tell L1 facts from L5 opinions; stale data presented as current. | Read-only on graph via retrieval MCP. | Inbound MCP (`query_graph`, `get_canonical_entity`; V1.x adds `search_by_topic`, `get_user_credibility`, `get_topic_consensus`). |
| **Crawler system** | External system that fetches new dumps and feeds them in; queries the engine to learn where the gaps + research-needs are. | Targeted crawling based on gap signals; idempotent dump submission. | Wasted crawls on already-ingested URLs; no signal on which topics need fresher data. | Write on ingestion (`register_dump`); read on outbound MCP (`get_gaps`, `get_research_needs`, etc.). | Outbound MCP. |

## V2 user types (deferred — for context only)

- **External tenant operator**: equivalent of the V1 ingestion operator but at another company, bringing their own data dumps. Triggers the V2 `developer_tool` posture.
- **Downstream agents** (PM-ideation, marketing/SEO-content-gen, search-verification, data-analyst): per `docs/01-core/out-of-scope.md`. Consume the graph via inbound MCP.
- **End-consumer of DentistJourney** (the dental applicant): not a user of *this* tool directly; the DentistJourney product fetches answers from this engine and serves them.

## What "permissions" mean in V1

V1 is internal-only and single-user. "Permissions" above describe **intent** — the surface a given user type is allowed to touch — not enforced auth. Auth is V2.

## How users are NOT users

This tool deliberately does NOT serve:
- Anonymous public queriers.
- Anonymous bulk-API consumers.
- End-applicants directly. The DentistJourney product is the consumer-facing layer; this engine is its backend.
