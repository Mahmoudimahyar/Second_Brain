# Feature: V1 Slice — Trust-Tier-Aware Ingestion + Canonicalization

**Status:** Spec only. Implementation blocked on: bake-off completion (GAP-027) → ADR-001 ratification → `tools/graphrag/` MCP context server stand-up (gate #6) → then this slice via TDD.
**Slice ratified:** Round 2 (Mahyar).
**Owner:** Mahyar (decisions) + Claude (implementation, post-gates).
**Time budget:** TBD after Phase 0 of implementation; provisional estimate is 1-2 weeks of focused work after gates pass.
**Acceptance level:** demonstrably end-to-end, but minimal — *one* L1 source + *one* L5 source, *one* subgraph of each layer, *one* retrieval API surface.

## What this slice proves

The smallest end-to-end demonstration that the architecture from `docs/04-architecture/system-overview.md` actually works on real data:

1. **Trust-tier-aware ingestion** — one L1 dump (ADEA Report 2, 2020-21 → 2024-25) and one L5 dump (r/DentalSchool — `~274K` posts + comments) are ingested through the source-pluggable `register_dump(...)` interface and emerge as graph nodes tagged with `source_tier` + `rank` + `references` + bitemporal edges.
2. **Canonicalization** — L5 mentions of dental-school names ("UPenn", "Penn Dental", "HSDM") are snapped to L1 canonical entities via BGE-small HNSW blocking + DITTO reranker, with confidence scores. Borderline cases (0.75-0.90) land in the HITL queue.
3. **L1 immutability** — extracted forum claims that conflict with L1 are flagged `Status: Invalidated_by_Official_Data` on the forum side; L1 is never modified.
4. **Bitemporal correctness** — querying the graph "as of 2023-05-01" returns the state of canonical aliases + claims that the graph believed were valid on that date, not today's state.
5. **Cost cascade in production** — content-addressable extraction cache hits on the second sweep; prompt-cache + batch usage confirmed by the audit log.
6. **Retrieval MCP surface** — at minimum `query_graph(...)` + `get_canonical_entity(alias, type)` callable via MCP and returning sensible results with citations.

## What this slice does NOT prove (deferred to later slices / V2)

- All 5 trust tiers — only L1 + L5 active here.
- All 3 graph layers richly populated — the user-credibility layer ships with the V1 rubric but isn't deeply exercised; opinion-consensus signed-graph clustering is computed but not yet a retrieval primitive in V1.
- Self-evolving loop — no automatic re-ingestion of L1 sources yet.
- HITL web UI — V1 ships CLI + flat-file review only.
- Downstream agents (PM / marketing / search-verification / analyst) — V2.
- Cross-vendor LLM-as-judge calibration — V2 (LLM-as-judge in V1 is restricted to same-tier same-year tie-breaks per A-031).
- Web-verification crawler trigger — V1 emits `research_need` records but the crawler is out of repo.

## Why this slice first

- It hits every architectural surface (ingestion, cascade extraction, ER, trust-tier schema, bitemporal edges, conflict resolution, retrieval MCP, HITL queue, audit log) at minimal volume.
- It uses **only data already in `External Data\`**, so no external dependencies block implementation start once gates pass.
- The L1 dataset is small (~5 Excel files), the L5 subset is the smallest subreddit (274K records), and the alias-resolution problem set (~1K canonical schools/programs) is closed-set — fast iteration on the hardest single problem (school-name disambiguation, which was the original pain point with the GPT-4o-mini attempt).
- Passing this slice + the GraphRAG verification checklist unlocks every subsequent slice (L2/L3/L4 plug-in, opinion-consensus surfacing, web-verification agent, etc.) on the same architecture.

## Acceptance criteria (testable, blocking)

1. `register_dump('L1', adea_report_2_manifest, file_paths)` → at least 56 `School` nodes + ≥ 500 `SchoolYearMetric` edges materialize, all with `source_tier=L1`, `rank=preferred`, `t_valid_from/to` set, `t_ingest_*` set.
2. `register_dump('L5', r_dentalschool_manifest, jsonl_paths)` → ingests all of r/DentalSchool, all posts + comments materialize with `source_tier=L5`, `rank=normal` (default), and bitemporal edges. Author nodes namespaced `reddit:DentalSchool:<author>`.
3. **Alias resolution F1 ≥ 0.92** on a hand-labeled 200-mention gold set covering common variants ("UPenn", "Penn Dental", "Penn Dental Med", "HSDM", "Harvard Dental", "U of P").
4. **HITL queue routing**: borderline matches (similarity 0.75-0.90) appear in the queue; auto-accept ≥ 0.90; reject < 0.75. Queue throughput matches a synthetic rate of 50 items/hour for V1 testing.
5. **Citation traceability** ≥ 99%: every retrieved entity / edge in `query_graph(...)` results carries `references` linking back to source post/file IDs.
6. **Bitemporal correctness**: a deterministic test that ingests the same source twice with different `t_valid_*` ranges, then queries "as of <past date>" returns the older snapshot.
7. **L1 invalidation**: a deterministic test where a forum claim states a conflicting tuition number for a known L1 school; the forum claim is flagged `Status: Invalidated_by_Official_Data`, L1 node unchanged.
8. **Cost-cascade observability**: audit log shows cache-hit rate ≥ 0 on first sweep (cold), ≥ 80% on second identical sweep (warm). Prompt-cache `ttl: 3600` is verified pinned on every Anthropic call.
9. **GraphRAG verification checklist** (`tools/graphrag/verification-checklist.md`) **for the repo MCP server** is passing before this slice's product engine starts.
10. **Verification Before Completion report** in `/.agent/reports/v1-slice-01.md` per AGENTS.md.

Non-functional:
- V1-slice extraction sweep over r/DentalSchool stays under **$25** of API spend (per R-008 + corpus inspection).
- All retrieval queries used in tests return p95 < 250 ms.
- Audit log entries written for every extraction, retrieval, HITL decision (per `docs/04-architecture/system-overview.md` §9).

## Sub-files in this packet

- `README.md` — this file
- `requirements.md` — functional + non-functional requirements
- `context.md` — links to upstream research + architecture + memory
- `plan.md` — phased implementation plan (post-gates)
- `data.md` — V1 slice data model (subset of full schema)
- `api.md` — MCP tool signatures for this slice
- `test-plan.md` — test matrix mapping acceptance criteria to test cases
- `state-machine.md` — ingestion + HITL state machine
- `decisions.md` — slice-local decisions (extends ADRs)
- `known-issues.md` — discovered during implementation
- `changelog.md` — slice-local change log

(Some files seeded this turn; others added in subsequent doc batches.)
