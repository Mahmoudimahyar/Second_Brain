---
adr: 016
title: Web-search-grounded conflict resolution — Tavily-only with query-rephrase + 3-judge cross-check
status: accepted
date: 2026-05-24
deciders: Mahyar, Claude
supersedes:
superseded_by:
revision_history:
  - 2026-05-24 v1 — original Brave + Tavily 2-of-2 proposal (replaced).
  - 2026-05-24 v2 — Tavily-only with internal cross-check (V1.5-R2).
  - 2026-05-25 — accepted. V1.5c shipped the agent skeleton + 3-signal combine + cap + cache, but the prior session shipped the BAML templates as Python heuristics and signal C as single-vendor (gap audit CRITICAL-1 + CRITICAL-2). **W1-1** (2026-05-25 remediation) wired `make_question_via_gateway`, `paraphrase_via_gateway`, `verify_claim_via_gateway` through `default_gateway()` per ADR-011 + tech-stack matrix lines 78-81; heuristic fallbacks are now gated on `SECBRAIN_OFFLINE=1`. **W1-2** added `verify_claim_two_vendor_via_gateway` running Haiku 4.5 + Gemini Flash in parallel via `ThreadPoolExecutor`, with 6s per-vendor timeout, agreement-required reconciliation, and per-vendor breakdown recorded on `WebVerificationRun.signal_c["vendor_breakdown"]`. Spec is fully implemented as of this ratification.
---

# ADR-016 — Web-search-grounded conflict resolution (v2)

## Context

V1's conflict-resolution chain (`docs/04-architecture/system-overview.md` §3) has six steps. Step 5 is "web-verification trigger" — V1 only **emits** `research_need` records; nothing in V1 actually fetches anything.

V1.5c moves step 5 inside the engine. The first draft of this ADR specified Brave + Tavily 2-of-2 agreement. Mahyar (V1.5-R2 2026-05-24) added `TAVILY_API_KEY` only and chose Tavily-only. That removes the multi-provider quorum but does not change the principle that **a single oracle is not trustworthy enough to write conflict-resolution verdicts** — that principle was the entire reason V1 ADR-006 mandated three-vendor LLM-as-judge.

We need an equivalent cross-check pattern that:
1. Uses only Tavily for the web layer.
2. Reaches a comparable confidence floor to the original Brave+Tavily plan.
3. Stays within latency + cost budgets.
4. Has a clean fallback for ambiguous results.

Tavily's actual surface (researched 2026-05-24):
- `search(query, search_depth='advanced'|'basic'|'fast'|'ultra-fast', include_answer=True)` — returns ranked URLs + Tavily's synthesized answer.
- `qna_search(query)` — purpose-built fact-answering shortcut.
- `extract(urls, extract_depth='basic'|'advanced')` — clean content extraction.
- `crawl()` / `map()` / `research()` — out of scope for V1.5c.

## Decision

**Tavily-only single-provider web verification, with cross-check via (a) query rephrasing + (b) multi-vendor LLM-as-judge on the retrieved evidence. Three "verdict signals" must agree before the resolver writes a verdict; otherwise escalate to HITL.**

Specifically:

1. `src/conflict/web_verify.py` defines `WebVerificationAgent.verify(claim, context) -> VerdictResult`. The agent runs three operations in parallel and combines them via majority vote.

2. **Signal A — Tavily QNA on original claim**:
   - Query = the disputed claim rephrased as a question (LLM-generated, Gemini Flash-Lite via gateway, BAML template `make_question_from_claim`).
   - Call `tavily.qna_search(question, search_depth='advanced', include_answer=True, max_results=5)`.
   - Returns: `{answer, urls[]}`. The synthesized `answer` is the verdict signal A.

3. **Signal B — Tavily search on a rephrased query**:
   - Generate a paraphrase of the original question (BAML template `paraphrase_question`, Gemini Flash-Lite). Paraphrase must change ≥ 3 content words OR change phrasing structure.
   - Call `tavily.search(paraphrased_question, search_depth='advanced', include_answer=True, max_results=5)`.
   - Returns: `{answer, urls[]}`. Synthesized `answer` is signal B.

4. **Signal C — Extract + LLM-verify on top URLs**:
   - Take the union of top 3 URLs from signals A + B (deduplicated, default cap = 6 URLs).
   - Call `tavily.extract(urls, extract_depth='advanced')` to get clean page text.
   - Run **two-vendor LLM verification** (Haiku 4.5 + Gemini Flash via gateway; both required) with BAML template `verify_claim_from_evidence(claim, evidence)`. Each LLM returns `{verdict: supports|refutes|unknown, evidence_excerpt, confidence}`.
   - Signal C = (verdict, evidence) only if both vendors return the **same verdict**. Otherwise signal C = `disagreement`.

5. **Combine**:
   - If at least 2 of {A, B, C} agree on the same verdict (`supports` or `refutes`) with confidence ≥ 0.7, write the verdict to the graph with `references` pointing to all corroborating URLs + extracted evidence excerpts.
   - If signal C is `disagreement` AND signals A/B disagree → escalate to HITL (`web_search_disagreement` item type).
   - If all three signals return `unknown` → emit a `research_need` for human follow-up; the resolver does not write a verdict.
   - If exactly two signals agree but the third disagrees → write the verdict but flag `low_confidence` and emit a `verification_followup` note in audit log.

6. **Verdict provenance**: every verdict stores a `web_verification_run` JSON containing all three signals, the questions used, raw Tavily responses, extracted page contents, per-vendor LLM verdicts, final combine logic. Citation traceability is per-URL plus per-page-excerpt.

7. **Cost cap**: per-corpus cap default $5 / sweep, configurable in `/settings/web-search`. Tracked by Langfuse + a SQLite `web_search_cost` table. Cap triggers a `cap_hit` audit event and freezes new web-verify calls until next sweep window or manual reset.

8. **Cache**: identical `(claim_hash, context_summary_hash, tavily_model_version, llm_versions)` cache key. 7-day TTL. Cache hit replays the prior signals + combine; no API calls.

9. **Latency budget**: typical run ~3-5s. Hard timeout 15s. Per-call timeouts: Tavily 8s; LLM verify 6s.

10. **Failure modes**:
    - Tavily rate-limit / 5xx → exponential backoff (3 tries, 1s/2s/4s). After 3 failures: emit `tavily_unavailable` and route to HITL.
    - LLM gateway failure (rare given ADR-011 Anthropic→OpenAI fallback) → re-cast signal C with a single vendor and `low_confidence` flag.
    - Empty Tavily result on a signal → that signal becomes `unknown`.

11. **API-key storage**: `TAVILY_API_KEY` in plaintext `.env` (V1.5-R1 Q8). Documented in `docs/12-security/v1.5-credentials.md`. Settings page (`/settings/web-search`) runs a health-check on save.

## Consequences

**Positive:**
- Mirrors ADR-006's three-judge invariant. Three independent verdict signals before writing a graph claim is comparable rigor to three-vendor LLM-as-judge.
- Query-rephrasing catches Tavily's index sensitivity to phrasing (a real problem with single-provider search).
- Two-vendor extract-verify (Haiku + Gemini) inside signal C reuses the existing model gateway + cost-tier matrix — no new infrastructure.
- Single Tavily dependency simplifies billing + key management.
- Tavily's `qna_search` + `include_answer` modes give us pre-synthesized answers, dramatically reducing the post-Tavily LLM workload vs raw URL scraping.
- Provenance + cache + cost cap all carry over from the v1 design.

**Negative:**
- One web provider = one outage = one ADR-level blast radius. Mitigated by HITL escalation on `tavily_unavailable`.
- LLM cost is higher than v1's "two search APIs" cost — we run 4 LLM calls per verification (question-gen, paraphrase, Haiku verify, Gemini verify). Per ADR-003's matrix this is ~$0.001-0.005 per verification at V1.5c volumes; well under budget.
- Three-signal combine logic is more complex than 2-of-2. Documented + property-tested.
- We're trusting Tavily's `include_answer` synthesis for signals A + B. If Tavily ever degrades on synthesis quality, signal C (LLM-verified extracts) becomes the load-bearing one. Mitigated by ongoing eval on the 5-seeded-clash gold set.

**Neutral:**
- The v2 design technically uses Tavily three times (qna_search + search + extract). Tavily counts each as a separate API hit for billing. Cost-cap math accounts for this.
- The user can swap Tavily for any other provider later by implementing `SearchProvider` Protocol; the three-signal combine logic stays intact.

## Alternatives considered (and rejected)

- **Brave + Tavily 2-of-2** (this ADR's v1) — rejected per V1.5-R2 user direction. Mahyar added Tavily key only.
- **Tavily-only with 1-of-1** — rejected. Single-oracle verdict is too low-confidence for a graph-write step that must hold under ADR-005 trust-tier invariants.
- **Tavily-only with N-of-1 paraphrases** (only signals A + B, no LLM-extract) — rejected. Both signals come from the same provider's index; "agreement" is just Tavily agreeing with itself.
- **Tavily-only with LLM-only verification** (skip signals A + B; just `tavily.extract` + LLM judge) — rejected. Loses Tavily's synthesized answers, which are higher-precision than raw scrape + LLM.
- **Add a free SearXNG meta-search as second provider** — considered. Rejected: ops burden + no AI re-ranking + worse quality.

## Implementation

V1.5c, after V1.5b ships. Code skeleton:

```
src/conflict/
  web_verify.py         # WebVerificationAgent
  providers/
    base.py             # SearchProvider Protocol (Tavily today; pluggable for future)
    tavily.py           # TavilyProvider (qna_search + search + extract)
  signal_combine.py     # three-signal combine logic + escalation
  baml/
    make_question_from_claim.baml
    paraphrase_question.baml
    verify_claim_from_evidence.baml
src/gateway/api.py      # ensure team_content_angles + web_verify tasks register in matrix
```

UI: `/settings/web-search` (V1.5c) for cap config + Tavily key health-check; `/hitl/escalated` renders `web_search_disagreement` + `tavily_unavailable` item types.

## References

- ADR-006 — conflict-resolution order; three-judge invariant
- ADR-011 — model gateway (LLM cost matrix + fallback chain)
- `docs/05-features/04-slice-v1.5c-conflict-and-teams/requirements.md` FR-1.5c-*
- V1.5-R1 Q10 web-search tool answer (originally Brave+Tavily); V1.5-R2 user direction changing to Tavily-only
- Research log 2026-05-24: Tavily SDK + few-shot collapse
- [Tavily SDK Reference](https://docs.tavily.com/sdk/python/reference)
- [Tavily Python SDK GitHub](https://github.com/tavily-ai/tavily-python)
