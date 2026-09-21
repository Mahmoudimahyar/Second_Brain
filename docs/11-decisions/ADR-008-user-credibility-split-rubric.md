# ADR-008: User-Credibility Rubric — Source-Aware Split (Reddit vs SDN)

Status: **accepted** (V1 hand-weighted rubric; V1.1 logistic regression replaces)
Date: 2026-05-20

## Context

The user-actor layer in the multi-layer graph derives a credibility score per author. Reddit data has karma / upvote / downvote signals; SDN data does **not** (only post count + author + timestamp + content). A single rubric across both sources would underweight SDN authors (because they have 0 karma by definition) or overweight Reddit authors (because karma noise is large). R-007c + GAP-032 + A-043 = source-aware split is required.

## Decision

**Two parallel rubrics for V1, hand-weighted, source-aware.** Both produce scores in `[0, 1]`. Source-tier weighting (ADR-006 step 3) multiplies tier weight × per-source credibility score.

### Reddit rubric (10 features)

| Feature | Weight | Bounds |
|---|---:|---|
| `post_count` (log-scaled) | 0.10 | cap at log(1000) |
| `comment_count` (log-scaled) | 0.10 | cap at log(5000) |
| `upvote_total` (log-scaled) | 0.15 | cap at log(50000) |
| `account_age_years` | 0.10 | cap at 2 years |
| `comment_to_post_ratio` | 0.05 | [0, 1] |
| **`on_topic_ratio`** | **0.20** | strongest signal; fraction of posts in dental-related topics |
| `sockpuppet_penalty` | -0.10 | subtractive; based on simple heuristics (account-age vs activity-burst, suspicious naming patterns) |
| `inactivity_half_life_multiplier` | (multiplicative) | half-life 1 year on `last_active` |
| `gilded_bonus` (gilded comments / posts) | 0.05 | normalized |
| `prescient_correct_count` | 0.15 | low-karma claims later confirmed by L1/L2 (A-032) |

### SDN rubric (7 features — no upvote signal)

| Feature | Weight | Bounds |
|---|---:|---|
| `post_count` (log-scaled) | 0.15 | cap at log(1000) |
| `account_age_proxy_years` (from earliest-post timestamp) | 0.10 | cap at 2 years |
| `comment_to_post_ratio` | 0.05 | [0, 1] |
| **`on_topic_ratio`** | **0.25** | even more important without upvotes |
| `megathread_participation` (count of posts in known megathreads) | 0.15 | normalized |
| `longevity_months` (continuous activity span) | 0.15 | cap at 60 months |
| `prescient_correct_count` | 0.15 | same as Reddit |

`sockpuppet_penalty` not yet defined for SDN (limited metadata); deferred to V1.x.

### Score combination

```
credibility = clip(Σ (feature × weight), 0, 1)
```

Inactivity half-life applies multiplicatively after the weighted sum:

```
final = credibility × 2 ** (-months_inactive / 12)
```

## Consequences

- The `prescient_correct` counter requires the conflict resolver to update it when a low-karma claim is later confirmed by L1/L2 ingest. Implementation in `src/conflict/resolver.py`'s commit path.
- Author IDs are namespaced (`reddit:<sub>:<author>` vs `sdn:<author>`) — no cross-source contamination of credibility.
- The rubrics are visible + version-controlled (one Python module each: `src/credibility/reddit_rubric.py` / `sdn_rubric.py`).
- V1 hand-weights are placeholders. The intended V1.1 upgrade is a logistic regression trained on HITL gold labels of "this person's claim was reliable / not reliable."
- HITL gold-set growth for the logistic regression is GAP-028.
- Cross-source identity reconciliation (the same person posting on both Reddit and SDN) is **out of scope for V1**. V2 may add a `Person` super-node owning multiple namespaced `User` aliases.

## Alternatives considered

- **Unified rubric with karma weight = 0 on SDN**: makes SDN authors' scores artificially low because karma features are 0 across the board. Rejected.
- **Karma-only credibility**: ignores volume, longevity, on-topic ratio — would underweight long-tenured non-shouty authors. Rejected.
- **Reputation from external sources** (e.g., LinkedIn lookups): out of scope V1; questionable in V2.
- **No credibility scoring** (treat all L5 authors equal): defeats the purpose of source-trust weighting in conflict resolution.
- **Machine-learned credibility in V1**: no labels yet. Deferred to V1.1.

## Related docs

- `docs/03-research/R-007-multi-source-kg.md` R-007c
- `docs/00-bootstrap/source-documents.md` (Reddit vs SDN metadata differences)
- `docs/00-bootstrap/assumptions.md` A-033, A-043
- `docs/00-bootstrap/gap-register.md` GAP-019, GAP-028, GAP-032

## Related code

- `src/credibility/reddit_rubric.py`
- `src/credibility/sdn_rubric.py`
- `src/credibility/api.py` — `CredibilityScorer` (V1: hand-weighted; V1.1: logistic regression)
- `src/conflict/resolver.py` — `prescient_correct` counter increment path
