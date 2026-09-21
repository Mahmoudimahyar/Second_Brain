# Product Vision

## One-sentence description
A generic, self-correcting, self-evolving knowledge-graph engine: dump arbitrary data (structured DBs, official websites, scraped forums, technical docs) and the system normalizes, deduplicates, anchors against authoritative ground truth, surfaces and resolves conflicts, and emits a queryable graph that updates itself as new sources arrive.

## Problem
Building a "one source of truth" knowledge base on any non-trivial domain today means hiring analysts to read, dedupe, and reconcile mountains of contradictory sources by hand. Most knowledge bases are either (a) authoritative but narrow (official datasets only — missing community insight, lived experience, edge cases), or (b) broad but unreliable (scraped community content with no conflict resolution, no source-trust weighting, no temporal awareness). Vector RAG over raw text gives confidently-wrong answers; bespoke ontologies don't scale across domains.

## Target users (V1, internal)

- **Mahyar** + collaborators building DentistJourney's dental-applicant knowledge engine (V1 anchor domain).
- **HITL reviewer** (the human-in-the-loop curator who ratifies new node/edge types, resolves borderline alias matches, and arbitrates irreducible conflicts).
- **Downstream human consumers** of the graph: product managers (gap detection in the market), marketing teams (real-pain-point surfacing), internal analysts.

## Target users (V2, external — out of V1 scope)

Other companies bringing their own data dumps. Possible future personas: research teams, regulated-domain knowledge owners, market-intelligence teams, brand/community owners.

## Current alternative / workaround

- Manual curation by domain experts.
- Vector RAG over raw scraped text (gives outdated and contradictory answers; no conflict resolution).
- Single-purpose knowledge graphs (Wikidata, ConceptNet) — too generic for any specific domain and don't ingest your private structured data.
- Microsoft GraphRAG out-of-the-box (great for global summarization, weak on **trust-tiering and conflict resolution** — still its genuine gap). *(Re-baselined per R-010: the old "expensive at 500K-thread scale" objection is stale — LazyGraphRAG/LightRAG and MS incremental indexing cut cost ~100–1000× since 2024. Our differentiator is the trust-tier + conflict layer, **not** cost. Whether to build that layer on top of LightRAG/Graphiti vs the custom pipeline is the ADR-025 spike.)*

## Why now

- LLM cost has dropped enough (Haiku 4.5, GPT-4o-mini, batch APIs) that cascade extraction over 500K threads is tens of dollars, not tens of thousands.
- Constrained-decoding libraries (Outlines, lm-format-enforcer) make structured extraction reliable enough to anchor LLMs against canonical entity lists.
- Embedding models (BGE, GTE, MiniLM) are small enough to run on commodity GPUs and good enough for entity-resolution-grade similarity.
- Graph DBs with native vector indices (Neo4j 5, KuzuDB) eliminate the operational pain of sidecar vector stores.
- DSPy and BAML make prompt-program optimization a tractable accuracy lever.

## Success definition (V1)

- One vertical slice ships: ADEA SQL (L1) + 1 subreddit (L5) → graph with source-tier attribution, alias resolution against ADEA canonical list, time-aware conflict resolution, HITL queue for ambiguous cases.
- Extraction precision ≥ 95% on the labeled gold set for the slice's primary entity type (e.g., dental-school name on L5 threads).
- Citation traceability: every retrieval result links back to its source post(s) + source tier.
- GraphRAG verification checklist (`tools/graphrag/verification-checklist.md`) fully passes.
- Total V1 extraction spend stays inside the budget envelope Mahyar provides (Q-016 round 2).
- HITL queue throughput matches Mahyar's available review hours/week.

## Success definition (V2)

- Second domain ingested via the pluggable source-handler interface without core-engine code changes.
- Downstream agents (PM ideation, marketing/SEO content gen, search-verification) consume the V1 graph through documented MCP / API surface.
- External-use security model satisfies whatever data-sharing posture Mahyar lands on.

## Product principles

1. **L1 is sacred.** Structured-truth sources are never overwritten by lower-tier extractions; conflicts with L1 are flagged on the lower-tier node, not on L1.
2. **Trust-tier-aware everything.** Every node, edge, and retrieval result carries `source_tier` (L1..L5) + `created_utc`. Retrieval treats **tier as a prior inside a calibrated score** (with recency-decay, user-credibility, and RA-RAG-style cross-source consistency) — **not** a hard tier-first sort, which would bury correct community/minority insight under stale official data (per R-010 / ADR-021). Source-reliability-weighted RAG is established (RA-RAG, Astute, TrustRAG); our extension is the explicit ordinal L1–L5 ladder + bitemporal recency.
3. **Source-pluggable.** Different source types (technical docs, official sites, structured DBs, scraped forums) use different ingestion strategies behind a shared plugin contract. No source-specific code in the core engine.
4. **Cost cascade.** Cheap proxies first (heuristics, classifiers, local 7-8B models). Expensive API LLMs only on the high-value filtered subset. Every architecture decision weighs accuracy gain per dollar.
5. **Temporal-first conflict resolution.** Time disambiguation before trust weighting; trust weighting before consensus clustering; consensus clustering before web-verification; web-verification before HITL.
6. **Active schema evolution with HITL gate.** New node/edge types may only be added via human approval. No ungoverned ontology sprawl.
7. **Citations always.** Every retrieval result includes source attribution; no answer without provenance.
8. **Self-evolving.** The system periodically re-ingests authoritative sources, detects drift against the existing graph, and updates itself. Drift > threshold triggers re-extraction; conflicts with L1 trigger web-verification; new node/edge categories trigger HITL review.
9. **Generic at V1, productized at V2.** V1 hardcodes nothing domain-specific outside the pluggable handlers; V2 generalizes the developer-facing surface.
