"""RA-RAG-style cross-source consistency estimator (ADR-021, GAP-048).

`consistency(claim)` = degree to which independent sources agree on a claim's
value, weighted by source reliability (tier x credibility). High agreement
boosts; an isolated claim contradicting a strong consensus is lowered. This is
the V1 cheap, no-LLM mechanism that lets a corroborated community finding
compete with a stale official record (Astute/RA-RAG; soften "tier-first").
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

# Source-tier prior weights (also the ranker's w_tier). L1 > L2 > ... > L5.
DEFAULT_TIER_WEIGHTS: dict[str, float] = {
    "L1": 1.0, "L2": 0.85, "L3": 0.7, "L4": 0.55, "L5": 0.4,
}


@dataclass(frozen=True)
class SourceClaim:
    """One source's assertion of a fact's value, for agreement scoring."""

    value: Any
    source_tier: str
    credibility: float = 1.0


def reliability(
    tier: str, credibility: float, tier_weights: dict[str, float] | None = None,
) -> float:
    """Reliability mass of a source = tier prior x (clamped) credibility."""
    weights = tier_weights if tier_weights is not None else DEFAULT_TIER_WEIGHTS
    return weights.get(tier, 0.4) * max(0.0, credibility)


def _values_agree(a: Any, b: Any) -> bool:
    if isinstance(a, str) and isinstance(b, str):
        return a.strip().lower() == b.strip().lower()
    return bool(a == b)


def consistency(
    target: SourceClaim,
    peers: Sequence[SourceClaim],
    tier_weights: dict[str, float] | None = None,
) -> float:
    """Reliability-weighted agreement ratio in ``[0, 1]``.

    ``peers`` is the full set of claims on the same (subject, predicate),
    **including** ``target``. Returns the fraction of total reliability mass
    that agrees with ``target``'s value. A lone claim (peers == [target])
    scores the neutral ``1.0``.
    """
    total = sum(reliability(p.source_tier, p.credibility, tier_weights) for p in peers)
    if total <= 0:
        return 1.0
    agree = sum(
        reliability(p.source_tier, p.credibility, tier_weights)
        for p in peers
        if _values_agree(p.value, target.value)
    )
    return agree / total
