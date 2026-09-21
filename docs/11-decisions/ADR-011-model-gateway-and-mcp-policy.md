# ADR-011: Model Gateway (LiteLLM SDK) + Component-MCP Three-Tier Policy

Status: **accepted**
Date: 2026-05-20

## Context

Mahyar's R4 directive: multi-vendor LLM strategy from V1, vendor-portable code, modular components with API + MCP-where-suitable. R-009 surveyed vendor-abstraction frameworks (LiteLLM, OpenRouter, Portkey, Vercel AI SDK, custom shim) and the "MCP per component" pattern.

Key findings from R-009:
- **LiteLLM proxy mode** has documented 1.7-4× throughput drop + memory leaks + ~500 µs overhead per call.
- **OpenRouter** adds a network hop + central billing dependency — not appropriate for V1 internal use.
- **Vercel AI SDK** treats Python as a second-class binding.
- **Portkey self-hosted** (Apache 2.0 since March 2026) is a credible runner-up.
- "**MCP per internal component**" is **NOT** a recognized 2025-2026 pattern. Anthropic itself treats MCP as the external agent-callable surface, not internal RPC.

## Decision

### Model gateway: LiteLLM SDK mode + custom `LLMClient` ABC

Use **LiteLLM as a Python SDK** (not as a proxy server). Wrap behind our own `LLMClient` Abstract Base Class in `src/gateway/`.

```python
class LLMClient(ABC):
    @abstractmethod
    def complete(self, task: TaskID, prompt: BAMLPrompt, inputs: dict,
                 schema: type[BaseModel] | None = None,
                 cache_ttl: int = 3600) -> GatewayResponse: ...
```

The ABC owns:
- **`ttl: 3600` lint enforcement** at the boundary (GAP-031).
- **Per-task model routing** (ADR-003 addendum per-task matrix).
- **Fallback chain** (Haiku → Gemini 2.5 Flash-Lite → GPT-4o-mini per ADR-003).
- **Cost telemetry** sink to Langfuse.
- **Idempotent retries** keyed by `audit_id`.

**Why SDK not proxy**: avoids the documented throughput regression + memory leaks + per-call overhead. SDK mode = direct vendor SDKs unified behind one interface, no extra process.

**Runner-up**: **Portkey self-hosted** if LiteLLM SDK proves too thin a layer.

**Rejected**:
- **Vercel AI SDK** — Python is second-class.
- **OpenRouter** — extra network hop + billing centralization unwanted for V1 internal.

**Telemetry**: **Langfuse** for per-call cost + latency + cache-hit + vendor breakdown.

### Three-tier MCP-per-component policy

| Tier | Surface | Criterion to be at this tier |
|---|---|---|
| **Tier 0** | Python API only (default) | In-process callers; deterministic invocation; no agent-callable benefit. |
| **Tier 1** | API + MCP | LLM-driven non-deterministic caller benefits from tool discovery + schema-validated invocation. |
| **Tier 2** | API + MCP + HTTP shim | Cross-process / cross-host access needed (V2). |

### V1 surface assignment

| Component | V1 Tier | V1.x Tier | Reason |
|---|---|---|---|
| Ingestion plane (outbound: `register_dump`, `get_gaps`, `get_research_needs`) | **Tier 1** | Tier 1 | Crawler is an external agent system. |
| Graph retrieval (inbound: `query_graph`, `get_canonical_entity`) | **Tier 1** | Tier 1 | Coding agent + future downstream agents call this. |
| Cascade extraction | Tier 0 | Tier 0 | Internal pipeline step; deterministic. |
| Entity resolver | Tier 0 | Tier 0 | Same. |
| Conflict resolver | Tier 0 | Tier 0 | Same. |
| Bitemporal graph writer | Tier 0 | Tier 0 | Internal storage primitive. |
| Model gateway | Tier 0 | **Tier 1** | V2 downstream agents will want gateway access. |
| HITL queue | Tier 0 | **Tier 1** | V2 external reviewers; V1 = CLI is enough. |
| Audit log | Tier 0 | Tier 0 | Queried via SQL; no agent-call benefit. |
| Credibility scorer | Tier 0 | Tier 0 | Internal scoring; results surface via retrieval. |

## Consequences

- **Vendor-locked code is forbidden** in product engine (`src/`). Only `src/gateway/` may `import anthropic` / `import openai` / `import google.genai`. Enforced by `ruff` import-ban rule.
- **All LLM call sites use `LLMClient`**. Direct vendor calls in product code fail CI.
- `ttl: 3600` enforcement is at two layers: the ABC sets it as a default + runtime check; `lint_ttl_pinning.py` static-checks every call site.
- Three-vendor accounts (Anthropic + OpenAI + Google) are needed from V1 — at minimum so the gateway can be tested + LLM-as-judge can activate in V1.x (A-052).
- Adding a 4th vendor is approval-required per `dependency-rules.md`.
- Per-task model routing is **config + tested**, not buried in code. Routing decisions are in `src/gateway/routing.py` with explicit unit tests per task.
- **MCP-per-component policy is sober**: V1 has exactly 2 MCP surfaces (ingestion outbound + retrieval inbound). New MCP tools require ADR justification + tier-1 criterion check.

## Alternatives considered

- **Direct Anthropic SDK only**: violates A-046 vendor portability. Rejected.
- **LiteLLM proxy mode**: documented perf regression + memory leaks. Rejected.
- **OpenRouter**: extra hop + centralized billing. Rejected.
- **Vercel AI SDK**: Python second-class. Rejected.
- **Portkey self-hosted**: viable; held as runner-up.
- **MCP per internal component**: not a recognized pattern + adds RPC overhead + schema drift between in-process and MCP versions of the same API. Rejected.

## Related docs

- `docs/03-research/R-009-multi-vendor-and-modularity.md` — full survey + recommendation
- `docs/04-architecture/tech-stack.md` Model gateway + Per-task model matrix sections
- `docs/04-architecture/system-overview.md` §6 retrieval / MCP plane
- `docs/12-security/mcp-security.md` — MCP security rules across both deployments
- `docs/00-bootstrap/assumptions.md` A-046..A-054

## Related code

- `src/gateway/api.py` — `LLMClient` ABC, `ModelGateway`, `default_gateway`
- `src/gateway/anthropic_adapter.py`, `src/gateway/openai_adapter.py`, `src/gateway/gemini_adapter.py` — concrete vendor adapters behind `LLMClient` (LiteLLM SDK-mode is the decision; there is no separate litellm_adapter module)
- `src/gateway/routing.py` — calibrated cascade + learned first-hop router — to be created in V1.7 (ADR-023)
- `src/gateway/api.py` — `FallbackClient` + `_pick_with_fallback` vendor fallback chain
- per-call cost/latency telemetry on `GatewayResponse` (`src/gateway/api.py`); dedicated Langfuse sink — not yet built
- `ttl: 3600` enforced at the gateway boundary (`src/gateway/api.py`, `cache_ttl must be 3600`); standalone `tools/lint_ttl_pinning.py` CI lint — to be created (GAP-031)
