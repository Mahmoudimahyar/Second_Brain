# ADR-024: LLM-as-Judge Hardening (Family-Exclusion + Independent Vote)

Status: **accepted** (2026-05-29)
Amends: ADR-006 (conflict resolution + LLM-as-judge restrictions).

## Context

ADR-006 restricts LLM-as-judge to same-tier same-year tie-breaks using a **3-vendor panel**
(Claude Sonnet 4.6 + Gemini 2.5 Flash + GPT-4.1-mini), ≥2/3 agreement, citing
"JudgeBiasBench >50% single-vendor error." The 2026-05-29 SOTA review (R-010) confirmed this
is **the strongest, most current piece of the design** — it maps almost exactly onto
**PoLL (Panel of LLM evaluators, Cohere, arXiv 2404.18796)** and uses the two best-supported
mitigations: cross-family diversity + majority vote, scoped narrowly to tie-breaks. Three
refinements + one correction:

1. **Generator/judge family overlap re-introduces self-preference bias.** If a candidate
   claim was produced/extracted by a Claude model and Claude Sonnet also judges, family/
   self-enhancement bias re-enters — the exact thing the panel removes. Must be guarded.
2. **Independent vote, not debate.** Multi-agent *debate* amplifies bias after round 1
   (arXiv 2505.19477). The panel must vote **independently** (judges do not see each other's
   verdicts), then majority. The current design intends this — make it explicit + tested.
3. **Reference-guided grading** where an L1 anchor exists is rated highly by the bias
   literature; use it when available.
4. **Correction:** "JudgeBiasBench" is **real** (arXiv 2603.08091, HIT, March 2026) but very
   fresh and the ">50% error" is on *adversarial bias-injected* items, **not** general
   judging accuracy. Re-state the citation precisely; don't lean on it as load-bearing.
   Also: the judge is currently **not wired** into the resolver (built, not wired — see
   `implementation-status.md`); wiring it is V1.7.

## Decision

1. **Family-exclusion rule.** For a given tie-break, the judge panel **excludes the vendor
   family that produced either candidate claim's extraction.** If exclusion would drop the
   panel below 3 distinct families, substitute another available vendor (e.g. add GPT-5.4-nano
   / Grok-4.1-Fast from the alternates) to keep ≥3 independent families. Record the panel
   composition in the audit log.
2. **Independent-vote, explicit + tested.** Judges are queried in isolation; no judge sees
   another's verdict or rationale. Majority (≥2/3) decides; no debate rounds. A test asserts
   no cross-judge context leakage.
3. **Reference-guided when L1 exists.** If an L1 anchor is available for the property, pass
   it as the reference; judges grade against it.
4. **Precise citation.** Update ADR-006 to state JudgeBiasBench correctly (adversarial-only,
   March-2026, treat as supporting not load-bearing) and cite PoLL as the primary basis.
5. **Keep the narrow scope** (same-tier same-year tie-breaks only) — good discipline, retained.

## Consequences

- `src/conflict/judge.py` gains family-exclusion panel selection + audit of composition;
  must be **wired into `ConflictResolver`** in the real pipeline (V1.7 — today it is built
  but the resolver is constructed without it).
- Slightly more vendor diversity bookkeeping (which family extracted the claim must be
  tracked on the claim — add `extractor_family` provenance).
- Robuster tie-breaks; removes a subtle self-preference leak; honest citations.

## Alternatives considered

- **Single strong judge (e.g. Sonnet).** Rejected — single-vendor bias; PoLL shows a diverse
  panel correlates better with humans and is cheaper.
- **Debate/See-each-other panel.** Rejected — amplifies bias (arXiv 2505.19477).
- **Ignore family overlap.** Rejected — reintroduces the bias the panel exists to remove.

## Related docs
- `docs/03-research/R-010-sota-review-2026-05.md` (PoLL arXiv 2404.18796; JudgeBiasBench arXiv 2603.08091; debate-amplifies-bias arXiv 2505.19477)
- `docs/11-decisions/ADR-006-conflict-resolution-and-llm-judge.md`
- `docs/00-bootstrap/implementation-status.md` (judge: Built→Wire in V1.7)

## Related code
- `src/conflict/judge.py` — family-exclusion panel selection + independent vote + audit
- `src/conflict/factory.py` — `build_three_vendor_judge` (3 vendor families from env keys)
- `src/cli.py` (`reconcile_demo`, `resolve`) + `flows/pass4_llm.py` — **construct the resolver WITH the judge** (wiring)
- `src/conflict/pass4_resolution.py` — reconcile real Pass-4 `Claim` conflicts
- `tests/conflict/test_judge_family_exclusion.py` — family-exclusion + independent-vote + builder tests
