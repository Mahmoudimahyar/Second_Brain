# Bootstrap Status

> ⚠️ **Historical snapshot, frozen at the end of the bootstrap phase.** Kept as a record of the pre-implementation gates. For current state see `docs/00-bootstrap/implementation-status.md`.

> Updated 2026-05-20 after R4 + ADRs + gate check.

## Core
- [x] Product vision *(seeded R2)*
- [x] Business context *(seeded R4)*
- [x] User types *(seeded R4 — light per ai_agent_system mode)*
- [x] Success metrics *(seeded R4)*
- [x] Out of scope *(seeded R2; updated R3)*
- [x] Non-negotiables *(seeded R4)*
- [x] Glossary *(seeded R4)*

## Product
- [x] Personas (light) *(R4)*
- [x] User journeys (light) *(R4)*
- [x] MVP roadmap *(R4)*
- [ ] Pricing/positioning **— SKIPPED** (standing rule)

## Architecture
- [x] Tech stack *(R4 — full picks; graph-DB bake-off complete 2026-05-21 → Kùzu, ADR-001)*
- [x] System overview *(R3 — full rewrite with R-006/R-007/R-008/R-009 findings)*
- [x] Module boundaries *(R4)*
- [x] Dependency rules *(R4)*
- [x] Data model *(R4 — `docs/07-data/data-dictionary.md`)*
- [x] Security model *(R4 — V1 light + V2 reopen plan)*
- [x] MCP security *(R4)*
- [x] Deployment plan *(R4 — V1 local)*
- [x] Code quality *(R4)*
- [x] Error handling *(R4)*
- [x] Error codes catalog *(R4)*
- [x] Performance budget *(R4)*
- [x] Library decision matrix *(R4)*
- [x] Observability *(R4)*
- [x] Monitoring *(R4)*

## Features
- [x] V1 vertical slice ratified *(R2)*
- [x] V1 slice feature packet complete *(R3-R4: README, requirements, plan, api, data, state-machine, test-plan, decisions, known-issues, changelog, context)*
- [x] Graph-DB bake-off feature packet *(R3)*

## Testing
- [x] Testing strategy *(R4)*
- [x] Test matrix *(R4)*
- [x] Test data + fixtures *(R4)*
- [x] Browser validation policy *(R4 — N/A for V1; placeholder for V2)*

## ADRs
- [x] ADR-001 graph DB *(**accepted** 2026-05-21 — Kùzu wins by M5 ops-complexity tiebreak)*
- [x] ADR-002 hybrid retrieval *(accepted)*
- [x] ADR-003 extraction stack + per-task matrix *(accepted)*
- [x] ADR-004 BAML / DSPy GEPA *(accepted)*
- [x] ADR-005 trust-tier schema + bitemporal edges *(accepted)*
- [x] ADR-006 conflict resolution + LLM-as-judge restrictions *(accepted)*
- [x] ADR-007 HALO temporal decay *(accepted)*
- [x] ADR-008 user-credibility split *(accepted)*
- [x] ADR-009 two-MCP framing + SQLite side store *(accepted)*
- [x] ADR-010 orchestrator *(**accepted** — Prefect 3, ratified R5 per A-059; Prefect flow implementation is V1.x deliverable)*
- [x] ADR-011 model gateway + MCP three-tier policy *(accepted)*
- [x] ADR-012 multi-level graph views *(**accepted** 2026-05-25 — three retrieval contracts for Levels A/B/C; shipped in V1.5b. Sigma.js canvas implementation is V1.6 polish per W2-1.)*
- [x] ADR-013 UI tech stack *(**accepted** 2026-05-25 — Next.js 15 + FastAPI + Pydantic + Zod shipped; codegen substitution noted in revision_history; W2-6 resolves spec-vs-implementation drift.)*
- [x] ADR-014 external DB connector tiering *(**accepted** 2026-05-25 — user-declared L2 default + L1 gate shipped in V1.5a.)*
- [x] ADR-015 cross-graph entity mapping *(**accepted** 2026-05-25 — V1.5a CrossGraphLinker; 100-pair gold F1 0.9505 vs 0.92 gate.)*
- [x] ADR-016 web-search conflict resolution *(**accepted** 2026-05-25 v2 — Tavily-only with query-rephrase + Haiku+Gemini parallel verify. V1.5c shipped the skeleton; W1-1 + W1-2 (2026-05-25 remediation) wired the gateway + two-vendor parallel verify per spec.)*
- [x] ADR-017 feedback loop via BAML prompt context *(**accepted** 2026-05-25 — amended by ADR-018; V1.5b shipped feedback_log + FeedbackContextLoader + BlocklistFilter + cache-key extension.)*
- [x] ADR-018 feedback log retention + active-learning context curation *(**accepted** 2026-05-25 — append-only log + K=4 examples cap + LFU+LRU blocklist; V1.5b. Live quality-lift smoke pending W1-7.)*
- [x] ADR-021 tier-as-prior ranking + RA-RAG cross-source consistency *(**accepted** 2026-05-29, R-010 — supersedes "tier-first sort". Ranker not yet built → V1.7 / GAP-048.)*
- [x] ADR-022 entity-resolution modernization *(**accepted** 2026-05-29 — EmbeddingGemma↑bge-small, NuNER-Zero A/B, LLM-matcher fallback. → V1.7.)*
- [x] ADR-023 calibrated cascade + learned first-hop router *(**accepted** 2026-05-29 — calibrated escalation; corrects the proxy-throughput rationale. → V1.7.)*
- [x] ADR-024 LLM-judge hardening *(**accepted** 2026-05-29 — family-exclusion + independent vote; judge not yet wired → V1.7 / GAP-052.)*
- [ ] ADR-025 GraphRAG engine evaluation *(**proposed — spike**; LightRAG/Graphiti vs custom; Q-029 sequencing.)*
- [ ] ADR-026 learned truth-discovery vs deterministic cascade *(**proposed — spike**; non-deferred: stop "majority cluster = truth", canonicalize cascade numbering.)*

> ⚠️ **Status caveat (2026-05-29):** several ADRs above marked `accepted` are **Decided, not yet wired** (see `implementation-status.md` — the single source of truth). "accepted" ≠ "implemented". See `why-drift-happened.md`.

## Environment
- [x] `.env.example` populated *(R4)*

## Agent infrastructure
- [x] AGENTS.md, CLAUDE.md, Cursor rules
- [x] Skill dispatcher + 14 skills
- [x] Role harnesses
- [x] Doc activation matrix + mode router + question bank + gates
- [x] Bootstrap session ledger (assumptions, unresolved-questions, gap-register, source-documents, question-round-log, skill-usage-log)
- [x] Project mode classification *(confirmed R1)*
- [x] V1 vertical slice **ratified** (R2)
- [x] Multi-layer graph V1 scope = **all 3 layers** (R2)
- [x] Ingestion model = data dumps; outbound MCP to crawler (R2)
- [x] Trust-tier schema = Wikidata-style rank (R-007a)
- [x] Bitemporal edge model (R-007b)
- [x] Conflict-resolution order + LLM-as-judge restrictions (R-007b)
- [x] User-credibility rubric source-aware split (R-007c)
- [x] Top 5 cost/accuracy levers (R-008)
- [x] Multi-vendor strategy + LiteLLM SDK + three-tier MCP policy (R-009)
- [x] Context-packs README *(R4)*
- [x] Gate-check report *(R4 — `docs/00-bootstrap/gate-check.md`)*
- [x] **Graph-DB bake-off** *(EXECUTED 2026-05-21; Kùzu wins by M5 ops-complexity tiebreak; ADR-001 `accepted`; GAP-027 CLOSED)*
- [x] **`tools/graphrag/` MCP context server** *(IMPLEMENTED + VERIFIED 2026-05-21; gate #6 PASS)*
- [x] V1 product engine implementation *(**Slice 01 scaffold shipped 2026-05-21**: 490 tests, ruff clean, mypy --strict clean on 55 src files. Real-data smoke 2026-05-21 ingested ADEA SDE2 2024-25 + r/DentalSchool 2000-post sample + 2 L2 HTML docs + SDN Pre-Dental 200-thread sample = 26626 nodes / 65487 edges. CLI commands `ingest l1-adea | l2-html | l5-reddit | l5-sdn`, `cluster`, `extract`, `query`, `canonical`, `stats`, `reconcile-demo`, `hitl` all functional. V1 product MCP `secbrain-v1` registered in `.mcp.json`. Pass 3 KMeans clustering, Pass 4 sweep (sentiment/interview_q/conflict_candidate), real BGE-small + vendor adapters (Anthropic/OpenAI/Gemini) implemented. Reports: `.agent/reports/v1-slice-01.md`, `.agent/reports/real-data-smoke-2026-05-21.md`, `.agent/reports/session-recovery-2026-05-21.md`.)*

## Phase progress (per MASTER_BOOTSTRAP_PROMPT)
- [x] Phase -2 Skill dispatch
- [x] Phase -1 Project mode
- [x] Phase 1 Discovery *(R3 mostly closed; some Q's open — see unresolved-questions.md)*
- [x] Phase 1b Gap detection *(34 gaps tracked; most closed; remainder scoped + non-blocking or scheduled)*
- [x] Phase 2 SOTA research *(R-001..R-009 done)*
- [x] Phase 3 Fill required docs *(R3 + R4 covered all activated doc groups)*
- [x] Phase 3b ADRs *(R4)*
- [x] Phase 4 Environment planning (.env.example) *(R4)*
- [x] **Gate check** *(All 6 gates PASS — Gate 6 closed 2026-05-21)*
- [x] **GraphRAG MCP server (repo retrieval) implement-or-connect** *(VERIFIED 2026-05-21, report at `.agent/reports/graphrag-verification-2026-05-21.md`)*
- [x] **Graph-DB bake-off execution** *(2026-05-21; Kùzu wins by M5 ops-complexity tiebreak; ADR-001 `accepted`)*
- [x] **First vertical slice via TDD** *(Slice 01 scaffold + V1.x deferrals partially folded in; see V1 product engine implementation row above)*
- [x] **V1.x backlog — fully drained 2026-05-21**: Prefect 3 flow scaffolds (F), runtime vendor-failure circuit-breaker, Pass 3 HDBSCAN, cross-vendor LLM-as-judge per ADR-006, HITL CLI workflow, ADEA Reports 1+3+4 ingest (SDE1 schools/metrics, SDE3 per-school finance, SDE4 as L1Document), Pass 5 RRF hybrid retrieval (M), deterministic Pass 3 cluster naming via cache (N), adversarial alias gold F1 = 0.993 on 326 entries (P), live cost telemetry (C + F). Final verdict: `.agent/reports/v1-final-verdict-2026-05-21.md`.
- [x] **V1 acceptance**: all 10 ACs + 9 NFRs MET (see verdict report). 541 tests / 84.88% coverage / ruff + mypy --strict / GraphRAG verify PASS / 38037 nodes / 71121 edges across 4 ingest paths.
- [x] **V1.5 scope ratified** *(2026-05-24, V1.5-R1 Q&A round)*. Master brief at `docs/05-features/v1.5-master-brief.md`. Three sub-slices specced:
  - [x] **V1.5a** — external DB connector (Postgres/MySQL/SQLite/Neo4j) + cross-graph entity mapping + user-declared source tiering. Feature packet at `docs/05-features/02-slice-v1.5a-db-connector/`. **COMPLETE 2026-05-25** — `.agent/reports/v1.5a-slice.md` + `.agent/reports/v1.5a-integration-smoke-2026-05-25.md`. 657 tests / 84.35% coverage / ruff + mypy --strict clean / 70 source files. MappingSuggester F1 0.900 (gate 0.85). Cross-graph F1 0.9505 (gate 0.92). 7 connector MCP tools registered on `secbrain-v1`. ADRs 012/013/014/015 ratified to accepted 2026-05-25 per W1-5.
  - [x] **V1.5b** — full web HITL UI (Next.js 15 + FastAPI + Pydantic + Zod) + three-level graph viewer (Levels A/B/C per ADR-012) + cluster-cull / node-edge-proposal loop + BAML feedback-context per ADR-017. **COMPLETE 2026-05-25 (Wave-2 remediation)** — `.agent/reports/v1.5b-slice.md` + `.agent/reports/v1.5-wave2-gate-report.md`. 835 tests / mypy + ruff + TS strict clean. Backend fully shipped (feedback loop + level retrieval + FastAPI mount + settings + audit + W2-4 UI-action middleware + W2-5 central schemas). Frontend now ships the Sigma.js GraphCanvas (W2-1), UI component library (W2-2), and MySQL/Neo4j/Upload engine forms (W2-3); Playwright + axe-core specs in place (W1-6 gated on dev-server stability).
  - [x] **V1.5c** — web-search-grounded conflict resolution (Tavily-only per ADR-016 v2) + PM/Social/Marketing dashboards. Feature packet at `docs/05-features/04-slice-v1.5c-conflict-and-teams/`. **COMPLETE 2026-05-25 (Wave-1 remediation)** — `.agent/reports/v1.5c-slice.md` + `.agent/reports/v1.5-fix-W1-1-baml-gateway.md` + `.agent/reports/v1.5-fix-W1-2-two-vendor-signal-c.md` + `.agent/reports/v1.5-fix-W1-3-team-real-data.md` + `.agent/reports/v1.5-fix-W1-8-tavily-live-smoke.md`. 835 tests / ruff + mypy --strict clean. WebVerificationAgent **5/5 on gold set via live Tavily + Haiku + Gemini** ($0.11 spend). All BAML templates + signal C verifier route through `default_gateway()`; signal C runs Haiku + Gemini in parallel; per-team backends read from V1 graph (not hand-typed seeds); AC-4 restored to ≥10.
- [x] **V1.5 final verdict (post-remediation) filed** *(2026-05-25)* — `.agent/reports/v1.5-final-verdict.md`. 13 of 15 W1+W2 items closed; 2 deferred (W1-6 Playwright on built server, W1-7 Pass-4 quality-lift) with documented user-driven triggers. V1 baseline preserved; GraphRAG verify PASS; ADRs 012-018 accepted.
- [ ] **V1.6 scope** — Discord/Discourse/Stack Exchange forum types; Slack/Notion/website-crawler data sources; Snowflake/BigQuery/MS SQL/Oracle DB engines; true signed-graph community detection on Pass 4 SUPPORTS/CONTRADICTS; per-school structured curriculum extraction from SDE4.
- [ ] **V2 scope** — multi-tenant security, OS-keychain credentials, cloud deployment, downstream marketing-content-generation agent, cross-vendor judge expansion, DSPy GEPA fine-tuning from HITL gold, real-time CDC ingestion.

## Remaining bootstrap blockers

**None.** All bootstrap blockers cleared 2026-05-21:

- 6/6 gates PASS.
- `tools/graphrag/` MCP context server live + verified (gate #6).
- Graph-DB bake-off executed → Kùzu picked → ADR-001 `accepted`.
- **490 tests pass**, ruff + mypy `--strict` clean on **55 source files** (was 156/33 at gate-pass; grew during Slice 01).
- ADR-010 (Prefect 3) ratified `accepted` per A-059.

**Next**: V1.x backlog (signed-graph clustering, cross-vendor judge, Prefect flows, gold-set growth, broader ADEA Reports ingest, live Pass 4 cost telemetry).

## What's NOT blocked

- Continuing to write any additional bootstrap docs.
- Refining ADRs in response to Mahyar's feedback.
- Drafting context packs.
- Drafting any docs for V2 deferrals.
- Iterating on the per-task model matrix as new vendor data arrives.
