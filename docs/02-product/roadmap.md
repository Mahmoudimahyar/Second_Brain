# Roadmap

> Light per `ai_agent_system` mode. V1 internal-only with concrete deliverables; V1.x improvements numbered; V2 generalizations sketched. Dates are targets, not commitments.

## V1 — Internal data engine (Q3 2026 target)

The minimum viable trust-tier-aware knowledge-graph engine. Single workstation. Internal use by Mahyar.

### Phase 0 — Gates ✅ COMPLETE (2026-05-29)

- [x] Bootstrap docs (PRD, architecture, V1 slice packet, test plan, observability, security)
- [x] **Graph-DB bake-off** → ADR-001 ratified; Kùzu chosen
- [x] ADRs landed (ADR-001..026)
- [x] `.env.example` complete
- [x] API keys provisioned (Anthropic + OpenAI + Together.ai)

### Phase 1 — V1 slice ✅ COMPLETE (2026-06-09)

ADEA L1 + full corpus (r/DentalSchool + r/predental + 5 SDN forums) → trust-tier-attributed graph + KB ask agent. See `docs/00-bootstrap/implementation-status.md` for validated counts.

Final corpus: **4,558,352 nodes / 13,103,287 edges**. Costs: Pass 4 $119.34 + comments $34.05 = $153.39 total. KB ask agent wired: `src/cli.py ask` + `POST /api/v1/ask`.

### Phase 2 — L1 ground-truth crawl + data bundle ✅ COMPLETE (2026-06-12)

- [x] L1 official-source registry: 20 verified domains (`docs/07-data/l1-official-source-registry.md`)
- [x] L1 website crawler wired end-to-end: `flows/website_crawl_worker.py` + CLI + UI
- [x] 10 registry domains crawled, merged, compacted on EC2 VM (4.56M nodes / 13.1M edges)
- [x] documents.sqlite thread-complete raw store (3.325M docs, 1.79 GB)
- [x] Parquet graph export (nodes.parquet 4.56M + edges.parquet 13.1M)
- [x] Self-contained MCP server bundled (`cloud/bundle_assets/mcp_server.py`)
- [x] V1-June12 zip assembled on VM + downloaded (3.27 GB, md5 a5a2abf4893d56a26cf57e7204d82f36)

### Phase 3 — Evidence Answer Engine (EAE) 🔄 IN PROGRESS (2026-06-17)

7-step plan turning the KB ask agent into a full evidence-grounded answer system:

| Step | Capability | Status |
|---|---|---|
| EAE-1 | Comment recall: FTS5 index over documents.sqlite (1.95M comments searchable) | Pending (task #49) |
| EAE-2 | EvidenceSet assembler: union semantic + comment + SDN + L1 + ForumConsensus hits, typed | Pending (task #50) |
| EAE-3 | Typed-count aggregator: "3 L1 + 47 L5 + 8 Comment" + most_reliable surfacing | Pending (task #51) |
| EAE-4 | EvidenceAnswer schema + `POST /api/v1/evidence` + L1 get_node drill-down | Pending (task #52) |
| EAE-5 | Wire ranking.py + consistency.py into KBAgent.answer (tier-weighted popular-vs-correct) | Pending (task #53) |
| EAE-6 | Stance clustering (KPA): 80/15/5 opinion distribution per question | Pending (task #54) |
| EAE-7 | Calibrated abstention + combination verdicts + coverage-vs-accuracy eval | Pending (task #55) |

See GAP-057..GAP-061 for the known pre-conditions.

### Phase 4 — Operational hardening (planned)

- `make dashboard` script.
- Vendor quality A/B: Gemini 2.5 Flash-Lite vs Haiku 4.5 on a held-out eval set.
- Replay-from-audit-log test passes.
- HITL operator pacing: real reviewer hours/week + queue depth in steady state.

## V1.x — Iterative improvements (Q4 2026 / Q1 2027)

| Improvement | Source | Notes |
|---|---|---|
| **Logistic-regression user-credibility** | A-033, GAP-028 | Replaces V1 hand-weighted rubric once HITL gold accumulates (~few thousand decisions). Source-aware (Reddit vs SDN) preserved. |
| **Cross-vendor LLM-as-judge in production** | A-052, FR-6.6 | Activates the 3-vendor judge (Sonnet 4.6 + Gemini 2.5 Flash + GPT-4.1-mini) once all keys are warmed + a calibration corpus is built. |
| **Signed-graph community detection as a retrieval primitive** | system-overview.md §4 | V1 computes clusters offline but doesn't yet rank by them in `query_graph`. V1.x makes them first-class. |
| **L2 / L3 / L4 adapters** | trust ladder rollout | One per release. License + provenance requirements vary by source. |
| **`tools/graphrag/` schema upgrades** | gate #6 | Add edge types as repo evolves (e.g., FEATURE → ADR linking). |
| **Distillation pipeline (early)** | R-008 V2 projection | Train a small local extractor on Stage-3 labels. Pulls full-corpus sweep cost down. |
| **HITL queue improvements** | reviewer feedback | Pull / commit ergonomics + diff visualization. Still CLI in V1.x; web UI deferred to V2. |
| **Gateway runner-up evaluation** | A-053 | If LiteLLM SDK proves friction-heavy, evaluate Portkey self-hosted. |
| **Self-evolving loop (limited)** | system-overview.md, GAP-022 | Periodic L1 / L2 re-ingest detection + automatic re-extraction trigger. Cron-driven. |

## V2 — Generalization + external use (date TBD, post-DentistJourney traction)

| Theme | Items |
|---|---|
| **Mode reframe** | `ai_agent_system` → `developer_tool`. New mode router classification + activated marketing docs (if explicitly requested). |
| **Source-pluggable interface** | Any company's data dumps via the documented plugin contract. |
| **Multi-tenant security model** | New `security-model.md` covering auth, per-tenant isolation, abuse handling, license enforcement. |
| **Downstream agents** | Product-management ideation agent. Marketing/SEO content generation agent (up to ~5,000 templated blog posts vision). Search-verification agent (autonomous web-fetch to confirm L5 disputes vs L1). Data-analyst agent. Each is a separate feature packet. |
| **Web HITL UI** | Replaces V1 CLI + flat YAML. |
| **Cloud deployment + DR** | Containerized; cloud TBD; backup + multi-region considerations. |
| **Streaming MCP transport** | HTTP/SSE for cross-process + cross-host calls. |
| **Per-tenant cost ceilings + dashboards** | Multi-tenant Langfuse views. |
| **Cross-source identity reconciliation** | Optional `Person` super-node owning multiple namespaced User aliases (KI-011). |
| **Right-to-be-forgotten** | DMCA / GDPR takedown handling on forum-author content. |
| **External licensing of the engine** | Commercial license; ADEA / CODA data NOT redistributed (license-bound to V1 internal). |

## Out of roadmap (explicit non-goals)

- Public consumer UI in this repo (that's DentistJourney's separate repo).
- Replacing DentistJourney's product — the engine is the backend, not the product.
- General-purpose RAG framework — we're not competing with LangChain / LlamaIndex; we're trust-tier-and-temporally-specialized.
- Owning the crawler — separate system, separate repo.

## Decision points that gate movement between phases

| Move | Gate |
|---|---|
| Bootstrap → V1 Phase 0 | All bootstrap doc gates pass per `gates.md` |
| Phase 0 → Phase 1 | ADR-001 ratified + `tools/graphrag/` verified + Mahyar go-ahead on code |
| Phase 1 → Phase 2 | V1 slice acceptance criteria all met + Verification Before Completion report filed |
| Phase 2 → Phase 3 | Multiple sources ingested without architectural rewrite (validates source-pluggability) |
| V1 → V1.x | Phase 3 done + Mahyar has empirical signal on what to iterate on |
| V1.x → V2 | DentistJourney public traction or a confirmed second-tenant ask |
