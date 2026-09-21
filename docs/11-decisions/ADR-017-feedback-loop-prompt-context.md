---
adr: 017
title: Iterative feedback loop — BAML prompt context + rejected-pattern blocklist
status: accepted
date: 2026-05-24
deciders: Mahyar, Claude
supersedes:
superseded_by:
amended_by: ADR-018
revision_history:
  - 2026-05-24 — proposed.
  - 2026-05-25 — accepted. V1.5b shipped the `feedback_log` SQLite table (append-only triggers enforced), `FeedbackContextLoader`, `BlocklistFilter` (cosine > 0.92), and the Pass-4 cache-key extension via `feedback_context_hash`. ADR-018 supersedes the original v1 cap of 20 examples with 4 (few-shot collapse research) and adds the active-learning hybrid scoring; this ADR is retained for design provenance. No additional drift.
---

# ADR-017 — Iterative feedback loop via BAML prompt context

> **Amended 2026-05-24 by ADR-018**: ADR-018 supersedes the 20-example cap below with **4 examples** (few-shot collapse research) and adds active-learning hybrid scoring + per-template scoping. ADR-018 is the authoritative cap; this ADR's text reflects the original v1 design and is retained for revision history.

## Context

V1 ships Pass 4 (LLM extraction) with a content-addressable cache: identical input + identical prompt = cache hit. The cache makes re-runs cheap but **doesn't learn**. If the user rejects an extracted node type as "this isn't useful for my purposes," the next sweep produces the same rejected output.

V1.5b introduces the cluster-cull + node/edge proposal review loop (HITL flows). For that loop to deliver value, user feedback must influence the next extraction sweep — otherwise we're just adding cosmetic review.

V1.5-R1 Q11 chose **prompt-context injection + rejected-pattern blocklist** over schema-level constraints or fine-tuning. The rationale:
- Prompt context is incremental (no schema migration, no retraining).
- Blocklist enforcement at prompt-and-post-filter levels covers most rejection cases.
- DSPy GEPA fine-tuning (per ADR-004) is the V2 follow-up once HITL log accumulates.

## Decision

**Each Pass-4 BAML template includes a `context_block` placeholder. At extraction time, a `FeedbackContextLoader` queries the `feedback_log` SQLite table, builds a context block containing (a) up to 20 recent `accepted` proposals as positive examples + (b) up to 50 `rejected` patterns as a blocklist, and injects it into the prompt. The blocklist is also enforced post-hoc as a regex/embedding filter on Pass-4 outputs.**

Specifically:

1. **`feedback_log` SQLite table** (V1.5b deliverable):
    ```
    feedback_id        TEXT  PRIMARY KEY
    corpus_id          TEXT  NOT NULL          -- scope feedback per-corpus
    item_type          TEXT  NOT NULL          -- "node_proposal" / "edge_proposal" / "cluster_review"
    pattern            TEXT  NOT NULL          -- the proposed node/edge type + example payload
    verdict            TEXT  NOT NULL          -- "accept" / "reject" / "refine" / "defer"
    refinement         TEXT                    -- user notes on `refine`
    pattern_embedding  BLOB                    -- BGE-small embedding for similarity lookup
    decided_by         TEXT  NOT NULL
    decided_at         DATETIME NOT NULL
    applied_in_sweep   TEXT                    -- which Pass-4 sweep first reflected this decision
    ```
2. **`FeedbackContextLoader.build(corpus_id, prompt_template_id) -> ContextBlock`**:
    - Loads accepted proposals from `feedback_log WHERE corpus_id = ? AND verdict = 'accept'`, ordered by `decided_at DESC LIMIT 20`.
    - Loads rejected patterns similarly, `LIMIT 50`.
    - Filters by per-template relevance: an extraction template for "sentiment" only loads accepted/rejected patterns where `item_type ∈ {'node_proposal:Sentiment*', 'edge_proposal:Expresses*'}`.
    - Produces a `ContextBlock` with two arrays — `examples` (positive) and `blocklist` (negative) — and serializes to ≤ 5 kB of prompt text.
3. **BAML template integration**:
    - Each Pass-4 BAML function (`extract_sentiment`, `extract_interview_q`, `extract_conflict_candidate`, etc.) gains a `context_block: ContextBlock` parameter.
    - The template renders examples as `# Previously accepted patterns:\n- ...` and blocklist as `# Do NOT extract these:\n- ...`.
4. **Post-hoc blocklist filter**:
    - After Pass-4 output is parsed, `BlocklistFilter.apply(extractions, blocklist) -> filtered_extractions` removes any extraction that:
        - exactly matches a rejected pattern (string equality on canonical form), OR
        - has cosine similarity > 0.92 to any blocklisted pattern's embedding.
    - Filtered extractions are NOT silently dropped — they write to `audit_log` with `kind=blocklist_filtered` so the user can audit + override.
5. **Per-corpus scoping**: feedback is corpus-scoped, not global. Decisions for the dental corpus don't pollute decisions for a hypothetical second corpus.
6. **Cache invalidation**: changing the `feedback_log` for a corpus invalidates Pass-4 cache entries for that corpus's affected templates (cache key includes `feedback_context_hash`).
7. **Settings page (V1.5b)**: `/settings/feedback-loop` shows the active context block + blocklist; user can manually edit (remove from blocklist, demote from examples). Edits write back to `feedback_log` with `decided_by='settings_override'`.
8. **Audit + replay**: every Pass-4 call's audit-log row records the `feedback_context_hash` it used, so any output is fully reproducible — and the user can diff "what did Pass 4 see in May vs in June" to explain quality drift.

## Consequences

**Positive:**
- Closes the V1.5b feedback loop without a model-training pipeline. Decisions take effect on the next sweep.
- Per-template + per-corpus scoping prevents context-block bloat or cross-corpus leakage.
- Post-hoc filter is a safety net against prompt-context "soft compliance" — even if the LLM ignores the blocklist in-prompt, the filter catches it.
- Cache invalidation tied to feedback hash means we never serve stale extractions after feedback changes.
- Replay-friendliness via `feedback_context_hash` in audit log preserves V1's reproducibility invariant.

**Negative:**
- Context block bloat is a real risk on long-running corpora. Hard cap (5 kB, 20 examples, 50 blocklist entries) plus LRU eviction by `decided_at`.
- Post-hoc filter false-positives can drop genuinely new patterns that look like rejected ones. Mitigated by writing dropped extractions to audit log (not silently discarded) + the user can promote them via settings.
- Per-template relevance filtering is heuristic. Initial setup picks coarse buckets; tune as the feedback log grows.
- Cache invalidation on every feedback decision means warm-cache hit rate drops post-feedback. Acceptable — feedback events are rare relative to extractions.

**Neutral:**
- Pure prompt-context approach buys time; the eventual DSPy GEPA fine-tuning (ADR-004 V2) is the proper long-term answer once volume justifies.
- Mirrors industry pattern: most "RAG with feedback" systems use in-context examples + blocklists before any fine-tuning.

## Alternatives considered (and rejected)

- **Rebuild BAML schemas from feedback** (rejected types literally removed from schema). Rejected: too deterministic, breaks if user changes their mind, expensive to migrate.
- **Fine-tune Haiku / Gemini from HITL log immediately**. Rejected: ADR-004 already maps this to V2; volume not justified yet.
- **No feedback loop at all in V1.5** — rejected; the loop is the V1.5b headline feature.
- **Feedback as RLHF reward signal** — way out of scope; defer indefinitely.

## Implementation

V1.5b, alongside the cluster-cull + node/edge proposal HITL flows. Code:

```
src/extraction/
  feedback_context.py   # FeedbackContextLoader + ContextBlock + BlocklistFilter
  cache.py              # extended cache-key to include feedback_context_hash
src/hitl/
  cli.py                # gains "show feedback log" command
  queue.py              # commit-decision writes to feedback_log
src/web/routes/
  settings.py           # /api/v1/settings/feedback-loop endpoints
web/src/app/settings/feedback-loop/page.tsx
```

## References

- ADR-003 + ADR-004 (BAML / DSPy GEPA — future fine-tuning path)
- `docs/05-features/03-slice-v1.5b-web-ui/requirements.md`
- V1.5-R1 Q11 (feedback loop) answer
- Industry pattern: RAG with in-context feedback (multiple 2024-2026 papers)
