# ADR-023: Calibrated Cascade Routing + Learned First-Hop Router

Status: **accepted** (2026-05-29)
Amends: ADR-003 addendum (per-task model matrix), ADR-011 (model gateway).

## Context

ADR-003/011 define a confidence-threshold cascade: Gemini 2.5 Flash-Lite → Claude Haiku 4.5
→ Claude Sonnet 4.6, escalating when a stage's confidence is below a hand-set threshold
(e.g. < 0.9, < 0.7). The gateway is LiteLLM **SDK mode** wrapped by a custom `LLMClient`
ABC, justified by "proxy mode is 1.7–4× slower."

The 2026-05-29 SOTA review (R-010) confirmed the architecture is sound but found two issues:

1. **Raw confidence thresholds are overconfident / poorly calibrated.** This is the
   documented weak spot of FrugalGPT-style cascades ("Overconfidence in LLM-as-a-Judge"
   arXiv 2508.06225; UCCI calibrated cascade arXiv 2605.18796). Thresholding raw
   self-reported confidence or logprobs over-escalates on easy items and under-escalates on
   hard ones. SOTA = **calibrated** escalation (isotonic/Platt scaling of the confidence
   signal, threshold chosen by cost-constrained optimization).
2. **Pure sequential escalation pays for failed cheap tiers on obviously-hard inputs.**
   A **learned first-hop router** (RouteLLM, arXiv 2406.18665) can send clearly-hard items
   straight to the strong model, skipping wasted tiers.
3. **The "proxy is 1.7–4× slower" rationale is cited out of regime.** That figure comes from
   a self-hosted vLLM high-RPS issue (LiteLLM #21046); our workload is **API-bound** vendor
   calls where the proxy overhead is single-digit-ms and negligible. The *honest* rationale
   for SDK mode is "avoid operating another stateful service (Redis/Postgres), in-process is
   simpler" — keep SDK mode, fix the justification.

## Decision

1. **Calibrate the escalation signal.** Replace raw-confidence thresholds with a calibrated
   probability of correctness per stage (isotonic regression fit on a small labeled set;
   fall back to a sensible fixed threshold until that set exists). Threshold picked to meet
   a target accuracy at minimum cost. Keep the 3-tier cascade.
2. **Add an optional learned first-hop router** (RouteLLM-style strong/weak classifier) in
   front of the cascade. It may route an item directly to Haiku or Sonnet, skipping
   Flash-Lite, when predicted hard. Config-gated; default off until the router is trained on
   accumulated traces, so V1 behavior is unchanged until we have data.
3. **Correct the SDK-mode rationale** in ADR-011 / tech-stack: SDK mode is chosen to avoid
   running another stateful service, **not** for a throughput claim that doesn't apply to
   API-bound calls. (A thin Go gateway like Bifrost is noted as a future option if a
   gateway hop ever becomes the bottleneck — not needed for V1.)
4. **Keep the per-task model matrix as the authoritative routing source** (non-negotiable
   #12) — calibration + router are *config + tested models*, not ad-hoc prompt switches.

## Consequences

- New module `src/gateway/routing.py` (calibrated thresholds + optional router) behind the
  `LLMClient` ABC. Telemetry (Langfuse) already captures the per-call data needed to fit the
  calibrator and train the router.
- Until a labeled/trace set exists, behavior == today's fixed-threshold cascade (router off,
  calibrator = identity). So this is a safe, incremental upgrade.
- Cost regression test extended: calibrated cascade must not *increase* spend on the V1 gold
  sweep; router (when on) must reduce failed-tier spend without F1 regression.
- Reconciles the gateway rationale with reality (removes an out-of-regime claim a reviewer
  would flag).

## Alternatives considered

- **Keep raw-confidence thresholds.** Rejected — known overconfidence; cheap to fix.
- **Replace cascade with pure learned routing (one-shot).** Rejected for V1 — needs training
  data; cascade is the safe default. Router is additive.
- **Switch gateways (Portkey / OpenRouter / Bifrost).** Not now — SDK + thin ABC is fine for
  API-bound V1; documented as future options in ADR-011.

## Related docs
- `docs/03-research/R-010-sota-review-2026-05.md` (UCCI arXiv 2605.18796; RouteLLM arXiv 2406.18665; LiteLLM #21046; FrugalGPT)
- `docs/11-decisions/ADR-003-extraction-stack.md`, `ADR-011-model-gateway-and-mcp-policy.md`
- `docs/04-architecture/tech-stack.md` (model gateway + per-task matrix)

## Related code (built in V1.7 — Q-031 → option a)
- `src/gateway/routing.py` — `CalibratedCascade` (LLMClient): cheapest-tier-first, escalate on calibrated confidence < threshold; optional `FirstHopRouter` (default off)
- `src/gateway/calibration.py` — `IdentityCalibrator` (default) + `IsotonicCalibrator` (identity until `fit`)
- `tests/gateway/test_calibrated_cascade.py`, `tests/gateway/test_router.py`
- Wiring: `src/gateway/api.py` `default_gateway()` registers the cascade for `PASS4_CONFLICT_CANDIDATE` + `PASS4_INTERVIEW_Q` (Haiku→Sonnet) under `SECBRAIN_CASCADE=1` — **default off**; behavior == task-matrix routing until enabled + a trace set trains the calibrator/router
