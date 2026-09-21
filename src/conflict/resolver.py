from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # avoid runtime circular import — judge module imports Claim
    from src.conflict.judge import LLMJudge
    from src.conflict.web_verify import WebVerificationAgent


class ResolutionStatus(StrEnum):
    """Conflict-resolution outcome per FR-6 + ADR-006."""

    L1_CLASH_INVALIDATED = "l1_clash_invalidated"
    TEMPORAL_SPLIT = "temporal_split"
    TRUST_WEIGHTED = "trust_weighted"
    JUDGE_RESOLVED = "judge_resolved"
    WEB_VERIFIED = "web_verified"       # V1.5c — ADR-016 v2
    ANOMALY = "anomaly"
    HITL_PENDING = "hitl_pending"
    NO_CONFLICT = "no_conflict"


@dataclass(frozen=True)
class Claim:
    """A factual / opinion claim about a subject's property."""

    claim_id: str
    subject_id: str           # e.g., "school:nyu"
    predicate: str            # e.g., "tuition_resident"
    object_value: Any
    source_tier: str          # L1..L5
    rank: str = "normal"      # preferred / normal / deprecated
    references: list[str] = field(default_factory=list)
    qualifiers: dict[str, Any] = field(default_factory=dict)
    t_valid_from: datetime | None = None
    t_valid_to: datetime | None = None
    confidence: float = 1.0
    credibility: float = 0.5  # source user-credibility (ADR-008)
    extractor_family: str | None = None  # ADR-024: vendor family that extracted this claim


@dataclass(frozen=True)
class ResolutionOutcome:
    status: ResolutionStatus
    winning_claim: Claim | None
    losing_claims: list[Claim]
    reason: str
    research_need_id: str | None = None  # set when FR-6.4 fires
    web_verification_run_id: str | None = None  # V1.5c — set when web-verify resolves
    citations: list[str] = field(default_factory=list)
    low_confidence: bool = False


class ConflictResolver:
    """Conflict resolver implementing the ADR-006 ordered cascade.

    Canonical step numbering (matches ADR-006 §Decision + system-overview §3 —
    these previously disagreed; canonicalized in V1.7 per ADR-026):
      1 L1-clash → 2 temporal disambiguation → 3 source-trust weighting
      (the 3-vendor LLM-as-judge tie-break fires *inside* step 3 on same-tier
      same-year ties when a `judge` is wired — ADR-024) → 4 signed-graph
      disagreement detection (V1.x, not built — GAP-049/ADR-026) → 5
      web-verification (when a `web_verifier` is wired — ADR-016, via
      `try_web_verify`) → 6 HITL escalation.

    Without a judge, same-tier ties go straight to HITL (step 6); without a
    web-verifier, step 5 is skipped. Legacy behavior preserved when neither is
    provided.
    """

    L1_STALE_MONTHS: int = 6   # FR-6.4 threshold

    def __init__(
        self,
        *,
        judge: LLMJudge | None = None,
        web_verifier: WebVerificationAgent | None = None,
    ) -> None:
        self._judge = judge
        self._web_verifier = web_verifier

    def try_web_verify(
        self, claim: Claim, context_summary: str = "",
    ) -> ResolutionOutcome | None:
        """V1.5c (ADR-016 v2) — if a web verifier is wired, attempt to
        resolve the claim via the 3-signal majority. Returns:
        - `WEB_VERIFIED` ResolutionOutcome on supports/refutes verdicts,
        - `None` to indicate the caller should fall back to step 6 (HITL).
        """

        if self._web_verifier is None:
            return None
        verdict = self._web_verifier.verify_claim(
            self._summarize_claim(claim),
            context_summary=context_summary,
        )
        if verdict.verdict in {"supports", "refutes"}:
            return ResolutionOutcome(
                status=ResolutionStatus.WEB_VERIFIED,
                winning_claim=claim if verdict.verdict == "supports" else None,
                losing_claims=[] if verdict.verdict == "supports" else [claim],
                reason=(
                    f"web-verified ({verdict.verdict}) per ADR-016 v2: "
                    f"{verdict.reason}"
                ),
                web_verification_run_id=verdict.run.run_id,
                citations=list(verdict.citations),
                low_confidence=verdict.low_confidence,
            )
        # Unknown / disagreement / cap_hit → fall through to HITL.
        return None

    @staticmethod
    def _summarize_claim(claim: Claim) -> str:
        """Render a Claim into a human-readable assertion for the verifier.

        If `object_value` is already a natural-language assertion (string ≥
        20 chars), prefer that — the verifier's lexical heuristics work
        better on prose than on `subject:id predicate = value` pseudo-syntax.
        """

        if isinstance(claim.object_value, str) and len(claim.object_value) > 20:
            return claim.object_value
        return (
            f"{claim.subject_id} {claim.predicate} = "
            f"{claim.object_value!r} (tier {claim.source_tier})"
        )

    def reconcile(  # noqa: PLR0911 — six-step protocol per FR-6 is intrinsically branchy
        self, new_claim: Claim, existing_claims: list[Claim],
    ) -> ResolutionOutcome:
        same_property = [
            c for c in existing_claims
            if c.subject_id == new_claim.subject_id
            and c.predicate == new_claim.predicate
        ]
        if not same_property:
            return ResolutionOutcome(
                status=ResolutionStatus.NO_CONFLICT,
                winning_claim=new_claim,
                losing_claims=[],
                reason="no prior claim on (subject, predicate)",
            )

        l1_claims = [c for c in same_property if c.source_tier == "L1"]
        non_l1 = [c for c in same_property if c.source_tier != "L1"]

        # Step 1: forum claim conflicts with L1.
        if l1_claims and new_claim.source_tier != "L1":
            return ResolutionOutcome(
                status=ResolutionStatus.L1_CLASH_INVALIDATED,
                winning_claim=l1_claims[0],
                losing_claims=[new_claim],
                reason="L1 source is immutable; non-L1 claim invalidated (FR-6.1)",
            )
        if new_claim.source_tier == "L1" and non_l1 and _values_disagree(
            new_claim, non_l1[0],
        ):
            return ResolutionOutcome(
                status=ResolutionStatus.L1_CLASH_INVALIDATED,
                winning_claim=new_claim,
                losing_claims=list(non_l1),
                reason="incoming L1 invalidates prior non-L1 claims (FR-6.1)",
            )

        # Step 2: same-property, same-tier — temporal disambiguation.
        if all(c.source_tier == new_claim.source_tier for c in same_property):
            other = same_property[0]
            if _temporal_distinct(new_claim, other):
                return ResolutionOutcome(
                    status=ResolutionStatus.TEMPORAL_SPLIT,
                    winning_claim=new_claim,
                    losing_claims=[],
                    reason="non-overlapping t_valid_* windows (FR-6.2)",
                )

        # Step 3: same-tier same-year — credibility-weighted.
        if all(c.source_tier == new_claim.source_tier for c in same_property):
            best_existing = max(same_property, key=lambda c: c.credibility)
            if new_claim.credibility > best_existing.credibility:
                return ResolutionOutcome(
                    status=ResolutionStatus.TRUST_WEIGHTED,
                    winning_claim=new_claim,
                    losing_claims=[best_existing],
                    reason="incoming claim's credibility outranks existing (FR-6.3)",
                )
            if new_claim.credibility < best_existing.credibility:
                return ResolutionOutcome(
                    status=ResolutionStatus.TRUST_WEIGHTED,
                    winning_claim=best_existing,
                    losing_claims=[new_claim],
                    reason="existing claim's credibility outranks incoming (FR-6.3)",
                )

            # Step 3 tie-break (ADR-006 §3 / ADR-024): tie at same tier + same
            # window + same credibility. If a 3-vendor judge is wired, ask it
            # before falling through to HITL (step 6).
            if self._judge is not None:
                vote = self._judge.adjudicate(new_claim, list(same_property))
                if vote.winner_claim_id is not None:
                    all_claims = [new_claim, *same_property]
                    winner = next(
                        (c for c in all_claims if c.claim_id == vote.winner_claim_id),
                        None,
                    )
                    if winner is not None:
                        losers = [c for c in all_claims if c is not winner]
                        return ResolutionOutcome(
                            status=ResolutionStatus.JUDGE_RESOLVED,
                            winning_claim=winner,
                            losing_claims=losers,
                            reason=(
                                f"3-vendor LLM-as-judge agreed {vote.agreement}/3 "
                                f"(ADR-006); {vote.transcript}"
                            ),
                        )
                return ResolutionOutcome(
                    status=ResolutionStatus.HITL_PENDING,
                    winning_claim=None,
                    losing_claims=[*list(same_property), new_claim],
                    reason=(
                        f"judge disagreement {vote.agreement}/3 — escalate to HITL "
                        f"(ADR-006); {vote.transcript}"
                    ),
                )

        # Step 6: irreducible — escalate to HITL (ADR-006 §6).
        return ResolutionOutcome(
            status=ResolutionStatus.HITL_PENDING,
            winning_claim=None,
            losing_claims=[*list(same_property), new_claim],
            reason="no deterministic rule applies; escalate to HITL (ADR-006 step 6)",
        )

    def queue_research_need(
        self, l1_value: Claim, non_l1_cluster: list[Claim], now: datetime,
    ) -> str | None:
        """FR-6.4: trigger when a non-L1 cluster contradicts L1 AND L1 is stale."""

        if not non_l1_cluster or l1_value.t_valid_to is None:
            return None
        months_stale = (now - l1_value.t_valid_to).days / 30
        if months_stale <= self.L1_STALE_MONTHS:
            return None
        return f"research_need:{l1_value.subject_id}:{l1_value.predicate}:{now.year}"


def _values_disagree(a: Claim, b: Claim) -> bool:
    return bool(a.object_value != b.object_value)


def _temporal_distinct(a: Claim, b: Claim) -> bool:
    """True iff a's t_valid_* window does not overlap b's window."""

    if a.t_valid_from is None or b.t_valid_from is None:
        return False
    a_end = a.t_valid_to or datetime.max.replace(tzinfo=a.t_valid_from.tzinfo)
    b_end = b.t_valid_to or datetime.max.replace(tzinfo=b.t_valid_from.tzinfo)
    return a_end < b.t_valid_from or b_end < a.t_valid_from
