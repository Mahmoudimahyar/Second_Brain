"""Tests for V1.5c Phase 3 — `ConflictResolver` web-verify hook (ADR-016 v2)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from src.conflict import Claim, ConflictResolver, ResolutionStatus
from src.conflict.web_verify import (
    VerdictResult,
    WebVerificationRun,
)


@dataclass
class _StubVerifier:
    verdict: str = "supports"
    confidence: float = 0.85
    citations: tuple[str, ...] = ("https://example.org/source",)
    low_confidence: bool = False
    reason: str = "stub verifier verdict"

    def verify_claim(
        self, claim: str, *, context_summary: str = "",
    ) -> VerdictResult:
        run = WebVerificationRun(
            run_id=f"webverify:stub:{hash(claim) & 0xFFFFFF:06x}",
            claim=claim,
            context_summary=context_summary,
            question_a="",
            question_b="",
            signal_a={},
            signal_b={},
            signal_c={},
            combine_outcome=self.verdict,
            combine_confidence=self.confidence,
            low_confidence=self.low_confidence,
            citations=list(self.citations),
            cost_usd=0.0,
            latency_ms=0.0,
            ts=datetime.now(UTC),
        )
        return VerdictResult(
            verdict=self.verdict,  # type: ignore[arg-type]
            confidence=self.confidence,
            citations=list(self.citations),
            low_confidence=self.low_confidence,
            reason=self.reason,
            run=run,
        )


def _claim(value: object = 87000.0) -> Claim:
    return Claim(
        claim_id="claim:test", subject_id="school:nyu",
        predicate="tuition_resident", object_value=value,
        source_tier="L5", credibility=0.5,
    )


def test_try_web_verify_returns_none_without_verifier() -> None:
    resolver = ConflictResolver()
    outcome = resolver.try_web_verify(_claim())
    assert outcome is None


def test_try_web_verify_supports_returns_web_verified() -> None:
    resolver = ConflictResolver(web_verifier=_StubVerifier(verdict="supports"))
    outcome = resolver.try_web_verify(_claim())
    assert outcome is not None
    assert outcome.status == ResolutionStatus.WEB_VERIFIED
    assert outcome.winning_claim is not None
    assert outcome.citations == ["https://example.org/source"]
    assert outcome.web_verification_run_id is not None


def test_try_web_verify_refutes_returns_web_verified_with_loser() -> None:
    resolver = ConflictResolver(web_verifier=_StubVerifier(verdict="refutes"))
    outcome = resolver.try_web_verify(_claim())
    assert outcome is not None
    assert outcome.status == ResolutionStatus.WEB_VERIFIED
    assert outcome.winning_claim is None
    assert outcome.losing_claims and outcome.losing_claims[0].claim_id == "claim:test"


def test_try_web_verify_disagreement_returns_none_for_hitl_fallback() -> None:
    resolver = ConflictResolver(
        web_verifier=_StubVerifier(verdict="disagreement"),
    )
    outcome = resolver.try_web_verify(_claim())
    assert outcome is None  # caller routes to HITL


def test_try_web_verify_unknown_returns_none_for_research_need() -> None:
    resolver = ConflictResolver(web_verifier=_StubVerifier(verdict="unknown"))
    outcome = resolver.try_web_verify(_claim())
    assert outcome is None


def test_try_web_verify_cap_hit_returns_none() -> None:
    resolver = ConflictResolver(web_verifier=_StubVerifier(verdict="cap_hit"))
    outcome = resolver.try_web_verify(_claim())
    assert outcome is None


def test_low_confidence_flag_propagates() -> None:
    resolver = ConflictResolver(
        web_verifier=_StubVerifier(verdict="supports", low_confidence=True),
    )
    outcome = resolver.try_web_verify(_claim())
    assert outcome is not None
    assert outcome.low_confidence is True


def test_v1_reconcile_path_unchanged() -> None:
    """V1 reconcile() callsites must not regress when no verifier is wired."""

    resolver = ConflictResolver()
    l1 = Claim(
        claim_id="claim:l1", subject_id="school:nyu",
        predicate="tuition_resident", object_value=87000.0,
        source_tier="L1", rank="preferred",
    )
    forum = Claim(
        claim_id="claim:forum", subject_id="school:nyu",
        predicate="tuition_resident", object_value=80000.0,
        source_tier="L5", credibility=0.3,
    )
    outcome = resolver.reconcile(forum, [l1])
    assert outcome.status == ResolutionStatus.L1_CLASH_INVALIDATED
