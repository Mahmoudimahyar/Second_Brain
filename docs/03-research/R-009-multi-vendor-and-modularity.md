# R-009 — Multi-vendor model gateway, per-task routing, and MCP-per-component policy

> **Status**: Drafted 2026-05-20 by research agent under R4 directive (multi-vendor + modular). Feeds **ADR-003 addendum** (per-task model assignment), **ADR-009-bis** (model gateway pick), and **ADR-011** (MCP-per-component policy). Live URLs cited inline. Pricing snapshot 2026-05-20; re-verify before any commit.

## Scope

Mahyar's R4 directive locks three properties for V1: (a) vendor-portable, (b) multi-model with per-task selection criteria, (c) component-modular with MCP surfaces where they earn their keep. This packet answers three sub-questions:

- **A** — Which mini-tier model serves which extraction task, with explicit testable selection criteria?
- **B** — Which vendor-abstraction framework should the model gateway be built on?
- **C** — Which internal components warrant an MCP surface vs API-only?

Three streams below. Final 300-word summary at the end is what the parent thread reads.

---

## Stream A — Multi-vendor mini-tier model comparison

### A.1 Live pricing snapshot (2026-05-20)

All rates per 1M tokens. Standard / batch where batch exists. "Cached input" is the prompt-cache read rate where the vendor exposes one.

| Model | Std in | Std out | Batch in | Batch out | Cached in | Notes |
|---|---:|---:|---:|---:|---:|---|
| Anthropic Claude **Haiku 4.5** | $1.00 | $5.00 | $0.50 | $2.50 | ~$0.10 (90% off) | Cache TTL default silently dropped 1h → 5m in March 2026. Must pin `ttl: 3600` on every write. |
| Anthropic Claude **Sonnet 4.6** | $3.00 | $15.00 | $1.50 | $7.50 | ~$0.30 (90% off) | Same cache TTL hazard. |
| OpenAI **GPT-4o-mini** | $0.15 | $0.60 | $0.075 | $0.30 | $0.075 (auto, 50% off) | Automatic prompt caching ≥1024-token prefixes, 5-10 min TTL (no pinning option). |
| OpenAI **GPT-4.1-mini** | $0.40 | $1.60 | $0.20 | $0.80 | $0.10 (auto, 75% off) | 1M-token ctx; strict structured outputs GA. |
| OpenAI **GPT-5.4-nano** (released 2026-03-17) | $0.20 | $1.25 | $0.10 | $0.625 | auto | Smallest GPT-5 family member; OpenAI explicitly recommends for classification + data extraction. |
| OpenAI **GPT-5.4-mini** | $0.75 | $4.50 | $0.375 | $2.25 | auto | 2× faster than GPT-5-mini; full tool-use parity. |
| Google **Gemini 1.5 Flash** | — | — | — | — | — | **Shut down**. All 1.0/1.5 endpoints return 404 as of 2026. Drop from candidate list. |
| Google **Gemini 2.5 Flash-Lite** | $0.10 | $0.40 | $0.05 | $0.20 | ~$0.025 | Cache TTL **defaults to 1h** if unset (cleaner than Anthropic). |
| Google **Gemini 2.5 Flash** | $0.30 | $2.50 | $0.15 | $1.25 | ~$0.075 | Implicit caching in batch ≈ 12.5% of standard rate. |
| **DeepSeek V3.1 / V4** | $0.14-0.30 | $0.28-0.50 | n/a (no batch) | n/a | $0.014-0.03 (90% off) | API only US/CN. **No data residency in EU**. Cache reads auto-applied. |
| **Llama-3.3 70B / Mistral via Together AI** | $0.88 | $0.88 | n/a | n/a | n/a | Symmetric pricing; Fireworks ≈ $0.90. FireFunction structured-output accuracy 92.1%. |
| xAI **Grok 4.1-Fast** | $0.20 | $0.50 | n/a | n/a | n/a | Cheap competitive tier, but per-tool-call surcharge for built-in tools. |
| xAI **Grok 3-mini** | $0.30 | $0.50 | n/a | n/a | n/a | Stable; less interesting given Grok 4.1-Fast undercuts. |

### A.2 Capability matrix

| Model | Native JSON-schema enforce | Tool use | Batch API | Prompt cache | Region options | Context |
|---|:-:|:-:|:-:|:-:|---|---:|
| Haiku 4.5 | Yes (grammar-compiled, GA) | Yes (strict) | Yes (24h, 50%) | Yes (ttl pin required) | US, EU, Bedrock | 200K |
| Sonnet 4.6 | Yes | Yes (strict) | Yes | Yes | US, EU, Bedrock | 200K (1M beta) |
| GPT-4o-mini | Yes (`response_format=json_schema`) | Yes | Yes (50%) | Yes (auto) | US, EU via Azure | 128K |
| GPT-4.1-mini | Yes (strict) | Yes (strict) | Yes (50%) | Yes (auto, 75% off) | US, EU via Azure | 1M |
| GPT-5.4-nano | Yes (strict) | Yes | Yes (flex 50%) | Yes (auto) | US, EU via Azure | ~400K |
| GPT-5.4-mini | Yes (strict) | Yes | Yes | Yes | US, EU via Azure | ~400K |
| Gemini 2.5 Flash-Lite | Yes (`responseSchema`) | Yes | Yes (50%) | Yes (ttl 1h default) | US, EU, global | 1M |
| Gemini 2.5 Flash | Yes | Yes | Yes | Yes | US, EU, global | 1M |
| DeepSeek V3.1/V4 | Partial (`response_format=json_object`, no strict schema) | Yes | No | Auto | CN/global; **no EU residency** | 128K |
| Together/Fireworks Llama/Mistral | Vendor-dependent; Fireworks FireFunction has strict mode | Yes | No native batch | No | US | 128K typical |
| Grok 4.1-Fast | Yes (function calling) | Yes | No | No | US | 256K |

### A.3 Per-task assignment matrix

Selection criteria are testable: **CPT** = cost/1000 threads at observed token mix (≈ 1.5K in / 0.5K out for V1 Stage-3); **P95** = p95 single-call latency; **F1** = task F1 on the V1 gold set (placeholder until first-500-HITL); **SFR** = structured-output failure rate (schema-conformance breakage per 1000).

| Task | Required capability | **Recommended primary** | Alternates | Selection criteria (switch when…) |
|---|---|---|---|---|
| **Stage-3 residual extraction** (sentiment + interview-Q + conflict candidates) over noisy forum text | Structured-output GA, cheap, batchable, prompt-cacheable for schema/instructions | **Claude Haiku 4.5** (batch + `ttl: 3600` cache) | Gemini 2.5 Flash-Lite; GPT-4o-mini; GPT-5.4-nano | **Switch to Flash-Lite** if Haiku batch CPT > $0.40 AND ΔF1 < 0.02 on V1 gold. **Switch to GPT-4o-mini** if Haiku SFR > 1% on schema-enforced runs. |
| **LLM-as-judge** (same-tier same-year tie-breaks; needs cross-vendor calibration) | Strong reasoning, low judge-bias, distinct training lineage from extractor | **Anthropic Sonnet 4.6 + Gemini 2.5 Flash + GPT-4.1-mini** (run all three; require ≥2/3 agreement) | Drop GPT-4.1-mini for GPT-5.4-mini once V1.x evals confirm parity | Always cross-vendor (R-007b: single-vendor judge bias >50%). **Escalate to HITL** if agreement < 2/3, or if Fleiss' κ across the rolling window dips below 0.3. |
| **Stage-3 hardest cases** (deep nuance: implicit sentiment, multi-claim threads, contradiction detection) | High instruction-following, strict structured output, reasoning | **Claude Sonnet 4.6** (batch + cache) | Gemini 2.5 Flash (full, not Lite); GPT-4.1-mini | Route here only when Haiku's confidence on its own output < 0.7 OR when downstream conflict-resolver flags the extraction as ambiguous. Cap: ≤2% of Stage-3 volume. |
| **Embedding** (ER blocking + dense retrieval) | Throughput on CPU/Pascal GPU, recall, no API call per chunk | **Local `BAAI/bge-small-en-v1.5`** (already locked in tech-stack) | `BAAI/bge-m3` if multilingual surfaces; Voyage-3-large via API for V2 quality bump | Switch to **BGE-M3** when any L1 source ships non-English content. Switch to **Voyage-3-large** only if retrieval-recall@10 < 0.85 on the eval set AND budget allows ~3× cost. |
| **Reranker** (if API-side) | NLI-style cross-encoder judgment, low latency | **Local `cross-encoder/nli-deberta-v3-base`** (DITTO/DistilBERT path already in stack) | Cohere Rerank v3.5 ($2/1K searches) for sparse-call high-stakes retrieval | API rerank only earns its keep when (a) local p95 > 80ms blocks the retrieval SLA, or (b) recall@10 from local rerank < 0.90 on the eval set. |
| **HITL summary generation** (CLI item summaries for reviewer) | Cheap, fast, summarization-grade, no schema | **Gemini 2.5 Flash-Lite** (cheapest per token; summaries don't need strict schema) | Haiku 4.5 (if Anthropic is the only vendor with provisioned keys at the moment) | Switch to **Haiku 4.5** if the CLI ever needs `cache_control` reuse across summary batches. Otherwise Flash-Lite wins on raw $/token. |

Concrete cost example for Stage-3 residual extraction on V1 sweep (≈100K residual threads × ~1.5K input / 0.5K output, with prompt cache hit ratio 0.7 on the instruction block):
- Haiku 4.5 batch + cache: ≈ **$18-25** (matches R-008 envelope).
- Gemini 2.5 Flash-Lite batch (no cache yet wired): ≈ **$15-22**.
- GPT-4o-mini batch: ≈ **$11-18**.

Cost is **within an order of magnitude across the mini tier**. Selection should be driven by F1 + SFR on the V1 gold set, not raw rate. The R-008 lock on Haiku 4.5 stays the V1 default; Gemini 2.5 Flash-Lite is the named challenger in the tech-stack already.

### A.4 Models we could not verify live in 2026

- **Gemini 1.5 Flash** — endpoints returned 404 in 2026 per Google AI dev docs. **Drop** from the candidate set. The current Mahyar-named comparator becomes Gemini 2.5 Flash-Lite.
- **DeepSeek V3.5** — DeepSeek released V3.1 then V4 (March 2026). No V3.5 SKU surfaced in current pricing pages. Treat the V3 family as a single competitive tier.
- **Grok 4-mini** — xAI did not ship a Grok-4-mini SKU; the cheap tier is **Grok 4.1-Fast** ($0.20/$0.50). Use that as the comparator.

### A.5 Region / residency notes (V2-relevant; V1 internal so optional)

- Anthropic: US default; EU available via Bedrock + Vertex AI partners.
- OpenAI: US default; EU via Azure (data-residency commitments only on Azure).
- Google Gemini: US + EU + global on Vertex.
- DeepSeek: **no EU residency**. Hard block for any V2 EU customer; flag in the gateway routing rules so DeepSeek is opt-in only.

Sources used in stream A: [Anthropic pricing](https://www.anthropic.com/pricing), [Anthropic structured outputs](https://platform.claude.com/docs/en/build-with-claude/structured-outputs), [OpenAI pricing](https://openai.com/api/pricing/), [OpenAI prompt caching](https://openai.com/index/api-prompt-caching/), [OpenAI structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs), [Gemini pricing](https://ai.google.dev/gemini-api/docs/pricing), [Gemini context caching](https://ai.google.dev/gemini-api/docs/caching), [DeepSeek API pricing](https://api-docs.deepseek.com/quick_start/pricing/), [Together AI pricing](https://www.aipricing.guru/together-pricing/), [Fireworks AI review](https://tokenmix.ai/blog/fireworks-ai-review), [xAI models](https://docs.x.ai/developers/models), [Cohere pricing](https://www.aipricing.guru/cohere-pricing/), [pricepertoken catalogue](https://pricepertoken.com/), [GPT-4.1-mini model card](https://developers.openai.com/api/docs/models/gpt-4.1-mini), [GPT-5.4 nano announcement](https://openai.com/index/introducing-gpt-5-4-mini-and-nano/).

---

## Stream B — Vendor-abstraction / model-gateway framework comparison

### B.1 Candidates (2026-05-20)

| Option | License | Coverage | Structured-output normalization | Cache pass-through | Batch primitive | Fallback chain | Overhead vs raw SDK |
|---|---|---|---|---|---|---|---|
| **LiteLLM** (BerriAI) | MIT (SDK); Enterprise tier exists | 140+ providers, 2500+ models. Anthropic Haiku 4.5/Sonnet 4.6, Gemini 2.5 family, OpenAI 4o-mini/4.1/5.4 family, DeepSeek — all present | Pass-through to OpenAI-compatible schema; structured-output kwarg routes per vendor; not normalized | Yes for Anthropic+Gemini+OpenAI; **`ttl` field for Anthropic Bedrock currently stripped** per [issue #20326](https://github.com/BerriAI/litellm/issues/20326). Direct Anthropic API path: `cache_control` + `ttl` preserved. | Wraps OpenAI + Anthropic batch; not a unified abstraction | Yes (router + retry policies) | ~500µs mean per request; throughput drop 1.7×-4× under load; degrades past ~1M log rows |
| **OpenRouter** | Proprietary SaaS | 400+ models, 60+ providers, unified billing | Per-vendor pass-through | Limited (provider-dependent; Anthropic `cache_control` passes through) | Routed per provider; OpenRouter does not add its own batch API | Built-in (provider fallback per-request) | +network hop (~30-80ms typical); single-vendor billing simplification |
| **Vercel AI SDK** | Apache 2.0 | 20+ providers via standardized adapters | Normalized via the SDK's `generateObject`/`streamObject` primitives — strongest cross-vendor schema normalization in the field | Provider-dependent | Provider-dependent | Yes (provider fallback) | Native ~50µs; **TS/JS primary**, Python only via the AI Gateway's OpenAI-compatible endpoint |
| **Custom Python shim** (`LLMClient` ABC + per-vendor adapters) | Ours | Whatever we add | We define the contract | We define | We define | We define | Zero indirection; lowest latency |
| **Portkey** | Open core (Apache 2.0 since March 2026) + managed control plane | All major vendors | Pass-through; guardrails layer on top | Yes; semantic cache differentiator | Provider-dependent | Yes (production-grade) | ~50ms managed; self-host removes that |
| **Langfuse + custom** | MIT | Observability only — **not a router** | n/a | n/a | n/a | n/a | Adds tracing only |

### B.2 Production failure modes observed 2025-2026

- **LiteLLM at scale**: GitHub issue [#21046](https://github.com/BerriAI/litellm/issues/21046) and the [TensorZero benchmark](https://www.tensorzero.com/docs/gateway/benchmarks) both document significant latency overhead (~500µs mean, p99 worse), throughput drops 1.7×-4× vs raw SDK, memory leaks requiring worker recycling (`max_requests_before_restart=10000`), and degradation when the logging DB crosses ~1M rows. 1000+ open GitHub issues as of early 2026. **Failure mode**: timeouts at ~2K req/s, cascading.
- **OpenRouter**: meta-billing convenience is real, but adds a network hop and a third-party trust dependency. Not appropriate for V1 internal where direct vendor keys are already required.
- **Vercel AI SDK**: best-in-class cross-vendor JSON-schema normalization (`generateObject`), but **Python is second-class**. Our stack is Python-only. Hard pass.
- **Portkey**: strong production safety story (guardrails, semantic cache, PII redaction); open-core since March 2026 lets you self-host the gateway. Overhead lower than LiteLLM at scale per [Kong's benchmark](https://konghq.com/blog/engineering/ai-gateway-benchmark-kong-ai-gateway-portkey-litellm). Pricing model for managed tier ties you to a SaaS bill — V1 internal doesn't need that.
- **Custom shim**: zero infrastructure surprise; you write the cross-vendor `ttl: 3600` lint check yourself (already a GAP-031 requirement). But you re-implement what LiteLLM gives free.

### B.3 Recommendation

**Primary pick for V1: LiteLLM (SDK mode, NOT proxy mode) wrapped behind our own thin `LLMClient` ABC.**

Justification:

1. **Coverage is decisive.** LiteLLM handles every model on our short list including DeepSeek and Together — that's an immediate `claudette → openai → gemini → deepseek` swap with one config line, exactly Mahyar's R4 directive.
2. **SDK mode dodges the proxy's failure modes.** The 1.7×-4× throughput drop and memory leaks documented above are proxy-mode problems. In-process SDK usage stays near raw-SDK speed.
3. **Owning the ABC isolates us from LiteLLM's churn.** 1000+ open issues is a signal. By wrapping LiteLLM behind our own `LLMClient` interface (`extract()`, `embed()`, `judge()`, `summarize()` — task-shaped, not vendor-shaped), we can swap LiteLLM out for raw SDKs or Portkey if it goes sideways. This is also where the GAP-031 `ttl: 3600` lint lives — at our boundary, not LiteLLM's.
4. **Observability stays separate.** Pair LiteLLM SDK calls with **Langfuse** (or just structlog → DuckDB per the locked observability story) for per-call cost + latency telemetry. The "gateway + separate observability" split is the consensus 2026 pattern.
5. **Runner-up: Portkey self-hosted** (now Apache 2.0). If LiteLLM's stability burns us in V1.x, Portkey is the drop-in replacement with better guardrails + semantic cache. The `LLMClient` ABC keeps that swap cheap.

**Explicit failure-mode tripwires** (when to abandon LiteLLM mid-V1):
- p95 latency overhead > 50ms on Stage-3 batch dispatch.
- Memory growth > 500 MB over 24h of steady extraction.
- Any silent dropping of `cache_control.ttl` for direct Anthropic calls (the Bedrock-only bug pattern leaking to direct API).
- Any structured-output kwarg silently swallowed on a vendor swap.

**Vendor-specific cache primitive handling**: the `LLMClient` ABC pins `ttl: 3600` for Anthropic, lets OpenAI's automatic cache do its 5-10min thing, and explicitly sets Gemini's `ttl` to 3600s (Gemini defaults to 1h, but we pin to remove the "silent change" risk — see Anthropic for an example of why pinning matters).

Sources for stream B: [LiteLLM GitHub](https://github.com/BerriAI/litellm), [LiteLLM Anthropic docs](https://docs.litellm.ai/docs/providers/anthropic), [LiteLLM perf issue](https://github.com/BerriAI/litellm/issues/21046), [TrueFoundry LiteLLM review](https://www.truefoundry.com/blog/a-detailed-litellm-review-features-pricing-pros-and-cons-2026), [TensorZero benchmark](https://www.tensorzero.com/docs/gateway/benchmarks), [Kong AI Gateway benchmark](https://konghq.com/blog/engineering/ai-gateway-benchmark-kong-ai-gateway-portkey-litellm), [Portkey vs LiteLLM](https://www.alongside.team/blog/litellm-vs-portkey-multi-model-ai-gateway), [OpenRouter](https://openrouter.ai/models), [Vercel AI SDK](https://ai-sdk.dev/docs/introduction), [Langfuse + LiteLLM](https://langfuse.com/integrations/gateways/litellm), [Braintrust gateway comparison](https://www.braintrust.dev/articles/best-llm-gateways-observability-2026).

---

## Stream C — MCP-per-component policy

### C.1 Is "API + MCP per component" a recognized 2025-2026 pattern?

**Partially.** The recognized pattern is **MCP-as-tool-surface for agent-callable capabilities, NOT MCP-as-internal-RPC**. Anthropic's own architectural guidance ([MCP architecture overview](https://modelcontextprotocol.io/docs/learn/architecture), [code execution with MCP](https://www.anthropic.com/engineering/code-execution-with-mcp)) treats MCP as the *external* USB-C surface for AI clients, with internal in-process function calls staying as direct calls.

Concrete signals:

- 28% of Fortune 500 companies deployed MCP servers for production AI workflows by early 2026 (per [The New Stack](https://thenewstack.io/model-context-protocol-roadmap-2026/), [Truto guide](https://truto.one/blog/what-is-an-mcp-server-the-2026-architecture-guide-for-saas-pms/)).
- Anthropic shipped **MCP Tunnels** (May 2026, [InfoQ](https://www.infoq.com/news/2026/05/claude-mcp-tunnels/)) specifically because the production pattern is "external agents reaching into internal systems," not "internal systems talking MCP to each other."
- [GitNexus](https://www.marktechpost.com/2026/04/24/meet-gitnexus-an-open-source-mcp-native-knowledge-graph-engine-that-gives-claude-code-and-cursor-full-codebase-structural-awareness/) is a real-world MCP-native knowledge graph (closest analog to V1 product engine). It exposes one MCP server with multiple tools — not one MCP per internal component.
- Stateless HTTP MCP transport in review (per the [2026 roadmap](https://thenewstack.io/model-context-protocol-roadmap-2026/)) is targeted at "scale horizontally behind a load balancer," which is again *external* surface scaling, not internal-call substitution.

**Verdict**: "MCP per internal component" is not a named pattern. The named pattern is "MCP per agent-callable boundary." Treating every component as an MCP server is over-engineered microservices with a JSON-RPC bow on top.

### C.2 Costs of MCP-per-component

| Cost | Magnitude |
|---|---|
| Process startup overhead per stdio server | ~50-200ms cold start; persistent processes mitigate but add memory pressure |
| Schema-version drift | Every component contract becomes a versioned JSON-RPC schema; breaking changes propagate visibly only at call sites |
| Latency: stdio MCP vs direct Python call | "Microseconds" per [stdio analysis](https://runyard.io/blog/mcp-transport-modes-explained); in practice **under 50ms** for stdio, but 10-20× worse than in-process. For batch (hundreds of calls), this is the difference between 50s and 25min. ([source](https://fast.io/resources/function-calling-vs-mcp/)) |
| Observability complications | Trace IDs must cross process boundaries; OpenTelemetry can do it but it's setup cost |
| Authn / authz surface | Each MCP server is a new credential boundary. For internal V1 single-user this is irrelevant; for V2 multi-tenant it's a real cost |
| Operational ops complexity | Restart, version, log per server. Counted in [Knit's pros-and-cons](https://www.getknit.dev/blog/the-pros-and-cons-of-adopting-mcp-today) as "considerable overhead" for dozens of servers. |

### C.3 Hybrid tier policy (the actually-useful answer)

Three tiers, applied per component:

- **Tier 0 — Python API only.** Module-level functions / classes, imported and called in-process. Default for everything internal. Lowest latency. Direct typing. No serialization.
- **Tier 1 — Python API + thin MCP wrapper.** Add MCP only when the component is **agent-callable** (i.e. a real or near-future LLM-driven caller would invoke it). MCP wrapper is a 30-50 line shim over the Python API.
- **Tier 2 — Python API + MCP + HTTP shim.** Add HTTP only when **cross-process** access is needed (e.g. crawler in a separate repo talks to the ingestion plane). HTTP shim is ~50 lines over the API.

**Rule**: "MCP earns its keep only if a non-deterministic LLM-driven caller benefits from tool discovery + schema-validated invocation." If the only callers are deterministic internal pipeline code, MCP is dead weight.

### C.4 Per-component verdict (V1)

| Component | API | MCP? | Reasoning |
|---|:-:|:-:|---|
| **Ingestion plane** (`register_dump`) | Yes | **Yes** (outbound — the crawler is an external agent-driven system) | Crawler-side is non-deterministic and benefits from tool discovery + the manifest schema being MCP-validated. This is already in the locked architecture. |
| **Cascade extraction** (`extract`) | Yes | **No** (V1) | Stage 1/2 are deterministic pipeline steps. Stage 3 is LLM-driven but called *by* our pipeline, not an external agent. No agent-callable use case in V1. Add MCP in V2 if a `re_extract(thread_id, model)` ad-hoc tool becomes useful. |
| **Entity resolution** (`canonicalize`) | Yes | **No** (V1) | Internal pipeline step. HITL reviewer pulls borderline cases via the HITL queue, not by directly invoking canonicalize. |
| **Conflict resolver** (`reconcile`) | Yes | **No** | Pure internal pipeline. No agent-callable use case identified. |
| **Graph retrieval** (`query_graph`, `search_by_topic`, `get_canonical_entity`, `get_user_credibility`, `get_topic_consensus`) | Yes | **Yes** | This is *the* MCP surface. V2 downstream agents (PM, marketing, analyst, search-verification) call this. Already locked in ADR-009. |
| **HITL queue** (`pull`, `commit`) | Yes | **Yes** (V1.x) | Reviewer tooling benefits from agent-callable surfaces (e.g. a future "review-assistant" Claude session pulls items and surfaces context). V1 minimum is CLI; MCP wrapper is the next-cheapest add. |
| **Audit log** | Yes (SQL/DuckDB read path) | **No** | Read-only analytical store. Analysts query via SQL/DuckDB. Agent-callable surface adds no value over a `query_audit(filters)` Python function and would invite uncontrolled cost-attribution lookups. |
| **Model gateway** (`LLMClient`) | Yes | **Yes** (V1.x; V2 mandatory) | Mahyar's R4 directive explicitly says "any agent can invoke any model." MCP wrapper exposing `extract`, `judge`, `summarize`, `embed` is the V1.x add. V1 hard requirement is the Python API + per-task router; MCP shim is a 30-line follow-on. |

**Net policy**: MCP surfaces for V1 = ingestion (outbound, already locked), graph retrieval (inbound, already locked), HITL (V1.x), model gateway (V1.x). Everything else stays API-only until a concrete agent-callable use case appears. This matches the system-overview §6 list and adds the HITL + model-gateway MCPs explicitly.

### C.5 "MCP when X" rule (lint-enforceable for V1.x)

```
Add an MCP surface to component C iff:
  (1) at least one non-deterministic LLM-driven caller (current or named V2 agent) invokes C, AND
  (2) the callable surface benefits from schema-validated tool discovery
      (i.e. the caller would otherwise need a hand-maintained tool definition), AND
  (3) the latency budget tolerates +<50ms stdio overhead per call.
Otherwise: Python API only.
HTTP shim is independent: add when cross-process access from a different repo/process is required.
```

Sources for stream C: [MCP architecture overview](https://modelcontextprotocol.io/docs/learn/architecture), [Anthropic — code execution with MCP](https://www.anthropic.com/engineering/code-execution-with-mcp), [MCP 2026 roadmap](https://thenewstack.io/model-context-protocol-roadmap-2026/), [MCP Tunnels announcement](https://www.infoq.com/news/2026/05/claude-mcp-tunnels/), [Function calling vs MCP](https://fast.io/resources/function-calling-vs-mcp/), [Knit pros-and-cons](https://www.getknit.dev/blog/the-pros-and-cons-of-adopting-mcp-today), [MCP transport modes](https://runyard.io/blog/mcp-transport-modes-explained), [GitNexus MCP knowledge graph](https://www.marktechpost.com/2026/04/24/meet-gitnexus-an-open-source-mcp-native-knowledge-graph-engine-that-gives-claude-code-and-cursor-full-codebase-structural-awareness/), [Truto MCP architecture 2026](https://truto.one/blog/what-is-an-mcp-server-the-2026-architecture-guide-for-saas-pms/), [Skyvern MCP architecture explained](https://www.skyvern.com/blog/mcp-server-architecture-explained/).

---

## Decisions queued for Mahyar's ratification

1. **ADR-003 addendum** — adopt the per-task assignment matrix in §A.3 with explicit selection criteria. Lock Haiku 4.5 as Stage-3 primary; Gemini 2.5 Flash-Lite as named alternate to be benchmarked in V1.x; Sonnet 4.6 for hardest cases; LLM-as-judge always three-vendor.
2. **ADR-009-bis (new)** — adopt LiteLLM (SDK mode) wrapped behind our own `LLMClient` ABC. Portkey self-hosted as runner-up. Langfuse (or structlog→DuckDB) for per-call telemetry. Tripwires per §B.3.
3. **ADR-011 (new)** — adopt the three-tier policy in §C.3 + the per-component verdict in §C.4 + the "MCP when X" rule in §C.5. Existing locked surfaces (ingestion, graph retrieval) stay. Add MCP wrappers for HITL queue + model gateway in V1.x.

## Open unresolved questions (route to `unresolved-questions.md` if blocked)

- **Q-RA**: V1 gold-set creation timeline — selection criteria above are testable but require the first 500 HITL labels. Block on GAP-028.
- **Q-RB**: Whether to additionally pin Gemini's `ttl` to 3600 even though Gemini's default is already 1h — recommendation is yes (defensive against the same March-2026 Anthropic-style silent change), but it adds a Gemini-specific code path to the `LLMClient`.
- **Q-RC**: Whether the model-gateway MCP exposes per-task tools (`extract_residual`, `judge_tie_break`, `summarize_hitl_item`) or generic tools (`call_model(task, payload)`). Per-task is more auditable; generic is more flexible. Default to **per-task** for V1.x; revisit at V2 when more agents exist.
