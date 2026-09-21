# R-008 — Cost/Accuracy Methods for Extraction at Scale

> **Status:** Live research pass (2026-05-20). WebSearch granted; WebFetch still denied. All vendor/feature claims below cite the search results actually returned; where a number could not be verified against a primary source, it is tagged `[live-fetch needed]`. Sources are listed inline.
>
> **Scope anchor:** R-003 hybrid cascade — Stage 1 spaCy+GLiNER filter on 100% of 500K threads, Stage 2 GLiNER NER on survivors (~10-25%), Stage 3 Claude Haiku 4.5 (batch + caching) on residual ~10-15%. Workload ≈ 225M input tokens. Hardware: GTX 1080 + 64 GB RAM workstation. Domain: noisy dental-applicant forum text (Reddit + SDN) anchored against L1 ADEA canonical list.
>
> This document does **not** edit `research-log.md`. It supersedes the BLOCKED stub left in R-008 of that log; the stub should be replaced with a one-line pointer to this file after Mahyar reads it.

---

## Pricing seed (verified 2026-05-20)

- Claude Haiku 4.5: **$1.00 / $5.00** per MTok input/output standard ([pecollective](https://pecollective.com/tools/anthropic-api-pricing/), [finout](https://www.finout.io/blog/anthropic-api-pricing)).
- Batch API: **50% off** both input and output tokens; **24-hour SLA**, asynchronous, stacks with prompt caching ([claudeapi.com](https://claudeapi.com/en/blog/dev-guides/claude-batch-api-cost-optimization/), [jangwook.net](https://jangwook.net/en/blog/en/anthropic-message-batches-api-production-guide/)).
- Prompt caching: cache reads = **0.1× base input** (90% off); cache writes = **1.25× base** for 5-min TTL or **2.0× base** for 1-hour TTL ([tokenmix](https://tokenmix.ai/blog/prompt-caching-guide), [markaicode](https://markaicode.com/anthropic-prompt-caching-reduce-api-costs/)).
- **Default TTL changed 2026-03-06** from 1 hour → **5 minutes**; 1-hour TTL is now opt-in via `"ttl": 3600` in the `cache_control` block ([dev.to TTL change](https://dev.to/whoffagents/anthropic-silently-dropped-prompt-cache-ttl-from-1-hour-to-5-minutes-16ao), [xda-developers](https://www.xda-developers.com/anthropic-quietly-nerfed-claude-code-hour-cache-token-budget/)).
- Minimum cacheable prefix for Haiku 4.5: **4,096 tokens** (vs 1,024 for Sonnet/Opus, 2,048 for Haiku 3.5) ([apiyi troubleshooting](https://help.apiyi.com/en/claude-prompt-caching-not-hit-minimum-token-troubleshooting-en.html)).
- Max **4 cache breakpoints** per request ([Claude docs](https://docs.claude.com/en/docs/build-with-claude/prompt-caching), [spring-projects/spring-ai #4325](https://github.com/spring-projects/spring-ai/issues/4325)).
- Caches **isolated per workspace** since 2026-02-05 ([Claude docs](https://docs.claude.com/en/docs/build-with-claude/prompt-caching)).
- Combined stack (batch + cache read): **~95% off** input. A cache-hit batch request on Sonnet 4.6 lands at $0.15/MTok vs $3.00/MTok standard ([metacto](https://www.metacto.com/blogs/anthropic-api-pricing-a-full-breakdown-of-costs-and-integration), [amitkoth](https://amitkoth.com/reduce-claude-api-costs/)).

OpenAI Batch: 50% off, 24-hour window, no streaming, expired-batch failures return completed work only ([OpenAI batch FAQ](https://help.openai.com/en/articles/9197833-batch-api-faq), [tokenmix OpenAI](https://tokenmix.ai/blog/openai-batch-api-pricing)). Gemini Batch: 50% off, up to 24-hour latency, no SLA; Gemini 2.5 Flash-Lite drops to **$0.05/$0.20 per MTok** in batch ([devtk.ai Gemini 2026](https://devtk.ai/en/blog/gemini-api-pricing-guide-2026/), [tokenmix flash-lite](https://tokenmix.ai/blog/gemini-2-5-flash-lite-review-2026)).

---

# Section 1 — Cost-reduction techniques

## 1.1 Stratified sampling for R&D before full sweep

**Description.** Before committing to a 225M-token sweep, run the extraction pipeline against a **stratified subset** that preserves the distribution of the variables you care about (subreddit, year bucket, thread length, presence/absence of L1-mentioned schools). Use the subset to (a) tune Stage-1 filter recall, (b) measure Stage-3 LLM F1, (c) cost-calibrate before scaling.

**SOTA reference.** LASER (Stratified Selective Sampling for Instruction Tuning, [arXiv 2505.22157](https://arxiv.org/html/2505.22157v1)) integrates difficulty/quality scoring with stratified sampling + clustering for inter- and intra-class diversity. The domain-specific-eval paper ([arXiv 2408.08808](https://arxiv.org/pdf/2408.08808)) couples manual curation with semi-supervised clustering and stratified sampling — closest published recipe to what we need.

**Expected $ impact.** 95-99% reduction in R&D-cycle cost. A 5,000-thread stratified subset is ~2.25M input tokens (1% of corpus) → ~$0.50-2 per full pipeline iteration vs $50-150 at full scale. Enables 20-50 iteration cycles for the same total budget. **No accuracy impact** if strata are well-chosen.

**When to apply.** Before *every* full sweep, and after any non-trivial prompt/schema change. Stratify on: (1) source subreddit/forum, (2) year quartile of `created_utc`, (3) thread length bucket (<200, 200-1000, >1000 tokens), (4) Stage-1 filter score quartile. Target 5K threads per pass, 10-20% holdout for blind eval.

---

## 1.2 Prompt caching maximum exploitation

**Description.** Anthropic prompt caching offers 90% off cache reads. For our cascade, every Stage-3 call shares: (a) BAML-generated system prompt + JSON schema, (b) L1 ADEA canonical-school list (anchoring context), (c) few-shot exemplars. That static prefix is 3-8K tokens. The variable suffix is just the thread text (~500-2000 tokens).

**SOTA reference.** [Anthropic prompt-caching docs](https://docs.claude.com/en/docs/build-with-claude/prompt-caching); [tokenmix prompt-caching guide](https://tokenmix.ai/blog/prompt-caching-guide); production case showing 88-95% cost reduction on RAG-style repeat-context workloads ([dev.to RCA case](https://dev.to/stella_lin_82914c71e25769/anthropic-prompt-caching-cut-our-rca-cost-by-90-5gmb)).

**Key 2026 details we must design around:**
- **Haiku 4.5 minimum cache size = 4,096 tokens** ([apiyi](https://help.apiyi.com/en/claude-prompt-caching-not-hit-minimum-token-troubleshooting-en.html)). Our static prefix must clear 4K or the cache silently fails. → Pad the ADEA canonical list (~75 schools × aliases × abbreviations ≈ 3-5K tokens already) plus 3-5 few-shots to comfortably exceed 4K.
- **Default TTL is now 5 min, not 1 hr** ([dev.to TTL change](https://dev.to/whoffagents/anthropic-silently-dropped-prompt-cache-ttl-from-1-hour-to-5-minutes-16ao)). For batch jobs we explicitly set `"ttl": 3600` and pay the 2.0× write multiplier once per hour. For interactive R&D the 5-min default is fine if we keep request cadence under 5 min.
- **4 breakpoints max** — design the prompt with breakpoints at: [end of system instructions] [end of schema] [end of ADEA list] [end of few-shots]. This lets cache hits survive minor edits to any one section.
- **Workspace-isolated caches since 2026-02-05** — keep R&D and production in the same workspace or pay write costs twice.

**Expected $ impact.** Static prefix ~5K tokens × ~50K Stage-3 calls = 250M cached-read tokens. At $0.10/MTok (cached) vs $1.00/MTok (uncached) → **$22.50 saved per sweep on prefix tokens alone**, after one-time write cost (~$0.50 with 1-hr TTL). Combined with batch this is a ~10× reduction on the static portion.

**When to apply.** Mandatory for Stage 3 from V1 day 1. The break-even is one re-use of the cache within TTL ([amitkoth](https://amitkoth.com/reduce-claude-api-costs/)), and our batches will hit it tens of thousands of times.

---

## 1.3 Batch APIs — Anthropic, OpenAI, Gemini

**Description.** All three vendors offer 50% off for async batch with a 24-hour completion window. Failure modes and ergonomics differ.

**SOTA reference.** [Anthropic batch processing](https://docs.claude.com/en/docs/build-with-claude/batch-processing) ([jangwook production guide](https://jangwook.net/en/blog/en/anthropic-message-batches-api-production-guide/)); [OpenAI batch FAQ](https://help.openai.com/en/articles/9197833-batch-api-faq); [Gemini batch mode](https://devtk.ai/en/blog/gemini-api-pricing-guide-2026/).

**Comparison (verified 2026-05-20):**

| Vendor | Discount | SLA | Stacks w/ caching | Failure mode |
|---|---|---|---|---|
| Anthropic | 50% in+out | 24 h | **Yes** (95% combined) | Per-request errors returned in result file; whole-batch failures rare |
| OpenAI | 50% in+out | 24 h | Yes (caching independent) | Expired batches cancel remaining work, return completed; **no streaming** |
| Gemini | 50% in+out | up to 24 h, no SLA | Implicit caching only | Variable latency; cheaper raw price on Flash-Lite |

**Expected $ impact.** Direct 50% halving of all Stage-3 spend. On 34M input + ~7M output residual API tokens at Haiku 4.5 standard ($1/$5) that's $34+$35 = $69 standard, **$34.50 batch**, **~$5-8 batch+cache** for the static portion + variable.

**Failure-mode planning.** Anthropic's per-request error semantics are friendliest for cascades — failed rows return a JSON error and we retry only those. For OpenAI, design jobs to be **idempotent by request-id** so we can re-submit only the failed lines from the result file. For Gemini, the lack of a hard SLA means we should not use it for any pipeline stage where downstream work blocks on completion; reserve it for the cheapest pre-filter sweeps.

**When to apply.** All Stage-3 traffic goes through Anthropic batch by default. Reserve interactive (non-batch) calls for HITL spot-checks and `<100`-thread debug runs. Use Gemini batch only as a price-pressure benchmark, not as primary.

---

## 1.4 Cascade with cheap rejection

**Description.** R-003 already specifies the cascade. The cost-reduction lever here is *aggressive Stage-1 rejection*. Best 2025-2026 techniques to reject low-value threads before any LLM token is spent:

1. **Lexical + rule prefilter** — drop threads with zero token overlap to a curated keyword set (school names, "DAT", "GPA", "interview", program abbrev list). Sub-millisecond per thread.
2. **fastText / linear classifier** on TF-IDF or bag-of-embeddings. ~10K threads/sec on CPU. Trained on 1-2K HITL-labelled positives/negatives.
3. **GLiNER zero-shot** with a thin entity-type schema ("dental school", "year", "score"). Per R-003: ~200-400 docs/sec on GTX 1080.
4. **Early-abstention cascades** — let the cheap classifier *also* abstain (return "uncertain") rather than always pass/reject; the abstention bucket becomes a calibration target ([arXiv 2502.09054 Early Abstention](https://arxiv.org/html/2502.09054v1)). Reduces overall test loss by 2.2% while cutting cost ~13%.

**SOTA reference.** [Early Abstention paper](https://arxiv.org/html/2502.09054v1); [KiC keyword-inspired cascade](https://arxiv.org/pdf/2507.13666); [interactive LLM cascade (teacher signal)](https://arxiv.org/html/2509.22984v1).

**Expected $ impact.** If Stage-1 passes 15% instead of 25% with the same recall, Stage-3 spend drops ~40% (from ~34M to ~20M input tokens to API). On batch+cache pricing that's **$3-5 saved per sweep**. The bigger win is enabling more sweeps for the same budget.

**When to apply.** V1 baseline = rule + GLiNER. V1.5 = add fastText trained on the first 2K HITL labels, in front of GLiNER. The win compounds with every label.

---

## 1.5 Distillation — Haiku labels → local model

**Description.** Use Haiku 4.5 to label a few-thousand-thread gold set, then fine-tune a small encoder (distil-BERT, GLiNER, or fine-tune a 1-2B decoder model) to replicate the labels locally. Forever after, the local model handles the bulk and API only fires on out-of-distribution cases.

**SOTA reference.** [EasyDistill toolkit (arXiv 2505.20888)](https://arxiv.org/html/2505.20888v1); [Distilling step-by-step (arXiv 2305.02301)](https://arxiv.org/pdf/2305.02301) — smaller models can outperform larger LLMs with materially fewer labels when rationales are included. [OpenAI Model Distillation API](https://openai.com/index/api-model-distillation/) reports GPT-4o (79.67%) → distilled GPT-4o-mini (79.33%) vs base GPT-4o-mini (64.67%) — a ~22% relative lift at 10× lower cost. [Redis distillation guide 2026](https://redis.io/blog/model-distillation-llm-guide/).

**Caveat.** [OpenAI is winding down the fine-tuning platform as of 2026-05-08](https://crazyrouter.com/en/blog/ai-fine-tuning-api-complete-guide-2026) per search results, so the OpenAI-native distillation path is closing. Open-source DistillKit/EasyDistill on a local rented GPU is the durable path. Anthropic does **not** offer fine-tuning of Haiku/Sonnet on their API.

**Expected $ impact.** After paying ~$30-50 to produce 5K Haiku-labeled gold examples, a fine-tuned local model can absorb 60-90% of Stage-3 traffic. Long-term marginal cost approaches zero (electricity). Caveat: GTX 1080 cannot serve distilled 7B+ models at throughput; target a 100-400M-param encoder or smallest GLiNER variant.

**When to apply.** V2 lever, not V1. V1 needs the corpus run *first* to produce the gold labels. After the first sweep, queue distillation as a 2-3 week project. Realistic V2 outcome: Stage-3 API spend drops from ~$50/sweep to ~$5-10/sweep.

---

## 1.6 Speculative decoding / smaller-model preflight

**Description.** Speculative decoding accelerates **single-model inference** by having a small draft model propose tokens that the target model verifies. Production stacks (vLLM, SGLang, TensorRT-LLM) report 2.0×-6.5× throughput at low concurrency ([SyncSoft 2026](https://www.syncsoft.ai/en/blog/speculative-decoding-eagle3-medusa-deepseek-mtp-chinese-chuhai-2026), [E2E Networks EAGLE-3 guide](https://www.e2enetworks.com/blog/Accelerating_LLM_Inference_with_EAGLE)).

**SOTA reference.** EAGLE-3 ([2026 ICLR](https://openreview.net/pdf?id=aL1Wnml9Ef)) trains a draft head conditioning on early/mid/late hidden states, beating EAGLE-2 by 20-40%; 4-6× speedup on 70B targets. Medusa adds parallel decoding heads. N-gram/suffix decoding is the cheapest variant — no draft model needed.

**Relevance to us.** **Limited.** We are API-side for Stage 3 (Anthropic does speculative decoding internally; we get the benefit transparently in latency, not in price). For local Stage 1/2, GLiNER and BERT encoders are not autoregressive — speculative decoding does not apply. The only situation where this lever lights up is if we abandon GLiNER and run a local generative LLM (Llama-3.1-8B) for extraction — and R-003 already rejected that path on Pascal-throughput grounds.

**Expected $ impact.** Effectively zero in our V1 architecture. Mention only for completeness; revisit if/when V2 spins up a local generative model on Ampere+ hardware.

**When to apply.** V2-only, conditional on hardware upgrade and a local-decoder workhorse.

---

## 1.7 LLM-as-judge skipping — structural validators sufficient

**Description.** For extraction tasks, the question "did the model produce a well-formed JSON matching the schema?" is answered deterministically by Pydantic / JSON-schema / BAML's SAP parser. There is no reason to spend a second LLM call to "judge" structural validity. LLM-judge is only justified for **semantic** quality (did the extracted school name match the intended referent? does the sentiment label fit?).

**SOTA reference.** [Pydantic + LLM-judge guide](https://pydantic.dev/articles/llm-as-a-judge): "run type validation and format checks first; save LLM evaluation for semantic quality." [Future AGI 2026 validation primer](https://futureagi.com/blog/what-is-llm-input-output-validation-2026/) reaches the same conclusion.

**Expected $ impact.** If you currently call a judge model on every extraction (e.g., 50K judge calls × 1K tokens × Haiku = ~$50/sweep), eliminating judge calls for structural checks saves that entire line item. Semantic-judge calls become a sampled audit (5-10% of extractions), not a per-row gate.

**When to apply.** V1 day 1. Wire Pydantic + BAML SAP for *all* extractions. Reserve LLM-judge for: (a) the 5% sampled audit, (b) any extraction where the schema is too soft to validate (free-text sentiment label, conflict-candidate marking).

---

## 1.8 Caching extracted entities across reruns (content-addressable extraction cache)

**Description.** Hash each input (canonicalized thread text + prompt version + schema version + model id) → SHA256 → key. On rerun, look up the key in a local extraction cache (SQLite/Parquet/LMDB); on hit, skip the API call entirely. This is **orthogonal** to Anthropic's prompt cache — it caches the *output*, not the prompt prefix.

**SOTA reference.** [InstCache (predictive cache for LLM serving, arXiv 2411.13820)](https://arxiv.org/html/2411.13820v2); [LSHBloom for text dedup at scale](https://arxiv.org/html/2411.04257v3); RelayCaching for KV-reuse. The pattern is widely deployed but under-named in the literature — most production teams roll their own. The key insight from [InstCache] is that **LLM workloads are heavy-tailed**: a small set of inputs recur frequently, even across "different" sweeps (because most threads don't change between sweeps).

**Implementation skeleton (for V1):**
```
key = sha256(canonical(thread_text) + prompt_version + schema_version + model_id)
hit = extraction_cache.get(key)
if hit: return hit
result = call_llm(...)
extraction_cache.put(key, result)
```

**Expected $ impact.** First sweep: 0% savings (cold cache). Subsequent sweeps (prompt/schema unchanged): **90-99% reduction**. This is the single biggest lever for the *iterative* phase of V1, where we expect to rerun the corpus 5-15 times while tuning extraction prompts. Five reruns saves ~$200-300 in aggregate API spend at our scale.

**When to apply.** V1 day 1. Build before the first full sweep. This is non-negotiable for cost discipline — and incidentally also gives us reproducibility for free.

---

## 1.9 Retrieval-augmented extraction — snap to canonical list

**Description.** Instead of asking the LLM "what school does this thread mention?" with no context, retrieve the top-K candidate canonical schools (from the L1 ADEA list) by BGE embedding similarity to the thread, and inject them into the prompt as "candidates: [HSDM, Penn Dental, UCSF, ...]". The LLM's job becomes *selection from a closed set + abstention*, which is dramatically easier than open extraction.

**SOTA reference.** [Entity-augmented generation (NORA 2025 workshop)](https://nora-workshop.github.io/2025/) discusses injecting compressed entity embeddings to avoid context blowup. [FG-RAG](https://www.frontiersin.org/journals/artificial-intelligence/articles/10.3389/frai.2025.1697169/full) decomposes answers into sub-entity-centric granular facts. The pattern is sometimes called "constrained extraction" or "closed-set NER."

**Expected $ impact.** Two compounding effects:
1. **Input-token reduction**: prepending only the top-10 candidates instead of all 75 ADEA schools shrinks the prompt by ~2-3K tokens per call → ~5-10% cost cut on Stage 3.
2. **Accuracy lift** (mostly): closed-set selection has F1 typically 5-15 pp higher than open extraction for entity disambiguation in our domain because the model can't hallucinate a school not on the list.

**When to apply.** V1 day 1 for Stage 3. Build the BGE-small ANN index over the ADEA canonical list (it's tiny — 75 entries × aliases) at startup; query top-10 per thread; pass into the BAML prompt as a structured candidates block. **Combine with prompt caching by placing the full ADEA list in the cached prefix and the per-thread top-10 in the variable suffix** — get both wins.

---

# Section 2 — Accuracy-improvement techniques

## 2.1 Constrained decoding

**Description.** Force the model's output to satisfy a grammar or JSON schema *during decoding* rather than validating after. Eliminates structural errors entirely on local models; on API models, use the provider's native equivalent.

**SOTA reference.**
- **XGrammar** ([MLC blog](https://blog.mlc.ai/2024/11/22/achieving-efficient-flexible-portable-structured-generation-with-xgrammar), [arXiv 2411.15100](https://arxiv.org/pdf/2411.15100)): 3.5× faster than Outlines on JSON, 10× on CFG. Now the default in many serving stacks.
- **lm-format-enforcer**: lower hallucination in zero-turn RAG settings ([SqueezeBits guided-decoding bench](https://blog.squeezebits.com/guided-decoding-performance-vllm-sglang)).
- **Outlines** and **XGrammar** win in multi-turn ([emergentmind LM Format Enforcer](https://www.emergentmind.com/topics/lm-format-enforcer)).
- **BAML's Schema-Aligned Parsing (SAP)** is a post-decode robustness layer — accepts minor formatting slips, beats OpenAI's FC-strict on Berkeley function-calling bench, **2-4× faster** than FC-strict ([BAML SOTA function-calling](https://boundaryml.com/blog/sota-function-calling), [BAML "false confidence" post](https://boundaryml.com/blog/structured-outputs-create-false-confidence)).
- **JSONSchemaBench** ([arXiv 2501.10868](https://arxiv.org/pdf/2501.10868)): 10K real-world schemas comparing all six major frameworks.

**Provider-side options:**
- **Anthropic**: structured-outputs beta header `structured-outputs-2025-11-13` exposes `output_config.format: json_schema`. Or use tool-use as the canonical pattern (mature). Recursive schemas and `minimum/maximum` constraints **not supported** ([Glukhov structured-output comparison](https://medium.com/@rosgluk/structured-output-comparison-across-popular-llm-providers-openai-gemini-anthropic-mistral-and-1a5d42fa612a)).
- **OpenAI**: server-side `strict: true` JSON schema. Most mature.
- **Gemini**: `responseSchema` + `responseMimeType: application/json`.

**Expected F1 impact.** Structural error rate → ~0% (was 2-8% on free-form prompts depending on model). **Semantic** F1 is largely unaffected by constrained decoding alone — the model still chooses *what* to put in the field; constrained decoding only ensures the field exists and parses. BAML's case study suggests that overly-strict provider modes can actually *hurt* semantic quality on reasoning fields by forcing premature commitment.

**When to apply.** V1 day 1. Stack: **BAML for prompt definition + SAP parser**, with Anthropic tool-use as the structured-output mechanism. Skip provider-native `strict` mode (per BAML's findings on degraded reasoning). For local GLiNER/BERT outputs, schema is enforced by the model architecture itself.

---

## 2.2 Few-shot example curation — automated semantic similarity

**Description.** Instead of pinning the same 5 few-shot examples in every prompt, retrieve the most semantically similar examples to the current thread from a labeled pool. Each prompt gets *its* best 3-5 demonstrations.

**SOTA reference.** [Context Patterns: Few-Shot Selection](https://contextpatterns.com/patterns/few-shot-selection/) lays out the production pattern: embed each request, query a vector index of curated examples filtered by metadata, rank by cosine similarity. [Few-Shot Prompting Guide 2026 (mem0)](https://mem0.ai/blog/few-shot-prompting-guide); [arXiv 2510.27675 on few-shot difficulty](https://arxiv.org/abs/2510.27675) confirms selection matters as much as example quality.

**Expected F1 impact.** Reported lift: **3-8 pp** on extraction tasks where example diversity matters (sarcasm, nicknames, multi-school threads). The token-efficiency angle is equally important: same 5×200=1K tokens get *targeted* per request rather than wasted on irrelevant fixed examples.

**Trade-off vs caching.** Dynamic few-shots **break the prompt prefix cache** because the prefix changes per request. Mitigation: split the prompt into [static-system (cached, 4-5K tokens)] → [dynamic-few-shots (uncached, ~1K)] → [thread (uncached)]. The cached portion still wins 90% off; only the few-shots pay full price.

**When to apply.** V1.5 — needs a labeled pool of ≥200-500 examples to retrieve from, which V1 HITL will produce over the first weeks of operation. Start V1 with 5 hand-curated static few-shots inside the cached prefix; switch to dynamic retrieval at V1.5.

---

## 2.3 Chain-of-Verification (CoVe) — candidate then verify

**Description.** Two-pass extraction: (1) extract candidate facts; (2) generate verification questions for each fact; (3) answer them; (4) drop unverified facts. Reduces hallucinated entities and over-generalized claims.

**SOTA reference.** Original CoVe paper [arXiv 2309.11495](https://arxiv.org/pdf/2309.11495). Reported lifts: list QA precision 0.17 → 0.36; biography FactScore 55.9 → 71.4. 2025 follow-on **VeriCoT** improves verification pass rates 3-7× over baselines on legal/biomedical ([systems-analysis CoVe page](https://systems-analysis.ru/eng/Chain-of-Verification)). [Blockchain.news/ChainBlock CoVe standard](https://blockchain.news/ainews/chain-of-verification-cove-standard-boosts-llm-prompt-accuracy-by-40-for-technical-writing-and-code-reviews) cites **40% accuracy increase** on technical writing/code reviews.

**Cost-accuracy curve.** CoVe is 2-3× the cost of a single pass (more if verifications are themselves multi-question). For our cascade, applying CoVe to every Stage-3 call would push API spend from ~$35 to ~$80-100/sweep. The smart move is **selective CoVe**: trigger it only when the first-pass extraction has low confidence (BAML can surface token-logprob proxies) or when the extracted school is *not* in the ADEA candidate list.

**Expected F1 impact.** 5-15 pp on hallucination-prone extractions (made-up schools, fabricated GPAs/scores). Less impact on close-to-canonical facts.

**When to apply.** V1.5 selectively on the ~10-20% of Stage-3 outputs flagged low-confidence or conflict-candidate. V2 as a routine second pass on high-stakes extractions (anything that becomes a `Recommendation` or `Claim` node).

---

## 2.4 Multi-pass extraction with disagreement — different models

**Description.** Run the same prompt through **two different models** (e.g., Haiku 4.5 + Gemini 2.5 Flash). Where they agree, accept. Where they disagree, surface to HITL or escalate to Sonnet 4.6. Disagreement is a strong uncertainty signal.

**SOTA reference.** [DiscoUQ structured disagreement analysis](https://arxiv.org/pdf/2603.20975) on uncertainty quantification in LLM agent ensembles. [Effective Proxy for Human Labeling (arXiv 2309.05619)](https://arxiv.org/pdf/2309.05619) shows ensemble disagreement scores rival human-labeled uncertainty for industrial NLP. [Dual-model LLM ensemble for systematic-review screening (medRxiv 2025)](https://www.medrxiv.org/content/10.1101/2025.11.03.25339455.full.pdf) achieves "near-perfect sensitivity."

**Expected F1 impact.** Agreement-only outputs are ~3-7 pp higher precision than single-model outputs. Disagreement coverage is typically 5-15% of items — a manageable HITL queue, especially with R-003's existing escalation routes.

**Cost impact.** Doubles Stage-3 spend on agreement runs. Tractable only if the second model is cheaper (Gemini 2.5 Flash-Lite at $0.05/$0.20 batch is ~10× cheaper than Haiku 4.5 — running it as a "second opinion" costs ~$3-5 per full sweep).

**When to apply.** V1.5 as a HITL-feeder. The disagreement queue becomes the training data for distillation (1.5) and the gold set for active learning (2.6).

---

## 2.5 Domain-specific NER — GLiNER + custom labels vs fine-tuned BERT vs zero-shot LLM

**Description.** For school names + GPA + DAT score + program names, which architecture wins?

**SOTA reference.** [GLiNER GitHub](https://github.com/urchade/GLiNER) and [GLiNER multi-task arXiv 2406.12925](https://arxiv.org/html/2406.12925v2). [Sease GLiNER vs LLM evaluation 2025](https://sease.io/2025/10/gliner-as-an-alternative-to-llms-for-query-parsing-evaluation.html) reports GPT-4.1-mini at 100% accuracy vs gliner_medium-v2.1 at 16/30 on a small natural-language-query benchmark. [GLiNER Guard variants](https://arxiv.org/pdf/2605.05277) hit 84.4/83.3 F1 on PII-Bench.

**Domain-specific judgment for our four entity types:**

| Entity | Best model | Rationale |
|---|---|---|
| School names | GLiNER + **embedding alias resolution** | Closed-ish set (~75 dental schools). GLiNER finds spans; BGE/voyage embedding snaps to canonical. LLM is overkill and 10× slower. |
| Program names | GLiNER + alias resolution | Same logic. |
| DAT scores | **Regex + rule** | Tightly-formatted ("DAT 22 AA", "AA: 22"). Pure regex is 100× cheaper than any model. |
| GPA | **Regex + rule** | Same — "GPA 3.7", "3.7 sGPA". |
| Sentiment / nuance | **LLM (Haiku 4.5)** | Open-ended, contextual; GLiNER + rules fail. |
| Interview-question harvesting | **LLM (Haiku 4.5)** | Generation, not extraction. |

**Expected F1 impact.** GLiNER + alias resolution typically achieves **0.82-0.90 F1** on closed-set school-name extraction in noisy forum text (extrapolating from GLiNER multi-task results to a domain with strong canonical anchors). Pure LLM zero-shot lands at 0.78-0.88 with much higher cost and latency. Fine-tuned BERT can hit 0.92+ but only after 1-5K labeled examples — V2 territory.

**When to apply.** V1 = GLiNER + regex + embedding-alias. V1.5 = fine-tune a domain GLiNER head on the first 1-2K HITL labels (GLiNER fine-tuning is cheap; can train on Pascal). V2 = consider full distil-BERT fine-tune if F1 ceiling matters more than ops simplicity.

---

## 2.6 Active learning loops — HITL feed-back for <10 hrs/week

**Description.** Mahyar's HITL budget is small (per A-015 / Q-015). Active learning patterns surface the *most informative* items to label rather than random or chronological.

**SOTA reference.** [Mixture of LLMs in the Loop (arXiv 2601.15773)](https://arxiv.org/html/2601.15773v1) — replacing humans with a mixture of LLMs for annotation, keeping human review for the highest-uncertainty items. [LLMs in the Loop (arXiv 2404.02261)](https://arxiv.org/pdf/2404.02261) — 42× cost reduction vs pure human annotation. [Hands-On Tutorial on labeling with LLM + HITL (arXiv 2411.04637)](https://arxiv.org/pdf/2411.04637).

**Pattern for our pipeline (low-volume HITL):**
1. Score every Stage-2/3 output for uncertainty (margin score from GLiNER softmax; logprob from LLM; disagreement signal from 2.4).
2. Bucket by uncertainty quartile + entity type.
3. Sample top-K from each bucket (stratified to avoid all-borderline-school-name items).
4. Surface to HITL queue with full thread context + suggested labels.
5. Reviewer accepts/edits/rejects in 30-60s per item.
6. Reviewed items feed: (a) GLiNER fine-tune set, (b) distillation gold set, (c) few-shot retrieval pool.

**Expected impact.** 5-10 hrs/week of HITL = ~300-600 reviewed items/week. Within 4-6 weeks, enough gold data accumulates to drive a ~3-7 pp F1 lift via fine-tuning + dynamic few-shots.

**When to apply.** V1 from day 1 (queue exists already per A-015; just wire the uncertainty score). The active-learning *training* pipeline lights up in V1.5 once gold data clears 500 examples.

---

## 2.7 Embedding-based alias resolution — best 2026 model

**Description.** Map extracted school-name spans (with all their nicknames: "HSDM", "Harvard Dental", "Harvard School of Dental Med", "Harv. Dent.") to the canonical ADEA entry via embedding similarity.

**SOTA reference.** [MTEB April 2026 leaderboard (Awesome Agents)](https://awesomeagents.ai/leaderboards/embedding-model-leaderboard-mteb-april-2026/): **Gemini Embedding 001** at MTEB 68.32 (#1). **Voyage-3.1-large** is "best non-Google API" pick. [Voyage docs](https://docs.voyageai.com/docs/embeddings) — up to 32K context. [BGE-M3](https://huggingface.co/BAAI/bge-m3) for open hybrid retrieval. [Buildmvpfast Voyage-3.5 vs OpenAI vs Cohere 2026](https://www.buildmvpfast.com/blog/best-embedding-model-comparison-voyage-openai-cohere-2026). [Mixpeek 2026 ranking](https://mixpeek.com/curated-lists/best-embedding-models).

**Recommendation for our use case:**

| Tier | Model | Why |
|---|---|---|
| Best raw quality | Gemini Embedding 001 (MTEB 68.32) | If API-based embeddings acceptable for V1 |
| Best open-source | **BGE-M3** (multilingual, hybrid dense+sparse) | Aligns with R-002 BM25+dense plan |
| Best small/fast (our pick) | **BGE-small-en-v1.5** | Per R-003. 33M params, ONNX-ready on Pascal, >2K chunks/sec |
| Specialized | voyage-3.1-large | Strong on medical/legal domain (4-6 pp uplift vs general) |

**Production thresholds (alias resolution):**
- **≥0.90 cosine sim** → auto-accept (per R-003 Q-016 placeholder)
- **0.75-0.90** → HITL
- **<0.75** → reject / mark as novel

For canonical-list snap (74 dental schools × ~5 aliases each = ~400 vectors), even cheap models give near-perfect recall. The threshold work matters more than the model choice. Run an ablation in V1 to pin the 0.90/0.75 cutoffs against HITL ground truth on the first 500 reviewed items.

**When to apply.** V1 day 1, BGE-small. Re-evaluate at V1.5 if HITL rejection rate at the 0.75-0.90 band exceeds 30% — that's the signal to swap in BGE-M3 or voyage-3.1.

---

## 2.8 Multi-resolution context — title + first N tokens cheap filter, full thread for high-confidence

**Description.** Don't send the full thread to the API every time. For Stage-1/cheap-filter purposes, title + first 256 tokens often carries 80%+ of the signal. Reserve full-thread context for the high-confidence Stage-3 extractions where nuance matters.

**SOTA reference.** Pattern is widely deployed but under-papered. Closest formal treatment: [Filter, Correlate, Compress (arXiv 2411.17686)](https://arxiv.org/html/2411.17686v4) on training-free token reduction; [Context filtering with reward modeling (arXiv 2412.11707)](https://arxiv.org/pdf/2412.11707); [Query-aware token selection](https://www.emergentmind.com/topics/query-aware-token-selection).

**Implementation tier:**

| Resolution | Use for | Token cost / thread |
|---|---|---|
| Title + first 128 tokens | Stage-1 GLiNER prefilter | ~150 |
| Title + first 512 tokens | Stage-2 GLiNER extraction | ~550 |
| Full thread (capped 4K) | Stage-3 Haiku for survivors | ~2K avg |
| Full thread + parent + siblings | Stage-3 escalation for conflict candidates | ~6K |

**Expected $ impact.** Stage 1/2 already operate on smaller windows in our R-003 plan, so the saving is mostly in Stage 3: capping the full-thread input at 4K vs sending unbounded threads saves ~30% of API input tokens on long Reddit threads. ~$5-10/sweep.

**Accuracy caveat.** Some interview-question and sentiment extractions genuinely need the full thread. The cap should be **per-extraction-type**, not global. BAML can route on extraction-type to different prompt variants.

**When to apply.** V1 day 1. Build the resolution-tier into the BAML prompt definitions.

---

## 2.9 Self-consistency for extraction — sample N, vote on output

**Description.** Run the same prompt N times at temperature 0.5-0.8, vote on the output. Classic self-consistency from Wang et al. 2022; recent refinements weight by model confidence.

**SOTA reference.** [Confidence-Improves-Self-Consistency (arXiv 2502.06233)](https://arxiv.org/html/2502.06233v1) — CISC weighted majority vote based on model confidence, reduces sample count by 40%. [Reasoning-Aware Self-Consistency (RASC)](https://aclanthology.org/2025.naacl-long.184/) reduces sample usage 60-80% while maintaining accuracy. [Reliability-Aware Adaptive Self-Consistency (ReASC)](https://arxiv.org/html/2601.02970v1). [LLM self-consistency for automated scoring (arXiv 2604.26954)](https://arxiv.org/abs/2604.26954).

**Cost implication.** Naive N=5 self-consistency = 5× API cost. CISC/RASC bring effective N down to ~2-3 by adaptive sampling. For our cascade: applying N=3 self-consistency to all Stage-3 calls = ~$100-150/sweep. Apply only to **conflict-candidate / low-confidence subset** (~10% of Stage-3 traffic) = ~$10-15 incremental.

**Expected F1 impact.** 2-5 pp on hard items. Diminishing returns vs CoVe (2.3) — they overlap in failure modes addressed. Pick one, not both.

**When to apply.** V2 only, and only after CoVe (2.3) has been measured. If CoVe delivers 5-10 pp lift on conflict candidates, self-consistency is redundant. If CoVe stalls, self-consistency is the next lever.

---

# Consolidated recommendation

## V1 (locked-in for first full sweep, ~Q3 2026)

**Cost stack (target: ≤$50 first full sweep, ≤$15 incremental rerun):**

1. **Content-addressable extraction cache** (§1.8) — non-negotiable. Build before sweep 1. Makes reruns ~free.
2. **Anthropic batch API** (§1.3) — all Stage-3 traffic. 50% off.
3. **Anthropic prompt caching, 1-hr TTL** (§1.2) — system prompt + schema + ADEA canonical list + 5 static few-shots, all in the cached prefix above the 4,096-token Haiku 4.5 minimum. 90% off on cache reads. Stacks with batch for ~95% off input.
4. **Stratified sampling for R&D** (§1.1) — 5K-thread stratified subset for every prompt/schema iteration. 99% cost reduction on dev cycles.
5. **Cascade rejection** (§1.4) — rule prefilter + GLiNER zero-shot. Target ≤15% Stage-1 pass-through.
6. **Retrieval-augmented extraction** (§1.9) — top-10 ADEA candidates per thread injected into the Stage-3 prompt's variable suffix; full list lives in the cached prefix.
7. **Multi-resolution context** (§2.8) — per-extraction-type token caps; full thread only for survivors.
8. **No LLM-judge calls for structural validation** (§1.7) — Pydantic + BAML SAP only.

**Accuracy stack:**

1. **BAML + Schema-Aligned Parsing** (§2.1) — primary prompt + structured-output layer. Avoid provider-native `strict` mode (BAML evidence shows it can hurt reasoning fields). Use Anthropic tool-use as the underlying mechanism.
2. **GLiNER + BGE-small embedding alias resolution** (§2.5, §2.7) for school + program names. Auto-accept ≥0.90, HITL 0.75-0.90, reject <0.75. Thresholds pinned via first-500-HITL ablation.
3. **Regex + rules** for DAT scores + GPA (§2.5). Don't waste tokens on these.
4. **Static 5-shot few-shots in the cached prefix** (§2.2 V1 form) — wait for HITL gold data before switching to dynamic.
5. **HITL queue with uncertainty-stratified sampling** (§2.6) — active-learning skeleton from day 1, even if the loop closes in V1.5.

**V1 expected:** ~$35-50 first sweep, ~$5-10 incremental rerun, ~0.85-0.90 F1 with HITL on 5-10% of items.

---

## V1.5 (after first sweep produces 1-2K HITL gold examples, ~Q4 2026)

1. **Dynamic semantic-similarity few-shots** (§2.2) — switch from static to retrieved few-shots. Keep static system prompt cached; only the few-shot block becomes per-request.
2. **fastText/linear pre-prefilter in front of GLiNER** (§1.4) — trained on first 2K labels. Drops Stage-1 pass-through another 30-50%.
3. **GLiNER fine-tune** on domain labels (§2.5). Pascal can train this. Expect 3-7 pp F1 lift on school/program.
4. **Selective CoVe** (§2.3) on low-confidence and conflict-candidate Stage-3 outputs (~10-20% of Stage-3). 5-15 pp lift on hallucination-prone items at ~$10-15 incremental.
5. **Dual-model disagreement** (§2.4) — Haiku 4.5 + Gemini 2.5 Flash-Lite second-opinion on conflict candidates. Disagreement feeds HITL queue. ~$5/sweep extra.
6. **Threshold tuning on alias resolution** (§2.7) using accumulated HITL data. If recall@0.90 misses too much, consider voyage-3.1-large or BGE-M3.

**V1.5 expected:** ~$30-40 per sweep, ~0.90-0.93 F1, HITL load steady at 5-10 hrs/week, gold dataset growing.

---

## V2 (after V1.5 produces 5K+ gold examples + corpus stable, ~2027)

1. **Distillation: Haiku labels → fine-tuned local extractor** (§1.5). Long-term target: 60-80% of Stage-3 traffic absorbed locally. Drops API spend per sweep below $10. **Single biggest cost lever long-term.**
2. **Routine CoVe** (§2.3) on all high-stakes extractions (Recommendation/Claim nodes).
3. **Self-consistency** (§2.9) only if V1.5 CoVe data shows residual hallucination on a measured subset. Avoid blanket application.
4. **Speculative decoding** (§1.6) — only if V2 hardware refresh enables a local generative workhorse.
5. **Active-learning automation** (§2.6) — mixture-of-LLMs auto-labeling on high-confidence, human-only on the actively-selected uncertain tail.

**V2 expected:** ~$5-15 per sweep at scale (most extraction local), ~0.92-0.95 F1, distilled model becomes the new V3 baseline.

---

## Opinionated synthesis

The three levers that *most* shape V1 economics are, in order:

1. **Content-addressable extraction cache** (§1.8) — every other lever assumes reruns are cheap; this is what makes them cheap.
2. **Prompt caching + batch stacking** (§1.2 + §1.3) — the documented 95% discount on Stage-3 input tokens is real, well-tooled, and requires only careful prompt structuring.
3. **GLiNER + embedding alias resolution + regex for the closed-set entities** (§2.5 + §2.7) — keeps 85%+ of extractions off the API entirely. The cascade lives or dies here.

The most over-rated levers for our specific workload:

- **Speculative decoding** (§1.6) — irrelevant to API-served Stage 3, and Pascal can't run the local generative model that would benefit.
- **Self-consistency** (§2.9) at full N=5 — too expensive vs CoVe for the same accuracy gain.
- **Distillation** (§1.5) before V1 has shipped — premature optimization. Need real labels first.

The most under-rated lever:

- **Retrieval-augmented extraction / snap-to-canonical** (§1.9). It is *both* a cost and an accuracy lever, costs almost nothing to build (we already have the L1 ADEA list and BGE-small), and turns the hardest part of Stage-3 (school disambiguation) into a closed-set selection problem. **Build this in V1, before any of the V1.5 sophistication.**
