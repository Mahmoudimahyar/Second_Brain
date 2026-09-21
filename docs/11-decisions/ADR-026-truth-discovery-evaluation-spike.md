# ADR-026: Learned/Probabilistic Truth-Discovery vs Deterministic Cascade — SPIKE

Status: **proposed** (2026-05-29) — **decision deferred to a spike.** The deterministic
6-step cascade (ADR-006) stays the V1 default until this spike shows a measured win.

## Context

ADR-006 resolves conflicts with a **fixed, hand-ordered cascade**: L1-clash → temporal →
source-trust → (signed-graph consensus) → web-verify → HITL. The 2026-05-29 SOTA review
(R-010) found this is **auditable and a fine engineering scaffold, but behind the field**:

- Mature conflict resolution is **probabilistic / learned truth-discovery**, where source
  trust and claim confidence are **jointly estimated**, not applied in a frozen priority
  order: **TruthFinder**, **Latent Truth Model**, **CRH** (truth-discovery survey
  arXiv 1505.02463), and 2025 LLM-hybrid fusion like **KARMA** (multi-agent conflict-
  resolution agents, NeurIPS 2025).
- A rigid order bakes in questionable invariants — e.g. that temporal recency always beats
  source trust (or vice versa) — which truth-discovery research shows is often wrong.
- **Two sub-parts of the cascade are also currently mis-built** (see `implementation-status.md`):
  signed-graph community detection is actually plain k-means (deferred to "V1.x" in code),
  and "majority cluster = truth" is the documented **majority ≠ correct** fallacy — dangerous
  in admissions where a correct policy change starts as a small minority cluster. So step 4
  needs rethinking regardless.

## Spike (the decision)

Bounded evaluation against the deterministic cascade:

1. **Candidates:** (a) deterministic cascade (current), (b) cascade with steps 2–3 (temporal
   + trust) **collapsed into one jointly-estimated confidence score** (source-reliability ×
   recency × corroboration, feeding ADR-021's `consistency`), ordered escalation kept only
   for tie-break → web-verify → HITL, (c) a truth-discovery layer (CRH/LTM-style) over the
   claim/source graph.
2. **Labeled set:** a HITL-labeled conflict set (grows from V1 forum ingest; seed with
   ADEA-vs-forum tuition/requirement contradictions where L1 gives ground truth).
3. **Metrics:** conflict-resolution accuracy vs HITL labels; **minority-correct recall**
   (does it keep a corroborated correct minority instead of binning it "Anomaly"?); HITL
   queue depth (how many it auto-resolves correctly); auditability/explainability.
4. **Decision criterion:** adopt (b) or (c) only if it beats the deterministic cascade on
   accuracy **and** minority-correct recall **without** an unacceptable loss of auditability,
   and **without ever overriding L1 immutability**. Otherwise keep deterministic, but still
   apply the two fixes below (they are not optional).

## Decisions that are NOT deferred (apply regardless of spike outcome)

- **Stop using cluster size to decide truth.** Signed-graph community detection (when built —
  GAP-049) is a *disagreement detector*, not an adjudicator. Consensus is decided by
  **source-trust-weighted stance aggregation** (ties into ADR-021 `consistency`), and a
  minority is routed to **web-verification**, **not** tagged `Anomaly` by default.
- **Canonicalize the cascade step numbering** across `system-overview.md`, `resolver.py`,
  and ADR-006 (they currently disagree — web-verify is step 4 vs 5 vs 6 in different docs).

## Measured outcome — bounded bake-off (V1.7, 2026-05-29 → 2026-05-30)

Ran (a) deterministic cascade vs (b) joint-confidence score vs **(c) the
L1-anchored joint-confidence hybrid** on an 8-case **L1-grounded** seed
(`tools/conflict_bakeoff/`; reports `.agent/reports/v1.7-wp5-adr026-conflict-bakeoff.md`
and `…-joint-resolver-wired.md`):

| | accuracy | minority-correct recall | C3 (rumor vs current L1) | C8 (genuine tie) |
|---|---|---|---|---|
| (a) deterministic cascade | 0.38 | **0.00** | ok | guesses |
| (b) joint-confidence score | 0.88 | **1.00** | **fails — overrides L1** | ok (lucky) |
| **(c) L1-anchored joint (hybrid)** | **0.88** | **1.00** | **ok — L1 protected** | **abstains (safe)** |

**(b) is far better** than (a) at the defining job (fresh corroborated corrections +
same-tier ties), but **fails the one case where a corroborated-wrong fresh majority
faces a current L1** — pure (b) would override L1 (forbidden). **(c) closes that gap**:
joint-confidence mass with a current-L1 hard guardrail + HALO-decayed stale-L1
correction + an abstain band — same accuracy/minority-recall as (b), fixes C3, and
abstains on genuine ties. **(c) is now built + wired** (`src/conflict/joint_resolver.py`,
behind `SECBRAIN_JOINT_RESOLVER=1`, default off) and validated end-to-end on the real
`secbrain resolve` CLI over the 78-school L1 graph. **Status stays `proposed`**: flip
the default to on / ADR to `accepted` only after validating on a **real HITL-labeled**
conflict set (this seed is the constructed bootstrap). Never override L1 immutability.

## Consequences

- If "adopt": a `src/conflict/truth_discovery.py` layer + a successor ADR; the resolver
  becomes score-driven with deterministic escalation for ties.
- If "keep": deterministic cascade stays, plus the two non-deferred fixes above.
- Either way, the conflict path must finally be **wired with the judge + web-verifier**
  (today the resolver is built with neither — ADR-024 + V1.7).

## Related docs
- `docs/03-research/R-010-sota-review-2026-05.md` (truth-discovery survey arXiv 1505.02463; KARMA; majority≠correct)
- `docs/11-decisions/ADR-006-conflict-resolution-and-llm-judge.md`, `ADR-021` (consistency term), `ADR-024` (judge wiring)
- `docs/00-bootstrap/gap-register.md` GAP-049 (signed-graph not built)

## Related code
- `tools/conflict_bakeoff/` — cascade vs joint-score vs **L1-anchored hybrid (c)** on the seed
- `src/conflict/joint_resolver.py` — `L1AnchoredJointResolver` (the hybrid, recommendation realized)
- `src/conflict/pass4_resolution.py` — `build_joint_resolver_if_enabled()` + set-based wiring (flag-gated, default off)
