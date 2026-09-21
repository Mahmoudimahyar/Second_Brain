# ADR-006: Conflict Resolution Order + LLM-as-Judge Restrictions

Status: **accepted**
Date: 2026-05-20

## Context

Forum data is noisy + contradictory. The engine has to resolve disagreements between extracted claims (and between L5 claims and L1 ground truth) using a deterministic order that's defensible + testable. R-007b surveyed temporal-KG conflict-resolution literature; R-009 specified that any LLM-as-judge step needs cross-vendor calibration because single-vendor judges show > 50% error rate on JudgeBiasBench.

## Decision

### 6-step conflict-resolution order (deterministic; tested in `tests/conflict/`)

1. **L1 clash check.** Forum claim contradicts an L1 fact → forum claim flagged `Status: Invalidated_by_Official_Data`. L1 is **never** modified.
2. **Temporal disambiguation.** Two non-L1 claims disagree → check `t_valid_*`. If they fall in different validity intervals, split into year-tagged versions; this is not a conflict.
3. **Source-trust weighting.** Same `(t_valid_year, source_tier)` window? Apply Wikidata `rank` × tier ordering (L1 > L2 > L3 > L4 > L5) × intra-tier user-credibility (ADR-008). Winner gets `rank: preferred`; loser gets `rank: normal`.
4. **Signed-graph disagreement detection.** Still ambiguous (e.g., trust tied)? Signed-graph community detection on SUPPORTS/CONTRADICTS edges *detects disagreement* — it does **not** adjudicate by cluster size. ⚠️ **Corrected per ADR-026 (non-deferred): majority cluster ≠ truth** (a correct policy change often starts as a small minority). Consensus is decided by **source-trust-weighted stance aggregation** (ADR-021 `consistency`); a contradicting minority is routed to **web-verification (step 5)**, never auto-tagged `Status: Anomaly` by majority vote. Anomalies are still preserved (A-032), just not decided by cluster size. **Not built in V1** — Pass 3 uses k-means (GAP-049); this step is the V1.x detector evaluated in the ADR-026 spike.
5. **Web-verification trigger.** Non-L1 cluster disputes L1 AND L1 is stale (`t_valid_to` > 6 months old) → emit a `research_need` via outbound MCP → crawler fetches → re-ingest restarts the chain.
6. **HITL escalation.** Anything still ambiguous → HITL queue with a structured reason.

### LLM-as-judge restrictions

LLM-as-judge is invoked at **most once per claim**, inside step 3 (source-trust weighting) only when the trust-tier and rank are exactly tied AND the year is the same (`same-tier same-year tie-breaks` only). Even then:

- **Three-vendor mandatory**: Sonnet 4.6 + Gemini 2.5 Flash + GPT-4.1-mini run in parallel through the gateway.
- **≥ 2/3 agreement required** for a decision. Otherwise → HITL.
- **Audit-logged** with all three vendor outputs.

Outside that narrow window, LLM-as-judge is **not used**. JudgeBiasBench shows single-vendor LLM-as-judge has > 50% error rate on broad judging tasks; Fleiss' κ ≈ 0.3.

### Signed-graph community detection (step 4)

- Run on the opinion-layer subgraph (SUPPORTS / CONTRADICTS edges).
- Algorithm: signed-graph clustering (e.g., signed Spectral or signed Louvain variant — implementation choice in `src/conflict/signed_graph.py`).
- Runs nightly (offline). V1 stores `cluster_id` as edge property; V1.x makes clusters first-class in retrieval ranking.
- **Not vanilla Leiden** — Leiden ignores edge signs; we need to separate supporting vs contradicting clusters.
- **ADR-026 correction (non-deferred, applies regardless of the spike outcome):** the signed graph is a *disagreement detector*, not a truth adjudicator. Consensus = source-trust-weighted stance aggregation (ADR-021 `consistency`); a contradicting minority → web-verification, never auto-`Anomaly` by majority vote (majority ≠ correct).

## Consequences

- The 6-step order is encoded as a state machine in `src/conflict/resolver.py` with the transitions in `docs/05-features/01-slice-trust-tier-canonicalize/state-machine.md`.
- L1 immutability is enforced at the data layer (ADR-005); the resolver never has to "check" — the layer below refuses mutations.
- LLM-as-judge use is severely restricted; this is intentional. V1 slice **does not activate it** at all (SD-007) — irreducible cases go straight to HITL.
- V1.x activates LLM-as-judge once all 3 vendor accounts (Anthropic + OpenAI + Google) are live (A-052).
- Outlier preservation: contrarian-but-correct claims kept as `Status: Anomaly` + `prescient_correct` counter tracked for users whose low-karma rumors L1/L2 later confirm.
- HITL queue depth depends on threshold quality + signed-graph cluster quality. Operational risk if queue depth grows unbounded (mitigated by `monitoring.md` heuristics).
- Audit log captures every resolution path (step number + outcome) for every claim — drives the conflict-resolution-path distribution metric.

## Alternatives considered

- **Trust-score-only resolution** (no temporal disambiguation): wrong — 2014 claims with high trust would beat 2024 claims with lower trust. Rejected.
- **Always-LLM-as-judge**: rejected per JudgeBiasBench evidence (R-007b).
- **Vanilla Leiden on opinion layer**: ignores SUPPORTS / CONTRADICTS edge signs — clusters mix agreement + disagreement. Rejected.
- **Delete outliers**: loses the "Reddit knows the policy change before ADEA" signal. Rejected (A-032).

## Related docs

- `docs/03-research/R-007-multi-source-kg.md` R-007b (conflict + temporal + LLM-judge)
- `docs/03-research/R-009-multi-vendor-and-modularity.md` (3-vendor judge requirement)
- `docs/04-architecture/system-overview.md` §3 conflict resolution
- `docs/05-features/01-slice-trust-tier-canonicalize/state-machine.md` — claim conflict-resolution state machine
- `docs/00-bootstrap/assumptions.md` A-011, A-031, A-032, A-050

## Related code

- `src/conflict/resolver.py`
- `src/conflict/signed_graph.py` — signed-graph disagreement detector — not built (GAP-049; ADR-026 spike)
- `src/conflict/judge.py` — 3-vendor LLM-as-judge panel (built; resolver wiring lands in V1.7 per ADR-024)
