---
adr: 018
title: Feedback log retention + active-learning context curation
status: accepted
date: 2026-05-24
deciders: Mahyar, Claude
supersedes:
superseded_by:
amends: ADR-017
revision_history:
  - 2026-05-24 — proposed.
  - 2026-05-25 — accepted. V1.5b shipped the two-layer architecture: append-only `feedback_log` SQLite (DB-trigger enforced) + `FeedbackContextLoader` with K=4 positive examples + ≤50 blocklist entries + hybrid LFU+LRU eviction + `feedback_context_hash` in the Pass-4 cache key. The few-shot collapse research finding is honored (K=4 hard cap). The active-learning instrumentation (`context_uncertainty`) is collected but not consumed — V1.6 candidate. Live quality-lift measurement is gated on W1-7. No spec drift.
---

# ADR-018 — Feedback log retention + active-learning context curation

## Context

ADR-017 (v1) decided that user HITL decisions get fed back into Pass 4 via BAML prompt context blocks: up to 20 accepted examples + up to 50 rejected patterns. Mahyar asked (V1.5-R2 2026-05-24) for an in-depth research-driven decision on retention policy.

Research findings (2026-05-24 web search log):

- **"Few-shot collapse" (2026)** — adding more than 4 in-context examples actively degrades GPT-5 + Claude 4.7 task performance. The original ADR-017 cap of 20 examples is wrong; it would hurt extraction quality rather than help it.
- **Active in-context example selection** — TF-IDF + stratified sampling outperforms larger example pools. The 2024-2026 research consensus: 2–4 examples chosen via uncertainty + diversity + similarity scoring beats 20 examples chosen by recency.
- **Active learning for RLHF** — Active Preference Optimization (APO) and Dual Active Learning patterns demonstrate that the *selection policy* matters more than the *log size*. The log can be unbounded; only the active example set should be curated.
- **DSPy `BootstrapFewShot`** — the canonical pattern. Score candidate examples on training signal, select top-K with diversity constraint.
- **Log retention industry practice** — append-only logs are the norm for compliance + replay. Eviction happens at the "active surface" layer (cache / context window), not the log itself.
- **LFU vs LRU** — hybrid strategies (recency + frequency) outperform pure-recency or pure-frequency on mixed access patterns.

## Decision

Two-layer architecture: an **append-only feedback log** that retains every decision forever, plus a separately-curated **active context block** that selects ≤ 4 positive examples + ≤ 50 blocklist entries per BAML template at extraction time. The active block uses an active-learning hybrid scoring function.

### Layer 1 — Feedback log (immutable, append-only)

1. **`feedback_log` SQLite table** retains every HITL decision forever. No eviction, no rotation, no truncation. Schema per ADR-017 (revised):
   ```
   feedback_id            TEXT  PRIMARY KEY
   corpus_id              TEXT  NOT NULL
   item_type              TEXT  NOT NULL
   pattern                TEXT  NOT NULL
   pattern_canonical      TEXT  NOT NULL           -- normalized form for matching
   verdict                TEXT  NOT NULL
   refinement             TEXT
   pattern_embedding      BLOB                     -- BGE-small embedding
   prompt_template_id     TEXT                     -- which BAML template the decision applies to
   decided_by             TEXT  NOT NULL
   decided_at             DATETIME NOT NULL
   applied_in_sweep_first TEXT
   review_session_id      TEXT
   confidence_at_decision REAL                     -- the system's pre-decision confidence
   ```
2. **Rationale**: compliance, replay, future fine-tuning (ADR-004 DSPy GEPA needs ≥ 500 decisions to train), debugging quality drift, audit. The log is the source of truth. Disk cost is negligible (1 KB / decision × 10K decisions = 10 MB).
3. **No eviction policy.** A 12-month-old decision that hasn't been touched stays in the log indefinitely.

### Layer 2 — Active context block (curated per extraction call)

4. **`FeedbackContextLoader.build(corpus_id, prompt_template_id) -> ContextBlock`** queries `feedback_log` and returns ≤ 4 positive examples + ≤ 50 blocklist entries.

5. **Positive-example selection (active learning hybrid score)**. For each candidate example, compute:
   ```
   score = w_relevance × cosine(example.embedding, template.signature_embedding)
         + w_recency  × exp(-(now - example.decided_at) / half_life)
         + w_diversity × min_distance(example, already_selected)
         + w_freq      × normalize(times_this_pattern_appeared)
   ```
   - Default weights: `w_relevance=0.4, w_recency=0.2, w_diversity=0.3, w_freq=0.1`.
   - Default `half_life = 90 days`.
   - Selection: greedy top-K (K=4) with diversity constraint — the next selection must have `min_distance ≥ 0.15` from all prior selections.
   - **Hard cap K = 4** per few-shot collapse research; configurable down to 0 if Mahyar wants no examples for a given template.

6. **Blocklist selection (different policy from examples)**:
   - Blocklist entries are *constraints*, not examples — adding more is safe (no few-shot collapse risk).
   - **Hard cap = 50** entries per template. If `feedback_log` has > 50 rejections, evict via hybrid LRU+LFU:
     ```
     evict_score = w_age × age_days + w_unused × days_since_last_violation - w_freq × hits
     ```
   - Most-recently-violated rejections + frequently-recurring categories stay.
   - Blocklist entries beyond cap stay in the log but don't appear in prompts. They are still enforced post-hoc by the embedding-similarity filter (cosine > 0.92).

7. **Per-template scoping**: an example tagged `prompt_template_id='extract_sentiment'` only appears in `extract_sentiment` context blocks. Cross-template fan-out is opt-in via a `tags=['cross-template']` flag.

8. **Cache invalidation**: the Pass-4 content cache key includes `feedback_context_hash` = `sha256(serialized_context_block)`. Any change to the selected examples or blocklist (e.g., a new HITL decision shifts the top-4) invalidates only the affected template's cache entries — not the whole corpus cache.

9. **Replay-friendliness**: every audit-log row for a Pass-4 call records both `feedback_log_count` (how many decisions existed at call-time) AND `feedback_context_hash` (which specific block was used). Reproducing a past extraction means re-deriving the block from the log as it existed at that timestamp (the log is append-only so this is trivially recoverable via `feedback_id <= max_id_at_timestamp`).

10. **Curation tunability**: `/settings/feedback-loop` exposes the weights + half-life as numeric inputs. Defaults shown above. Changes write a `feedback_loop_policy` audit row.

11. **Active-learning instrumentation**: every extraction emits a `context_uncertainty` metric — the entropy of the LLM's confidence distribution given the context. This metric drives a V1.6 candidate task: auto-prioritize HITL items that would resolve the highest-entropy regions.

## Consequences

**Positive:**
- Drops the catastrophic risk of few-shot collapse from the V1.5b feedback loop. Max 4 examples is research-aligned.
- Append-only log is the canonical safe pattern. We never lose data; eviction is recoverable.
- Two-layer split is clean: ops (log) vs ML (context). Each can evolve independently.
- Diversity constraint prevents the top-K examples from being four near-duplicates of the same accepted pattern.
- Hybrid LFU+LRU blocklist eviction keeps the prompt practical without forgetting "this category keeps coming up."
- Per-template scoping prevents cross-task pollution.
- Replay invariant preserved — V1's reproducibility NFR continues to hold.

**Negative:**
- The 4-example hard cap is a regression on ADR-017's 20. Some users may find this surprising; explained in `/settings/feedback-loop` copy with a citation to the few-shot collapse research.
- Computing the active score on every Pass-4 init adds ~5-20ms per template. Acceptable.
- The diversity constraint requires storing embeddings on every `feedback_log` row. 384-dim × 4 bytes = 1.5 kB per row. At 10K decisions = 15 MB. Fine.
- Manual override is required if a user wants > 4 examples. We do not expose a way to override the few-shot cap; we expose a way to expand the blocklist instead.

**Neutral:**
- Logs grow forever. SQLite file growth is bounded by usage at fully-acceptable rates for V1.5 (single-user); V2 multi-tenant may revisit. Worst-case mitigation: archive log entries older than N years to Parquet cold storage.
- The active-learning instrumentation (`context_uncertainty`) is collected but not yet consumed by any feature. V1.6 candidate.

## Alternatives considered (and rejected)

- **Keep 20-example default (ADR-017 v1)** — rejected. Directly contradicts 2026 few-shot collapse findings.
- **LRU eviction of the feedback log** — rejected. Loses replay + future fine-tuning data. The log is cheap; deletion is expensive.
- **No active selection, just take the last 4 examples by recency** — rejected. Diversity-blind selection produces four near-duplicates of the most-recently-reviewed pattern.
- **Use DSPy BootstrapFewShot directly to choose examples** — appealing, but DSPy GEPA is V2 per ADR-004. The hybrid score here is a lightweight ancestor; we can migrate to BootstrapFewShot when GEPA lands.
- **Per-corpus global eviction at N decisions** — rejected. Mahyar's corpora may have wildly different volumes; a global cap penalizes the high-volume one.

## Implementation

V1.5b, alongside the cluster-cull + node/edge proposal HITL flows. Code:

```
src/extraction/
  feedback_context.py   # FeedbackContextLoader + ContextBlock + scoring functions
  feedback_log.py       # SQLite ORM layer; append-only invariant enforced at DB level
  blocklist_filter.py   # post-hoc cosine-similarity filter
  cache.py              # extended cache-key (feedback_context_hash)

src/web/routes/
  settings.py           # /api/v1/settings/feedback-loop endpoints

web/src/app/settings/feedback-loop/page.tsx
  # Renders active context + blocklist; weight sliders; preview "what would change if I edit"
```

Migration from ADR-017 v1:
- `feedback_log` schema unchanged (was already append-only in v1).
- Hard cap drops 20 → 4 for examples (immediate; one-line config).
- Add diversity constraint to selector (new code).
- Blocklist cap stays at 50; add LFU+LRU eviction logic.

## References

- ADR-017 — feedback loop via BAML prompt context (this ADR amends the cap + selection policy)
- ADR-004 — BAML / DSPy GEPA (future fine-tuning consumer of the log)
- ADR-006 — conflict resolution + LLM-as-judge restrictions
- V1.5-R2 user direction: "Please do an in-depth research and determine what would be the best case for us and stick with that"
- Research log 2026-05-24:
  - [When More Examples Make Your LLM Worse: Few-Shot Collapse — Medium, Feb 2026](https://shuntaro-okuma.medium.com/when-more-examples-make-your-llm-worse-discovering-few-shot-collapse-d3c97ff9eb01)
  - [Active Learning Principles for In-Context Learning — arxiv 2305.14264](https://arxiv.org/pdf/2305.14264)
  - [Active Example Selection for In-Context Learning — arxiv 2211.04486](https://arxiv.org/pdf/2211.04486)
  - [LFU vs LRU eviction policy choice — Redis blog](https://redis.io/blog/lfu-vs-lru-how-to-choose-the-right-cache-eviction-policy/)
