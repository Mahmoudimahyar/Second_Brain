# ADR-021: Trust-Tier-as-Prior Ranking + RA-RAG Cross-Source Consistency

Status: **accepted** (2026-05-29)
Amends: ADR-002 (hybrid retrieval), ADR-007 (HALO decay), Product Principle #2.
Supersedes the "ranks by tier **first**, then recency, then consensus" lexicographic rule.

## Context

The V1 docs describe retrieval as "ranks by **tier first**, then recency, then consensus
weight" (Product Principle #2), and `system-overview.md §5` gives
`ranking_score = tier_weight × rank_weight × decay × user_credibility`.

Two problems surfaced in the 2026-05-29 SOTA review (R-010):

1. **The lexicographic "tier-first sort" is a documented failure mode.** Sorting strictly
   by tier before anything else structurally buries a *correct minority/community* finding
   under *stale-but-official* L1 data. This is exactly the case the project most needs to
   get right in dental admissions: a policy change (new CASPA/prereq/CASPer rule) appears
   first as a small, correct L5 cluster while the L1 record is a year stale. Astute RAG
   quantifies that internal/community evidence is correct a large fraction of the time in
   conflict cases. (Note: the multiplicative `ranking_score` formula is **not** lexicographic
   and is fine — the *prose* "tier first" rule is the part that was wrong.)
2. **The claim "trust-tier retrieval is under-published — we are inventing it" is
   overstated.** Source-reliability-weighted RAG is a real 2024–2025 thread: **RA-RAG**
   (reliability estimation + weighted majority voting), **Astute RAG** (source-aware
   internal/external consolidation), **TrustRAG/ReliabilityRAG**. What is genuinely
   under-served is the *explicit ordinal L1–L5 provenance ladder* — that is our extension,
   not the whole idea.

Separately, neither the scorer nor HALO decay is actually wired (see
`implementation-status.md`): retrieval currently does substring + BFS with tier as a pure
filter. So this ADR specifies the ranking we will *build*, correctly.

## Decision

1. **Tier is a prior inside a calibrated score, not a hard pre-sort.** Keep the
   multiplicative form and add an explicit consistency term:

   ```
   ranking_score =
       w_tier(source_tier)              # monotone L1>L2>…>L5, but a WEIGHT not a gate
     × w_rank(rank)                     # preferred 1.0 / normal 0.5 / deprecated 0.0
     × decay(now, t_valid_from, half_life)   # HALO, per ADR-007 (now actually wired)
     × user_credibility(source)         # ADR-008 rubric
     × consistency(claim)               # NEW — RA-RAG-style cross-source agreement, [0,1]
   ```

   `w_tier` is configured so a high-`consistency`, high-`credibility`, fresh L5 cluster
   **can** outrank a stale, low-`decay` L1 record. Tier still dominates *all else equal*.

2. **RA-RAG-style cross-source consistency check.** `consistency(claim)` = degree to which
   independent sources agree on the claim's value, estimated by cross-checking agreement
   across the retrieved set (weighted by source reliability). High agreement boosts;
   isolated contradiction of a strong consensus lowers. This is the mechanism that lets a
   corroborated community finding compete with stale official data, and it feeds conflict
   resolution (ADR-006 / proposed ADR-026).

3. **Soften the novelty framing in the docs.** Replace "we are inventing this layer" with:
   *"source-reliability-weighted RAG exists (RA-RAG, Astute, TrustRAG); we extend it with an
   explicit ordinal L1–L5 provenance ladder and bitemporal recency."*

4. **`as_of` semantics unchanged.** Bitemporal filtering (ADR-005) still gates which edges
   are visible; ranking applies to the visible set.

## Consequences

- The retrieval ranker (`src/retrieval/ranking.py`, to be created — it does not exist
  today) becomes the single place tier/recency/credibility/consistency combine. Testable +
  deterministic given inputs.
- Need a `consistency` estimator over the retrieved/candidate set. V1: source-reliability-
  weighted agreement ratio (cheap, no LLM). V1.x: align with truth-discovery (ADR-026).
- `w_tier` becomes a tunable config, not a sort key — covered by ranking unit tests +
  a "minority-correct" regression fixture (a fresh corroborated L5 claim must be able to
  outrank a stale L1 claim).
- Removes a real product risk (burying correct community insight) and removes an overstated
  novelty claim reviewers would flag.

## Alternatives considered

- **Keep lexicographic tier-first sort.** Rejected — documented majority/staleness bias.
- **Pure learned reranker (LTR).** Deferred — no labeled relevance data yet; revisit when
  HITL produces judgments. The multiplicative prior is the interpretable V1 stand-in.
- **Drop tiers, use only earned reliability (pure RA-RAG).** Rejected for V1 — the L1
  license/immutability requirement needs an explicit tier anchor; we keep the ladder as a
  prior and add earned consistency on top.

## Related docs
- `docs/03-research/R-010-sota-review-2026-05.md` (citations: RA-RAG arXiv 2410.22954; Astute RAG arXiv 2410.07176; Wikidata Help:Ranking)
- `docs/04-architecture/system-overview.md` §5–6, `tech-stack.md` (ADR-002 row)
- `docs/11-decisions/ADR-002-hybrid-retrieval.md`, `ADR-007-halo-temporal-decay.md`
- `docs/00-bootstrap/implementation-status.md` (rows: tier ranking, HALO, hybrid retrieval)

## Related code (built in V1.7 — GAP-048/050)
- `src/retrieval/ranking.py` — scorer (tier prior + HALO decay + credibility + consistency)
- `src/retrieval/consistency.py` — RA-RAG-style cross-source agreement estimator
- `tests/retrieval/test_ranking.py` — incl. minority-correct regression fixture
- Wiring: `src/retrieval/api.py:query_graph` must call the scorer to order results
