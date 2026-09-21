# ADR-022: Entity-Resolution Modernization (Embeddings + NuNER A/B + LLM-Matcher Fallback)

Status: **accepted** (2026-05-29)
Amends: ADR-003 (extraction stack).

> **Q-030 resolved 2026-05-29 → primary blocking embedder = `Qwen3-Embedding-0.6B`**
> (Apache-2.0, no Gemma-terms gate). Adopted in WP4.2: A/B blocking-recall ≥ BGE-small
> (`.agent/reports/v1.7-wp4.2-embedder-ab.md`); BGE kept as low-VRAM fallback.
> EmbeddingGemma-300M deferred (Decision #1 below reads "EmbeddingGemma primary" at
> authoring time — superseded by this Q-030 outcome).

## Context

ADR-003 fixes the ER cascade as: spaCy + GLiNER2 filter → BGE-small (`bge-small-en-v1.5`,
384-d) HNSW blocking → DITTO/DistilBERT reranker → snap to ADEA canonical list; target
alias F1 ≥ 0.92. The 2026-05-29 SOTA review (R-010) found three things worth changing and
one factual correction:

- **`bge-small-en-v1.5` is a 2023 model.** For blocking *recall* it is fine but dated.
  **EmbeddingGemma-300M** (best MTEB <500M, ~200 MB, Sept 2025) and **Qwen3-Embedding-0.6B**
  (Jun 2025) are strictly better at similar/2× footprint — both run on the GTX 1080.
- **DITTO is no longer SOTA for entity matching.** GPT-4-class LLM matchers meet/beat
  fine-tuned PLM matchers (Peeters & Bizer arXiv 2310.11244; OpenSanctions Pairs 2026). DITTO
  remains a *good, cheap, low-latency* choice for **closed-world snap-to-canonical**, but the
  hard/ambiguous tail benefits from an LLM matcher.
- **GLiNER2 still a sensible 2025 zero-shot NER choice**, but it enumerates spans, so very
  long program names can be missed; **NuNER-Zero** (token-classifier, arbitrary-length spans)
  is worth an A/B. **Factual correction:** GLiNER2 is an **EMNLP 2025 *System Demonstrations***
  paper, not main-track — fix the citation in ADR-003 / tech-stack.
- **Current alias gold is trivial** (verbatim-substring; F1 = 1.000 — GAP-044). The 0.92
  target is currently met on a distribution that cannot fail. This must be fixed or the
  metric is meaningless (handled in V1.7 / GAP-044).

## Decision

1. **Upgrade the blocking embedder** from `bge-small-en-v1.5` to **EmbeddingGemma-300M**
   (primary) behind the existing `EmbeddingService` Protocol; keep BGE-small as a fallback
   for low-VRAM. Re-measure blocking recall@k on the alias gold; ship the upgrade only if
   recall ≥ current. Per-task matrix entry updated.
2. **Add an LLM-matcher fallback** for the **low-confidence reranker band** only. DITTO
   stays the default closed-world matcher; when DITTO/DistilBERT score is in the ambiguous
   band (e.g. 0.45–0.75, calibrated), escalate that pair to an LLM matcher via the gateway
   (cheap tier first per ADR-023). Auto-accept high, reject low, LLM-resolve the middle.
   This concentrates LLM spend on the ~few % of hard aliases.
3. **A/B NuNER-Zero vs GLiNER2** on the long-program-name failure class; adopt whichever
   wins on the (rebuilt, non-trivial) gold set. No default change until measured.
4. **Stop calling DITTO "SOTA"** in the docs — it is a "strong, cost-efficient closed-world
   matcher; LLM-matcher fallback for the hard tail."

## Consequences

- ER quality on hard/ambiguous aliases improves without paying LLM cost on the easy 95%.
- New per-task matrix rows: `entity_match_hard` (LLM matcher, cheap→escalate); embedder swap.
- Requires the rebuilt adversarial gold set (paraphrase / abbreviation / misspelling /
  substring-trap) to *measure* any of this — otherwise we cannot tell if it helped (GAP-044).
- EmbeddingGemma adds a model download + license check (Gemma terms) — note in deps.
- Vendor-lock rule unaffected: LLM matcher calls go through `src/gateway/` like everything else.

## Alternatives considered

- **Replace DITTO entirely with an LLM matcher.** Rejected for V1 — latency/cost on 500K
  threads; closed-world snap doesn't need it for the easy majority.
- **Keep bge-small.** Acceptable but leaves cheap recall on the table; we upgrade behind the
  Protocol so rollback is one line.
- **Qwen3-Embedding-0.6B as primary** instead of EmbeddingGemma. Viable; chosen as the
  documented alternate (slightly larger). Pick by measured recall on the gold set.

## Related docs
- `docs/03-research/R-010-sota-review-2026-05.md` (EmbeddingGemma arXiv 2509.20354; Qwen3-Embedding; LLM entity matching arXiv 2310.11244; GLiNER2 EMNLP 2025 Demos)
- `docs/11-decisions/ADR-003-extraction-stack.md`, `docs/04-architecture/tech-stack.md`
- `docs/00-bootstrap/gap-register.md` GAP-044 (gold-set triviality)

## Related code (to be created/changed in V1.7)
- `src/embeddings/qwen_embedder.py` — Qwen3-0.6B adapter behind `EmbeddingService` (Q-030 → Qwen3, Apache-2.0); `evals/blocking_recall.py` — BGE-vs-Qwen3 A/B harness
- `src/er/llm_matcher.py` — `GatewayLLMMatcher` (gateway `ENTITY_MATCH_HARD`, cheap tier); `src/extraction/pass1_mention_extractor.py` — borderline-band gating (auto-accept / LLM / reject); `tests/er/test_llm_matcher_fallback.py`
- `evals/build_alias_gold.py` — extend to adversarial/fuzzy/abbreviation cases
- `tests/er/test_llm_matcher_fallback.py`, `tests/embeddings/test_gemma.py`
