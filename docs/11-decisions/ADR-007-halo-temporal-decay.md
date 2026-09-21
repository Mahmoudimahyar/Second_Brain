# ADR-007: HALO Per-Edge-Type Half-Life Decay

Status: **accepted**
Date: 2026-05-20

## Context

Retrieval ranking + conflict resolution need temporal weighting: a 2014 tuition claim should weigh less in 2026 than a 2024 claim. R-007b surveyed time-sensitive RAG literature: global temporal decay (one half-life for all edge types) is wrong because different facts decay at different rates (`founding_year` never decays; `opinion_sentiment` decays in months). HALO-style **per-edge-type half-life** is the recommended pattern.

## Decision

**Per-edge-type half-life table** (NOT a global decay function). V1 hand-set; V1.1 may learn weights from data.

### V1 half-life table (`src/conflict/halo_table.py`)

| Edge type | Half-life | Rationale |
|---|---:|---|
| `tuition` | **1 year** | Annual updates from school registrars. |
| `avg_DAT` (school-level) | **2 years** | Slower drift than tuition. |
| `avg_GPA` (school-level) | **2 years** | Same drift pattern. |
| `interview_format` (MMI / traditional / panel) | **3 years** | Schools rarely change mid-stream. |
| `interview_question_reported` | **3 years** | Same as format; questions repeat across cohorts. |
| `program_requirement` (Casper required, etc.) | **2 years** | Cycle-by-cycle changes. |
| `founding_year` | **∞** | Never decays. |
| `school_attribute` (city, state, accreditation) | **∞** | Static facts. |
| `opinion_sentiment` (L5) | **6 months** | Community mood is fast. |
| `applicant_anecdote` (L5 self-report) | **2 years** | Personal stat snapshot. |
| `policy_advice` | **1 year** | Annual cycle drift. |
| any unmapped edge type | **1 year (default)** | Conservative default; new types must be added explicitly within 1 release. |

### Decay function

Exponential decay:

```
decay(now, t_valid_from, half_life) = 2 ** (-(now - t_valid_from) / half_life)
```

Final retrieval ranking weight (per `system-overview.md` §5):

```
ranking_score = tier_weight × rank_weight × decay(now, t_valid_from, half_life) × user_credibility
```

Where `tier_weight` decreases monotonically L1 > L2 > L3 > L4 > L5; `rank_weight` = 1.0 for preferred, 0.5 for normal, 0.0 for deprecated; `user_credibility` from the per-source rubric (ADR-008).

### Update policy

- HITL escalation when retrieval ranking surfaces clearly-stale results → reviewer can propose adjusting the half-life table.
- Changes to the table are an ADR-007 amendment (or a successor ADR if structurally different).
- V1.1 may replace the hand-set table with learned per-edge-type half-lives, once a labeled "what users found stale" dataset exists.

## Consequences

- Retrieval ranking is testable: deterministic decay + tier weights + rank weights mean any change to the table is reproducible.
- New edge types require a table entry (or fall back to the 1-year default). Adding a type without an entry triggers `HALO_HALFLIFE_MISSING` at runtime.
- The table is small + central — easy to audit + version-control.
- V1 default (1 year on unmapped types) is conservative — favors recency over staleness if forgotten.
- Mahyar can tune individual half-lives without architectural changes.

## Alternatives considered

- **Global decay** (one half-life for everything): wrong per R-007b. Rejected.
- **Linear decay** instead of exponential: simpler but doesn't match the long-tail of "old but still valid" facts well. Rejected for V1.
- **No decay** (rely on `as_of` filtering only): loses ranking-by-recency for present-time queries. Rejected.
- **Learn half-lives from labeled data**: V1.1 option. Requires labeled "user found this stale" data we don't have yet.
- **Per-domain decay** (different half-lives for dental-school vs medical-school data): out of scope; V1 is dental-only.

## Related docs

- `docs/03-research/R-007-multi-source-kg.md` R-007b
- `docs/04-architecture/system-overview.md` §5 retrieval ranking
- `docs/00-bootstrap/assumptions.md` A-019
- `docs/00-bootstrap/gap-register.md` GAP-020

## Related code

- `src/conflict/halo_table.py` — the per-edge-type half-life table
- `src/retrieval/ranking.py` — the decay function + ranking-weight combiner
- `tests/conflict/test_halo.py` — property-based tests + invariants
