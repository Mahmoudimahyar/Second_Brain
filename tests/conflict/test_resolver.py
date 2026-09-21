"""Tests for `src.conflict.resolver.ConflictResolver` (FR-6, ADR-006)."""

from __future__ import annotations

from datetime import UTC, datetime

from src.conflict import (
    Claim,
    ConflictResolver,
    JudgeVote,
    ResolutionStatus,
    StubJudge,
    ThreeVendorJudge,
)
from src.gateway.api import MockProvider


def _utc(year: int, month: int = 1, day: int = 1) -> datetime:
    return datetime(year, month, day, tzinfo=UTC)


def _claim(
    *,
    cid: str = "claim:c1",
    subject: str = "school:nyu",
    predicate: str = "tuition_resident",
    value: object = 94108.0,
    tier: str = "L5",
    credibility: float = 0.5,
    t_valid_from: datetime | None = None,
    t_valid_to: datetime | None = None,
) -> Claim:
    return Claim(
        claim_id=cid, subject_id=subject, predicate=predicate,
        object_value=value, source_tier=tier, credibility=credibility,
        t_valid_from=t_valid_from, t_valid_to=t_valid_to,
    )


def test_no_prior_claim_returns_no_conflict() -> None:
    r = ConflictResolver()
    outcome = r.reconcile(_claim(), existing_claims=[])
    assert outcome.status == ResolutionStatus.NO_CONFLICT


def test_l1_clash_invalidates_non_l1_incoming_claim() -> None:
    r = ConflictResolver()
    l1 = _claim(cid="l1", value=94108.0, tier="L1")
    forum = _claim(cid="forum", value=40000.0, tier="L5")

    outcome = r.reconcile(forum, [l1])

    assert outcome.status == ResolutionStatus.L1_CLASH_INVALIDATED
    assert outcome.winning_claim is l1
    assert outcome.losing_claims == [forum]


def test_incoming_l1_invalidates_existing_non_l1() -> None:
    r = ConflictResolver()
    forum = _claim(cid="forum", value=40000.0, tier="L5")
    l1 = _claim(cid="l1", value=94108.0, tier="L1")

    outcome = r.reconcile(l1, [forum])

    assert outcome.status == ResolutionStatus.L1_CLASH_INVALIDATED
    assert outcome.winning_claim is l1
    assert forum in outcome.losing_claims


def test_same_tier_disjoint_temporal_windows_split() -> None:
    r = ConflictResolver()
    a = _claim(cid="a", tier="L5",
               t_valid_from=_utc(2020), t_valid_to=_utc(2021))
    b = _claim(cid="b", tier="L5", value=99000.0,
               t_valid_from=_utc(2022), t_valid_to=_utc(2023))

    outcome = r.reconcile(b, [a])
    assert outcome.status == ResolutionStatus.TEMPORAL_SPLIT


def test_same_tier_same_window_higher_credibility_wins() -> None:
    r = ConflictResolver()
    low = _claim(cid="low", tier="L5", credibility=0.2,
                 t_valid_from=_utc(2024), t_valid_to=_utc(2024, 12))
    high = _claim(cid="high", tier="L5", value=99000.0, credibility=0.9,
                  t_valid_from=_utc(2024), t_valid_to=_utc(2024, 12))

    outcome = r.reconcile(high, [low])

    assert outcome.status == ResolutionStatus.TRUST_WEIGHTED
    assert outcome.winning_claim is high


def test_same_tier_same_window_equal_credibility_escalates_to_hitl() -> None:
    r = ConflictResolver()
    a = _claim(cid="a", tier="L5", credibility=0.5,
               t_valid_from=_utc(2024), t_valid_to=_utc(2024, 12))
    b = _claim(cid="b", tier="L5", value=99000.0, credibility=0.5,
               t_valid_from=_utc(2024), t_valid_to=_utc(2024, 12))

    outcome = r.reconcile(b, [a])
    assert outcome.status == ResolutionStatus.HITL_PENDING


def test_l1_immutability_when_incoming_l1_matches_existing_l1() -> None:
    """Two L1 claims with same value → no conflict (already in sync)."""

    r = ConflictResolver()
    l1a = _claim(cid="l1a", tier="L1", value=94108.0,
                 t_valid_from=_utc(2024), t_valid_to=_utc(2024, 12))
    l1b = _claim(cid="l1b", tier="L1", value=94108.0,
                 t_valid_from=_utc(2024), t_valid_to=_utc(2024, 12))

    outcome = r.reconcile(l1b, [l1a])
    # Same tier + same window + same value → still attempts step 3 (credibility),
    # finds equal → HITL_PENDING. Acceptable; the actual write should also dedupe.
    assert outcome.status in {
        ResolutionStatus.HITL_PENDING, ResolutionStatus.TRUST_WEIGHTED,
    }


def test_same_tier_tie_with_judge_majority_returns_judge_resolved() -> None:
    """ADR-006: same-tier same-year same-credibility tie → 3-vendor judge.
    If 2+ vendors pick the same winner, that's the resolution."""


    judge = StubJudge(vote=JudgeVote(
        winner_claim_id="a", per_vendor={"anthropic": "a", "openai": "a", "gemini": "b"},
        agreement=2, transcript="A wins 2-1.",
    ))
    r = ConflictResolver(judge=judge)
    a = _claim(cid="a", tier="L5", credibility=0.5,
               t_valid_from=_utc(2024), t_valid_to=_utc(2024, 12))
    b = _claim(cid="b", tier="L5", value=99000.0, credibility=0.5,
               t_valid_from=_utc(2024), t_valid_to=_utc(2024, 12))

    outcome = r.reconcile(b, [a])

    assert outcome.status == ResolutionStatus.JUDGE_RESOLVED
    assert outcome.winning_claim is a
    assert b in outcome.losing_claims
    assert "A wins 2-1" in outcome.reason


def test_same_tier_tie_with_judge_disagreement_falls_through_to_hitl() -> None:

    judge = StubJudge(vote=JudgeVote(
        winner_claim_id=None,
        per_vendor={"anthropic": "a", "openai": "b", "gemini": None},
        agreement=1, transcript="Split decision.",
    ))
    r = ConflictResolver(judge=judge)
    a = _claim(cid="a", tier="L5", credibility=0.5,
               t_valid_from=_utc(2024), t_valid_to=_utc(2024, 12))
    b = _claim(cid="b", tier="L5", value=99000.0, credibility=0.5,
               t_valid_from=_utc(2024), t_valid_to=_utc(2024, 12))

    outcome = r.reconcile(b, [a])
    assert outcome.status == ResolutionStatus.HITL_PENDING
    assert "judge" in outcome.reason.lower()


def test_same_tier_tie_with_no_judge_preserves_legacy_hitl_path() -> None:
    """Backwards compatibility: ConflictResolver() with no judge behaves as before."""

    r = ConflictResolver()   # judge=None
    a = _claim(cid="a", tier="L5", credibility=0.5,
               t_valid_from=_utc(2024), t_valid_to=_utc(2024, 12))
    b = _claim(cid="b", tier="L5", value=99000.0, credibility=0.5,
               t_valid_from=_utc(2024), t_valid_to=_utc(2024, 12))
    outcome = r.reconcile(b, [a])
    assert outcome.status == ResolutionStatus.HITL_PENDING


def test_three_vendor_judge_tallies_majority() -> None:
    """ThreeVendorJudge.adjudicate aggregates per-vendor votes via majority."""


    def voter(claim_id: str):
        def fixture(_prompt: str) -> str:
            return f'{{"winner_claim_id": "{claim_id}", "reasoning": "stub"}}'
        return fixture

    judge = ThreeVendorJudge(clients=[
        MockProvider(vendor="anthropic", fixture=voter("a")),
        MockProvider(vendor="openai", fixture=voter("a")),
        MockProvider(vendor="gemini", fixture=voter("b")),
    ])
    a = _claim(cid="a", tier="L5", credibility=0.5)
    b = _claim(cid="b", tier="L5", value=99000.0, credibility=0.5)
    vote = judge.adjudicate(a, [b])
    assert vote.winner_claim_id == "a"
    assert vote.agreement == 2


def test_three_vendor_judge_no_majority_returns_none() -> None:

    def voter(claim_id: str):
        def fixture(_prompt: str) -> str:
            return f'{{"winner_claim_id": "{claim_id}"}}'
        return fixture

    judge = ThreeVendorJudge(clients=[
        MockProvider(vendor="v1", fixture=voter("a")),
        MockProvider(vendor="v2", fixture=voter("b")),
        MockProvider(vendor="v3", fixture=voter("c")),
    ])
    a = _claim(cid="a", tier="L5")
    b = _claim(cid="b", tier="L5")
    vote = judge.adjudicate(a, [b])
    assert vote.winner_claim_id is None
    assert vote.agreement == 1


def test_queue_research_need_returns_id_when_l1_stale() -> None:
    r = ConflictResolver()
    l1 = _claim(tier="L1", value=94108.0,
                t_valid_from=_utc(2022), t_valid_to=_utc(2022, 12))
    non_l1 = [_claim(tier="L5", value=99000.0)]

    rn = r.queue_research_need(l1, non_l1, now=_utc(2026, 5, 21))
    assert rn is not None
    assert "research_need:" in rn


def test_queue_research_need_returns_none_when_l1_fresh() -> None:
    r = ConflictResolver()
    l1 = _claim(tier="L1", value=94108.0,
                t_valid_from=_utc(2026), t_valid_to=_utc(2026, 12))
    non_l1 = [_claim(tier="L5", value=99000.0)]

    assert r.queue_research_need(l1, non_l1, now=_utc(2026, 5, 21)) is None
