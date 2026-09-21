# Known Issues

> Populated during implementation. Each issue gets an ID, a category, a severity, a workaround if any, and a resolution plan.

## Slice-spec issues (pre-implementation, identified by R-006 / R-007 / R-008 / R-009)

| ID | Issue | Category | Severity | Workaround | Resolution plan |
|---|---|---|---|---|---|
| KI-001 | **Anthropic prompt-cache default TTL changed from 1h to 5m in March 2026** — silent regression for unpinned writes; cache-creation cost inflates 20-32%. | Cost | High | Explicit `ttl: 3600` on every cache write. Lint enforced. | `lint_ttl_pinning.py` rejects any call site without explicit TTL; ABC layer in `src/gateway/` sets a default that the lint also verifies. (GAP-031) |
| KI-002 | **HNSW indexes degrade under deletion/update workloads** (Kùzu/LadybugDB, Neo4j 5, pgvector) | Performance | Med | Rebuild nightly from canonical embedding store. | Schedule cron task; embeddings live in a Parquet `embedding_store` partitioned by `dump_id`. |
| KI-003 | **AGE Cypher coverage lags Neo4j** — some patterns (e.g., variable-length paths with property filters mid-traversal) may fail or be slow. | Architecture | Med (only if AGE wins bake-off) | Express affected queries in raw SQL with recursive CTEs; benchmark in bake-off. | Bake-off measures this on Q-A through Q-E; if AGE wins despite, document specific query rewrites in V1 ADR-001. |
| KI-004 | **GTX 1080 (Pascal) lacks FP16 tensor cores** — local 8B LLM throughput is impractical for full-corpus sweeps. | Hardware | High | Cascade design — local work limited to GLiNER + embeddings; LLM-heavy steps go to API. | Architectural; no in-slice fix needed. Document for V2 hardware planning. |
| KI-005 | **SDN data has no upvote/score signal** — Reddit-style credibility rubric cannot be applied directly. | Data | High | Source-aware split: Reddit rubric vs SDN rubric (SD-011). | Two parallel rubrics in V1; V1.1 logistic regression learns per-source weights. |
| KI-006 | **r/dentistry subreddit scope is broader than dental-school admissions** (practicing dentists + patients). Mixing it into V1 would dilute signal. | Data | Med | Exclude r/dentistry from V1 slice; sweep separately in a later slice with topic-filtering. | SD-001 picks r/DentalSchool exclusively for V1. |
| KI-007 | **Reddit + SDN timestamps use different formats** (Reddit: Unix epoch int; SDN: ISO-8601 with tz). | Data | Low | Normalizer in ingestion adapter converts to canonical UTC int. | Single conversion utility in `src/ingestion/normalize.py`. |
| KI-008 | **Gemini 1.5 Flash deprecated / 404'd in 2026** — Mahyar named it specifically. | Vendor | Med (had we hard-coded it) | Use Gemini 2.5 Flash-Lite as substitute. | A-040, per-task matrix. |
| KI-009 | **LiteLLM proxy mode has documented throughput regression (1.7-4×) and memory leaks** | Vendor / Performance | High (had we used proxy) | Use LiteLLM SDK mode wrapped in `LLMClient` ABC. | ADR-011 specifies SDK mode. |
| KI-010 | **JudgeBiasBench shows frontier-model LLM-as-judge error >50%** when used broadly. | Eval / Safety | High | Restrict LLM-as-judge to same-tier same-year tie-breaks; three-vendor ≥2/3 agreement (A-031 + A-052). | Hard rule encoded in `src/conflict/resolver.py`. |
| KI-011 | **Author handles overlap is impossible across `reddit:` and `sdn:` namespaces but a person may post under both** | Data / V2 | Low (V1) | Namespace IDs prevent collision; cross-source identity inference is V2. | V2 task: add a `Person` super-node that owns multiple namespaced `User` aliases. |
| KI-012 | **ADEA Report file naming inconsistent across years** (some `SDE1_*.xlsx`, some `SDE2_*.xlsx`, some with `_final` suffix). | Data | Low | Adapter accepts a glob pattern + does header-based schema detection rather than relying on filename. | `src/ingestion/l1_excel_adapter.py` reads headers to map columns. |
| KI-013 | **R-009 unresolved**: V1 gold-set timeline, Gemini-specific cache `ttl` pinning, per-task vs generic MCP tool shape. | Spec | Med | Parked until V1 implementation start. | A-054. |

## Implementation issues (populated during Phase 1+ of plan.md)

Format for added rows:

```
| KI-XXX | <issue summary> | Hardware/Data/Vendor/Performance/etc. | High/Med/Low | <workaround or "none"> | <resolution plan, link to ADR if architectural> |
```

(empty until implementation begins)

## Closure protocol

When an issue is resolved:
1. Move the row to the **Resolved issues** section below with the date + closing commit / ADR reference.
2. Update related tests if the issue had a test workaround.
3. If the resolution changes architecture, link the ADR; if it changes the slice spec, update `decisions.md`.

## Resolved issues

(empty)
