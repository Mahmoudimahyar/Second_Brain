"""ADR-026 L1-anchored joint-confidence conflict resolver (the hybrid).

The bounded ADR-026 bake-off (`tools/conflict_bakeoff/`, 75ff25b) found that pure
joint-confidence scoring beats the deterministic cascade on accuracy and
minority-correct recall, but would let a corroborated-but-*wrong* L5 majority
override a **current** L1 fact (seed case C3 — majority != truth). This resolver
keeps joint-confidence's strengths and restores L1 immutability (non-negotiable
#3) with three rules, applied per ``(subject, predicate)`` claim group:

  1. **Current-L1 immutability (hard guardrail).** If any L1 claim is still
     *current* — its HALO decay is at or above ``tau_current`` — that L1 value
     wins outright, regardless of how corroborated a contradicting non-L1
     cluster is. This is what pure joint-confidence lacked (fixes C3).

  2. **Joint-confidence mass** (only when no L1 claim is current). The winner is
     the value with the most confidence mass::

         mass(v) = SUM over claims asserting v of
                   anchor[tier] * halo_decay(now, t_valid_from, predicate)
                                * max(credibility, cred_floor)

     Corroboration falls out naturally as claim count (more independent claims
     for a value -> more mass). The L1 ``anchor`` weight (a multiple of the base
     tier prior) keeps a still-fresh L1 dominant, while HALO decay erodes a
     *stale* L1 so a fresh, corroborated lower-tier correction can win — the
     minority-correct cases (C2/C5/C7). ``tau_current`` lives in decay-space, so
     it is per-predicate via the HALO half-life for free: a never-decaying
     ``founding_year`` L1 is permanently immutable; a fast-decaying opinion goes
     correctable sooner.

  3. **Abstain band.** If the top value's relative lead over the runner-up is
     below ``abstain_margin``, the group is abstained to HITL rather than
     guessed — genuine ties with no recency/corroboration signal (C8).

ADR-026 stays ``proposed``: this is **Built + Wired behind a flag**
(``SECBRAIN_JOINT_RESOLVER=1`` on the Pass-4 path), default off, pending a real
HITL-labeled conflict set to justify flipping the default.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from src.conflict.halo_table import decay
from src.conflict.resolver import ResolutionStatus
from src.retrieval.consistency import DEFAULT_TIER_WEIGHTS

if TYPE_CHECKING:
    from datetime import datetime

    from src.conflict.resolver import Claim

# L1 gets a 3x prior over its base tier weight — the "anchor". Tuned on the
# ADR-026 bake-off seed so a *current* L1 dominates a fresh 3x-corroborated L5
# rumor, while a deeply-decayed stale L1 yields. Validated as candidate (c) in
# tools/conflict_bakeoff (7/7 decidable correct, C8 abstains, C3 fixed).
L1_ANCHOR_MULTIPLIER: float = 3.0
# HALO decay at/above this => L1 is "current" and immutable; below => stale and
# correctable by fresh corroborated evidence. In decay-space => per-predicate.
DEFAULT_TAU_CURRENT: float = 0.05
# Credibility floor so a 0-credibility source still contributes a little mass.
DEFAULT_CRED_FLOOR: float = 0.05
# Abstain when (top_mass - runner_mass) / top_mass is below this.
DEFAULT_ABSTAIN_MARGIN: float = 0.10


def _hashable(value: Any) -> Any:
    """Return a hashable key for an arbitrary claim value (mass-dict key)."""
    try:
        hash(value)
    except TypeError:
        return repr(value)
    return value


@dataclass(frozen=True)
class JointResolution:
    """Outcome of resolving one ``(subject, predicate)`` group."""

    status: ResolutionStatus
    winner_value: Any | None
    winning_claim: Claim | None
    losing_claims: list[Claim]
    mass: dict[Any, float] = field(default_factory=dict)
    margin: float = 0.0
    reason: str = ""
    low_confidence: bool = False


class L1AnchoredJointResolver:
    """Set-based conflict resolver: L1-anchored joint-confidence (ADR-026)."""

    def __init__(
        self,
        *,
        anchor_multiplier: float = L1_ANCHOR_MULTIPLIER,
        tau_current: float = DEFAULT_TAU_CURRENT,
        cred_floor: float = DEFAULT_CRED_FLOOR,
        abstain_margin: float = DEFAULT_ABSTAIN_MARGIN,
    ) -> None:
        self._tau = tau_current
        self._cred_floor = cred_floor
        self._abstain_margin = abstain_margin
        self._weights = dict(DEFAULT_TIER_WEIGHTS)
        self._weights["L1"] = self._weights.get("L1", 1.0) * anchor_multiplier

    # -- public ---------------------------------------------------------------

    def resolve_group(self, claims: list[Claim], *, now: datetime) -> JointResolution:
        """Resolve a list of competing claims for one (subject, predicate)."""

        if not claims:
            return JointResolution(
                status=ResolutionStatus.NO_CONFLICT, winner_value=None,
                winning_claim=None, losing_claims=[], reason="empty group",
            )

        distinct = {_hashable(c.object_value) for c in claims}
        if len(distinct) == 1:
            return JointResolution(
                status=ResolutionStatus.NO_CONFLICT,
                winner_value=claims[0].object_value, winning_claim=claims[0],
                losing_claims=[], reason="single agreed value (no conflict)",
            )

        # Rule 1: current-L1 immutability (hard guardrail).
        current_l1 = [
            c for c in claims
            if c.source_tier == "L1"
            and self._claim_decay(c, now) >= self._tau
        ]
        if current_l1:
            l1_values = {_hashable(c.object_value) for c in current_l1}
            if len(l1_values) > 1:
                # L1 internally disagrees — an anomaly; do not guess.
                return JointResolution(
                    status=ResolutionStatus.HITL_PENDING, winner_value=None,
                    winning_claim=None, losing_claims=list(claims),
                    reason="current L1 claims disagree (anomaly) — escalate to HITL",
                    low_confidence=True,
                )
            winner = max(current_l1, key=lambda c: self._mass_of(c, now))
            losers = [
                c for c in claims
                if _hashable(c.object_value) != _hashable(winner.object_value)
            ]
            return JointResolution(
                status=ResolutionStatus.L1_CLASH_INVALIDATED,
                winner_value=winner.object_value, winning_claim=winner,
                losing_claims=losers, mass=self._mass_table(claims, now),
                margin=1.0,
                reason="current L1 is immutable; contradicting non-L1 claims "
                       "invalidated (non-negotiable #3; ADR-026 rule 1)",
            )

        # Rule 2: joint-confidence mass (no current L1).
        mass = self._mass_table(claims, now)
        ranked = sorted(mass.items(), key=lambda kv: kv[1], reverse=True)
        top_key, top_mass = ranked[0]
        runner_mass = ranked[1][1] if len(ranked) > 1 else 0.0
        margin = (top_mass - runner_mass) / top_mass if top_mass > 0 else 0.0

        # Rule 3: abstain on a thin margin (genuine tie).
        if margin < self._abstain_margin:
            return JointResolution(
                status=ResolutionStatus.HITL_PENDING, winner_value=None,
                winning_claim=None, losing_claims=list(claims), mass=mass,
                margin=margin,
                reason=f"top-vs-runner margin {margin:.0%} < "
                       f"{self._abstain_margin:.0%} — genuine tie, escalate to HITL",
                low_confidence=True,
            )

        winner = max(
            (c for c in claims if _hashable(c.object_value) == top_key),
            key=lambda c: self._mass_of(c, now),
        )
        losers = [
            c for c in claims if _hashable(c.object_value) != top_key
        ]
        # Did a (stale) L1 value lose to a fresher non-L1 cluster?
        stale_l1_corrected = any(c.source_tier == "L1" for c in losers)
        reason = (
            "stale L1 corrected by fresh corroborated evidence "
            "(ADR-026 rule 2; HALO-decayed L1 out-massed)"
            if stale_l1_corrected else
            "highest joint-confidence mass wins (ADR-026 rule 2)"
        )
        return JointResolution(
            status=ResolutionStatus.TRUST_WEIGHTED, winner_value=winner.object_value,
            winning_claim=winner, losing_claims=losers, mass=mass, margin=margin,
            reason=reason, low_confidence=stale_l1_corrected,
        )

    # -- internals ------------------------------------------------------------

    def _claim_decay(self, claim: Claim, now: datetime) -> float:
        return decay(now, claim.t_valid_from, claim.predicate)

    def _mass_of(self, claim: Claim, now: datetime) -> float:
        w = self._weights.get(claim.source_tier, 0.4)
        d = self._claim_decay(claim, now)
        cred = max(claim.credibility, self._cred_floor)
        return w * d * cred

    def _mass_table(self, claims: list[Claim], now: datetime) -> dict[Any, float]:
        mass: dict[Any, float] = defaultdict(float)
        for c in claims:
            mass[_hashable(c.object_value)] += self._mass_of(c, now)
        return dict(mass)
