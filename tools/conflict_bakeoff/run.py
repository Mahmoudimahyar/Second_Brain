"""Run the ADR-026 conflict bake-off: deterministic cascade vs joint-confidence.

  python -m tools.conflict_bakeoff.run
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from src.conflict.halo_table import decay
from src.conflict.joint_resolver import L1AnchoredJointResolver
from src.conflict.resolver import Claim, ConflictResolver
from src.retrieval.consistency import DEFAULT_TIER_WEIGHTS
from tools.conflict_bakeoff.seed import SEED, ConflictCase

_NOW = datetime(2026, 5, 29, tzinfo=UTC)


def _to_claim(case: ConflictCase, idx: int, value: str, tier: str,
              year: int, credibility: float) -> Claim:
    return Claim(
        claim_id=f"{case.case_id}:{idx}", subject_id=case.subject,
        predicate=case.predicate, object_value=value, source_tier=tier,
        t_valid_from=datetime(year, 1, 1, tzinfo=UTC), credibility=credibility,
    )


def cascade_resolve(case: ConflictCase) -> str | None:
    """Candidate (a): the current deterministic ConflictResolver (ADR-006), no
    judge wired (V1 default → ties abstain to HITL). Returns the winning value
    or None (abstained)."""
    resolver = ConflictResolver()
    claims = [
        _to_claim(case, i, c.value, c.source_tier, c.t_valid_year, c.credibility)
        for i, c in enumerate(case.claims)
    ]
    winner = claims[0]
    resolved = True
    for c in claims[1:]:
        outcome = resolver.reconcile(c, [winner])
        if outcome.winning_claim is not None:
            winner = outcome.winning_claim
            resolved = True
        else:
            resolved = False  # HITL_PENDING → abstain
    return str(winner.object_value) if resolved else None


def joint_score_resolve(case: ConflictCase) -> str:
    """Candidate (b): pick the value with the most jointly-estimated confidence
    mass = sum of source-reliability(tier) x recency(HALO decay) x credibility x
    corroboration (ADR-026 candidate b). Reuses consistency tier weights + HALO."""
    mass: dict[str, float] = defaultdict(float)
    for c in case.claims:
        w_tier = DEFAULT_TIER_WEIGHTS.get(c.source_tier, 0.4)
        d = decay(_NOW, datetime(c.t_valid_year, 1, 1, tzinfo=UTC), case.predicate)
        mass[c.value] += w_tier * d * max(c.credibility, 0.0) * c.corroborations
    return max(mass, key=lambda v: mass[v])


def joint_anchored_resolve(case: ConflictCase) -> str | None:
    """Candidate (c): the L1-anchored joint-confidence hybrid (ADR-026 reco).

    Expands each ClaimInput's corroboration count into N independent Claims (so
    corroboration = claim count, the real-pipeline semantics), then resolves the
    group. Returns the winning value or None (abstained to HITL)."""
    claims: list[Claim] = []
    for i, ci in enumerate(case.claims):
        for k in range(ci.corroborations):
            claims.append(_to_claim(case, i * 1000 + k, ci.value, ci.source_tier,
                                    ci.t_valid_year, ci.credibility))
    out = L1AnchoredJointResolver().resolve_group(claims, now=_NOW)
    return None if out.winner_value is None else str(out.winner_value)


@dataclass(frozen=True)
class MethodScore:
    name: str
    correct: int
    total: int
    minority_correct: int
    minority_total: int

    @property
    def accuracy(self) -> float:
        return self.correct / self.total if self.total else 0.0

    @property
    def minority_recall(self) -> float:
        return self.minority_correct / self.minority_total if self.minority_total else 0.0


def _score(name: str, resolve: Callable[[ConflictCase], str | None]) -> MethodScore:
    correct = mc = mt = 0
    for case in SEED:
        picked = resolve(case)
        hit = picked == case.ground_truth
        correct += int(hit)
        if case.minority_correct:
            mt += 1
            mc += int(hit)
    return MethodScore(name, correct, len(SEED), mc, mt)


def main() -> int:
    cascade = _score("deterministic-cascade (a)", cascade_resolve)
    joint = _score("joint-confidence-score (b)", joint_score_resolve)
    anchored = _score("l1-anchored-joint (c)", joint_anchored_resolve)

    print(f"ADR-026 conflict bake-off — {len(SEED)} L1-grounded cases\n")
    for m in (cascade, joint, anchored):
        print(f"  {m.name:30} accuracy={m.accuracy:.2f} ({m.correct}/{m.total})  "
              f"minority-correct recall={m.minority_recall:.2f} ({m.minority_correct}/{m.minority_total})")

    print("\nper-case (ok/XX = matches ground truth; -- = abstained):")
    for case in SEED:
        a = cascade_resolve(case)
        b = joint_score_resolve(case)
        c = joint_anchored_resolve(case)
        flag = " [minority-correct]" if case.minority_correct else ""
        print(f"  {case.case_id:42} truth={case.ground_truth!r:>12}  "
              f"a={'ok' if a == case.ground_truth else 'XX'}({a})  "
              f"b={'ok' if b == case.ground_truth else 'XX'}({b})  "
              f"c={'ok' if c == case.ground_truth else ('--' if c is None else 'XX')}({c}){flag}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
