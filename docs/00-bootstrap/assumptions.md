# Assumptions

| ID | Assumption | Confidence | Impact if wrong | Status |
|---|---|---:|---|---|
| A-001 | V1 mode: `ai_agent_system` + `data_pipeline` overlay; V2 → `developer_tool`. | High | Wrong activation matrix. | **Confirmed** R1 |
| A-002 | Separate repo from DentistJourney. V1 internal. | High | Premature generalization. | **Confirmed** R1 |
| A-003 | Corpus scale: ~173K SDN threads + ~2.34M Reddit records; full corpus ~4-6M records. | High | Cost projections under-scoped. | **Confirmed live** R3 |
| A-004 | ADEA + CODA = L1 ground truth; Excel files under `External Data\Official Dental *\`; 10-yr coverage 2015-16 → 2024-25. | High | Anchor strategy collapses. | **Confirmed live** R3 |
| A-005 | V1 internal-only; no Reddit/SDN ToS work. | High | Legal exposure if external. | **Confirmed** R1 |
| A-006 | L1 immutable, `Trust_Score = 1.0`, no overwrite. HITL exception. | High | Wrong if L1 has gaps. | **Confirmed** R1 |
| A-007 | Hardware: GTX 1080 8 GB VRAM + 64 GB RAM. Pascal, no FP16 tensor cores. | High | Wrong throughput. | **Confirmed** |
| A-008 | Marketing/sales/pricing/competitor docs out of scope. | High | Over-documentation. | **Confirmed** R1 |
| A-009 | `tools/graphrag/` MCP context server before V1 product code. | High | Coding agent without retrieval. | **Confirmed** |
| A-010 | TDD discipline once implementation begins. | High | Regressions. | **Confirmed** |
| A-011 | Conflict resolution: L1-clash → temporal → trust → signed-graph → web-verify → HITL. | High | Wrong order → noise. | **Confirmed** R3 |
| A-012 | Hybrid cascade extraction. (R5 superseded by 5-pass — see A-055.) | High | Single-tier wastes resources. | **Superseded** R5 by A-055 |
| A-013 | Source-pluggable; tool ingests dumps; crawler separate. | High | V2 rewrite. | **Confirmed** |
| A-014 | 5-tier trust ladder. | High | Wrong model. | **Confirmed** |
| A-015 | V1 ships all 3 graph layers. | High | Scope wrong. | **Confirmed** R2 |
| A-016 | Downstream agents = V2. | High | V1 half-done swarm. | **Confirmed** |
| A-017 | New node/edge types require HITL approval. | High | Ontology sprawl. | **Confirmed** |
| A-018 | Cost discipline is a design layer. | High | Budget overrun. | **Confirmed** |
| A-019 | HALO per-edge-type half-life. | High | Bad temporal weighting. | **Confirmed** R3 |
| A-020 | V1 slice: ADEA L1 + 1 subreddit L5. | High | Wrong slice. | **Confirmed** R2 |
| A-021 | Tool ingests dumps; outbound MCP to crawler. | High | Doubles V1. | **Confirmed** |
| A-022 | Outbound MCP minimum: `register_dump`, `get_gaps()`, `query_graph(...)`. | Med | Wrong scope. | Updated R5: also `is_url_ingested`, `get_topic_state`, `get_pending_verifications` (Mahyar OK'd). |
| A-023 | Two GraphRAG deployments. | High | Confusion. | **Confirmed** |
| A-024 | Goal = full corpus; V1 slice = subset; architecture must extrapolate. | High | Won't scale. | **Confirmed** |
| A-025 | Research live-verified. | High | If picks change, ADRs change. | **Confirmed** |
| A-026 | Kùzu acquired by Apple. Candidates: LadybugDB / Graphiti+Neo4j / Postgres+AGE+pgvector. | High | Wrong pick → rebuild. | **Confirmed live** R3 |
| A-027 | Bitemporal edges (Graphiti/Zep). | High | Lose "when did we know what". | **Confirmed** R3 |
| A-028 | Trust-tier schema = Wikidata `rank` + `references` + `qualifiers`. | High | Conflict + retrieval misbehave. | **Confirmed** R3 |
| A-029 | ER = BGE-small HNSW blocking → DITTO/DistilBERT reranker. | High | Alias accuracy collapses. | **Confirmed** R3 |
| A-030 | Opinion clustering = signed-graph community detection. | Med-High | Wrong consensus. | **Confirmed** R3 |
| A-031 | LLM-as-judge = same-tier same-year tie-breaks only; three-vendor cross-check required. | High | Systematic bias. | **Confirmed** R3+R4 |
| A-032 | Outlier preservation `Status: Anomaly` + `prescient_correct`. | High | Lose Reddit-knows-policy-change value. | **Confirmed** R3 |
| A-033 | User-credibility V1 = 10-feature hand-weighted, source-aware split (Reddit vs SDN); V1.1 = logistic regression. | Med-High | Bad rubric → bad trust weighting. | **Confirmed direction** R3 |
| A-034 | Constrained decoding (local) = XGrammar/XGrammar-2. | Med | Lib change if regresses. | **Confirmed** R3 |
| A-035 | NER = GLiNER2 (EMNLP 2025). | High | Wrong version pin. | **Confirmed** R3 |
| A-036 | Prompt-cache TTL = explicit `ttl: 3600`. Lint-enforced. | High | Cost math breaks. | **Confirmed live** R3+R4 |
| A-037 | DSPy GEPA replaces MIPROv2. | Med | Fall back if regresses. | **Confirmed live** R3 |
| A-038 | Top 5 cost levers. V1 slice budget < $25. | High | Replanning. | **Confirmed live** R3 |
| A-039 | Memgraph definitively rejected. | High | Blocks V2 self-host. | **Confirmed live** R3 |
| A-040 | Gemini 1.5 Flash deprecated/404'd; substitute = 2.5 Flash-Lite. | Med | Vendor swap. | **Confirmed live** R3+R4+R5 |
| A-041 | GraphRAG ref arch = Microsoft LazyGraphRAG. | Med | Stay on paper if OSS slips. | **Confirmed live** R3 |
| A-042 | Data in `External Data\`. | High | Ingestion plugins wrong. | **Confirmed live** R3 |
| A-043 | SDN ≠ Reddit metadata. Author namespaces don't overlap. | High | Cross-source collisions. | **Confirmed live** R3 |
| A-044 | ADEA + CODA = Excel files. SQLite for V1 L1 side store. | High | Migration plan. | **Confirmed live** R3 |
| A-045 | Bake-off sample = r/DentalSchool + 5 ADEA Excel slices. | Med | Different sample if Mahyar prefers. | **Confirmed** R5 (Mahyar OK'd) |
| A-046 | Multi-vendor LLM strategy locked from V1. | High | Vendor lock-in. | **Confirmed** R4 |
| A-047 | Model gateway = LiteLLM SDK + custom `LLMClient` ABC. | High | Perf regression. | **Confirmed live** R4 |
| A-048 | MCP-per-component policy = three-tier. | High | Over-engineering. | **Confirmed live** R4 |
| A-049 | V1 Tier 1 (MCP) = Ingestion outbound + Graph retrieval inbound. | High | Broken integration. | **Confirmed live** R4 |
| A-050 | Per-task model matrix. (R5 superseded — see A-056.) | High | Cost/accuracy regression. | **Superseded** R5 by A-056 |
| A-051 | Langfuse for LLM telemetry. | Med | Lib swap. | **Confirmed** R4 |
| A-052 | Three-vendor accounts required from V1 (Anthropic + OpenAI + Google). | High | Cannot deliver judge. | **Confirmed direction** R4 |
| A-053 | Gateway runner-up = Portkey self-hosted. | Med | Easy swap. | **Confirmed live** R4 |
| A-054 | R-009 unresolved Q's parked. | Med | Doesn't block bootstrap. | Open |
| **A-055** | **Extraction = 5-pass architecture (R5)**: Pass 1 structural (`$0`, deterministic graph build, fuzzy-match canonical), Pass 2 cheap labels (Reddit flair / SDN category → Topic, $0), Pass 3 semantic clustering (BGE-small + signed-graph community detection, ~$0 local GPU), Pass 4 selective LLM (utility filter applies here only: 3a Gemini Flash-Lite, 3b Haiku 4.5, 3c Sonnet 4.6), Pass 5 knowledge surfacing (retrieval-time, $0). **The graph preserves every post; the utility filter only avoids LLM tokens at Pass 4.** | High | Wrong architecture → 10× cost. | **Confirmed** R5 — supersedes A-012 |
| **A-056** | **Per-task model matrix R5-refined**: Pass-3 cluster summary + Pass-4 sentiment = Gemini 2.5 Flash-Lite. Pass-4 interview-Q + conflict candidates = Haiku 4.5. Hardest ~2% = Sonnet 4.6. Embeddings + reranker local. LLM-as-judge (conflict only, not extraction) = 3-vendor. HITL summary = Gemini 2.5 Flash-Lite. | High | Cost/accuracy regression. | **Confirmed** R5 — supersedes A-050 |
| **A-057** | **Utility filter heuristics (Pass 4 only)**: drop `[deleted]`/`[removed]`/AutoModerator/known-bots/ultra-short-non-replies/generic-no-entity-no-stance/crosspost-dupes. Filter is reversible — the `Post`/`Comment` node remains in the graph; only the `LLMExtraction` edge is skipped. Marketers can later request sentiment on filtered subset. | High | Either over-filter (lose `prescient_correct` signal) or under-filter (waste tokens). | **Confirmed** R5 |
| **A-058** | **Daily incremental re-ingest cadence** (R5). Drives orchestrator decision. | High | Wrong if cadence is actually weekly or one-off — would over-engineer scheduling. | **Confirmed** R5 |
| **A-059** | **Orchestrator = Prefect 3** (R5 — supersedes ADR-010 "pending"). Daily cadence + retries + observability dashboards favor Prefect over plain Python or Dagster at V1 scale. | High | Wrong if cadence changes or Dagster becomes clearly better at V1.x. | **Confirmed** R5 — see ADR-010 |
| **A-060** | **Versatile retrieval surface required from V1** (R5). PMs / marketers / sales / agents all use the same MCP primitives + convenience tools (`get_top_concerns_by_audience`, `get_sentiment_distribution`). Don't over-specialize. | High | Over-specialized retrieval → painful V2 rework. | **Confirmed** R5 |
| **A-061** | **Canonical school + program list can be derived from ADEA + CODA Excel**, OR Mahyar may provide a curated list. V1 implementation will derive from Excel; replaces with curated when/if provided. | High | If derived list is incomplete, alias-snap accuracy drops at V1 start; HITL catches gaps. | Direction confirmed R5; curated list = soft dependency |
| **A-062** | **`tools/graphrag/` reindex trigger = both** git-hook (opt-in via `.git/hooks/post-commit`) AND manual `index.py --incremental`. | Med | Wrong if git-hook is too slow for active dev iteration. | **Confirmed** R5 |
| **A-063** | **Pass 1 fuzzy match library = `rapidfuzz` with `token_set_ratio`**. Threshold: ≥ 95 auto-accept; < 95 defers to Pass 2/3/4 for context-aware resolution. | High | Library swap if accuracy regresses; threshold tuning expected. | **Confirmed** R5 |
| **A-064** | **Pass 4 sentiment runs broadly on Pass-4-surviving posts**. Cheap by design (Gemini 2.5 Flash-Lite). Mahyar called sentiment out specifically as cheap-and-useful. | High | Cost overrun if filter is too permissive; mitigated by per-task cost-regression test. | **Confirmed** R5 |
| **A-065** | **Pass 2 promotes existing Reddit flair + SDN category to `Topic` nodes**. Both `link_flair_text` + `link_flair_css_class` are extracted from Reddit; `category` from SDN. New `Topic` types from Pass 3 clustering require HITL approval (A-017). | High | Wrong if certain subreddits don't expose flair fields in the dumps; mitigated by adapter null-handling. | **Confirmed** R5 |
| **A-066** | **V1.5 scope = `Everything` bundle** (forum polish + DB connector + cross-graph mapping + web HITL UI + multi-level graph viewer + iterative cull/propose loop + web-search conflict resolution + PM/Social/Marketing dashboards), ~12-16 weeks across three sub-slices V1.5a/b/c. | High | If scope slips, gate per sub-slice catches early. | **Confirmed** V1.5-R1 (2026-05-24) |
| **A-067** | **Forum types in V1.5 = Reddit + SDN only**. Discord / Discourse / Stack Exchange deferred to V1.6. | High | Wrong if a customer demands Discord ingestion at V1.5 timing. | **Confirmed** V1.5-R1 |
| **A-068** | **UI tech stack = Next.js 15 + FastAPI + Pydantic + Zod**. shadcn/ui + Tremor + Sigma.js (WebGL) + TanStack Query. Per ADR-013. | High | Wrong if Mahyar prefers a different stack — would need re-platforming. | **Confirmed** V1.5-R1 |
| **A-069** | **DB engines in V1.5a = Postgres + MySQL + SQLite + Neo4j**. Snowflake / BigQuery / MS SQL / Oracle deferred to V1.6. | High | Wrong if customer presents an unsupported engine; pluggable Protocol mitigates. | **Confirmed** V1.5-R1 |
| **A-070** | **HITL surface in V1.5b = full web UI for all flows**. CLI stays as power-user fallback. | High | Wrong if usability testing shows CLI users prefer CLI-first; mitigated by keeping both. | **Confirmed** V1.5-R1 |
| **A-071** | **Multi-level graph viewer = three separate views/tabs/routes** (Level A / B / C) per ADR-012. | High | Wrong if single-canvas zoom-driven LOD is preferred later; V1.5b UI is independently per-route so refactor cost is bounded. | **Confirmed** V1.5-R1 |
| **A-072** | **Schema-to-graph mapping = auto-suggest + HITL approve/edit**. BGE embeddings on column names + values; same 0.90/0.75 thresholds as V1 alias resolution. Per ADR-015. | High | Wrong if heuristics are off; HITL catches errors. | **Confirmed** V1.5-R1 |
| **A-073** | **Secrets storage for V1.5 = plaintext `.env`**. V1.5-only allowance per single-user local posture. V2 migrates to OS keychain. UI banner shows the plaintext warning on every credential entry. | Med | Risk if user shares the machine or commits `.env`. Mitigated by `.gitignore` + lint + UI banner. | **Confirmed** V1.5-R1 (knowingly accepted) |
| **A-074** | **External DB tier = user-declared at connect-time, default L2**. L1 requires explicit `confirm_l1_immutable=True`. Per ADR-014. | High | Wrong if users default to L1 silently — would corrupt the ADEA-anchor model. | **Confirmed** V1.5-R1 |
| **A-075** | **Feedback loop into next Pass 4 = BAML prompt context + blocklist** (NOT fine-tuning). Per ADR-017. Amended by ADR-018: K=4 examples cap per few-shot collapse research. | High | Wrong if 4 examples insufficient for some templates; settings UI exposes weights for tuning. | **Confirmed** V1.5-R1 + amended V1.5-R2 (research-driven) |
| **A-076** | **Per-team dashboards in V1.5c = PM + Social + Marketing** (three separate dashboards). PM = pain points → feature angles; Social = trending → post angles; Marketing = content gaps → angle suggestions. | High | Risk: three dashboards is a lot of frontend; sub-slice gating catches scope creep. | **Confirmed** V1.5-R1 |
| **A-077** | **Sub-slice sequencing = V1.5a → V1.5b → V1.5c with gates between**. Each sub-slice has its own Verification Before Completion report; the next is blocked until the prior is green. | High | Wrong if parallel work could ship faster; intentional choice for risk control. | **Confirmed** V1.5-R1 |
| **A-078** | **Cluster review trigger = manual** (user opens `/hitl/clusters` when ready). Pass 4 is gated on cluster review status. | High | Wrong if user forgets to review and the pipeline stalls; mitigated by inbox count badge in `/`. | **Confirmed** V1.5-R1 |
| **A-079** | **Pass 3 cluster input = posts + comments together** (V1 behavior preserved). NOT posts-only despite initial preference. | High | Configurable per sweep; can switch to posts-only if cluster quality regresses. | **Confirmed** V1.5-R1 |
| **A-080** | **Auth model for V1.5 = single-user local, no auth**. Backend localhost-bound; UI localhost. V2 adds multi-tenant. | High | Wrong if any multi-reviewer scenario emerges in V1.5; revisit then. | **Confirmed** V1.5-R1 |
| **A-081** | **Web-search provider = Tavily only** (V1.5-R2 user direction; supersedes V1.5-R1 Brave + Tavily). Cross-check via query-rephrasing (signal B) + two-vendor LLM extract-verify (signal C) instead of multi-provider. Per ADR-016 v2. | High | Single-provider risk mitigated by 3-signal majority + escalation to HITL on disagreement. | **Confirmed** V1.5-R2 (2026-05-24) |
| **A-082** | **Brand system = shadcn defaults** for V1.5. No custom palette / typography / logo. V2 multi-tenant theming reopens. | Med | Wrong if Mahyar later wants distinctive branding; cost to switch is bounded (CSS custom properties only). | **Confirmed** V1.5-R2 |
| **A-083** | **Team content-angle generation = Gemini 2.5 Flash-Lite** per ADR-003 cost matrix, but **model-swappable via per-task matrix edit** (no code change). Task name: `team_content_angles`. | High | Wrong if Flash-Lite quality is too low; switch to Haiku in one matrix edit. | **Confirmed** V1.5-R2 |
| **A-084** | **Feedback log retention = append-only, retain forever**. Eviction happens only at the active context-block layer via active-learning hybrid scoring (recency × diversity × similarity × frequency). Per ADR-018. | High | Wrong if disk usage explodes (low risk at V1.5 single-user scale; ~1.5 KB/decision). | **Confirmed** V1.5-R2 (research-driven) |
| **A-085** | **Few-shot examples per BAML template hard-capped at K=4** per 2026 few-shot-collapse research. Blocklist cap = 50 entries (LFU+LRU eviction beyond cap). Per ADR-018. | High | Empirically validated by research; settings page exposes weights for tuning per template. | **Confirmed** V1.5-R2 |
