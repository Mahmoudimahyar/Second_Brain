# ADR-003: Extraction Stack — 5-Pass Architecture (R5 revision)

Status: **accepted** (R5 revision supersedes the prior 3-stage cascade)
Date: 2026-05-20 (initial), revised 2026-05-20 (R5)

## Context

Prior GPT-4o-mini freeform extraction was unsatisfactory. R-003 + R-006 + R-008 + R-009 converged on a hybrid cascade. **R5 (Mahyar's directive)** refined this further:

- Build the structural graph first, deterministically, for ALL data. No filtering.
- Use existing metadata (Reddit flair / SDN category) as cheap labels.
- Cluster semantically with embeddings only.
- LLM tokens spent ONLY at the deep-extraction tier, on a selective utility-filtered subset.
- Graph preserves everything; LLM avoids tokens on low-utility posts.
- Tool must be versatile (PMs / marketers / sales reps / downstream agents).
- Updates are daily.

Constraints unchanged: GTX 1080 Pascal (8 GB VRAM, no FP16 tensor cores), vendor portability (A-046), accuracy bar (F1 ≥ 0.92 on alias resolution, ≥ 0.85 on sentiment, ≥ 0.90 precision on interview-Q).

## Decision

**5-pass extraction architecture.** Each pass operates on the whole corpus; only Pass 4 (LLM tier) applies a utility filter to avoid token spend on low-utility posts. **The graph itself preserves every post and every comment, always.**

### Pass 1 — Structural graph ($0)

Deterministic. No models.

- Adapters per source (ADEA Excel / Reddit JSONL / SDN JSONL) emit canonical records.
- Nodes: `User` (namespaced), `Post`, `Comment`, `Thread`, `Subreddit` / `SDNCategory`, `School` (L1 from ADEA), `Program` (L1 from CODA).
- Edges: `AUTHORED`, `COMMENTED`, `REPLIED_TO`, `BELONGS_TO_THREAD`, `POSTED_IN_FORUM`, `UPVOTED` (Reddit only), `MENTIONS_SCHOOL` (from fuzzy match).
- **Fuzzy entity match** via `rapidfuzz` `token_set_ratio` against the canonical school + program list (≥ 95 % → auto-accept; < 95 → defer to Pass 2/3/4 for context-aware resolution).
- **User-credibility score** computed per ADR-008 (source-aware rubric). Reddit uses karma; SDN uses volume + longevity + on-topic ratio.

### Pass 2 — Cheap labels ($0)

Promote existing metadata. No models.

- Reddit `link_flair_text` / `link_flair_css_class` → `Topic` nodes (e.g., "Advice", "DAT", "Acceptance", "Personal Statement", "Interviews"). Edge: `REFERENCES_TOPIC`.
- SDN thread `category` → `Topic` nodes (e.g., "Pre-Dental", "Dental Students").
- Builds the first layer of topic categorization for free.

### Pass 3 — Semantic clustering (~$0 local GPU)

Local models only.

- Embed every post + comment body via BGE-small (384-d). Pre-compute once; reuse across runs (content-addressable cache).
- HNSW + signed-graph community detection (NOT vanilla Leiden — preserves SUPPORTS/CONTRADICTS opposition).
- Emerges mid-level groupings: "School Selection", "Personal Statement Review", "Interview Prep", "GPA / DAT Anxiety", etc. — **discovered** from data, not declared upfront.
- One cluster summary per cluster (~50-200 clusters expected V1 slice) via Gemini 2.5 Flash-Lite — ~$0.10-1.00 total for the cluster-summarization step.
- HITL approval for new `Topic` nodes per A-017 (ontology sprawl prevention).

### Pass 4 — Selective deep extraction ($35-50 per full sweep est.)

LLM tier. **Utility filter applies HERE only.**

#### Utility filter

A post is **skipped at Pass 4** if ANY of:

| Drop condition | Examples |
|---|---|
| Tombstone | `[deleted]`, `[removed]`, AutoModerator, known-bot list |
| Ultra-short non-reply | `<3 words` AND not a comment-reply in a question thread |
| Generic-no-entity-no-stance | No entity mention from Pass 1 fuzzy + no question/answer structure + no sentiment marker (e.g., "dental students are so beautiful") |
| Crosspost dupe | Same `content_hash` as already-processed post in this sweep |

**Important**: the filter is reversible. The `Post` / `Comment` node remains in the graph; only the `LLMExtraction` edge for that post is not created. A marketer asking "what's the vibe in r/predental during exam season?" can later run sentiment on the previously-filtered subset by clearing the filter on a topic.

#### Stage 3a — Cheap API (default workhorse)

- **Gemini 2.5 Flash-Lite** ($0.10/$0.40 std; batch discount). Use for:
  - Sentiment classification (broad, low cost, high volume).
  - Pass-3 cluster summarization.
  - Initial pass at interview-Q candidates (the high-recall sweep).
- Confidence ≥ 0.9 commit. 0.6-0.9 route to Stage 3b. < 0.6 → HITL or `Status: Anomaly`.

#### Stage 3b — Mid API (when Flash-Lite uncertain)

- **Claude Haiku 4.5** (batch $0.50/$2.50 + 90 % cache-read with `ttl: 3600`).
- Use for nuanced extraction that Flash-Lite couldn't structure confidently:
  - Specific interview-question parsing (multi-part questions, school-specific context).
  - Conflict-candidate marking when paired with L1 entities.

#### Stage 3c — Premium API (hardest ~2%)

- **Claude Sonnet 4.6** (batch $1.50/$7.50).
- Routed only when Haiku self-confidence < 0.7 AND the case has high downstream impact (e.g., a forum claim challenging L1).

### Pass 5 — Knowledge surfacing ($0 retrieval-time)

MCP retrieval primitives (`query_graph`, `get_canonical_entity`, etc. + convenience tools `get_top_concerns_by_audience`, `get_sentiment_distribution`). Versatile by design — PMs, marketers, sales reps, downstream agents all use the same surface.

## Constrained decoding + cache

- **XGrammar / XGrammar-2** for any local-model schema-constrained decoding.
- **Content-addressable extraction cache** for Pass 4: key = `hash(post_content + prompt_id + prompt_version + schema_hash + model + model_version)`. 90-99 % off reruns.
- **Prompt-cache `ttl: 3600`** explicit pinning on every Anthropic call. Lint-enforced.

## Pre-task model matrix (replaces the old per-task addendum)

| Task | Default model | Fallback / escalation | Switch criteria |
|---|---|---|---|
| Pass 1 fuzzy entity match | `rapidfuzz` (CPU) | — | — |
| Pass 2 label promotion | None (direct field extraction) | — | — |
| Pass 3 embeddings | local BGE-small | — | — |
| Pass 3 cluster summary | Gemini 2.5 Flash-Lite | Haiku 4.5 | only if Flash-Lite cluster summary is incoherent (heuristic) |
| Pass 4 sentiment | Gemini 2.5 Flash-Lite | Haiku 4.5 | F1 on gold-set < 0.85 → switch |
| Pass 4 interview-Q harvest | Haiku 4.5 | Sonnet 4.6 | Haiku confidence < 0.7 |
| Pass 4 conflict candidates | Haiku 4.5 | Sonnet 4.6 | Same |
| Pass 4 hardest 2% | Sonnet 4.6 | — | (this is already the escalation tier) |
| LLM-as-judge (conflict resolution, NOT extraction) | 3-vendor mandatory (Sonnet 4.6 + Gemini 2.5 Flash + GPT-4.1-mini) | HITL | < 2/3 agreement → HITL (per ADR-006) |
| HITL summary generation | Gemini 2.5 Flash-Lite | Haiku 4.5 | — |

**Dropped**: Gemini 1.5 Flash (404'd 2026; sub = 2.5 Flash-Lite). Kept as alternates: GPT-5.4-nano/mini, Grok 4.1-Fast.

## Amendment — routing refresh (2026-05-30)

Re-researched against current (May 2026) vendor-doc pricing + benchmarks
(`.agent/reports/v1.7-model-routing-research-2026-05-30.md`). Implemented in
`src/gateway/api.py` `_wire_extraction_models`; **all IDs env-overridable
(`SECBRAIN_MODEL_*`)**.

| Task | Was | Now (default) | Fallback | Note |
|---|---|---|---|---|
| Pass 4 sentiment / Pass 3 summary / HITL | Gemini 2.5 Flash-Lite | **Gemini 2.5 Flash-Lite (kept)** | — | verified still cheapest GA ($0.10/$0.40); aggregator "cheaper" options were mispriced |
| Pass 4 interview-Q | Haiku 4.5 | **GPT-5 mini** ($0.125/$1) | Haiku 4.5 | ~3× cheaper, ranked ≥ for extraction; low-stakes |
| Pass 4 conflict-candidate | Haiku 4.5 | **Haiku 4.5 (kept)** | GPT-5 mini | precision-critical (feeds resolver) → flip only after on-data A/B (gap G2) |
| Pass 4 hardest ~2% | Sonnet 4.6 | **GPT-5.4** ($2.50/$15) | Sonnet 4.6 | verified reasoning leader, cheaper than Sonnet |
| Fallback (was GPT-4.1-mini) | GPT-4.1-mini | **GPT-5 mini** | — | GPT-4.1-mini superseded |
| LLM-judge (3-vendor) | Sonnet + Gemini 2.5 Flash + GPT-4.1-mini | **Sonnet 4.6 + Gemini 3.5 Flash + GPT-5 mini** (recommended) | HITL | refresh per vendor; family-exclusion intact (factory) |

Notes: `FallbackClient` degrades a bad OpenAI id to the Anthropic model, so an
unverified id costs the *saving*, not the run. Defaults verified vs vendor docs
but **not runtime-pinged** — confirm with one live call before a full run.
DeepSeek (cheapest competent, 4th vendor) deferred per ADR-011. Net cost on
r/predental Pass-4: ~$36 → ~$12 → ~$6 with Batch.

## Consequences

- **Graph is the ground truth.** Pass 4 utility filter doesn't delete data. Retrospective "what about that low-utility comment?" queries remain possible.
- **Pass 1 builds an immediately useful structural artifact** even before any LLM runs. Mahyar can query the graph + user-credibility scores before Pass 4 finishes (or runs at all).
- **Pass 2 surfaces the existing categorization for free** (Reddit flair / SDN category). Downstream consumers can group on those before Pass 3 clustering completes.
- **Pass 3 emerges sub-topics from data** without forcing an upfront ontology. New `Topic` types from clusters require HITL approval (per A-017).
- **Cost compresses dramatically.** Most of the 4-6 M-record corpus only sees Pass 1-3 (free / cheap). Pass 4 runs on a utility-filtered subset, with Stage 3a (Gemini Flash-Lite) as the workhorse for Pass-4 sentiment + cluster refinement.
- **Daily updates feasible.** Incremental: only new posts since last sweep are added in Pass 1; only changed clusters re-summarized in Pass 3; only new posts go to Pass 4. ADR-010 picks Prefect 3 for the scheduler.
- **`prescient_correct` interaction preserved** (ADR-008): low-score outlier posts that get later confirmed by L1 still get retroactive credibility — because they're not filtered from the graph, only from LLM token spend at the time.
- **Versatility for PMs / marketers / sales** baked into the design: convenience tools wrap the primitives but use the same underlying cleaned graph.

## Alternatives considered

- **Single-pass (LLM on everything)**: $$$ + slow + wasteful on Reddit nonsense. Rejected.
- **3-stage vertical cascade (prior ADR-003 form)**: less granular about WHAT is filtered WHEN. Replaced by R5 5-pass.
- **Drop low-utility posts at ingestion time**: kills the `prescient_correct` mechanism + retrospective marketer queries. Rejected.
- **Hand-defined ontology for topic groupings** (no Pass 3 clustering): loses the "discover what's there" property Mahyar wants. Rejected; clustering stays.

## Related docs

- `docs/03-research/research-log.md` R-003
- `docs/03-research/R-006-live-verification.md` R-003 verification + Haiku 4.5 / Gemini Flash-Lite pricing
- `docs/03-research/R-008-cost-accuracy.md` cascade cost levers
- `docs/03-research/R-009-multi-vendor-and-modularity.md` per-task matrix
- `docs/04-architecture/system-overview.md` §2 cascade extraction (R5 rewrite)
- `docs/04-architecture/tech-stack.md` Extraction stack + per-task matrix
- `docs/00-bootstrap/assumptions.md` A-012, A-029, A-034-A-038, A-050, A-055..A-060 (R5 additions)
- `docs/05-features/01-slice-trust-tier-canonicalize/plan.md` 5-pass phase split

## Related code

- `src/extraction/pass1_structural.py` — adapters + fuzzy match + credibility
- `src/extraction/pass2_labels.py` — flair / category promotion
- `src/extraction/pass3_clustering.py` — embeddings + signed-graph
- `src/extraction/pass4_sweep.py` + `src/extraction/pass4_runners.py` — Stage 3a/b/c routing + sweep orchestration
- `src/extraction/utility_filter.py` — drop heuristics
- `src/extraction/cache.py` — content-addressable cache
- `src/gateway/` — multi-vendor abstraction
- `src/conflict/baml/*.baml` — BAML-style prompt templates (V1.5c; the only BAML present in V1)
