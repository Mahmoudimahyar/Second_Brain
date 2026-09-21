# R-010 — State-of-the-Art Review (2026-05-29, live-verified)

> **Why this exists.** The original research (R-001…R-009) ran with WebSearch/WebFetch
> **denied** (see `research-log.md` methodology note) and explicitly flagged
> "re-run the live-source pass before ratifying the ADRs." That pass had not been run, so
> several ADR premises were stale or overstated. This is that pass: a live-verified SOTA
> review across the 8 highest-stakes pillars, conducted 2026-05-29. It drives ADR-021…026
> and the doc corrections in the V1.7 patch. All citations below were live-checked.

## Verdicts by pillar

| Pillar | Project choice | Verdict | Action |
|---|---|---|---|
| Trust-tier retrieval | "we are inventing it"; tier-first sort | **Overstated + risky** | ADR-021: tier-as-prior + RA-RAG cross-check; soften framing |
| GraphRAG cost/arch | "MS GraphRAG too expensive at scale"; custom 5-pass | **Stale premise; partly redundant** | ADR-025 spike; re-baseline cost docs |
| Bitemporal + Wikidata rank | bitemporal 4-tuple + rank enum | **Current/standard** | Keep; only worth it if `as_of` actually queried; rank ≠ temporal axis |
| Conflict resolution | fixed 6-step cascade | **Behind (rigid); SOTA is learned truth-discovery** | ADR-026 spike; collapse temporal+trust into joint score |
| Signed-graph consensus | "majority cluster = truth"; (actually k-means) | **Right algo, wrong decision rule; not built** | ADR-026: disagreement-detector only; trust-weighted aggregation |
| Entity resolution | GLiNER2 + bge-small + DITTO | **Functional; "SOTA" framing dated** | ADR-022: embedding upgrade, NuNER A/B, LLM-matcher fallback |
| Gateway + cascade | LiteLLM SDK + custom ABC; raw-confidence cascade | **Sound; rationale out-of-regime; 1 gen behind on routing** | ADR-023: calibrated escalation + learned router; fix rationale |
| Constrained decoding + prompt fw | XGrammar(-2), BAML, DSPy+GEPA | **Current / ahead** | Keep; note vendor-native structured outputs for hosted models |

## Key corrections to existing docs

- **"HALO"** is real (arXiv 2505.07509, May 2025) and accurately described, but it is a
  single very-recent TKG-reasoning paper — cite as "HALO-style per-type half-life decay,"
  not a settled standard. (ADR-007 is otherwise fine; its bigger problem is it was never
  implemented — see `implementation-status.md`.)
- **GLiNER2** is an **EMNLP 2025 *System Demonstrations*** paper, not main-track.
- **"JudgeBiasBench >50% single-vendor error"** — real (arXiv 2603.08091, HIT, Mar 2026) but
  fresh; the ">50%" is on *adversarial bias-injected* items, not general accuracy.
- **"proxy mode 1.7–4× slower"** — sourced from a self-hosted vLLM high-RPS issue
  (LiteLLM #21046); **out of regime** for our API-bound workload. Keep SDK mode for the
  honest reason (avoid operating another stateful service).
- **No invented tools/benchmarks found.** GLiNER2, XGrammar-2, GEPA, DSPy 3, JudgeBiasBench
  and the model lineup (Gemini 2.5 Flash-Lite, Haiku 4.5, Sonnet 4.6, GPT-4.1-mini,
  GPT-5.4-nano) are all real; GEPA's "35× fewer rollouts than MIPROv2" checks out.

## Citations (live-verified 2026-05-29)

- RA-RAG (reliability-aware RAG): https://arxiv.org/abs/2410.22954
- Astute RAG (source-aware, minority-correct): https://arxiv.org/abs/2410.07176
- Wikidata ranking model: https://www.wikidata.org/wiki/Help:Ranking
- LazyGraphRAG (cost collapse): https://www.microsoft.com/en-us/research/blog/lazygraphrag-setting-a-new-standard-for-quality-and-cost/
- LightRAG: https://arxiv.org/abs/2410.05779
- Zep / Graphiti (bitemporal KG): https://arxiv.org/abs/2501.13956
- HippoRAG 2: https://arxiv.org/abs/2502.14802
- GraphRAG-Bench (when graphs help): https://arxiv.org/html/2506.05690v3
- Truth-discovery survey (TruthFinder/LTM/CRH; majority≠correct): https://arxiv.org/pdf/1505.02463
- KARMA (multi-agent KG conflict resolution): https://openreview.net/pdf?id=k0wyi4cOGy
- HALO half-life decay: https://arxiv.org/abs/2505.07509
- Robust Deep Signed Graph Clustering (WWW'25): https://arxiv.org/html/2502.05472
- SPONGE (signed spectral clustering): https://arxiv.org/abs/1904.08575
- LLM entity matching > DITTO: https://arxiv.org/abs/2310.11244
- EmbeddingGemma: https://arxiv.org/abs/2509.20354
- Qwen3-Embedding: https://qwenlm.github.io/blog/qwen3-embedding/
- GLiNER2 (EMNLP 2025 Demos): https://aclanthology.org/2025.emnlp-demos.10/
- XGrammar: https://arxiv.org/abs/2411.15100
- GEPA (DSPy): https://arxiv.org/abs/2507.19457
- RouteLLM: https://arxiv.org/pdf/2406.18665
- UCCI (calibrated cascade): https://arxiv.org/abs/2605.18796
- FrugalGPT: https://arxiv.org/abs/2305.05176
- PoLL (panel of LLM judges): https://arxiv.org/abs/2404.18796
- JudgeBiasBench: https://arxiv.org/abs/2603.08091
- Debate amplifies judge bias: https://arxiv.org/abs/2505.19477
- LiteLLM proxy throughput issue (#21046): https://github.com/BerriAI/litellm/issues/21046
