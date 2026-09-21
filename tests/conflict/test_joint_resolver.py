"""Invariants for the ADR-026 L1-anchored joint-confidence resolver."""

from __future__ import annotations

from datetime import UTC, datetime

from src.conflict.joint_resolver import L1AnchoredJointResolver
from src.conflict.resolver import Claim, ResolutionStatus

_NOW = datetime(2026, 5, 29, tzinfo=UTC)


def _claim(
    value: str, tier: str, year: int, *, cred: float = 0.5, cid: str = "c",
    predicate: str = "tuition_resident", subject: str = "school:x",
) -> Claim:
    return Claim(
        claim_id=cid, subject_id=subject, predicate=predicate, object_value=value,
        source_tier=tier, t_valid_from=datetime(year, 1, 1, tzinfo=UTC),
        credibility=cred,
    )


def _corroborated(value: str, tier: str, year: int, n: int, **kw: object) -> list[Claim]:
    return [_claim(value, tier, year, cid=f"{value}-{i}", **kw) for i in range(n)]  # type: ignore[arg-type]


def _resolve(claims: list[Claim]) -> object:
    return L1AnchoredJointResolver().resolve_group(claims, now=_NOW)


# -- Rule 1: current-L1 immutability --------------------------------------------


def test_current_l1_beats_corroborated_wrong_majority() -> None:
    """C3 — a current L1 wins over a fresh, corroborated, wrong L5 majority."""
    claims = [*_corroborated("70000", "L5", 2025, 3, cred=0.5),
              _claim("0", "L1", 2024, cred=1.0, cid="l1")]
    out = _resolve(claims)
    assert out.winner_value == "0"
    assert out.status is ResolutionStatus.L1_CLASH_INVALIDATED


def test_current_l1_immutable_against_scaling_corroboration() -> None:
    """The immutability guarantee: no amount of corroboration overrides a
    current L1 (the mass race is bypassed by the hard guardrail)."""
    claims = [*_corroborated("70000", "L5", 2025, 50, cred=0.9),
              _claim("0", "L1", 2024, cred=1.0, cid="l1")]
    out = _resolve(claims)
    assert out.winner_value == "0"
    assert out.status is ResolutionStatus.L1_CLASH_INVALIDATED


def test_current_l1_disagreement_abstains() -> None:
    """Two current L1 claims with different values = anomaly -> HITL, no guess."""
    claims = [_claim("0", "L1", 2024, cred=1.0, cid="a"),
              _claim("100", "L1", 2024, cred=1.0, cid="b")]
    out = _resolve(claims)
    assert out.winner_value is None
    assert out.status is ResolutionStatus.HITL_PENDING


# -- Rule 2: stale-L1 correction + joint mass -----------------------------------


def test_stale_l1_corrected_by_fresh_corroborated() -> None:
    """C2 — a 5-year-stale L1 yields to a fresh, corroborated L5 correction."""
    claims = [_claim("no", "L1", 2021, cred=1.0, cid="l1", predicate="casper_required"),
              *_corroborated("yes", "L5", 2025, 3, cred=0.6, predicate="casper_required")]
    out = _resolve(claims)
    assert out.winner_value == "yes"
    assert out.status is ResolutionStatus.TRUST_WEIGHTED
    assert out.low_confidence is True            # flagged: a stale L1 was overridden


def test_recency_wins_without_l1() -> None:
    """C5 — fresh single L5 beats stale corroborated L5 (HALO recency)."""
    claims = [*_corroborated("78000", "L5", 2019, 2, cred=0.5),
              _claim("91000", "L5", 2025, cred=0.5, cid="fresh")]
    out = _resolve(claims)
    assert out.winner_value == "91000"
    assert out.status is ResolutionStatus.TRUST_WEIGHTED
    assert out.low_confidence is False           # no L1 involved


def test_corroboration_breaks_tie_without_l1() -> None:
    """C4 — same tier/year/credibility: corroboration count breaks the tie."""
    claims = [*_corroborated("MMI", "L5", 2025, 3, cred=0.5, predicate="interview_format"),
              _claim("traditional", "L5", 2025, cred=0.5, cid="t",
                     predicate="interview_format")]
    out = _resolve(claims)
    assert out.winner_value == "MMI"


# -- Rule 3: abstain band + no-conflict -----------------------------------------


def test_genuine_tie_abstains() -> None:
    """C8 — equal mass, no recency/corroboration signal -> abstain to HITL."""
    claims = [_claim("MMI", "L5", 2025, cid="a", predicate="interview_format"),
              _claim("panel", "L5", 2025, cid="b", predicate="interview_format")]
    out = _resolve(claims)
    assert out.winner_value is None
    assert out.status is ResolutionStatus.HITL_PENDING


def test_single_value_is_no_conflict() -> None:
    claims = _corroborated("MMI", "L5", 2025, 2, predicate="interview_format")
    out = _resolve(claims)
    assert out.winner_value == "MMI"
    assert out.status is ResolutionStatus.NO_CONFLICT


def test_empty_group_is_safe() -> None:
    out = L1AnchoredJointResolver().resolve_group([], now=_NOW)
    assert out.status is ResolutionStatus.NO_CONFLICT
    assert out.winner_value is None
