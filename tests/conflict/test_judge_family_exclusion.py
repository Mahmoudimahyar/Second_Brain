"""WP3.4 / ADR-024 — LLM-judge family-exclusion + independent vote + builders.

Family-exclusion: the panel excludes the vendor family that produced a
candidate's extraction (self-preference bias). Independent vote: each judge is
queried in isolation (no debate / cross-verdict leakage).
"""

from __future__ import annotations

import pytest

from src.conflict.factory import build_three_vendor_judge
from src.conflict.judge import ThreeVendorJudge, _family_of
from src.conflict.resolver import Claim, ConflictResolver, ResolutionStatus
from src.gateway.api import MockProvider


def _voter(winner: str):
    def fixture(_prompt: str) -> str:
        return f'{{"winner_claim_id": "{winner}", "reasoning": "stub"}}'
    return fixture


def _claim(cid: str, *, tier: str = "L5", value: object = "x",
           extractor_family: str | None = None, cred: float = 0.5) -> Claim:
    return Claim(claim_id=cid, subject_id="school:s", predicate="p",
                 object_value=value, source_tier=tier, credibility=cred,
                 extractor_family=extractor_family)


def test_family_of_normalizes() -> None:
    assert _family_of("gemini") == "google"
    assert _family_of("Anthropic") == "anthropic"
    assert _family_of("grok") == "xai"


def test_panel_excludes_extractor_family_when_alternate_available() -> None:
    judge = ThreeVendorJudge(clients=[
        MockProvider(vendor="anthropic", fixture=_voter("a")),
        MockProvider(vendor="openai", fixture=_voter("a")),
        MockProvider(vendor="gemini", fixture=_voter("a")),
        MockProvider(vendor="grok", fixture=_voter("a")),  # alternate family
    ])
    vote = judge.adjudicate(_claim("a", extractor_family="anthropic"), [_claim("b")])
    assert "anthropic" not in vote.per_vendor  # excluded
    assert set(vote.per_vendor) == {"openai", "gemini", "grok"}
    assert "excluded_families=['anthropic']" in vote.transcript


def test_panel_best_effort_keeps_three_when_no_alternate() -> None:
    judge = ThreeVendorJudge(clients=[
        MockProvider(vendor="anthropic", fixture=_voter("a")),
        MockProvider(vendor="openai", fixture=_voter("a")),
        MockProvider(vendor="gemini", fixture=_voter("a")),
    ])
    vote = judge.adjudicate(_claim("a", extractor_family="anthropic"), [_claim("b")])
    assert len(vote.per_vendor) == 3  # cannot drop below 3 families → keep all 3


def test_independent_vote_same_prompt_no_leakage() -> None:
    seen: list[str] = []

    def spy(winner: str):
        def fixture(prompt: str) -> str:
            seen.append(prompt)
            return f'{{"winner_claim_id": "{winner}"}}'
        return fixture

    judge = ThreeVendorJudge(clients=[
        MockProvider(vendor="anthropic", fixture=spy("a")),
        MockProvider(vendor="openai", fixture=spy("a")),
        MockProvider(vendor="gemini", fixture=spy("b")),
    ])
    judge.adjudicate(_claim("a"), [_claim("b")])
    assert len(seen) == 3              # each vendor queried once
    assert len(set(seen)) == 1         # identical prompt — no debate / verdict leakage


def test_resolver_resolves_same_tier_tie_via_panel() -> None:
    """The real wiring: a same-tier same-year tie reaches the 3-vendor panel."""
    judge = ThreeVendorJudge(clients=[
        MockProvider(vendor="anthropic", fixture=_voter("a")),
        MockProvider(vendor="openai", fixture=_voter("a")),
        MockProvider(vendor="gemini", fixture=_voter("b")),
    ])
    resolver = ConflictResolver(judge=judge)
    a = _claim("a", value="x", cred=0.5)
    b = _claim("b", value="y", cred=0.5)  # same tier + cred + window → tie → judge
    outcome = resolver.reconcile(a, [b])
    assert outcome.status == ResolutionStatus.JUDGE_RESOLVED
    assert outcome.winning_claim is not None
    assert outcome.winning_claim.claim_id == "a"  # 2/3 voted "a"


def test_build_judge_none_without_three_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    for k in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GOOGLE_API_KEY", "GEMINI_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    assert build_three_vendor_judge() is None


def test_build_judge_constructs_with_three_vendor_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    monkeypatch.setenv("GOOGLE_API_KEY", "x")
    judge = build_three_vendor_judge()
    assert judge is not None
    assert len({_family_of(c.vendor) for c in judge.clients}) >= 3
